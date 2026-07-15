from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from .database import connection
from .models import ConflictCreate, ConflictRecord, ConflictUpdate


router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])

DEMO_CONFLICTS = (
    ConflictCreate(source_a="CSUB University Handbook 2025, Appendix G", source_b="RES 252644, WPAF Contents and Timelines", topic="WPAF evidence format", description="The Handbook retains paper-binder language while the later supplied resolution uses electronic organization and representative evidence."),
    ConflictCreate(source_a="Unit 3 CBA, Article 29.8", source_b="CalPERS Employment After Retirement Guide", topic="FERP work limits", description="The appointment must satisfy both the CBA period-of-employment limit and CalPERS retired-annuitant limits; the ceilings are cumulative, not alternatives."),
    ConflictCreate(source_a="CSUB University Handbook 2025, Appendix K", source_b="Demo AI Resolution Stand-in", topic="Accessible instructional technology", description="Any future AI-use rule must preserve accessibility review and an equally effective alternative when technology is not accessible.", status="Under review"),
)


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


def list_conflicts() -> list[ConflictRecord]:
    with connection() as database:
        rows = database.execute("SELECT * FROM conflicts ORDER BY updated_at DESC, id DESC").fetchall()
    return [_record(row) for row in rows]


def create_or_get_conflict(payload: ConflictCreate) -> ConflictRecord:
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
    return _record(row)


def seed_demo_conflicts() -> list[ConflictRecord]:
    return [create_or_get_conflict(payload) for payload in DEMO_CONFLICTS]


@router.get("", response_model=list[ConflictRecord])
def get_conflicts() -> list[ConflictRecord]:
    return list_conflicts()


@router.post("", response_model=ConflictRecord, status_code=status.HTTP_201_CREATED)
def create_conflict(payload: ConflictCreate) -> ConflictRecord:
    return create_or_get_conflict(payload)


@router.patch("/{conflict_id}", response_model=ConflictRecord)
def update_conflict(conflict_id: int, payload: ConflictUpdate) -> ConflictRecord:
    with connection() as database:
        database.execute(
            """UPDATE conflicts SET status = ?, resolution_note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?""",
            (payload.status, payload.resolution_note.strip(), conflict_id),
        )
        row = database.execute("SELECT * FROM conflicts WHERE id = ?", (conflict_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")
    return _record(row)
