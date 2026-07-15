"""Persistence stores for application memory, with SQLite as the default."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from .config import PersistenceSettings, PERSISTENCE_SETTINGS
from .database import connection
from .dynamodb_client import get_dynamodb_resource
from .models import (
    ConflictCreate,
    ConflictRecord,
    ConflictUpdate,
    FeedbackCreate,
    FeedbackRecord,
    RecurringQuestionRecord,
)


def normalize_recurring_question(question_text: str) -> str:
    """Normalize simple question variations without semantic inference."""
    return re.sub(r"[^a-z0-9]+", " ", question_text.lower()).strip()


def recurring_question_id(normalized_text: str) -> str:
    """Build a stable DynamoDB/SQLite key from normalized question text."""
    digest = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    return f"rq_{digest}"


class ConflictStore(Protocol):
    """Persistence operations needed by the conflict-log API."""

    def list_conflicts(
        self, status: str | None = None, topic: str | None = None
    ) -> list[ConflictRecord]: ...

    def create_conflict(
        self, payload: ConflictCreate, origin: str = "manual"
    ) -> ConflictRecord: ...

    def update_conflict(
        self, conflict_id: str, payload: ConflictUpdate
    ) -> ConflictRecord | None: ...

    def get_conflict(self, conflict_id: str) -> ConflictRecord | None: ...


class FeedbackStore(Protocol):
    """Persistence operations needed by the answer-feedback API."""

    def create_feedback(self, payload: FeedbackCreate) -> FeedbackRecord: ...

    def list_feedback(
        self,
        rating: str | None = None,
        issue_type: str | None = None,
        limit: int | None = None,
    ) -> list[FeedbackRecord]: ...


class RecurringQuestionStore(Protocol):
    """Persistence operations for normalized recurring policy questions."""

    def record_question(
        self,
        question_text: str,
        answer_id: str | None = None,
        citations: list[str] | None = None,
        topic: str = "general",
    ) -> RecurringQuestionRecord: ...

    def list_questions(
        self, topic: str | None = None, limit: int = 8
    ) -> list[RecurringQuestionRecord]: ...


class SQLiteConflictStore:
    """Adapter for the existing SQLite conflict table and its idempotent writes."""

    @staticmethod
    def _record(row: object) -> ConflictRecord:
        values = dict(row)  # type: ignore[arg-type]
        return ConflictRecord(
            id=int(values["id"]),
            source_a=str(values["source_a"]),
            source_b=str(values["source_b"]),
            topic=str(values["topic"]),
            description=str(values["description"]),
            status=str(values["status"]),
            resolution_note=str(values["resolution_note"]),
            created_at=datetime.fromisoformat(str(values["created_at"])),
            updated_at=datetime.fromisoformat(str(values["updated_at"])),
        )

    @staticmethod
    def _sqlite_id(conflict_id: str) -> int | None:
        try:
            return int(conflict_id)
        except ValueError:
            return None

    def list_conflicts(
        self, status: str | None = None, topic: str | None = None
    ) -> list[ConflictRecord]:
        clauses: list[str] = []
        values: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            values.append(status)
        if topic is not None:
            clauses.append("topic = ?")
            values.append(topic)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with connection() as database:
            rows = database.execute(
                f"SELECT * FROM conflicts{where} ORDER BY updated_at DESC, id DESC", values
            ).fetchall()
        return [self._record(row) for row in rows]

    def create_conflict(
        self, payload: ConflictCreate, origin: str = "manual"
    ) -> ConflictRecord:
        del origin  # SQLite schema intentionally remains unchanged for this migration.
        with connection() as database:
            database.execute(
                """
                INSERT OR IGNORE INTO conflicts(source_a, source_b, topic, description, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload.source_a, payload.source_b, payload.topic, payload.description, payload.status),
            )
            row = database.execute(
                """SELECT * FROM conflicts
                WHERE source_a = ? AND source_b = ? AND topic = ? AND description = ?""",
                (payload.source_a, payload.source_b, payload.topic, payload.description),
            ).fetchone()
        if row is None:
            raise RuntimeError("Conflict insert did not return a record")
        return self._record(row)

    def get_conflict(self, conflict_id: str) -> ConflictRecord | None:
        sqlite_id = self._sqlite_id(conflict_id)
        if sqlite_id is None:
            return None
        with connection() as database:
            row = database.execute("SELECT * FROM conflicts WHERE id = ?", (sqlite_id,)).fetchone()
        return None if row is None else self._record(row)

    def update_conflict(
        self, conflict_id: str, payload: ConflictUpdate
    ) -> ConflictRecord | None:
        sqlite_id = self._sqlite_id(conflict_id)
        if sqlite_id is None:
            return None
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        values: list[str | int] = []
        if payload.status is not None:
            updates.insert(0, "status = ?")
            values.append(payload.status)
        if payload.resolution_note is not None:
            updates.insert(0, "resolution_note = ?")
            values.insert(0, payload.resolution_note.strip())
        values.append(sqlite_id)
        with connection() as database:
            database.execute(
                f"UPDATE conflicts SET {', '.join(updates)} WHERE id = ?", values
            )
            row = database.execute("SELECT * FROM conflicts WHERE id = ?", (sqlite_id,)).fetchone()
        return None if row is None else self._record(row)


