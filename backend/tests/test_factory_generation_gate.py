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


def test_no_fast_model_shares_one_llm(monkeypatch: Any) -> None:
    """Without BEDROCK_FAST_MODEL_ID, mechanical and prose LLMs are the same instance."""
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-123")
    monkeypatch.delenv("BEDROCK_FAST_MODEL_ID", raising=False)
    monkeypatch.setattr(factory, "strands_available", lambda: False)

    sentinel = object()
    monkeypatch.setattr(factory, "BedrockConverseLLM", lambda: sentinel)

    pipeline = create_pipeline()
    assert pipeline.llm is sentinel
    assert pipeline.synthesis_llm is sentinel


def test_fast_model_splits_mechanical_from_prose(monkeypatch: Any) -> None:
    """BEDROCK_FAST_MODEL_ID routes mechanical stages to the fast model, prose to the default."""
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-123")
    monkeypatch.setenv("BEDROCK_FAST_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    monkeypatch.setattr(factory, "strands_available", lambda: False)

    # BedrockConverseLLM is constructed twice: fast model (arg) and default (no arg).
    monkeypatch.setattr(factory, "BedrockConverseLLM", lambda model_id=None: ("converse", model_id))

    pipeline = create_pipeline()
    assert pipeline.authoritative is True
    assert pipeline.llm == ("converse", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    assert pipeline.synthesis_llm == ("converse", None)


def test_fast_model_splits_with_strands(monkeypatch: Any) -> None:
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-123")
    monkeypatch.setenv("BEDROCK_FAST_MODEL_ID", "fast-model")
    monkeypatch.setattr(factory, "strands_available", lambda: True)
    monkeypatch.setattr(factory, "StrandsLLM", lambda model_id=None: ("strands", model_id))

    pipeline = create_pipeline()
    assert pipeline.llm == ("strands", "fast-model")
    assert pipeline.synthesis_llm == ("strands", None)
