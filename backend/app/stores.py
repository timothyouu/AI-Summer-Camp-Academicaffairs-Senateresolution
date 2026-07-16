from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from .config import get_settings
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: object) -> datetime:
    """Parse a stored timestamp, tolerating the trailing 'Z' that Pydantic emits.

    Records written through the DynamoDB resource API are serialized with
    model_dump(mode="json"), which renders aware-UTC datetimes as '...Z'.
    datetime.fromisoformat only accepts that suffix on Python 3.11+, so
    normalize it rather than depending on the runtime's version.
    """
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)


def _conflict(values: dict[str, object]) -> ConflictRecord:
    return ConflictRecord(
        id=int(values["id"]),
        source_a=str(values["source_a"]),
        source_b=str(values["source_b"]),
        topic=str(values["topic"]),
        description=str(values["description"]),
        status=str(values["status"]),  # type: ignore[arg-type]
        resolution_note=str(values.get("resolution_note", "")),
        created_at=_timestamp(values["created_at"]),
        updated_at=_timestamp(values["updated_at"]),
    )


class ConflictStore(Protocol):
    def list(self) -> list[ConflictRecord]: ...
    def create_or_get(self, payload: ConflictCreate) -> ConflictRecord: ...
    def get(self, conflict_id: int) -> ConflictRecord | None: ...
    def update(self, conflict_id: int, payload: ConflictUpdate) -> ConflictRecord | None: ...


class SQLiteConflictStore:
    def list(self) -> list[ConflictRecord]:
        with connection() as database:
            rows = database.execute("SELECT * FROM conflicts ORDER BY updated_at DESC, id DESC").fetchall()
        return [_conflict(dict(row)) for row in rows]

    def create_or_get(self, payload: ConflictCreate) -> ConflictRecord:
        with connection() as database:
            database.execute(
                "INSERT OR IGNORE INTO conflicts(source_a, source_b, topic, description, status) VALUES (?, ?, ?, ?, ?)",
                (payload.source_a, payload.source_b, payload.topic, payload.description, payload.status),
            )
            row = database.execute(
                "SELECT * FROM conflicts WHERE source_a=? AND source_b=? AND topic=? AND description=?",
                (payload.source_a, payload.source_b, payload.topic, payload.description),
            ).fetchone()
        if row is None:
            raise RuntimeError("Conflict insert did not return a record")
        return _conflict(dict(row))

    def get(self, conflict_id: int) -> ConflictRecord | None:
        with connection() as database:
            row = database.execute("SELECT * FROM conflicts WHERE id=?", (conflict_id,)).fetchone()
        return _conflict(dict(row)) if row is not None else None

    def update(self, conflict_id: int, payload: ConflictUpdate) -> ConflictRecord | None:
        assignments = ["updated_at=CURRENT_TIMESTAMP"]
        values: list[object] = []
        if payload.status is not None:
            assignments.append("status=?")
            values.append(payload.status)
        if payload.resolution_note is not None:
            assignments.append("resolution_note=?")
            values.append(payload.resolution_note.strip())
        values.append(conflict_id)
        with connection() as database:
            database.execute(f"UPDATE conflicts SET {', '.join(assignments)} WHERE id=?", values)
            row = database.execute("SELECT * FROM conflicts WHERE id=?", (conflict_id,)).fetchone()
        return _conflict(dict(row)) if row is not None else None


