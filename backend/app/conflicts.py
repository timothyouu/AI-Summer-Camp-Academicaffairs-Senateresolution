from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import require_reviewer
from .config import get_settings
from .models import ConflictCreate, ConflictRecord, ConflictStatus, ConflictUpdate
from .stores import conflict_store


router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])

DEMO_CONFLICTS = (
    ConflictCreate(source_a="CSUB University Handbook 2025, Appendix G", source_b="RES 252644, WPAF Contents and Timelines", topic="WPAF evidence format", description="The Handbook retains paper-binder language while the later supplied resolution uses electronic organization and representative evidence."),
    ConflictCreate(source_a="Unit 3 CBA, Article 29.8", source_b="CalPERS Employment After Retirement Guide", topic="FERP work limits", description="The appointment must satisfy both the CBA period-of-employment limit and CalPERS retired-annuitant limits; the ceilings are cumulative, not alternatives."),
    ConflictCreate(source_a="CSUB University Handbook 2025, Appendix K", source_b="Demo AI Resolution Stand-in", topic="Accessible instructional technology", description="Any future AI-use rule must preserve accessibility review and an equally effective alternative when technology is not accessible.", status="Under review"),
)


def list_conflicts(status_filter: ConflictStatus | None = None, topic: str | None = None) -> list[ConflictRecord]:
    records = conflict_store().list()
    return [
        record for record in records
        if (status_filter is None or record.status == status_filter)
        and (topic is None or record.topic == topic)
    ]


def create_or_get_conflict(payload: ConflictCreate, origin: str = "manual") -> ConflictRecord:
    del origin  # The current ConflictLog schema keeps findings idempotent by content.
    return conflict_store().create_or_get(payload)


def seed_demo_conflicts() -> list[ConflictRecord]:
    if get_settings().conflicts_aws:
        return []
    return [create_or_get_conflict(payload) for payload in DEMO_CONFLICTS]


def _parse_conflict_id(conflict_id: str) -> int:
    try:
        return int(conflict_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found") from error


@router.get("", response_model=list[ConflictRecord])
def get_conflicts(
    status_filter: ConflictStatus | None = Query(default=None, alias="status"),
    topic: str | None = Query(default=None),
    _: None = Depends(require_reviewer),
) -> list[ConflictRecord]:
    return list_conflicts(status_filter=status_filter, topic=topic)


@router.get("/{conflict_id}", response_model=ConflictRecord)
def get_conflict(conflict_id: str, _: None = Depends(require_reviewer)) -> ConflictRecord:
    record = conflict_store().get(_parse_conflict_id(conflict_id))
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")
    return record


@router.post("", response_model=ConflictRecord, status_code=status.HTTP_201_CREATED)
def create_conflict(payload: ConflictCreate, _: None = Depends(require_reviewer)) -> ConflictRecord:
    return create_or_get_conflict(payload)


@router.patch("/{conflict_id}", response_model=ConflictRecord)
def update_conflict(conflict_id: str, payload: ConflictUpdate, _: None = Depends(require_reviewer)) -> ConflictRecord:
    record = conflict_store().update(_parse_conflict_id(conflict_id), payload)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")
    return record
