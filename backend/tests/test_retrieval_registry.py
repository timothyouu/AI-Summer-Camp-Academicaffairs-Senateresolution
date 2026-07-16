from __future__ import annotations

from backend.app.models import SourceUpsert
from backend.app.registry import registry_store
from backend.app.retrieval import SearchResult, apply_registry_policy


def _result(source: str, score: float) -> SearchResult:
    return SearchResult(
        text="t", source=source, section="s", doc_type="md", page=None,
        topic="workload", score=score,
    )


def test_archived_sources_are_filtered_out() -> None:
    registry_store().upsert(SourceUpsert(
        id="old-doc", title="Old Doc", source_type="policystat", status="archived",
    ))
    kept = apply_registry_policy([_result("Old Doc", 0.9), _result("Unregistered", 0.5)], k=8)
    assert [item.source for item in kept] == ["Unregistered"]


def test_non_current_edition_is_down_ranked_not_dropped() -> None:
    registry_store().upsert(SourceUpsert(
        id="catalog-2024", title="CSUB Catalog 2024", source_type="catalog",
        status="active", is_current=False, edition_year=2024,
    ))
    registry_store().upsert(SourceUpsert(
        id="catalog-2026", title="CSUB Catalog 2026", source_type="catalog",
        status="active", is_current=True, edition_year=2026,
    ))
    kept = apply_registry_policy(
        [_result("CSUB Catalog 2024", 0.8), _result("CSUB Catalog 2026", 0.6)], k=8,
    )
    assert [item.source for item in kept] == ["CSUB Catalog 2026", "CSUB Catalog 2024"]
    assert kept[1].score == 0.4


def test_registry_adds_canonical_and_section_links() -> None:
    registry_store().upsert(SourceUpsert(
        id="linked-doc", title="Linked Doc", source_type="handbook", status="active",
        canonical_url="https://example.edu/handbook",
        section_index={"Section 4": "https://example.edu/handbook#section-4"},
    ))
    linked = apply_registry_policy([
        SearchResult(
            text="text", source="Linked Doc", section="Section 4", doc_type="handbook",
            page=None, topic="workload", score=0.9,
        ),
    ], k=1)[0]
    assert linked.canonical_url == "https://example.edu/handbook"
    assert linked.section_url == "https://example.edu/handbook#section-4"


def test_bedrock_filename_matches_registry_s3_key() -> None:
    registry_store().upsert(SourceUpsert(
        id="catalog-2024-policy",
        title="Policy (2024 Catalog)",
        source_type="catalog",
        status="archived",
        s3_key="raw/catalog/2024/catalog-2024-policy.md",
    ))
    kept = apply_registry_policy([_result("catalog-2024-policy.md", 0.9)], k=8)
    assert kept == []


def test_k_is_applied_after_filtering() -> None:
    kept = apply_registry_policy([_result(f"Doc {index}", 1.0 - index / 10) for index in range(6)], k=2)
    assert len(kept) == 2
