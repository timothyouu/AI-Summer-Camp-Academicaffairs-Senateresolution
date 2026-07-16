from __future__ import annotations

import sys
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import drafting
from backend.app.drafting import (
    DynamoDBDraftStore,
    deterministic_revision,
    draft_store,
    draft_versions,
    get_draft,
    list_drafts,
    llm_revision,
    restore_draft_version,
    revise_draft,
    save_draft,
)
from backend.app.main import app
from backend.app.models import (
    DraftReviseRequest,
    DraftRestoreRequest,
    DraftSaveRequest,
    DraftVersion,
    ResolutionFinding,
)
from backend.app.permissions import ADMIN_EMAIL


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
        def add_version(self, draft_id: str, text: str, suggestion: str, **kwargs: Any) -> DraftVersion:
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

    response = revise_draft(DraftReviseRequest(text="Original draft."), None, None)

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
        assert versions.json()[0]["text"] == body["revised_text"]
        assert versions.json()[0]["source_text"] == "Faculty must keep a three-inch binder for WPAF evidence."


def test_save_list_compare_and_restore_workflow() -> None:
    with TestClient(app) as client:
        first = client.post("/api/draft/save", json={
            "title": "Accessible Technology Resolution",
            "text": "Campus websites must pass an accessibility review.",
            "status": "draft",
        })
        assert first.status_code == 200
        draft_id = first.json()["draft_id"]

        second = client.post("/api/draft/save", json={
            "draft_id": draft_id,
            "title": "Accessible Technology Resolution",
            "text": "Campus websites must pass an annual accessibility review.",
            "status": "in_review",
        })
        assert second.status_code == 200 and second.json()["version"] == 2

        listed = client.get("/api/draft")
        assert listed.status_code == 200
        summary = next(item for item in listed.json() if item["draft_id"] == draft_id)
        assert summary["latest_version"] == 2
        assert summary["status"] == "in_review"
        assert "annual" in summary["latest_text"]

        compared = client.get(
            f"/api/draft/{draft_id}/compare",
            params={"from_version": 1, "to_version": 2},
        )
        assert compared.status_code == 200
        assert "+Campus websites must pass an annual accessibility review." in compared.json()["unified_diff"]

        restored = client.post(f"/api/draft/{draft_id}/restore/1", json={})
        assert restored.status_code == 200
        assert restored.json()["version"] == 3
        assert restored.json()["restored_from_version"] == 1
        assert restored.json()["text"] == first.json()["text"]


def test_revision_instruction_is_persisted_with_generated_version() -> None:
    with TestClient(app) as client:
        response = client.post("/api/draft/revise", json={
            "title": "Workload Resolution",
            "text": "Faculty may submit workload documentation.",
            "instruction": "Make the requirement less restrictive.",
        })
        assert response.status_code == 200
        body = response.json()
        versions = client.get(f"/api/draft/{body['draft_id']}/versions").json()
        assert versions[-1]["instruction"] == "Make the requirement less restrictive."
        assert versions[-1]["text"] == body["revised_text"]
        assert body["title"] == "Workload Resolution"


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


def test_dynamodb_add_version_copies_new_version_to_s3_when_corpus_bucket_configured(
    monkeypatch: Any,
) -> None:
    """DynamoDBDraftStore.add_version must mirror each new version to S3 once
    CORPUS_BUCKET is configured, without requiring a real boto3 install."""

    class Client:
        def query(self, **_: object) -> dict[str, object]:
            return {"Items": []}

        def put_item(self, **_: object) -> dict[str, object]:
            return {}

    class FakeS3:
        def __init__(self) -> None:
            self.put_calls: list[dict[str, object]] = []

        def put_object(self, **kwargs: object) -> dict[str, object]:
            self.put_calls.append(kwargs)
            return {}

    fake_s3 = FakeS3()

    def fake_boto3_client(service_name: str, **kwargs: object) -> Any:
        assert service_name == "s3"
        assert kwargs.get("region_name") == "us-west-2"
        return fake_s3

    monkeypatch.setenv("DDB_DRAFTS_TABLE", "DraftVersions")
    monkeypatch.setenv("CORPUS_BUCKET", "policy-corpus")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_boto3_client))

    store = DynamoDBDraftStore(Client())
    version = store.add_version("draft-s3", "Draft body text.", "Saved.")

    assert version.version == 1
    assert len(fake_s3.put_calls) == 1
    call = fake_s3.put_calls[0]
    assert call["Bucket"] == "policy-corpus"
    assert call["Key"] == "drafts/draft-s3/v1.md"
    assert call["Body"] == b"Draft body text."
    assert call["ContentType"] == "text/markdown"


def test_owner_can_access_own_draft_but_other_reviewer_is_forbidden() -> None:
    created = save_draft(
        DraftSaveRequest(text="Original text.", title="Owner Draft"),
        None, "owner-a@campus.edu",
    )
    draft_id = created.draft_id

    # The owner can read and act on their own draft.
    summary = get_draft(draft_id, None, "owner-a@campus.edu")
    assert summary.draft_id == draft_id
    assert [item.version for item in draft_versions(draft_id, None, "owner-a@campus.edu")] == [1]

    # A different reviewer identity is forbidden from every draft-workspace route.
    with pytest.raises(HTTPException) as get_error:
        get_draft(draft_id, None, "other@campus.edu")
    assert get_error.value.status_code == 403

    with pytest.raises(HTTPException) as versions_error:
        draft_versions(draft_id, None, "other@campus.edu")
    assert versions_error.value.status_code == 403

    with pytest.raises(HTTPException) as restore_error:
        restore_draft_version(
            draft_id, created.version, DraftRestoreRequest(), None, "other@campus.edu",
        )
    assert restore_error.value.status_code == 403

    with pytest.raises(HTTPException) as save_error:
        save_draft(
            DraftSaveRequest(draft_id=draft_id, text="Hijack attempt.", title="Owner Draft"),
            None, "other@campus.edu",
        )
    assert save_error.value.status_code == 403

    with pytest.raises(HTTPException) as revise_error:
        revise_draft(
            DraftReviseRequest(text="Hijack revision.", draft_id=draft_id),
            None, "other@campus.edu",
        )
    assert revise_error.value.status_code == 403


def test_admin_can_read_any_users_draft() -> None:
    created = save_draft(
        DraftSaveRequest(text="Admin visibility test.", title="Admin Draft"),
        None, "owner-b@campus.edu",
    )

    summary = get_draft(created.draft_id, None, ADMIN_EMAIL)
    assert summary.draft_id == created.draft_id
    assert [item.version for item in draft_versions(created.draft_id, None, ADMIN_EMAIL)] == [1]


def test_list_drafts_hides_other_users_drafts_from_non_admins() -> None:
    mine = save_draft(DraftSaveRequest(text="Mine.", title="Mine"), None, "owner-c@campus.edu")
    theirs = save_draft(DraftSaveRequest(text="Theirs.", title="Theirs"), None, "owner-d@campus.edu")

    only_mine = list_drafts(None, "owner-c@campus.edu")
    mine_ids = {item.draft_id for item in only_mine}
    assert mine.draft_id in mine_ids
    assert theirs.draft_id not in mine_ids
    assert all(item.owner == "owner-c@campus.edu" for item in only_mine)

    everything = list_drafts(None, ADMIN_EMAIL)
    all_ids = {item.draft_id for item in everything}
    assert {mine.draft_id, theirs.draft_id}.issubset(all_ids)
