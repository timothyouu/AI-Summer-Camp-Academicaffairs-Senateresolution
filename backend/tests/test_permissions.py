from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models import PermissionUpdate
from backend.app.permissions import ADMIN_EMAIL, permission_store, seed_default_permissions


def test_seed_grants_admin_everything() -> None:
    seed_default_permissions()
    for source_type in ("handbook", "cba", "policystat", "catalog", "uploads"):
        record = permission_store().get(ADMIN_EMAIL, source_type)  # type: ignore[arg-type]
        assert record is not None and record.can_add and record.can_edit


def test_grant_and_list_roundtrip() -> None:
    record = permission_store().grant(
        PermissionUpdate(user_email="colleague@campus.edu", source_type="uploads", can_add=True, can_edit=False),
        granted_by=ADMIN_EMAIL,
    )
    assert record.can_add and not record.can_edit and record.granted_by == ADMIN_EMAIL
    assert any(item.user_email == "colleague@campus.edu" for item in permission_store().list())


def test_permissions_endpoints() -> None:
    with TestClient(app) as client:
        saved = client.put("/api/permissions", json={
            "user_email": "colleague@campus.edu", "source_type": "cba", "can_add": True, "can_edit": True,
        }, headers={"X-User-Email": ADMIN_EMAIL})
        assert saved.status_code == 200
        listed = client.get("/api/permissions")
        assert listed.status_code == 200 and isinstance(listed.json(), list)


def test_employee_identity_cannot_manage_permissions() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/permissions",
            headers={"X-User-Email": "employee@campus.edu"},
        )
        assert response.status_code == 403

        spoofed = client.get(
            "/api/permissions",
            headers={
                "X-User-Email": "employee@campus.edu",
                "X-Role": "reviewer",
            },
        )
        assert spoofed.status_code == 403


def test_upload_denied_without_can_add_identity() -> None:
    with TestClient(app) as client:
        seed_default_permissions()
        response = client.post(
            "/api/upload", files={"file": ("note.md", b"---\ntitle: Note\n---\nBody", "text/markdown")},
            headers={"X-User-Email": "stranger@campus.edu"},
        )
        assert response.status_code == 403


def test_upload_allowed_without_identity_header() -> None:
    # Backwards compatibility: no identity -> no enforcement (frozen tests rely on this).
    with TestClient(app) as client:
        response = client.post(
            "/api/upload", files={"file": ("free.md", b"---\ntitle: Free\n---\nBody", "text/markdown")},
        )
        assert response.status_code == 201
