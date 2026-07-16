from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from backend.app.agents.factory import StrandsLLM
from backend.app.config import get_settings


def test_guardrails_aws_tracks_guardrail_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_GUARDRAIL_ID", raising=False)
    assert get_settings().guardrails_aws is False

    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "guardrail-123")
    assert get_settings().guardrails_aws is True


def test_strands_llm_applies_configured_guardrail(monkeypatch: pytest.MonkeyPatch) -> None:
    model_kwargs: list[dict[str, Any]] = []
    agent_kwargs: list[dict[str, Any]] = []

    class FakeBedrockModel:
        def __init__(self, **kwargs: Any) -> None:
            model_kwargs.append(kwargs)

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            agent_kwargs.append(kwargs)

        def __call__(self, user: str) -> str:
            return user

    strands = ModuleType("strands")
    strands.Agent = FakeAgent  # type: ignore[attr-defined]
    models = ModuleType("strands.models")
    models.BedrockModel = FakeBedrockModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "strands", strands)
    monkeypatch.setitem(sys.modules, "strands.models", models)
    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "guardrail-123")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_VERSION", "7")

    llm = StrandsLLM()
    llm.generate("system instructions", "user request")

    assert model_kwargs == [{"guardrail_id": "guardrail-123", "guardrail_version": "7"}]
    assert agent_kwargs == [{"model": llm._bedrock_model, "system_prompt": "system instructions"}]
    assert agent_kwargs[0]["model"] is llm._bedrock_model


def test_strands_llm_without_guardrail_uses_unchanged_agent_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_kwargs: list[dict[str, Any]] = []
    agent_kwargs: list[dict[str, Any]] = []

    class FakeBedrockModel:
        def __init__(self, **kwargs: Any) -> None:
            model_kwargs.append(kwargs)

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            agent_kwargs.append(kwargs)

        def __call__(self, user: str) -> str:
            return user

    strands = ModuleType("strands")
    strands.Agent = FakeAgent  # type: ignore[attr-defined]
    models = ModuleType("strands.models")
    models.BedrockModel = FakeBedrockModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "strands", strands)
    monkeypatch.setitem(sys.modules, "strands.models", models)
    monkeypatch.delenv("BEDROCK_GUARDRAIL_ID", raising=False)
    monkeypatch.delenv("BEDROCK_GUARDRAIL_VERSION", raising=False)

    llm = StrandsLLM()
    llm.generate("system instructions", "user request")

    assert model_kwargs == []
    assert agent_kwargs == [{"system_prompt": "system instructions"}]