class DynamoDBConflictStore:
    """Conflict persistence for a DynamoDB table keyed by ``conflict_id``."""

    def __init__(self, settings: PersistenceSettings, resource: Any | None = None) -> None:
        self._settings = settings
        self._resource = resource

    @property
    def _table(self) -> Any:
        resource = self._resource or get_dynamodb_resource(self._settings)
        return resource.Table(self._settings.dynamodb_conflicts_table)

    @staticmethod
    def _record(item: dict[str, Any]) -> ConflictRecord:
        return ConflictRecord(
            id=item.get("id", item["conflict_id"]),
            source_a=item["source_a"],
            source_b=item["source_b"],
            topic=item["topic"],
            description=item["description"],
            status=item.get("status", "Open"),
            resolution_note=item.get("resolution_note", ""),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )

    @staticmethod
    def _conflict_id(payload: ConflictCreate) -> str:
        """Create a stable UUID so repeated detector findings remain idempotent."""
        identity = "\x1f".join(
            (payload.source_a, payload.source_b, payload.topic, payload.description)
        )
        return str(uuid5(NAMESPACE_URL, identity))

    def list_conflicts(
        self, status: str | None = None, topic: str | None = None
    ) -> list[ConflictRecord]:
        scan_kwargs: dict[str, Any] = {}
        filters: list[str] = []
        names: dict[str, str] = {}
        values: dict[str, str] = {}
        if status is not None:
            filters.append("#status = :status")
            names["#status"] = "status"
            values[":status"] = status
        if topic is not None:
            filters.append("#topic = :topic")
            names["#topic"] = "topic"
            values[":topic"] = topic
        if filters:
            scan_kwargs["FilterExpression"] = " AND ".join(filters)
            scan_kwargs["ExpressionAttributeNames"] = names
            scan_kwargs["ExpressionAttributeValues"] = values

        items: list[dict[str, Any]] = []
        while True:
            response = self._table.scan(**scan_kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if last_key is None:
                break
            scan_kwargs["ExclusiveStartKey"] = last_key
        records = [self._record(item) for item in items]
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    def create_conflict(
        self, payload: ConflictCreate, origin: str = "manual"
    ) -> ConflictRecord:
        conflict_id = self._conflict_id(payload)
        existing = self.get_conflict(conflict_id)
        if existing is not None:
            return existing
        now = datetime.now(timezone.utc).isoformat()
        item = {
            "conflict_id": conflict_id,
            "id": conflict_id,
            "source_a": payload.source_a,
            "source_b": payload.source_b,
            "topic": payload.topic,
            "description": payload.description,
            "status": payload.status,
            "resolution_note": "",
            "origin": origin,
            "created_at": now,
            "updated_at": now,
        }
        self._table.put_item(Item=item)
        return self._record(item)

    def get_conflict(self, conflict_id: str) -> ConflictRecord | None:
        response = self._table.get_item(Key={"conflict_id": conflict_id})
        item = response.get("Item")
        return None if item is None else self._record(item)

    def update_conflict(
        self, conflict_id: str, payload: ConflictUpdate
    ) -> ConflictRecord | None:
        if self.get_conflict(conflict_id) is None:
            return None
        updates = ["updated_at = :updated_at"]
        values: dict[str, str] = {
            ":updated_at": datetime.now(timezone.utc).isoformat(),
        }
        names: dict[str, str] = {}
        if payload.status is not None:
            updates.insert(0, "#status = :status")
            names["#status"] = "status"
            values[":status"] = payload.status
        if payload.resolution_note is not None:
            updates.insert(0, "resolution_note = :resolution_note")
            values[":resolution_note"] = payload.resolution_note.strip()
        update_kwargs: dict[str, Any] = {
            "Key": {"conflict_id": conflict_id},
            "UpdateExpression": f"SET {', '.join(updates)}",
            "ExpressionAttributeValues": values,
            "ReturnValues": "ALL_NEW",
        }
        if names:
            update_kwargs["ExpressionAttributeNames"] = names
        response = self._table.update_item(
            **update_kwargs,
        )
        attributes = response.get("Attributes")
        return None if attributes is None else self._record(attributes)


class SQLiteFeedbackStore:
    """Feedback persistence in the existing local SQLite application database."""

    @staticmethod
    def _record(row: object) -> FeedbackRecord:
        values = dict(row)  # type: ignore[arg-type]
        try:
            citations_used = json.loads(str(values["citations_used"]))
        except json.JSONDecodeError:
            citations_used = []
        return FeedbackRecord(
            feedback_id=str(values["feedback_id"]),
            answer_id=str(values["answer_id"]),
            question=str(values["question"]),
            rating=str(values["rating"]),
            comment=str(values["comment"]) or None,
            issue_type=str(values["issue_type"]) or None,
            role=str(values["role"]) or None,
            citations_used=citations_used if isinstance(citations_used, list) else [],
            provider=str(values["provider"]) or None,
            created_at=datetime.fromisoformat(str(values["created_at"])),
        )

    def create_feedback(self, payload: FeedbackCreate) -> FeedbackRecord:
        record = FeedbackRecord(
            feedback_id=str(uuid4()),
            **payload.model_dump(),
            created_at=datetime.now(timezone.utc),
        )
        with connection() as database:
            database.execute(
                """INSERT INTO feedback(
                    feedback_id, answer_id, question, rating, comment, issue_type,
                    role, citations_used, provider, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.feedback_id,
                    record.answer_id,
                    record.question,
                    record.rating,
                    record.comment or "",
                    record.issue_type or "",
                    record.role or "",
                    json.dumps(record.citations_used),
                    record.provider or "",
                    record.created_at.isoformat(),
                ),
            )
        return record

    def list_feedback(
        self,
        rating: str | None = None,
        issue_type: str | None = None,
        limit: int | None = None,
    ) -> list[FeedbackRecord]:
        clauses: list[str] = []
        values: list[str | int] = []
        if rating is not None:
            clauses.append("rating = ?")
            values.append(rating)
        if issue_type is not None:
            clauses.append("issue_type = ?")
            values.append(issue_type)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM feedback{where} ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            values.append(limit)
        with connection() as database:
            rows = database.execute(query, values).fetchall()
        return [self._record(row) for row in rows]


class DynamoDBFeedbackStore:
    """Feedback persistence for a DynamoDB table keyed by ``feedback_id``."""

    def __init__(self, settings: PersistenceSettings, resource: Any | None = None) -> None:
        self._settings = settings
        self._resource = resource

    @property
    def _table(self) -> Any:
        resource = self._resource or get_dynamodb_resource(self._settings)
        return resource.Table(self._settings.dynamodb_feedback_table)

    @staticmethod
    def _record(item: dict[str, Any]) -> FeedbackRecord:
        return FeedbackRecord(
            feedback_id=item["feedback_id"],
            answer_id=item["answer_id"],
            question=item["question"],
            rating=item["rating"],
            comment=item.get("comment") or None,
            issue_type=item.get("issue_type") or None,
            role=item.get("role") or None,
            citations_used=item.get("citations_used", []),
            provider=item.get("provider") or None,
            created_at=item["created_at"],
        )

    def create_feedback(self, payload: FeedbackCreate) -> FeedbackRecord:
        record = FeedbackRecord(
            feedback_id=str(uuid4()),
            **payload.model_dump(),
            created_at=datetime.now(timezone.utc),
        )
        self._table.put_item(
            Item={
                **record.model_dump(mode="json"),
                "comment": record.comment or "",
                "issue_type": record.issue_type or "",
                "role": record.role or "",
                "provider": record.provider or "",
            }
        )
        return record

    def list_feedback(
        self,
        rating: str | None = None,
        issue_type: str | None = None,
        limit: int | None = None,
    ) -> list[FeedbackRecord]:
        scan_kwargs: dict[str, Any] = {}
        filters: list[str] = []
        names: dict[str, str] = {}
        values: dict[str, str] = {}
        if rating is not None:
            filters.append("#rating = :rating")
            names["#rating"] = "rating"
            values[":rating"] = rating
        if issue_type is not None:
            filters.append("issue_type = :issue_type")
            values[":issue_type"] = issue_type
        if filters:
            scan_kwargs["FilterExpression"] = " AND ".join(filters)
            scan_kwargs["ExpressionAttributeValues"] = values
            if names:
                scan_kwargs["ExpressionAttributeNames"] = names

        items: list[dict[str, Any]] = []
        while True:
            response = self._table.scan(**scan_kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if last_key is None:
                break
            scan_kwargs["ExclusiveStartKey"] = last_key
        records = sorted(
            (self._record(item) for item in items),
            key=lambda record: record.created_at,
            reverse=True,
        )
        return records if limit is None else records[:limit]


class SQLiteRecurringQuestionStore:
    """Recurring-question aggregation in the local SQLite application database."""

    @staticmethod
    def _record(row: object) -> RecurringQuestionRecord:
        values = dict(row)  # type: ignore[arg-type]
        try:
            citations = json.loads(str(values["sample_citations"]))
        except json.JSONDecodeError:
            citations = []
        return RecurringQuestionRecord(
            question_id=str(values["question_id"]),
            question_text=str(values["question_text"]),
            normalized_text=str(values["normalized_text"]),
            topic=str(values["topic"]),
            ask_count=int(values["ask_count"]),
            first_asked_at=datetime.fromisoformat(str(values["first_asked_at"])),
            last_asked_at=datetime.fromisoformat(str(values["last_asked_at"])),
            sample_answer_id=str(values["sample_answer_id"]) or None,
            sample_citations=citations if isinstance(citations, list) else [],
            scope=str(values["scope"]),
            visibility=str(values["visibility"]),
            created_at=datetime.fromisoformat(str(values["created_at"])),
            updated_at=datetime.fromisoformat(str(values["updated_at"])),
        )

    def record_question(
        self,
        question_text: str,
        answer_id: str | None = None,
        citations: list[str] | None = None,
        topic: str = "general",
    ) -> RecurringQuestionRecord:
        normalized_text = normalize_recurring_question(question_text)
        question_id = recurring_question_id(normalized_text)
        now = datetime.now(timezone.utc).isoformat()
        with connection() as database:
            database.execute(
                """INSERT INTO recurring_questions(
                    question_id, question_text, normalized_text, topic, ask_count,
                    first_asked_at, last_asked_at, sample_answer_id, sample_citations,
                    scope, visibility, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 'global', 'published', ?, ?)
                ON CONFLICT(question_id) DO UPDATE SET
                    question_text = excluded.question_text,
                    topic = excluded.topic,
                    ask_count = recurring_questions.ask_count + 1,
                    last_asked_at = excluded.last_asked_at,
                    sample_answer_id = excluded.sample_answer_id,
                    sample_citations = excluded.sample_citations,
                    updated_at = excluded.updated_at""",
                (
                    question_id,
                    question_text,
                    normalized_text,
                    topic,
                    now,
                    now,
                    answer_id or "",
                    json.dumps(citations or []),
                    now,
                    now,
                ),
            )
            row = database.execute(
                "SELECT * FROM recurring_questions WHERE question_id = ?", (question_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Recurring question insert did not return a record")
        return self._record(row)

    def list_questions(
        self, topic: str | None = None, limit: int = 8
    ) -> list[RecurringQuestionRecord]:
        query = "SELECT * FROM recurring_questions WHERE visibility = 'published'"
        values: list[str | int] = []
        if topic is not None:
            query += " AND topic = ?"
            values.append(topic)
        query += " ORDER BY ask_count DESC, last_asked_at DESC LIMIT ?"
        values.append(limit)
        with connection() as database:
            rows = database.execute(query, values).fetchall()
        return [self._record(row) for row in rows]


class DynamoDBRecurringQuestionStore:
    """Recurring-question aggregation for a DynamoDB table keyed by question ID."""

    def __init__(self, settings: PersistenceSettings, resource: Any | None = None) -> None:
        self._settings = settings
        self._resource = resource

    @property
    def _table(self) -> Any:
        resource = self._resource or get_dynamodb_resource(self._settings)
        return resource.Table(self._settings.dynamodb_recurring_questions_table)

    @staticmethod
    def _record(item: dict[str, Any]) -> RecurringQuestionRecord:
        return RecurringQuestionRecord(
            question_id=item["question_id"],
            question_text=item["question_text"],
            normalized_text=item["normalized_text"],
            topic=item.get("topic", "general"),
            ask_count=int(item.get("ask_count", 1)),
            first_asked_at=item["first_asked_at"],
            last_asked_at=item["last_asked_at"],
            sample_answer_id=item.get("sample_answer_id") or None,
            sample_citations=item.get("sample_citations", []),
            scope=item.get("scope", "global"),
            visibility=item.get("visibility", "published"),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )

    def record_question(
        self,
        question_text: str,
        answer_id: str | None = None,
        citations: list[str] | None = None,
        topic: str = "general",
    ) -> RecurringQuestionRecord:
        normalized_text = normalize_recurring_question(question_text)
        question_id = recurring_question_id(normalized_text)
        now = datetime.now(timezone.utc).isoformat()
        response = self._table.update_item(
            Key={"question_id": question_id},
            UpdateExpression=(
                "SET #question_text = :question_text, #normalized_text = :normalized_text, "
                "#topic = :topic, #last_asked_at = :now, #sample_answer_id = :answer_id, "
                "#sample_citations = :citations, #scope = if_not_exists(#scope, :scope), "
                "#visibility = if_not_exists(#visibility, :visibility), "
                "#first_asked_at = if_not_exists(#first_asked_at, :now), "
                "#created_at = if_not_exists(#created_at, :now), #updated_at = :now "
                "ADD #ask_count :one"
            ),
            ExpressionAttributeNames={
                "#question_text": "question_text",
                "#normalized_text": "normalized_text",
                "#topic": "topic",
                "#last_asked_at": "last_asked_at",
                "#sample_answer_id": "sample_answer_id",
                "#sample_citations": "sample_citations",
                "#scope": "scope",
                "#visibility": "visibility",
                "#first_asked_at": "first_asked_at",
                "#created_at": "created_at",
                "#updated_at": "updated_at",
                "#ask_count": "ask_count",
            },
            ExpressionAttributeValues={
                ":question_text": question_text,
                ":normalized_text": normalized_text,
                ":topic": topic,
                ":now": now,
                ":answer_id": answer_id or "",
                ":citations": citations or [],
                ":scope": "global",
                ":visibility": "published",
                ":one": 1,
            },
            ReturnValues="ALL_NEW",
        )
        return self._record(response["Attributes"])

    def list_questions(
        self, topic: str | None = None, limit: int = 8
    ) -> list[RecurringQuestionRecord]:
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": "#visibility = :published",
            "ExpressionAttributeNames": {"#visibility": "visibility"},
            "ExpressionAttributeValues": {":published": "published"},
        }
        if topic is not None:
            scan_kwargs["FilterExpression"] += " AND #topic = :topic"
            scan_kwargs["ExpressionAttributeNames"]["#topic"] = "topic"
            scan_kwargs["ExpressionAttributeValues"][":topic"] = topic

        items: list[dict[str, Any]] = []
        while True:
            response = self._table.scan(**scan_kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if last_key is None:
                break
            scan_kwargs["ExclusiveStartKey"] = last_key
        records = [self._record(item) for item in items]
        return sorted(
            records,
            key=lambda record: (record.ask_count, record.last_asked_at),
            reverse=True,
        )[:limit]


@dataclass(frozen=True)
class StoreFactory:
    """Selects the configured persistence backend for application-memory stores."""

    settings: PersistenceSettings

    @property
    def backend(self) -> str:
        return self.settings.backend

    @property
    def uses_sqlite(self) -> bool:
        return self.backend == "sqlite"

    @property
    def uses_dynamodb(self) -> bool:
        return self.backend == "dynamodb"

    def dynamodb_resource(self) -> Any:
        """Return a DynamoDB resource only for the explicitly selected backend."""
        if not self.uses_dynamodb:
            raise RuntimeError(
                "DynamoDB was requested while APP_PERSISTENCE_BACKEND is not set to 'dynamodb'."
            )
        return get_dynamodb_resource(self.settings)

    def conflict_store(self) -> ConflictStore:
        if self.uses_sqlite:
            return SQLiteConflictStore()
        return DynamoDBConflictStore(self.settings)

    def feedback_store(self) -> FeedbackStore:
        if self.uses_sqlite:
            return SQLiteFeedbackStore()
        return DynamoDBFeedbackStore(self.settings)

    def recurring_question_store(self) -> RecurringQuestionStore:
        if self.uses_sqlite:
            return SQLiteRecurringQuestionStore()
        return DynamoDBRecurringQuestionStore(self.settings)


def get_store_factory(settings: PersistenceSettings | None = None) -> StoreFactory:
    """Build the store-selection helper; this never contacts AWS on its own."""
    return StoreFactory(settings=settings or PERSISTENCE_SETTINGS)


def get_conflict_store(settings: PersistenceSettings | None = None) -> ConflictStore:
    """Return the configured conflict store without making a database call."""
    return get_store_factory(settings).conflict_store()


def get_feedback_store(settings: PersistenceSettings | None = None) -> FeedbackStore:
    """Return the configured feedback store without making a database call."""
    return get_store_factory(settings).feedback_store()


def get_recurring_question_store(
    settings: PersistenceSettings | None = None,
) -> RecurringQuestionStore:
    """Return the configured recurring-question store without a persistence call."""
    return get_store_factory(settings).recurring_question_store()