class DynamoDBConflictStore:
    def __init__(self, client: object | None = None) -> None:
        settings = get_settings()
        if not settings.ddb_conflicts_table:
            raise ValueError("DDB_CONFLICTS_TABLE is required")
        if client is None:
            import boto3  # type: ignore[import-not-found]

            client = boto3.client("dynamodb", region_name=settings.aws_region)
        self.client = client
        self.table = settings.ddb_conflicts_table

    def list(self) -> list[ConflictRecord]:
        records: list[ConflictRecord] = []
        start_key: dict[str, object] | None = None
        while True:
            kwargs: dict[str, object] = {"TableName": self.table}
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.client.scan(**kwargs)  # type: ignore[attr-defined]
            records.extend(_conflict(_ddb_decode(item)) for item in response.get("Items", []))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return sorted(records, key=lambda value: (value.updated_at, int(value.id)), reverse=True)

    def create_or_get(self, payload: ConflictCreate) -> ConflictRecord:
        identity = "\x1f".join((payload.source_a, payload.source_b, payload.topic, payload.description))
        conflict_id = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:4], "big") & 0x7FFF_FFFF
        existing = self.client.get_item(TableName=self.table, Key=_ddb_conflict_key(conflict_id)).get("Item")  # type: ignore[attr-defined]
        if existing:
            return _conflict(_ddb_decode(existing))
        now = _now().isoformat()
        values: dict[str, object] = {
            "id": conflict_id,
            **payload.model_dump(),
            "resolution_note": "",
            "created_at": now,
            "updated_at": now,
        }
        try:
            self.client.put_item(  # type: ignore[attr-defined]
                TableName=self.table,
                Item=_ddb_encode({**values, "id": str(conflict_id)}),
                ConditionExpression="attribute_not_exists(id)",
            )
        except Exception as error:
            if _ddb_error_code(error) != "ConditionalCheckFailedException":
                raise
            existing = self.client.get_item(TableName=self.table, Key=_ddb_conflict_key(conflict_id)).get("Item")  # type: ignore[attr-defined]
            if not existing:
                raise
            return _conflict(_ddb_decode(existing))
        return _conflict(values)

    def get(self, conflict_id: int) -> ConflictRecord | None:
        item = self.client.get_item(TableName=self.table, Key=_ddb_conflict_key(conflict_id)).get("Item")  # type: ignore[attr-defined]
        return _conflict(_ddb_decode(item)) if item else None

    def update(self, conflict_id: int, payload: ConflictUpdate) -> ConflictRecord | None:
        assignments = ["updated_at=:updated"]
        names: dict[str, str] = {}
        values: dict[str, dict[str, str]] = {":updated": {"S": _now().isoformat()}}
        if payload.status is not None:
            assignments.append("#status=:status")
            names["#status"] = "status"
            values[":status"] = {"S": payload.status}
        if payload.resolution_note is not None:
            assignments.append("resolution_note=:note")
            values[":note"] = {"S": payload.resolution_note.strip()}
        kwargs: dict[str, object] = {
            "TableName": self.table,
            "Key": _ddb_conflict_key(conflict_id),
            "UpdateExpression": f"SET {', '.join(assignments)}",
            "ConditionExpression": "attribute_exists(id)",
            "ExpressionAttributeValues": values,
            "ReturnValues": "ALL_NEW",
        }
        if names:
            kwargs["ExpressionAttributeNames"] = names
        try:
            response = self.client.update_item(**kwargs)  # type: ignore[attr-defined]
        except Exception as error:
            if _ddb_error_code(error) == "ConditionalCheckFailedException":
                return None
            raise
        item = response.get("Attributes")
        return _conflict(_ddb_decode(item)) if item else None

@dataclass(frozen=True)
class UploadRecord:
    upload_id: str
    filename: str
    status: str
    chunks_added: int
    ingestion_job_id: str | None = None
    error: str | None = None


class UploadStore(Protocol):
    def register(
        self,
        filename: str,
        status: str,
        chunks_added: int = 0,
        upload_id: str | None = None,
        ingestion_job_id: str | None = None,
        error: str | None = None,
    ) -> str: ...
    def get(self, upload_id: str) -> UploadRecord | None: ...


class SQLiteUploadStore:
    def register(
        self,
        filename: str,
        status: str,
        chunks_added: int = 0,
        upload_id: str | None = None,
        ingestion_job_id: str | None = None,
        error: str | None = None,
    ) -> str:
        identifier = upload_id or filename
        with connection() as database:
            database.execute(
                "INSERT INTO uploads(upload_id,filename,status,chunks_added,ingestion_job_id,error) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(upload_id) DO UPDATE SET filename=excluded.filename,status=excluded.status,"
                "chunks_added=excluded.chunks_added,ingestion_job_id=excluded.ingestion_job_id,error=excluded.error",
                (identifier, filename, status, chunks_added, ingestion_job_id, error),
            )
        return identifier

    def get(self, upload_id: str) -> UploadRecord | None:
        with connection() as database:
            row = database.execute(
                "SELECT upload_id, filename, status, chunks_added, ingestion_job_id, error FROM uploads WHERE upload_id=?",
                (upload_id,),
            ).fetchone()
        if row is None:
            return None
        return UploadRecord(
            upload_id=str(row["upload_id"]),
            filename=str(row["filename"]),
            status=str(row["status"]),
            chunks_added=int(row["chunks_added"]),
            ingestion_job_id=row["ingestion_job_id"],
            error=row["error"],
        )


