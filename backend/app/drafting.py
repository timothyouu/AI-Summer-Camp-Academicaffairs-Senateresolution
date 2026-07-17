from __future__ import annotations

import json
from difflib import unified_diff
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from .agents import LLM, create_pipeline, resolution_output
from .auth import require_reviewer
from .dynamodb_client import get_dynamodb_client
from .config import get_settings
from .database import connection, initialize_database
from .models import (
    DraftComparison,
    DraftRestoreRequest,
    DraftReviseRequest,
    DraftReviseResponse,
    DraftSaveRequest,
    DraftSummary,
    DraftVersion,
    ResolutionFinding,
)
from .permissions import ADMIN_EMAIL, identity_email
from .stores import _ddb_decode, _ddb_encode, _ddb_error_code, _timestamp

router = APIRouter(prefix="/api/draft", tags=["drafting"])


def _version(values: dict[str, object]) -> DraftVersion:
    created = values.get("created_at")
    restored = values.get("restored_from_version")
    return DraftVersion(
        draft_id=str(values["draft_id"]),
        version=int(values["version"]),  # type: ignore[arg-type]
        title=str(values.get("title", "Untitled draft")),
        owner=str(values.get("owner", "")),
        status=str(values.get("status", "draft")),  # type: ignore[arg-type]
        text=str(values["text"]),
        source_text=str(values.get("source_text", "")),
        instruction=str(values.get("instruction", "")),
        suggestion=str(values.get("suggestion", "")),
        restored_from_version=int(restored) if restored not in (None, "") else None,
        created_at=_timestamp(created),
    )


def _summary(version: DraftVersion) -> DraftSummary:
    return DraftSummary(
        draft_id=version.draft_id,
        title=version.title,
        owner=version.owner,
        status=version.status,
        latest_version=version.version,
        latest_text=version.text,
        updated_at=version.created_at,
    )


def _requester(authorization: str | None, x_user_email: str | None) -> str:
    return identity_email(authorization, x_user_email) or "local-reviewer"


def _owner_of(version: DraftVersion) -> str:
    """Legacy versions saved before owner tracking default to the local demo reviewer."""
    return version.owner or "local-reviewer"


def _ensure_owner_access(versions: list[DraftVersion], requester: str) -> None:
    """Raise 403 unless the requester owns the draft's latest version or is the admin."""
    if not versions or requester == ADMIN_EMAIL:
        return
    if _owner_of(versions[-1]) != requester:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this draft")


class DraftStore(Protocol):
    def add_version(
        self, draft_id: str, text: str, suggestion: str, *, title: str = "Untitled draft",
        owner: str = "", status: str = "draft", source_text: str = "",
        instruction: str = "", restored_from_version: int | None = None,
    ) -> DraftVersion: ...

    def list_versions(self, draft_id: str) -> list[DraftVersion]: ...

    def list_drafts(self) -> list[DraftSummary]: ...


class SQLiteDraftStore:
    def __init__(self) -> None:
        # Store methods are also used directly outside the FastAPI lifespan.
        initialize_database()

    def add_version(
        self, draft_id: str, text: str, suggestion: str, *, title: str = "Untitled draft",
        owner: str = "", status: str = "draft", source_text: str = "",
        instruction: str = "", restored_from_version: int | None = None,
    ) -> DraftVersion:
        with connection() as database:
            row = database.execute(
                "SELECT COALESCE(MAX(version), 0) AS current FROM drafts WHERE draft_id=?", (draft_id,)
            ).fetchone()
            next_version = int(row["current"]) + 1
            database.execute(
                "INSERT INTO drafts(draft_id,version,title,owner,status,text,source_text,instruction,suggestion,restored_from_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (draft_id, next_version, title, owner, status, text, source_text, instruction,
                 suggestion, restored_from_version),
            )
            stored = database.execute(
                "SELECT * FROM drafts WHERE draft_id=? AND version=?", (draft_id, next_version)
            ).fetchone()
        return _version(dict(stored))

    def list_versions(self, draft_id: str) -> list[DraftVersion]:
        with connection() as database:
            rows = database.execute(
                "SELECT * FROM drafts WHERE draft_id=? ORDER BY version", (draft_id,)
            ).fetchall()
        return [_version(dict(row)) for row in rows]

    def list_drafts(self) -> list[DraftSummary]:
        with connection() as database:
            rows = database.execute(
                "SELECT draft.* FROM drafts AS draft JOIN ("
                "SELECT draft_id, MAX(version) AS version FROM drafts GROUP BY draft_id"
                ") AS latest ON latest.draft_id=draft.draft_id AND latest.version=draft.version "
                "ORDER BY draft.created_at DESC"
            ).fetchall()
        return [_summary(_version(dict(row))) for row in rows]


