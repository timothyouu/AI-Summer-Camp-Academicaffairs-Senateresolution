from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from backend.app.retrieval import SearchResult
from backend.app.topics import TOPIC_TAXONOMY, get_topic, get_topics


def _result(text: str = "Policy passage") -> SearchResult:
    return SearchResult(
        text=text,
        source="University Handbook",
        section="Section 304.4.1",
        doc_type="handbook",
        page=42,
        topic="tenure & promotion",
        score=0.91,
    )


def test_aws_topic_list_returns_fixed_taxonomy(monkeypatch: Any) -> None:
    calls: list[tuple[str, int]] = []

    def stub_search(query: str, k: int) -> list[SearchResult]:
        calls.append((query, k))
        return [_result()] if query == "workload" else []

    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.setattr("backend.app.topics.search", stub_search)

    topics = get_topics()

    assert [topic.name for topic in topics] == list(TOPIC_TAXONOMY)
    assert [topic.count for topic in topics] == [1 if topic == "workload" else 0 for topic in TOPIC_TAXONOMY]
    assert calls == [(topic, 50) for topic in TOPIC_TAXONOMY]


def test_aws_topic_detail_maps_retrieved_passages(monkeypatch: Any) -> None:
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.setattr("backend.app.topics.search", lambda query, k: [_result("x" * 600)])

    detail = get_topic("tenure-promotion")

    assert detail.name == "tenure & promotion"
    assert detail.chunks[0].source == "University Handbook"
    assert detail.chunks[0].section == "Section 304.4.1"
    assert detail.chunks[0].excerpt == "x" * 500


def test_aws_topic_detail_404s_when_retrieval_is_empty(monkeypatch: Any) -> None:
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.setattr("backend.app.topics.search", lambda query, k: [])

    with pytest.raises(HTTPException) as exc_info:
        get_topic("curriculum")

    assert exc_info.value.status_code == 404


def test_local_topic_behavior_still_uses_index(monkeypatch: Any) -> None:
    monkeypatch.delenv("BEDROCK_KB_ID", raising=False)
    monkeypatch.setattr(
        "backend.app.topics.INDEX._chunks",
        [{"topic": "workload", "source": "Handbook", "section": "12", "text": "Local passage"}],
    )
    monkeypatch.setattr(
        "backend.app.topics.search",
        lambda query, k: pytest.fail("local mode must not use the KB search seam"),
    )

    assert get_topics()[0].model_dump() == {"name": "workload", "count": 1}
    assert get_topic("workload").chunks[0].excerpt == "Local passage"