class DynamoDBUploadStore:
    def __init__(self, client: object | None = None) -> None:
        settings = get_settings()
        if not settings.ddb_uploads_table:
            raise ValueError("DDB_UPLOADS_TABLE is required")
        if client is None:
            import boto3  # type: ignore[import-not-found]

            client = boto3.client("dynamodb", region_name=settings.aws_region)
        self.client = client
        self.table = settings.ddb_uploads_table

    def register(
        self,
        filename: str,
        status: str,
        chunks_added: int = 0,
        upload_id: str | None = None,
        ingestion_job_id: str | None = None,
        error: str | None = None,
    ) -> str:
        identifier = upload_id or str(uuid4())
        self.client.put_item(TableName=self.table, Item=_ddb_encode({  # type: ignore[attr-defined]
            "id": identifier,
            "filename": filename,
            "status": status,
            "chunks_added": chunks_added,
            "ingestion_job_id": ingestion_job_id or "",
            "error": error or "",
            "created_at": _now().isoformat(),
            "updated_at": _now().isoformat(),
        }))
        return identifier

    def get(self, upload_id: str) -> UploadRecord | None:
        response = self.client.get_item(TableName=self.table, Key={"id": {"S": upload_id}})  # type: ignore[attr-defined]
        item = response.get("Item")
        if not item:
            return None
        values = _ddb_decode(item)
        return UploadRecord(
            upload_id=str(values["id"]),
            filename=str(values["filename"]),
            status=str(values["status"]),
            chunks_added=int(values.get("chunks_added", 0)),
            ingestion_job_id=str(values["ingestion_job_id"]) if values.get("ingestion_job_id") else None,
            error=str(values["error"]) if values.get("error") else None,
        )


class FeedbackStore(Protocol):
    def create_feedback(self, payload: FeedbackCreate) -> FeedbackRecord: ...
    def list_feedback(self, rating: str | None = None, issue_type: str | None = None, limit: int = 100) -> list[FeedbackRecord]: ...


def _feedback(values: dict[str, Any]) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=str(values["feedback_id"]),
        answer_id=str(values["answer_id"]),
        question=str(values["question"]),
        rating=str(values["rating"]),  # type: ignore[arg-type]
        comment=str(values.get("comment") or "") or None,
        issue_type=str(values.get("issue_type") or "") or None,  # type: ignore[arg-type]
        role=str(values.get("role") or "") or None,  # type: ignore[arg-type]
        citations_used=list(values.get("citations_used") or []),
        provider=str(values.get("provider") or "") or None,
        created_at=_timestamp(values["created_at"]),
    )


