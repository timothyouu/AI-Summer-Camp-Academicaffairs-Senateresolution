from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
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
    (CORPUS_DIR / "Unit 3 CBA 2022-2026.pdf").write_bytes(b"%PDF-1.4 test")
    seed_registry_from_corpus()
    records = {record.id: record for record in registry_store().list()}
    assert records["synthetic-handbook-service-credit"].source_type == "handbook"
    assert records["unit 3 cba 2022-2026"].source_type == "cba"


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
