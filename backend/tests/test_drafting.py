from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.drafting import deterministic_revision, draft_store
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