class SQLiteFeedbackStore:
    def create_feedback(self, payload: FeedbackCreate) -> FeedbackRecord:
        feedback_id = str(uuid4())
        created_at = _now()
        with connection() as database:
            database.execute(
                "INSERT INTO feedback(feedback_id,answer_id,question,rating,comment,issue_type,role,citations_used,provider,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    feedback_id,
                    payload.answer_id,
                    payload.question,
                    payload.rating,
                    payload.comment or "",
                    payload.issue_type or "",
                    payload.role or "",
                    json.dumps(payload.citations_used),
                    payload.provider or "",
                    created_at.isoformat(),
                ),
            )
        return FeedbackRecord(feedback_id=feedback_id, created_at=created_at, **payload.model_dump())

    def list_feedback(self, rating: str | None = None, issue_type: str | None = None, limit: int = 100) -> list[FeedbackRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if rating:
            clauses.append("rating=?")
            params.append(rating)
        if issue_type:
            clauses.append("issue_type=?")
            params.append(issue_type)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with connection() as database:
            rows = database.execute(
                f"SELECT * FROM feedback{where} ORDER BY created_at DESC LIMIT ?", params
            ).fetchall()
        return [_feedback({**dict(row), "citations_used": json.loads(row["citations_used"])}) for row in rows]


class DynamoDBFeedbackStore:
    def __init__(self, resource: Any | None = None, table_name: str | None = None) -> None:
        name = table_name or get_settings().ddb_feedback_table
        if not name:
            raise ValueError("DDB_FEEDBACK_TABLE is required")
        self.table_name = name
        self.resource = resource

    @property
    def table(self) -> Any:
        return (self.resource or get_dynamodb_resource()).Table(self.table_name)

    def create_feedback(self, payload: FeedbackCreate) -> FeedbackRecord:
        record = FeedbackRecord(feedback_id=str(uuid4()), created_at=_now(), **payload.model_dump())
        self.table.put_item(Item=record.model_dump(mode="json", exclude_none=False))
        return record

    def list_feedback(self, rating: str | None = None, issue_type: str | None = None, limit: int = 100) -> list[FeedbackRecord]:
        filters: list[str] = []
        names: dict[str, str] = {}
        values: dict[str, object] = {}
        if rating:
            filters.append("#rating = :rating")
            names["#rating"] = "rating"
            values[":rating"] = rating
        if issue_type:
            filters.append("issue_type = :issue_type")
            values[":issue_type"] = issue_type
        kwargs: dict[str, object] = {"Limit": limit}
        if filters:
            kwargs["FilterExpression"] = " AND ".join(filters)
            kwargs["ExpressionAttributeValues"] = values
        if names:
            kwargs["ExpressionAttributeNames"] = names
        items = self.table.scan(**kwargs).get("Items", [])
        return sorted((_feedback(item) for item in items), key=lambda item: item.created_at, reverse=True)[:limit]


def normalize_recurring_question(question_text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", question_text.lower()).strip()


def recurring_question_id(normalized_text: str) -> str:
    return f"rq_{hashlib.sha256(normalized_text.encode()).hexdigest()}"


class RecurringQuestionStore(Protocol):
    def record_question(
        self,
        question_text: str,
        answer_id: str | None = None,
        citations: list[str] | None = None,
        topic: str = "general",
    ) -> RecurringQuestionRecord: ...
    def list_questions(self, topic: str | None = None, limit: int = 8) -> list[RecurringQuestionRecord]: ...


def _recurring(values: dict[str, Any]) -> RecurringQuestionRecord:
    return RecurringQuestionRecord(
        question_id=str(values["question_id"]),
        question_text=str(values["question_text"]),
        normalized_text=str(values["normalized_text"]),
        topic=str(values.get("topic", "general")),
        ask_count=int(values.get("ask_count", 1)),
        first_asked_at=_timestamp(values["first_asked_at"]),
        last_asked_at=_timestamp(values["last_asked_at"]),
        sample_answer_id=str(values.get("sample_answer_id") or "") or None,
        sample_citations=list(values.get("sample_citations") or []),
        scope=str(values.get("scope", "global")),
        visibility=str(values.get("visibility", "published")),
        created_at=_timestamp(values["created_at"]),
        updated_at=_timestamp(values["updated_at"]),
    )


class SQLiteRecurringQuestionStore:
    def record_question(
        self,
        question_text: str,
        answer_id: str | None = None,
        citations: list[str] | None = None,
        topic: str = "general",
    ) -> RecurringQuestionRecord:
        normalized = normalize_recurring_question(question_text)
        identifier = recurring_question_id(normalized)
        now = _now().isoformat()
        with connection() as database:
            database.execute(
                """INSERT INTO recurring_questions(
                    question_id,question_text,normalized_text,topic,ask_count,first_asked_at,last_asked_at,
                    sample_answer_id,sample_citations,scope,visibility,created_at,updated_at
                ) VALUES (?,?,?,?,1,?,?,?,?,?,?,?,?)
                ON CONFLICT(question_id) DO UPDATE SET
                    question_text=excluded.question_text, topic=excluded.topic,
                    ask_count=recurring_questions.ask_count+1, last_asked_at=excluded.last_asked_at,
                    sample_answer_id=excluded.sample_answer_id, sample_citations=excluded.sample_citations,
                    updated_at=excluded.updated_at""",
                (
                    identifier, question_text.strip(), normalized, topic, now, now,
                    answer_id or "", json.dumps(citations or []), "global", "published", now, now,
                ),
            )
            row = database.execute("SELECT * FROM recurring_questions WHERE question_id=?", (identifier,)).fetchone()
        if row is None:
            raise RuntimeError("Recurring question upsert did not return a record")
        return _recurring({**dict(row), "sample_citations": json.loads(row["sample_citations"])})

    def list_questions(self, topic: str | None = None, limit: int = 8) -> list[RecurringQuestionRecord]:
        query = "SELECT * FROM recurring_questions WHERE visibility='published'"
        params: list[object] = []
        if topic:
            query += " AND topic=?"
            params.append(topic)
        query += " ORDER BY ask_count DESC, last_asked_at DESC LIMIT ?"
        params.append(limit)
        with connection() as database:
            rows = database.execute(query, params).fetchall()
        return [_recurring({**dict(row), "sample_citations": json.loads(row["sample_citations"])}) for row in rows]


class DynamoDBRecurringQuestionStore:
    def __init__(self, resource: Any | None = None, table_name: str | None = None) -> None:
        name = table_name or get_settings().ddb_recurring_questions_table
        if not name:
            raise ValueError("DDB_RECURRING_QUESTIONS_TABLE is required")
        self.table_name = name
        self.resource = resource

    @property
    def table(self) -> Any:
        return (self.resource or get_dynamodb_resource()).Table(self.table_name)

    def record_question(
        self,
        question_text: str,
        answer_id: str | None = None,
        citations: list[str] | None = None,
        topic: str = "general",
    ) -> RecurringQuestionRecord:
        normalized = normalize_recurring_question(question_text)
        identifier = recurring_question_id(normalized)
        now = _now().isoformat()
        response = self.table.update_item(
            Key={"question_id": identifier},
            UpdateExpression=(
                "SET question_text=:question_text, normalized_text=:normalized_text, topic=:topic, "
                "last_asked_at=:now, sample_answer_id=:answer_id, sample_citations=:citations, "
                "#scope=if_not_exists(#scope,:scope), visibility=if_not_exists(visibility,:visibility), "
                "first_asked_at=if_not_exists(first_asked_at,:now), created_at=if_not_exists(created_at,:now), "
                "updated_at=:now ADD ask_count :one"
            ),
            ExpressionAttributeNames={"#scope": "scope"},
            ExpressionAttributeValues={
                ":question_text": question_text.strip(),
                ":normalized_text": normalized,
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
        return _recurring(response["Attributes"])

    def list_questions(self, topic: str | None = None, limit: int = 8) -> list[RecurringQuestionRecord]:
        filters = ["visibility = :visibility"]
        values: dict[str, object] = {":visibility": "published"}
        if topic:
            filters.append("topic = :topic")
            values[":topic"] = topic
        items = self.table.scan(
            FilterExpression=" AND ".join(filters),
            ExpressionAttributeValues=values,
        ).get("Items", [])
        return sorted((_recurring(item) for item in items), key=lambda item: (item.ask_count, item.last_asked_at), reverse=True)[:limit]


def feedback_store() -> FeedbackStore:
    return DynamoDBFeedbackStore() if get_settings().feedback_aws else SQLiteFeedbackStore()


def recurring_question_store() -> RecurringQuestionStore:
    return DynamoDBRecurringQuestionStore() if get_settings().recurring_questions_aws else SQLiteRecurringQuestionStore()


def conflict_store() -> ConflictStore:
    return DynamoDBConflictStore() if get_settings().conflicts_aws else SQLiteConflictStore()


def upload_store() -> UploadStore:
    return DynamoDBUploadStore() if get_settings().uploads_aws else SQLiteUploadStore()


def _ddb_encode(values: dict[str, object]) -> dict[str, dict[str, str]]:
    # bool is a subclass of int, so it must be tested first — otherwise True
    # encodes as {"N": "True"}, which DynamoDB rejects because N must parse as a
    # number. Booleans ride the existing numeric decode path as 1/0.
    def encode(value: object) -> dict[str, str]:
        if isinstance(value, bool):
            return {"N": str(int(value))}
        if isinstance(value, (int, float)):
            return {"N": str(value)}
        return {"S": str(value)}

    return {key: encode(value) for key, value in values.items()}


def _ddb_conflict_key(conflict_id: int) -> dict[str, dict[str, str]]:
    return {"id": {"S": str(conflict_id)}}


def _ddb_error_code(error: Exception) -> str | None:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return None
    details = response.get("Error")
    return str(details.get("Code")) if isinstance(details, dict) and details.get("Code") else None


def _ddb_decode(item: dict[str, dict[str, str]]) -> dict[str, object]:
    return {
        key: int(value["N"]) if "N" in value and value["N"].isdigit() else value.get("N", value.get("S", ""))
        for key, value in item.items()
    }
