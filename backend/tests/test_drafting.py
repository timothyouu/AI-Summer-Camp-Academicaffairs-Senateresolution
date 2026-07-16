from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from backend.app.drafting import DynamoDBDraftStore, deterministic_revision, draft_store
from backend.app.main import app
from backend.app.models import ResolutionFinding


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
