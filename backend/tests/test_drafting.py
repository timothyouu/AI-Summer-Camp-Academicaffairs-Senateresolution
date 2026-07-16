from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from backend.app import drafting
from backend.app.drafting import (
    DynamoDBDraftStore,
    deterministic_revision,
    draft_store,
    llm_revision,
    revise_draft,
)
from backend.app.main import app
from backend.app.models import DraftReviseRequest, DraftVersion, ResolutionFinding


def test_version_numbers_increment_per_draft() -> None:
    store = draft_store()
    first = store.add_version("draft-a", "v1 text", "sugg")
    second = store.add_version("draft-a", "v2 text", "sugg2")
    other = store.add_version("draft-b", "other", "")
    assert (first.version, second.version, other.version) == (1, 2, 1)
    assert [item.version for item in store.list_versions("draft-a")] == [1, 2]


def test_deterministic_revision_cites_findings() -> None:
    revised, rationale = deterministic_revision(
        "Faculty must keep a three-inch binder.",
        conflicts=[
            ResolutionFinding(
                source="RES 252644",
                section="WPAF",
                description="Electronic evidence replaces binders.",
            )
        ],
        recommendation="Replace the physical binder limit.",
    )
    assert "RES 252644" in rationale
    assert revised


def test_llm_revision_uses_selected_pipeline_llm() -> None:
    class FakeLLM:
        def generate(self, system: str, user: str, json_mode: bool = False) -> str:
            assert "Return JSON only" in system
            assert json.loads(user)["draft"] == "Original draft."
            assert json_mode is True
            return json.dumps(
                {
                    "revised_text": "Revision produced by Bedrock.",
                    "rationale": "Bedrock rationale citing RES 252644.",
                }
            )

    revised, rationale = llm_revision(
        FakeLLM(),
        "Original draft.",
        [
            ResolutionFinding(
                source="RES 252644",
                section="WPAF",
                description="Electronic evidence replaces binders.",
            )
        ],
        "Replace the physical binder limit.",
    )

    assert revised == "Revision produced by Bedrock."
    assert rationale == "Bedrock rationale citing RES 252644."


def test_revise_draft_falls_back_when_selected_llm_raises(monkeypatch: Any) -> None:
    conflict = ResolutionFinding(
        source="RES 252644",
        section="WPAF",
        description="Electronic evidence replaces binders.",
    )

    class RaisingLLM:
        def generate(self, system: str, user: str, json_mode: bool = False) -> str:
            raise RuntimeError("Local LLM seam")

    class FakePipeline:
        def __init__(self) -> None:
            self.llm = RaisingLLM()

        def run(self, topic: str, *, draft: bool = False) -> SimpleNamespace:
            return SimpleNamespace(agent_trace=[])

    class FakeStore:
        def add_version(self, draft_id: str, text: str, suggestion: str) -> DraftVersion:
            return DraftVersion(
                draft_id=draft_id,
                version=1,
                text=text,
                suggestion=suggestion,
                created_at=datetime.now(timezone.utc),
            )

    def fake_resolution_output(_result: object) -> SimpleNamespace:
        return SimpleNamespace(
            conflicts=[conflict], overlaps=[], duplicates=[], recommendation="Revise it."
        )

    monkeypatch.setattr(drafting, "create_pipeline", FakePipeline)
    monkeypatch.setattr(drafting, "resolution_output", fake_resolution_output)
    monkeypatch.setattr(drafting, "draft_store", FakeStore)

    response = revise_draft(DraftReviseRequest(text="Original draft."), None)

    assert "RES 252644" in response.rationale
    assert "Revision note" in response.revised_text


def test_revise_endpoint_persists_versions() -> None:
    with TestClient(app) as client:
        first = client.post(
            "/api/draft/revise",
            json={"text": "Faculty must keep a three-inch binder for WPAF evidence."},
        )
        assert first.status_code == 200
        body = first.json()
        assert body["version"] == 1 and body["revised_text"] and body["draft_id"]
        second = client.post(
            "/api/draft/revise",
            json={"text": body["revised_text"], "draft_id": body["draft_id"]},
        )
        assert second.status_code == 200 and second.json()["version"] == 2
        versions = client.get(f"/api/draft/{body['draft_id']}/versions")
        assert versions.status_code == 200 and len(versions.json()) == 2


def test_dynamodb_version_allocation_retries_a_concurrent_writer(monkeypatch: Any) -> None:
    class ConditionalCheckFailed(Exception):
        response = {"Error": {"Code": "ConditionalCheckFailedException"}}

    class Client:
        def __init__(self) -> None:
            self.query_calls = 0
            self.put_calls = 0

        def query(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["ConsistentRead"] is True
            self.query_calls += 1
            if self.query_calls == 1:
                return {"Items": []}
            return {"Items": [{
                "draft_id": {"S": "draft-race"},
                "version": {"N": "1"},
                "text": {"S": "concurrent"},
                "suggestion": {"S": ""},
                "created_at": {"S": datetime.now(timezone.utc).isoformat()},
            }]}

        def put_item(self, **_: object) -> dict[str, object]:
            self.put_calls += 1
            if self.put_calls == 1:
                raise ConditionalCheckFailed()
            return {}

    monkeypatch.setenv("DDB_DRAFTS_TABLE", "DraftVersions")
    store = DynamoDBDraftStore(Client())
    version = store.add_version("draft-race", "ours", "retry")
    assert version.version == 2
    assert store.client.put_calls == 2  # type: ignore[attr-defined]
