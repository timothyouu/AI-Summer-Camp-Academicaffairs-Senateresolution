from __future__ import annotations

from typing import Any

from backend.app.agents import factory
from backend.app.agents.factory import create_pipeline


def test_kb_without_strands_is_authoritative_via_bedrock_converse(monkeypatch: Any) -> None:
    """Naming BEDROCK_KB_ID alone must yield real generation, even with no Strands.

    Regression for the two-gate tripwire: previously the pipeline stayed local
    (ModuleLLM, whose generate raises) unless Strands was also installed, so a
    KB-only deployment silently produced no synthesized answers.
    """
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-123")
    monkeypatch.setattr(factory, "strands_available", lambda: False)

    # Avoid constructing a real boto3 client during the unit test.
    sentinel = object()
    monkeypatch.setattr(factory, "BedrockConverseLLM", lambda: sentinel)

    pipeline = create_pipeline()
    assert pipeline.authoritative is True
    assert pipeline.llm is sentinel


def test_kb_with_strands_prefers_strands(monkeypatch: Any) -> None:
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-123")
    monkeypatch.setattr(factory, "strands_available", lambda: True)

    strands_sentinel = object()
    monkeypatch.setattr(factory, "StrandsLLM", lambda: strands_sentinel)

    pipeline = create_pipeline()
    assert pipeline.authoritative is True
    assert pipeline.llm is strands_sentinel


def test_no_kb_stays_local_and_non_authoritative(monkeypatch: Any) -> None:
    monkeypatch.delenv("BEDROCK_KB_ID", raising=False)
    pipeline = create_pipeline()
    assert pipeline.authoritative is False
