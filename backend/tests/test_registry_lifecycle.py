from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models import PermissionUpdate
from backend.app.permissions import ADMIN_EMAIL, permission_store
from backend.app.registry import registry_store, seed_registry_from_corpus
from backend.app.models import SourceUpsert


def test_upsert_and_status_flip() -> None:
    store = registry_store()
    record = store.upsert(SourceUpsert(
        id="unit-3-cba", title="Unit 3 Collective Bargaining Agreement",
        source_type="cba", status="active", canonical_url="https://example.edu/cba",
    ))
    assert record.status == "active"
    flipped = store.set_status("unit-3-cba", "archived")
    assert flipped is not None and flipped.status == "archived"
    assert store.get("unit-3-cba").status == "archived"  # type: ignore[union-attr]


def test_set_status_unknown_source_returns_none() -> None:
    assert registry_store().set_status("nope", "active") is None


def test_sources_endpoint_lists_and_flips() -> None:
    with TestClient(app) as client:
        registry_store().upsert(SourceUpsert(
            id="handbook-2025", title="CSUB University Handbook 2025",
            source_type="handbook", status="active",
        ))
        listed = client.get("/api/sources")
        assert listed.status_code == 200
        assert any(item["id"] == "handbook-2025" for item in listed.json())
        flip = client.post("/api/sources/handbook-2025/status", json={"status": "archived"})
        assert flip.status_code == 200 and flip.json()["status"] == "archived"
        assert client.post("/api/sources/missing/status", json={"status": "active"}).status_code == 404


def test_source_editor_grant_controls_lifecycle_changes() -> None:
    with TestClient(app) as client:
        registry_store().upsert(SourceUpsert(
            id="owned-cba", title="Owned CBA", source_type="cba", status="active",
        ))
        permission_store().grant(
            PermissionUpdate(
                user_email="writer@campus.edu", source_type="cba",
                can_add=False, can_edit=False,
            ),
            granted_by=ADMIN_EMAIL,
        )
        headers = {"X-User-Email": "writer@campus.edu", "X-Role": "reviewer"}
        denied = client.post("/api/sources/owned-cba/status", json={"status": "archived"}, headers=headers)
        assert denied.status_code == 403

        permission_store().grant(
            PermissionUpdate(
                user_email="writer@campus.edu", source_type="cba",
                can_add=False, can_edit=True,
            ),
            granted_by=ADMIN_EMAIL,
        )
        allowed = client.post("/api/sources/owned-cba/status", json={"status": "archived"}, headers=headers)
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "archived"


def test_source_owner_can_change_lifecycle_without_type_grant() -> None:
    with TestClient(app) as client:
        registry_store().upsert(SourceUpsert(
            id="owner-policy", title="Owner Policy", source_type="handbook", status="active",
            owner="owner@campus.edu",
        ))
        response = client.post(
            "/api/sources/owner-policy/status",
            json={"status": "archived"},
            headers={"X-User-Email": "owner@campus.edu", "X-Role": "reviewer"},
        )
        assert response.status_code == 200


def test_employee_cannot_change_source_lifecycle() -> None:
    with TestClient(app) as client:
        registry_store().upsert(SourceUpsert(
            id="employee-policy", title="Employee Policy", source_type="handbook", status="active",
        ))
        response = client.post(
            "/api/sources/employee-policy/status",
            json={"status": "archived"},
            headers={"X-User-Email": "employee@campus.edu", "X-Role": "reviewer"},
        )
        assert response.status_code == 403


def test_employee_catalog_only_lists_active_sources() -> None:
    with TestClient(app) as client:
        registry_store().upsert(SourceUpsert(
            id="employee-active", title="Employee Active", source_type="handbook", status="active",
        ))
        registry_store().upsert(SourceUpsert(
            id="employee-archived", title="Employee Archived", source_type="handbook", status="archived",
        ))
        response = client.get(
            "/api/sources",
            headers={"X-User-Email": "employee@campus.edu"},
        )
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()}
        assert "employee-active" in ids
        assert "employee-archived" not in ids


def test_seed_marks_uploads_archived(tmp_path, monkeypatch) -> None:
    # conftest already isolates POLICY_DATA_ROOT; create one corpus seed and one upload.
    from backend.app.config import CORPUS_DIR, UPLOAD_DIR, ensure_data_directories
    ensure_data_directories()
    (CORPUS_DIR / "synthetic-demo.md").write_text("---\ntitle: Demo Seed\nsource_type: policystat\n---\nBody.", encoding="utf-8")
    (UPLOAD_DIR / "late-upload.md").write_text("---\ntitle: Late Upload\n---\nBody.", encoding="utf-8")
    seed_registry_from_corpus()
    records = {record.id: record for record in registry_store().list()}
    assert records["synthetic-demo"].status == "active"
    assert records["late-upload"].status == "archived"


def test_seed_types_known_corpus_by_taxonomy_not_uploads() -> None:
    # The Handbook/CBA corpus files carry human-readable front matter
    # ("handbook excerpt") or none at all (PDFs); seeding must still type them
    # with the retrieval taxonomy, matching the AWS prepare_corpus mapping,
    # rather than silently degrading everything to "uploads".
    from backend.app.config import CORPUS_DIR, ensure_data_directories
    ensure_data_directories()
    (CORPUS_DIR / "synthetic-handbook-service-credit.md").write_text(
        "---\ntitle: CSUB University Handbook 2025\nsource_type: handbook excerpt\n---\nBody.",
        encoding="utf-8",
    )
    fake_pdf = CORPUS_DIR / "Unit 3 CBA 2022-2026.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 test")
    try:
        seed_registry_from_corpus()
        records = {record.id: record for record in registry_store().list()}
        assert records["synthetic-handbook-service-credit"].source_type == "handbook"
        assert records["unit 3 cba 2022-2026"].source_type == "cba"
    finally:
        # The corpus dir is shared across the session; a truncated PDF left
        # behind would crash later app startups now that lifespan re-indexes.
        fake_pdf.unlink()


def test_seed_preserves_existing_catalog_edition_metadata() -> None:
    from backend.app.config import CORPUS_DIR, ensure_data_directories

    ensure_data_directories()
    catalog_path = CORPUS_DIR / "catalog-2024-policy.md"
    catalog_path.write_text(
        "---\ntitle: Academic Policy (2024 Catalog)\nsource_type: catalog\n---\nBody.",
        encoding="utf-8",
    )
    registry_store().upsert(SourceUpsert(
        id=catalog_path.stem,
        title="Academic Policy (2024 Catalog)",
        source_type="catalog",
        status="active",
        edition_year=2024,
        is_current=False,
    ))

    seed_registry_from_corpus()

    record = registry_store().get(catalog_path.stem)
    assert record is not None
    assert record.edition_year == 2024
    assert record.is_current is False


def test_seed_recovers_catalog_edition_metadata_from_front_matter() -> None:
    from backend.app.config import CORPUS_DIR, ensure_data_directories

    ensure_data_directories()
    catalog_path = CORPUS_DIR / "catalog-2024-recovered.md"
    catalog_path.write_text(
        "---\ntitle: Recovered Policy (2024 Catalog)\nsource_type: catalog\n"
        "edition_year: 2024\nis_current: false\n---\nBody.",
        encoding="utf-8",
    )

    seed_registry_from_corpus()

    record = registry_store().get(catalog_path.stem)
    assert record is not None
    assert record.edition_year == 2024
    assert record.is_current is False
