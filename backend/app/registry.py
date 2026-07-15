from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import require_reviewer
from .config import CORPUS_DIR, UPLOAD_DIR, get_settings
from .database import connection, initialize_database
from .ingest import _parse_front_matter, discover_corpus_files
from .models import SourceLifecycleStatus, SourceRecord, SourceStatusUpdate, SourceUpsert
from .stores import _ddb_decode, _ddb_encode

router = APIRouter(prefix="/api/sources", tags=["source registry"])


def _record(values: dict[str, object]) -> SourceRecord:
    updated = values.get("updated_at")
    return SourceRecord(
        id=str(values["id"]), title=str(values["title"]), source_type=str(values["source_type"]),  # type: ignore[arg-type]
        status=str(values["status"]), canonical_url=str(values.get("canonical_url", "")),  # type: ignore[arg-type]
        edition_year=int(values["edition_year"]) if values.get("edition_year") not in (None, "") else None,
        is_current=bool(int(values.get("is_current", 1))), s3_key=str(values.get("s3_key", "")),
        passages=int(values.get("passages", 0)),
        updated_at=updated if isinstance(updated, datetime) else datetime.fromisoformat(str(updated)),
    )


class RegistryStore(Protocol):
    def list(self) -> list[SourceRecord]: ...
    def get(self, source_id: str) -> SourceRecord | None: ...
    def upsert(self, record: SourceUpsert) -> SourceRecord: ...
    def set_status(self, source_id: str, status: SourceLifecycleStatus) -> SourceRecord | None: ...


class SQLiteRegistryStore:
    def __init__(self) -> None:
        # Store methods are also used directly outside the FastAPI lifespan.
        initialize_database()

    def list(self) -> list[SourceRecord]:
        with connection() as database:
            rows = database.execute("SELECT * FROM registry ORDER BY title").fetchall()
        return [_record(dict(row)) for row in rows]

    def get(self, source_id: str) -> SourceRecord | None:
        with connection() as database:
            row = database.execute("SELECT * FROM registry WHERE id=?", (source_id,)).fetchone()
        return _record(dict(row)) if row is not None else None

    def upsert(self, record: SourceUpsert) -> SourceRecord:
        with connection() as database:
            database.execute(
                "INSERT INTO registry(id,title,source_type,status,canonical_url,edition_year,is_current,s3_key,passages) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,"
                "source_type=excluded.source_type,status=excluded.status,canonical_url=excluded.canonical_url,"
                "edition_year=excluded.edition_year,is_current=excluded.is_current,s3_key=excluded.s3_key,"
                "passages=excluded.passages,updated_at=CURRENT_TIMESTAMP",
                (record.id, record.title, record.source_type, record.status, record.canonical_url,
                 record.edition_year, int(record.is_current), record.s3_key, record.passages),
            )
        stored = self.get(record.id)
        if stored is None:
            raise RuntimeError("Registry upsert did not persist")
        return stored

    def set_status(self, source_id: str, status: SourceLifecycleStatus) -> SourceRecord | None:
        if self.get(source_id) is None:
            return None
        with connection() as database:
            database.execute("UPDATE registry SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, source_id))
        return self.get(source_id)


class DynamoDBRegistryStore:
    def __init__(self, client: object | None = None) -> None:
        settings = get_settings()
        if not settings.ddb_registry_table:
            raise ValueError("DDB_REGISTRY_TABLE is required")
        if client is None:
            import boto3  # type: ignore[import-not-found]
            client = boto3.client("dynamodb", region_name=settings.aws_region)
        self.client = client
        self.table = settings.ddb_registry_table

    def list(self) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        start_key: dict[str, object] | None = None
        while True:
            kwargs: dict[str, object] = {"TableName": self.table}
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.client.scan(**kwargs)  # type: ignore[attr-defined]
            records.extend(_record(_ddb_decode(item)) for item in response.get("Items", []))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return sorted(records, key=lambda value: value.title)

    def get(self, source_id: str) -> SourceRecord | None:
        item = self.client.get_item(TableName=self.table, Key={"id": {"S": source_id}}).get("Item")  # type: ignore[attr-defined]
        return _record(_ddb_decode(item)) if item else None

    def upsert(self, record: SourceUpsert) -> SourceRecord:
        now = datetime.now(timezone.utc).isoformat()
        values: dict[str, object] = {**record.model_dump(), "is_current": int(record.is_current),
                                     "edition_year": record.edition_year or "", "updated_at": now}
        self.client.put_item(TableName=self.table, Item=_ddb_encode(values))  # type: ignore[attr-defined]
        return _record({**values, "edition_year": record.edition_year})

    def set_status(self, source_id: str, status: SourceLifecycleStatus) -> SourceRecord | None:
        existing = self.get(source_id)
        if existing is None:
            return None
        return self.upsert(SourceUpsert(**{**existing.model_dump(exclude={"updated_at"}), "status": status}))


def registry_store() -> RegistryStore:
    return DynamoDBRegistryStore() if get_settings().registry_aws else SQLiteRegistryStore()


def _seed_id(path: Path) -> str:
    return path.stem.lower()


def register_document(path: Path, *, status: SourceLifecycleStatus, source_type: str | None = None,
                      canonical_url: str = "", edition_year: int | None = None, is_current: bool = True,
                      passages: int = 0) -> SourceRecord:
    """Create the registry entry for one corpus document, preserving an existing status."""
    text = path.read_text(encoding="utf-8", errors="replace") if path.suffix.lower() in {".md", ".txt"} else ""
    metadata, _ = _parse_front_matter(text)
    store = registry_store()
    existing = store.get(_seed_id(path))
    resolved_type = source_type or metadata.get("source_type", "uploads")
    if resolved_type not in {"handbook", "cba", "policystat", "catalog", "uploads"}:
        resolved_type = "uploads"
    return store.upsert(SourceUpsert(
        id=_seed_id(path), title=metadata.get("title", path.stem),
        source_type=resolved_type,  # type: ignore[arg-type]
        status=existing.status if existing is not None else status,
        canonical_url=canonical_url or metadata.get("canonical_url", ""),
        edition_year=edition_year, is_current=is_current,
        passages=passages or (existing.passages if existing is not None else 0),
    ))


def seed_registry_from_corpus() -> None:
    """Seeds start active; anything under uploads/ starts archived (locked decision)."""
    for path in discover_corpus_files(CORPUS_DIR):
        in_uploads = UPLOAD_DIR in path.parents or path.parent == UPLOAD_DIR
        register_document(path, status="archived" if in_uploads else "active")


@router.get("", response_model=list[SourceRecord])
def list_sources() -> list[SourceRecord]:
    return registry_store().list()


@router.post("/{source_id}/status", response_model=SourceRecord)
def update_source_status(source_id: str, payload: SourceStatusUpdate, _: None = Depends(require_reviewer)) -> SourceRecord:
    record = registry_store().set_status(source_id, payload.status)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return record