class DynamoDBDraftStore:
    def __init__(self, client: object | None = None) -> None:
        settings = get_settings()
        if not settings.ddb_drafts_table:
            raise ValueError("DDB_DRAFTS_TABLE is required")
        if client is None:
            client = get_dynamodb_client(settings)
        self.client = client
        self.table = settings.ddb_drafts_table

    def add_version(
        self, draft_id: str, text: str, suggestion: str, *, title: str = "Untitled draft",
        owner: str = "", status: str = "draft", source_text: str = "",
        instruction: str = "", restored_from_version: int | None = None,
    ) -> DraftVersion:
        values: dict[str, object] | None = None
        for _attempt in range(5):
            existing = self.list_versions(draft_id)
            next_version = (existing[-1].version + 1) if existing else 1
            values = {
                "draft_id": draft_id,
                "version": next_version,
                "title": title,
                "owner": owner,
                "status": status,
                "text": text,
                "source_text": source_text,
                "instruction": instruction,
                "suggestion": suggestion,
                "restored_from_version": restored_from_version or "",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                self.client.put_item(  # type: ignore[attr-defined]
                    TableName=self.table,
                    Item=_ddb_encode(values),
                    ConditionExpression="attribute_not_exists(draft_id) AND attribute_not_exists(version)",
                )
                break
            except Exception as error:
                if _ddb_error_code(error) != "ConditionalCheckFailedException":
                    raise
        else:
            raise RuntimeError("Draft version allocation remained contended after 5 attempts")
        if values is None:
            raise RuntimeError("Draft version allocation failed")
        settings = get_settings()
        if settings.corpus_aws:
            import boto3  # type: ignore[import-not-found]

            boto3.client("s3", region_name=settings.aws_region).put_object(
                Bucket=settings.corpus_bucket,
                Key=f"drafts/{draft_id}/v{next_version}.md",
                Body=text.encode("utf-8"),
                ContentType="text/markdown",
            )
        return _version(values)

    def list_versions(self, draft_id: str) -> list[DraftVersion]:
        items: list[dict[str, object]] = []
        start_key: dict[str, object] | None = None
        while True:
            kwargs: dict[str, object] = {
                "TableName": self.table,
                "KeyConditionExpression": "draft_id = :draft",
                "ExpressionAttributeValues": {":draft": {"S": draft_id}},
                "ConsistentRead": True,
            }
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.client.query(**kwargs)  # type: ignore[attr-defined]
            items.extend(response.get("Items", []))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return sorted(
            (_version(_ddb_decode(item)) for item in items),
            key=lambda value: value.version,
        )

    def list_drafts(self) -> list[DraftSummary]:
        latest: dict[str, DraftVersion] = {}
        start_key: dict[str, object] | None = None
        while True:
            kwargs: dict[str, object] = {"TableName": self.table}
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = self.client.scan(**kwargs)  # type: ignore[attr-defined]
            for item in response.get("Items", []):
                version = _version(_ddb_decode(item))
                current = latest.get(version.draft_id)
                if current is None or version.version > current.version:
                    latest[version.draft_id] = version
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return sorted((_summary(value) for value in latest.values()), key=lambda item: item.updated_at, reverse=True)


def draft_store() -> DraftStore:
    return DynamoDBDraftStore() if get_settings().drafts_aws else SQLiteDraftStore()


def deterministic_revision(
    text: str, conflicts: list[ResolutionFinding], recommendation: str, instruction: str = "",
) -> tuple[str, str]:
    """LLM-free fallback so the loop works with zero Bedrock access."""
    if not conflicts and instruction:
        revised = f"{text}\n\n[Requested revision] {instruction.strip()}"
        return revised, f"Applied the requested revision instruction: {instruction.strip()}. {recommendation}"
    if not conflicts:
        return text, f"No verified conflict to revise against. {recommendation}"
    notes = "; ".join(f"{item.source} ({item.section}): {item.description}" for item in conflicts)
    revised = (
        f"{text}\n\n[Revision note — reconcile before advancing] "
        f"This draft conflicts with: {notes}"
    )
    return revised, f"Flagged {len(conflicts)} verified conflict(s) for reconciliation: {notes}"


def llm_revision(
    llm: LLM,
    text: str,
    conflicts: list[ResolutionFinding],
    recommendation: str,
    instruction: str = "",
) -> tuple[str, str]:
    system = (
        "You revise draft university policy resolutions. Rewrite the draft so it no longer contradicts "
        "the cited existing policies, changing as little as possible. Return JSON only: "
        '{"revised_text": string, "rationale": string}. The rationale must cite each conflicting '
        "source by name. Never invent sources."
    )
    user = json.dumps(
        {
            "draft": text,
            "verified_conflicts": [item.model_dump() for item in conflicts],
            "recommendation": recommendation,
            "revision_instruction": instruction,
        }
    )
    raw = llm.generate(system, user, json_mode=True)
    parsed = json.loads(raw)
    revised, rationale = str(parsed["revised_text"]), str(parsed["rationale"])
    if not revised.strip() or not rationale.strip():
        raise ValueError("Empty revision")
    return revised, rationale


@router.post("/revise", response_model=DraftReviseResponse)
def revise_draft(
    payload: DraftReviseRequest,
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    _: None = Depends(require_reviewer),
) -> DraftReviseResponse:
    requester = _requester(authorization, x_user_email)
    owner = requester
    if payload.draft_id:
        existing = draft_store().list_versions(payload.draft_id)
        _ensure_owner_access(existing, requester)
        if existing:
            # Appends (including admin ones) must not transfer ownership.
            owner = _owner_of(existing[-1])
    draft_id = payload.draft_id or str(uuid4())
    pipeline = create_pipeline()
    result = pipeline.run(payload.text, draft=True)
    output = resolution_output(result)
    conflicts = [
        ResolutionFinding(source=item.source, section=item.section, description=item.description)
        for item in output.conflicts
    ]
    try:
        revised, rationale = llm_revision(
            getattr(pipeline, "synthesis_llm", None) or pipeline.llm,
            payload.text, conflicts, output.recommendation, payload.instruction,
        )
    except Exception:
        revised, rationale = deterministic_revision(
            payload.text, conflicts, output.recommendation, payload.instruction,
        )
    version = draft_store().add_version(
        draft_id, revised, rationale, title=payload.title.strip(), owner=owner,
        status=payload.status, source_text=payload.text, instruction=payload.instruction.strip(),
    )
    return DraftReviseResponse(
        draft_id=draft_id,
        version=version.version,
        revised_text=revised,
        rationale=rationale,
        title=version.title,
        owner=version.owner,
        status=version.status,
        overlaps=[
            ResolutionFinding(source=item.source, section=item.section, description=item.description)
            for item in output.overlaps
        ],
        duplicates=[
            ResolutionFinding(source=item.source, section=item.section, description=item.description)
            for item in output.duplicates
        ],
        conflicts=conflicts,
        recommendation=output.recommendation,
        agent_trace=result.agent_trace,
    )


@router.post("/save", response_model=DraftVersion)
def save_draft(
    payload: DraftSaveRequest,
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    _: None = Depends(require_reviewer),
) -> DraftVersion:
    requester = _requester(authorization, x_user_email)
    owner = requester
    if payload.draft_id:
        existing = draft_store().list_versions(payload.draft_id)
        _ensure_owner_access(existing, requester)
        if existing:
            owner = _owner_of(existing[-1])
    return draft_store().add_version(
        payload.draft_id or str(uuid4()), payload.text, "Saved manually.",
        title=payload.title.strip(), owner=owner, status=payload.status,
        source_text=payload.text,
    )


@router.get("", response_model=list[DraftSummary])
def list_drafts(
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    _: None = Depends(require_reviewer),
) -> list[DraftSummary]:
    requester = _requester(authorization, x_user_email)
    summaries = draft_store().list_drafts()
    if requester == ADMIN_EMAIL:
        return summaries
    return [item for item in summaries if (item.owner or "local-reviewer") == requester]


@router.get("/{draft_id}", response_model=DraftSummary)
def get_draft(
    draft_id: str,
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    _: None = Depends(require_reviewer),
) -> DraftSummary:
    versions = draft_store().list_versions(draft_id)
    if not versions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    _ensure_owner_access(versions, _requester(authorization, x_user_email))
    return _summary(versions[-1])


@router.get("/{draft_id}/versions", response_model=list[DraftVersion])
def draft_versions(
    draft_id: str,
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    _: None = Depends(require_reviewer),
) -> list[DraftVersion]:
    versions = draft_store().list_versions(draft_id)
    _ensure_owner_access(versions, _requester(authorization, x_user_email))
    return versions


@router.post("/{draft_id}/restore/{version}", response_model=DraftVersion)
def restore_draft_version(
    draft_id: str,
    version: int,
    payload: DraftRestoreRequest,
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    _: None = Depends(require_reviewer),
) -> DraftVersion:
    versions = draft_store().list_versions(draft_id)
    selected = next((item for item in versions if item.version == version), None)
    if selected is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft version not found")
    requester = _requester(authorization, x_user_email)
    _ensure_owner_access(versions, requester)
    latest = versions[-1]
    owner = _owner_of(latest)
    return draft_store().add_version(
        draft_id, selected.text, f"Restored from version {version}.",
        title=(payload.title or latest.title).strip(), owner=owner, status=latest.status,
        source_text=latest.text, instruction=f"Restore version {version}",
        restored_from_version=version,
    )


@router.get("/{draft_id}/compare", response_model=DraftComparison)
def compare_draft_versions(
    draft_id: str,
    from_version: int = Query(ge=1),
    to_version: int = Query(ge=1),
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    _: None = Depends(require_reviewer),
) -> DraftComparison:
    all_versions = draft_store().list_versions(draft_id)
    _ensure_owner_access(all_versions, _requester(authorization, x_user_email))
    versions = {item.version: item for item in all_versions}
    first, second = versions.get(from_version), versions.get(to_version)
    if first is None or second is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft version not found")
    difference = "".join(unified_diff(
        first.text.splitlines(keepends=True), second.text.splitlines(keepends=True),
        fromfile=f"version-{from_version}", tofile=f"version-{to_version}",
    ))
    return DraftComparison(
        draft_id=draft_id, from_version=from_version, to_version=to_version,
        from_text=first.text, to_text=second.text, unified_diff=difference,
    )
