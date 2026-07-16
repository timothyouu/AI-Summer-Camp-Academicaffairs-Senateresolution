"""Conflict route coverage carried over from the app-memory branch.

The DynamoDB conflict store itself is exercised in test_aws_modes.py and
test_aws_review_fixes.py against the low-level client it actually uses; this
file covers the GET/PATCH-by-id routes that arrived with the app-memory work.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_sqlite_conflict_routes_support_get_and_string_compatible_ids(client: TestClient) -> None:
    created = client.post(
        "/api/conflicts",
        json={
            "source_a": "Test source A",
            "source_b": "Test source B",
            "topic": "Store API test",
            "description": "Verify the SQLite route remains available.",
        },
    )
    assert created.status_code == 201
    conflict_id = created.json()["id"]

    fetched = client.get(f"/api/conflicts/{conflict_id}")
    updated = client.patch(
        f"/api/conflicts/{conflict_id}",
        json={"status": "Resolved", "resolution_note": "Checked in test."},
    )

    assert fetched.status_code == 200
    assert fetched.json()["id"] == conflict_id
    assert updated.status_code == 200
    assert updated.json()["status"] == "Resolved"
    assert client.get("/api/conflicts/not-an-integer").status_code == 404
