from __future__ import annotations

from pathlib import Path

from backend.app.ingest import build_chunks, chunk_text
from backend.app.retrieval import INDEX, reload_index


def test_chunk_text_preserves_requested_overlap() -> None:
    words = [f"word-{index}" for index in range(20)]
    chunks = chunk_text(" ".join(words), chunk_words=10, overlap_words=3)
    assert chunks[0].split()[-3:] == chunks[1].split()[:3]
    assert all(len(chunk.split()) <= 10 for chunk in chunks)


def test_build_chunks_carries_front_matter_metadata(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text(
        "---\ntitle: Sample Handbook\nsource_type: handbook\nsection: 304.4.1\n---\nPrior service credit applies to tenure.",
        encoding="utf-8",
    )
    chunks = build_chunks([source])
    assert len(chunks) == 1
    assert chunks[0].source == "Sample Handbook"
    assert chunks[0].section == "304.4.1"
    assert chunks[0].doc_type == "handbook"
    assert chunks[0].topic == "tenure & promotion"


def test_build_chunks_skips_unreadable_files(tmp_path: Path, caplog) -> None:
    # Startup re-indexes the corpus every boot, so a corrupt file (e.g. a
    # truncated PDF) must be skipped with a warning, not crash indexing.
    good = tmp_path / "policy.md"
    good.write_text("---\ntitle: Good Policy\n---\nSabbatical leave requires six years of service.", encoding="utf-8")
    corrupt = tmp_path / "truncated.pdf"
    corrupt.write_bytes(b"%PDF-1.4 truncated garbage")
    with caplog.at_level("WARNING"):
        chunks = build_chunks([corrupt, good])
    assert [chunk.source for chunk in chunks] == ["Good Policy"]
    assert any("truncated.pdf" in record.getMessage() for record in caplog.records)


def test_local_retrieval_returns_known_source(client: object) -> None:
    del client
    reload_index()
    results = INDEX.search("prior service credit tenure", k=3)
    assert results
    assert results[0].source == "Test Policy"
