from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from backend.app.agents.factory import StrandsLLM
from backend.app.config import (
    DEFAULT_BEDROCK_MAX_TOKENS,
    DEFAULT_BEDROCK_MODEL_ID,
    DEFAULT_BEDROCK_STREAMING,
    DEFAULT_BEDROCK_TEMPERATURE,
    get_settings,
)


def test_guardrails_aws_tracks_guardrail_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_GUARDRAIL_ID", raising=False)
    assert get_settings().guardrails_aws is False

    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "guardrail-123")
    assert get_settings().guardrails_aws is True


def test_bedrock_model_defaults_to_scp_compatible_regional_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    assert DEFAULT_BEDROCK_MODEL_ID == "us.anthropic.claude-sonnet-4-6"
    assert get_settings().bedrock_model_id == DEFAULT_BEDROCK_MODEL_ID


def test_bedrock_generation_defaults_are_bounded_and_non_streaming() -> None:
    settings = get_settings()

    assert DEFAULT_BEDROCK_STREAMING is False
    assert DEFAULT_BEDROCK_MAX_TOKENS == 1024
    assert DEFAULT_BEDROCK_TEMPERATURE == 0.0
    assert settings.bedrock_streaming is DEFAULT_BEDROCK_STREAMING
    assert settings.bedrock_max_tokens == DEFAULT_BEDROCK_MAX_TOKENS
    assert settings.bedrock_temperature == DEFAULT_BEDROCK_TEMPERATURE


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
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.test-model")

    llm = StrandsLLM()
    llm.generate("system instructions", "user request")

    assert model_kwargs == [{
        "model_id": "us.test-model",
        "streaming": False,
        "max_tokens": 1024,
        "temperature": 0.0,
        "guardrail_id": "guardrail-123",
        "guardrail_version": "7",
    }]
    assert agent_kwargs == [{"model": llm._bedrock_model, "system_prompt": "system instructions"}]
    assert agent_kwargs[0]["model"] is llm._bedrock_model


def test_strands_llm_without_guardrail_still_pins_regional_model(
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
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.test-model")

    llm = StrandsLLM()
    llm.generate("system instructions", "user request")

    assert model_kwargs == [{
        "model_id": "us.test-model",
        "streaming": False,
        "max_tokens": 1024,
        "temperature": 0.0,
    }]
    assert agent_kwargs == [{"model": llm._bedrock_model, "system_prompt": "system instructions"}]
