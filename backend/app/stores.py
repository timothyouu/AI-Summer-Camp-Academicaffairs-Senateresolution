from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from .config import get_settings
from .database import connection
from .models import ConflictCreate, ConflictRecord, ConflictUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conflict(values: dict[str, object]) -> ConflictRecord:
    def timestamp(name: str) -> datetime:
        value = values[name]
        return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return ConflictRecord(
        id=int(values["id"]), source_a=str(values["source_a"]), source_b=str(values["source_b"]),
        topic=str(values["topic"]), description=str(values["description"]), status=str(values["status"]),  # type: ignore[arg-type]
        resolution_note=str(values.get("resolution_note", "")), created_at=timestamp("created_at"), updated_at=timestamp("updated_at"),
    )


class ConflictStore(Protocol):
    def list(self) -> list[ConflictRecord]: ...
    def create_or_get(self, payload: ConflictCreate) -> ConflictRecord: ...
    def update(self, conflict_id: int, payload: ConflictUpdate) -> ConflictRecord | None: ...


class SQLiteConflictStore:
    def list(self) -> list[ConflictRecord]:
        with connection() as database:
            rows = database.execute("SELECT * FROM conflicts ORDER BY updated_at DESC, id DESC").fetchall()
        return [_conflict(dict(row)) for row in rows]

    def create_or_get(self, payload: ConflictCreate) -> ConflictRecord:
        with connection() as database:
            database.execute("INSERT OR IGNORE INTO conflicts(source_a, source_b, topic, description, status) VALUES (?, ?, ?, ?, ?)",
                             (payload.source_a, payload.source_b, payload.topic, payload.description, payload.status))
            row = database.execute("SELECT * FROM conflicts WHERE source_a=? AND source_b=? AND topic=? AND description=?",
                                   (payload.source_a, payload.source_b, payload.topic, payload.description)).fetchone()
        if row is None:
            raise RuntimeError("Conflict insert did not return a record")
        return _conflict(dict(row))

    def update(self, conflict_id: int, payload: ConflictUpdate) -> ConflictRecord | None:
        with connection() as database:
            database.execute("UPDATE conflicts SET status=?, resolution_note=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                             (payload.status, payload.resolution_note.strip(), conflict_id))
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
        response = self.client.scan(TableName=self.table)  # type: ignore[attr-defined]
        records = [_conflict(_ddb_decode(item)) for item in response.get("Items", [])]
        return sorted(records, key=lambda value: (value.updated_at, value.id), reverse=True)

    def create_or_get(self, payload: ConflictCreate) -> ConflictRecord:
        identity = "\x1f".join((payload.source_a, payload.source_b, payload.topic, payload.description))
        conflict_id = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:4], "big") & 0x7FFF_FFFF
        existing = self.client.get_item(TableName=self.table, Key={"id": {"N": str(conflict_id)}}).get("Item")  # type: ignore[attr-defined]
        if existing:
            return _conflict(_ddb_decode(existing))
        now = _now().isoformat()
        values: dict[str, object] = {"id": conflict_id, **payload.model_dump(), "resolution_note": "", "created_at": now, "updated_at": now}
        self.client.put_item(TableName=self.table, Item=_ddb_encode(values), ConditionExpression="attribute_not_exists(id)")  # type: ignore[attr-defined]
        return _conflict(values)

    def update(self, conflict_id: int, payload: ConflictUpdate) -> ConflictRecord | None:
        response = self.client.update_item(  # type: ignore[attr-defined]
            TableName=self.table, Key={"id": {"N": str(conflict_id)}},
            UpdateExpression="SET #status=:status, resolution_note=:note, updated_at=:updated",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": {"S": payload.status}, ":note": {"S": payload.resolution_note.strip()}, ":updated": {"S": _now().isoformat()}},
            ReturnValues="ALL_NEW",
        )
        item = response.get("Attributes")
        return _conflict(_ddb_decode(item)) if item else None


@dataclass(frozen=True)
class UploadRecord:
    upload_id: str
    filename: str
    status: str
    chunks_added: int


class UploadStore(Protocol):
    def register(self, filename: str, status: str, chunks_added: int = 0, upload_id: str | None = None) -> str: ...
    def get(self, upload_id: str) -> UploadRecord | None: ...


class SQLiteUploadStore:
    def register(self, filename: str, status: str, chunks_added: int = 0, upload_id: str | None = None) -> str:
        with connection() as database:
            database.execute("INSERT INTO uploads(filename,status,chunks_added) VALUES (?,?,?) ON CONFLICT(filename) DO UPDATE SET status=excluded.status,chunks_added=excluded.chunks_added",
                             (filename, status, chunks_added))
        return upload_id or filename

    def get(self, upload_id: str) -> UploadRecord | None:
        with connection() as database:
            row = database.execute("SELECT filename, status, chunks_added FROM uploads WHERE filename=?", (upload_id,)).fetchone()
        if row is None:
            return None
        return UploadRecord(upload_id=upload_id, filename=str(row["filename"]), status=str(row["status"]), chunks_added=int(row["chunks_added"]))


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

    def register(self, filename: str, status: str, chunks_added: int = 0, upload_id: str | None = None) -> str:
        identifier = upload_id or str(uuid4())
        self.client.put_item(TableName=self.table, Item=_ddb_encode({  # type: ignore[attr-defined]
            "id": identifier, "filename": filename, "status": status, "chunks_added": chunks_added,
            "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
        }))
        return identifier

    def get(self, upload_id: str) -> UploadRecord | None:
        response = self.client.get_item(TableName=self.table, Key={"id": {"S": upload_id}})  # type: ignore[attr-defined]
        item = response.get("Item")
        if not item:
            return None
        values = _ddb_decode(item)
        return UploadRecord(
            upload_id=str(values["id"]), filename=str(values["filename"]), status=str(values["status"]),
            chunks_added=int(values.get("chunks_added", 0)),
        )


def conflict_store() -> ConflictStore:
    return DynamoDBConflictStore() if get_settings().conflicts_aws else SQLiteConflictStore()


def upload_store() -> UploadStore:
    return DynamoDBUploadStore() if get_settings().uploads_aws else SQLiteUploadStore()


def _ddb_encode(values: dict[str, object]) -> dict[str, dict[str, str]]:
    encoded: dict[str, dict[str, str]] = {}
    for key, value in values.items():
        encoded[key] = {"N": str(value)} if isinstance(value, (int, float)) else {"S": str(value)}
    return encoded


def _ddb_decode(item: dict[str, dict[str, str]]) -> dict[str, object]:
    return {key: int(value["N"]) if "N" in value and value["N"].isdigit() else value.get("N", value.get("S", "")) for key, value in item.items()}
