from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends

from .agents import LLM, create_pipeline, resolution_output
from .auth import require_reviewer
from .dynamodb_client import get_dynamodb_client
from .config import get_settings
from .database import connection, initialize_database
from .models import DraftReviseRequest, DraftReviseResponse, DraftVersion, ResolutionFinding
from .stores import _ddb_decode, _ddb_encode, _ddb_error_code

router = APIRouter(prefix="/api/draft", tags=["drafting"])


def _version(values: dict[str, object]) -> DraftVersion:
    created = values.get("created_at")
    return DraftVersion(
        draft_id=str(values["draft_id"]),
        version=int(values["version"]),  # type: ignore[arg-type]
        text=str(values["text"]),
        suggestion=str(values.get("suggestion", "")),
        created_at=created if isinstance(created, datetime) else datetime.fromisoformat(str(created)),
    )


class DraftStore(Protocol):
    def add_version(self, draft_id: str, text: str, suggestion: str) -> DraftVersion: ...

    def list_versions(self, draft_id: str) -> list[DraftVersion]: ...


class SQLiteDraftStore:
    def __init__(self) -> None:
        # Store methods are also used directly outside the FastAPI lifespan.
        initialize_database()

    def add_version(self, draft_id: str, text: str, suggestion: str) -> DraftVersion:
        with connection() as database:
            row = database.execute(
                "SELECT COALESCE(MAX(version), 0) AS current FROM drafts WHERE draft_id=?", (draft_id,)
            ).fetchone()
            next_version = int(row["current"]) + 1
            database.execute(
                "INSERT INTO drafts(draft_id,version,text,suggestion) VALUES (?,?,?,?)",
                (draft_id, next_version, text, suggestion),
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


class DynamoDBDraftStore:
    def __init__(self, client: object | None = None) -> None:
        settings = get_settings()
        if not settings.ddb_drafts_table:
            raise ValueError("DDB_DRAFTS_TABLE is required")
        if client is None:
            client = get_dynamodb_client(settings)
        self.client = client
        self.table = settings.ddb_drafts_table

    def add_version(self, draft_id: str, text: str, suggestion: str) -> DraftVersion:
        values: dict[str, object] | None = None
        for _attempt in range(5):
            existing = self.list_versions(draft_id)
            next_version = (existing[-1].version + 1) if existing else 1
            values = {
                "draft_id": draft_id,
                "version": next_version,
                "text": text,
                "suggestion": suggestion,
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
        response = self.client.query(  # type: ignore[attr-defined]
            TableName=self.table,
            KeyConditionExpression="draft_id = :draft",
            ExpressionAttributeValues={":draft": {"S": draft_id}},
            ConsistentRead=True,
        )
        return sorted(
            (_version(_ddb_decode(item)) for item in response.get("Items", [])),
            key=lambda value: value.version,
        )


def draft_store() -> DraftStore:
    return DynamoDBDraftStore() if get_settings().drafts_aws else SQLiteDraftStore()


def deterministic_revision(
    text: str, conflicts: list[ResolutionFinding], recommendation: str
) -> tuple[str, str]:
    """LLM-free fallback so the loop works with zero Bedrock access."""
    if not conflicts:
        return text, f"No verified conflict to revise against. {recommendation}"
    notes = "; ".join(f"{item.source} ({item.section}): {item.description}" for item in conflicts)
    revised = (
        f"{text}\n\n[Revision note — reconcile before advancing] "
        f"This draft conflicts with: {notes}"
    )
    return revised, f"Flagged {len(conflicts)} verified conflict(s) for reconciliation: {notes}"


def llm_revision(
    llm: LLM, text: str, conflicts: list[ResolutionFinding], recommendation: str
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
    payload: DraftReviseRequest, _: None = Depends(require_reviewer)
) -> DraftReviseResponse:
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
            pipeline.llm, payload.text, conflicts, output.recommendation
        )
    except Exception:
        revised, rationale = deterministic_revision(payload.text, conflicts, output.recommendation)
    version = draft_store().add_version(draft_id, payload.text, rationale)
    return DraftReviseResponse(
        draft_id=draft_id,
        version=version.version,
        revised_text=revised,
        rationale=rationale,
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


@router.get("/{draft_id}/versions", response_model=list[DraftVersion])
def draft_versions(
    draft_id: str, _: None = Depends(require_reviewer)
) -> list[DraftVersion]:
    return draft_store().list_versions(draft_id)
