from __future__ import annotations

import json
import sys
from threading import Lock
from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.agents import AgentPipeline, Claim, ConflictAnalysis, GroundedPassage, span_is_grounded


class RecordingLLM:
    def __init__(self) -> None:
        self.extractor_inputs: list[list[dict[str, object]]] = []
        self._lock = Lock()

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        assert json_mode
        if "blind policy claim extractor" in system:
            passages = json.loads(user)
            with self._lock:
                self.extractor_inputs.append(passages)
            item = passages[0]
            modality = "must_not" if "must not" in item["text"].lower() else "may"
            return json.dumps([{
                "subject": "prior service credit", "modality": modality, "condition": None,
                "value_threshold": "two years", "scope": "tenure clock",
                "citation_span": item["text"], "source": item["source"],
                "section": item["section"], "topic": item["topic"],
            }])
        if "Compare only claims" in system:
            values = json.loads(user)
            return json.dumps([{
                "classification": "contradiction", "typology": "cba_vs_handbook_jurisdiction",
                "topic": values["topic"], "claim_a": values["claims"][0],
                "claim_b": values["claims"][1], "explanation": "The CBA permits credit while the Handbook prohibits it.",
            }])
        return '{"context_valid": true, "confidence": 0.94}'


class MemoryStore:
    def __init__(self) -> None:
        self.created: list[object] = []

    def create_or_get(self, payload: object) -> object:
        self.created.append(payload)
        return payload


def _passages() -> list[GroundedPassage]:
    return [
        GroundedPassage(text="Prior service credit may count for two years on the tenure clock.", span="Prior service credit may count for two years on the tenure clock.", source="Unit 3 CBA", section="13.4", topic="service credit"),
        GroundedPassage(text="Prior service credit must not count for two years on the tenure clock.", span="Prior service credit must not count for two years on the tenure clock.", source="University Handbook", section="304.4.1", topic="service credit"),
    ]


def test_programmatic_span_verification_accepts_real_and_rejects_fabricated_quote() -> None:
    source = "Faculty  may request up to two years of prior-service credit."
    assert span_is_grounded("Faculty may request up to two years of prior-service credit.", source)
    assert not span_is_grounded("Faculty must receive three years of credit.", source)


def test_blind_extractors_receive_only_their_own_source() -> None:
    llm = RecordingLLM()
    result = AgentPipeline(llm=llm, store=MemoryStore()).run("service credit", passages=_passages())
    assert len(result.claims) == 2
    assert len(llm.extractor_inputs) == 2
    assert all(len({item["source"] for item in call}) == 1 for call in llm.extractor_inputs)
    assert {call[0]["source"] for call in llm.extractor_inputs} == {"Unit 3 CBA", "University Handbook"}


def test_scripted_cba_handbook_conflict_is_verified_and_escalated() -> None:
    store = MemoryStore()
    result = AgentPipeline(llm=RecordingLLM(), store=store).run("service-credit tenure-clock calibration", passages=_passages())
    assert result.analyses[0].classification == "contradiction"
    assert result.analyses[0].typology == "cba_vs_handbook_jurisdiction"
    assert result.verified_conflicts[0].accepted
    assert "consult your dean or the Provost's office" in (result.escalation or "")
    assert len(store.created) == 1


class _ArrayVerifierLLM:
    """Simulates a live Bedrock/Claude model that answers the verify step with a
    JSON array instead of the requested ``{context_valid, confidence}`` object.

    json.loads succeeds, so this is not a decode error the pipeline already
    caught — before the fix, ``parsed.get(...)`` raised AttributeError and 500'd
    the request. This shape only appears on the authoritative path; locally
    ``llm.generate`` raises and the deterministic fallback runs instead.
    """

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        assert json_mode
        if "blind policy claim extractor" in system:
            item = json.loads(user)[0]
            modality = "must_not" if "must not" in item["text"].lower() else "may"
            return json.dumps([{
                "subject": "prior service credit", "modality": modality,
                "citation_span": item["text"], "source": item["source"],
                "section": item["section"], "topic": item["topic"],
            }])
        if "Compare only claims" in system:
            values = json.loads(user)
            return json.dumps([{
                "classification": "contradiction", "typology": "direct_contradiction",
                "topic": values["topic"], "claim_a": values["claims"][0],
                "claim_b": values["claims"][1], "explanation": "The claims conflict.",
            }])
        # Deviant shape: array, not the requested object.
        return json.dumps([{"context_valid": True, "confidence": 0.9}])


def test_verifier_survives_non_object_json_from_live_model() -> None:
    result = AgentPipeline(llm=_ArrayVerifierLLM(), store=MemoryStore()).run(
        "service credit", passages=_passages(),
    )
    # The candidate contradiction is detected but cannot be confirmed from a
    # malformed verification response, so it is rejected rather than crashing.
    assert result.analyses[0].classification == "contradiction"
    assert result.verified_conflicts[0].accepted is False
    assert result.verified_conflicts[0].context_valid is False


class _GarbageVerifierLLM(_ArrayVerifierLLM):
    """Simulates a live model answering the verify step with non-JSON prose."""

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        if "Re-read the complete supplied passages" in system:
            return "I believe the conflict is valid, confidence high."
        return super().generate(system, user, json_mode)


def test_verifier_rejects_unparseable_live_response() -> None:
    result = AgentPipeline(llm=_GarbageVerifierLLM(), store=MemoryStore()).run(
        "service credit", passages=_passages(),
    )
    # A live model that cannot produce the requested JSON gives us nothing to
    # confirm with; the conflict must be rejected, not accepted at 0.75 as the
    # local RuntimeError seam is.
    assert result.verified_conflicts[0].accepted is False
    assert result.verified_conflicts[0].context_valid is False
    assert result.verified_conflicts[0].confidence == 0.0


def test_abstains_when_no_grounded_normative_claim_exists() -> None:
    passage = GroundedPassage(text="This section provides historical background.", span="This section provides historical background.", source="History", section="1")
    result = AgentPipeline(store=MemoryStore()).run("unanswered question", passages=[passage])
    assert result.abstained
    assert result.analyses[0].classification == "gap"
    assert not result.verified_conflicts


def test_trace_matches_frontend_contract() -> None:
    result = AgentPipeline(llm=RecordingLLM(), store=MemoryStore()).run("service credit", passages=_passages())
    expected = ["orchestrator", "retrieval", "extractor", "conflict", "verifier", "escalation"]
    assert [step.agent for step in result.agent_trace] == expected
    allowed_statuses = {"pending", "running", "complete", "warning", "failed"}
    for step in result.agent_trace:
        payload = step.model_dump(exclude_none=True)
        assert set(payload) <= {"agent", "label", "status", "detail", "citations"}
        assert payload["status"] in allowed_statuses


def test_strands_message_text_extraction() -> None:
    from backend.app.agents.factory import _message_text

    structured = {"role": "assistant", "content": [{"text": '{"claims": '}, {"text": "[]}"}]}
    assert _message_text(structured) == '{"claims": []}'
    assert _message_text('{"ok": true}') == '{"ok": true}'
    assert _message_text({"role": "assistant", "content": []}) == str({"role": "assistant", "content": []})


def test_strands_adapter_uses_fresh_agent_and_prompt_for_each_invocation(monkeypatch: Any) -> None:
    from backend.app.agents.factory import StrandsLLM

    created: list[dict[str, str]] = []
    model_kwargs: list[dict[str, object]] = []

    class FakeBedrockModel:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            model_kwargs.append(kwargs)

    class FakeAgent:
        def __init__(self, *, model: object, system_prompt: str, **kwargs: object) -> None:
            assert isinstance(model, FakeBedrockModel)
            assert kwargs == {"callback_handler": None, "retry_strategy": None}
            self.system_prompt = system_prompt
            created.append({"system": system_prompt, "user": ""})

        def __call__(self, user: str, **kwargs: object) -> dict[str, object]:
            assert kwargs == {"limits": {"max_turns": 1}}
            created[-1]["user"] = user
            return {"role": "assistant", "content": [{"text": "[]"}]}

    monkeypatch.setitem(sys.modules, "strands", SimpleNamespace(Agent=FakeAgent))
    monkeypatch.setitem(sys.modules, "strands.models", SimpleNamespace(BedrockModel=FakeBedrockModel))
    llm = StrandsLLM()

    client_config = model_kwargs[0]["boto_client_config"]
    assert getattr(client_config, "connect_timeout") == 3
    assert getattr(client_config, "read_timeout") == 20.0
    assert getattr(client_config, "retries") == {"total_max_attempts": 1, "mode": "standard"}

    assert llm.generate("extract source A", "source A", json_mode=True) == "[]"
    assert llm.generate("extract source B", "source B", json_mode=True) == "[]"
    assert created == [
        {"system": "extract source A", "user": "source A"},
        {"system": "extract source B", "user": "source B"},
    ]


def test_strands_adapter_normalizes_max_tokens_error(monkeypatch: Any) -> None:
    from backend.app.agents.factory import StrandsLLM

    class MaxTokensReachedException(Exception):
        pass

    class FakeBedrockModel:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

    class FakeAgent:
        def __init__(self, *, model: object, system_prompt: str, **kwargs: object) -> None:
            del model, system_prompt, kwargs

        def __call__(self, user: str, **kwargs: object) -> object:
            del user, kwargs
            raise MaxTokensReachedException("output token limit reached")

    exceptions = SimpleNamespace(MaxTokensReachedException=MaxTokensReachedException)
    monkeypatch.setitem(sys.modules, "strands", SimpleNamespace(Agent=FakeAgent))
    monkeypatch.setitem(sys.modules, "strands.models", SimpleNamespace(BedrockModel=FakeBedrockModel))
    monkeypatch.setitem(sys.modules, "strands.types.exceptions", exceptions)

    with pytest.raises(RuntimeError, match="output token limit reached") as raised:
        StrandsLLM().generate("system", "user")
    assert isinstance(raised.value.__cause__, MaxTokensReachedException)


def test_strands_adapter_normalizes_transport_timeout_and_opens_circuit(monkeypatch: Any) -> None:
    from botocore.exceptions import ReadTimeoutError
    from backend.app.agents.factory import StrandsLLM

    calls = 0

    class FakeBedrockModel:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

    class FakeAgent:
        def __init__(self, *, model: object, system_prompt: str, **kwargs: object) -> None:
            del model, system_prompt, kwargs

        def __call__(self, user: str, **kwargs: object) -> object:
            nonlocal calls
            del user, kwargs
            calls += 1
            raise ReadTimeoutError(endpoint_url="https://bedrock-runtime.us-west-2.amazonaws.com")

    monkeypatch.setitem(sys.modules, "strands", SimpleNamespace(Agent=FakeAgent))
    monkeypatch.setitem(sys.modules, "strands.models", SimpleNamespace(BedrockModel=FakeBedrockModel))
    monkeypatch.setitem(sys.modules, "strands.types.exceptions", SimpleNamespace())

    llm = StrandsLLM(generation_timeout_seconds=0.01)
    with pytest.raises(RuntimeError, match="Read timeout"):
        llm.generate("system", "user")
    with pytest.raises(RuntimeError, match="generation disabled"):
        llm.generate("system", "second user")
    assert calls == 1


def test_strands_adapter_rejects_repeated_guardrail_refusal(monkeypatch: Any) -> None:
    from backend.app.agents.factory import StrandsLLM

    refusal = (
        "I can help you find and understand existing policy, but I can't help with that. "
        "Please contact the appropriate office."
    )

    class FakeBedrockModel:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

    class FakeAgent:
        def __init__(self, *, model: object, system_prompt: str, **kwargs: object) -> None:
            del model, system_prompt, kwargs

        def __call__(self, user: str, **kwargs: object) -> object:
            del user, kwargs
            return {
                "role": "assistant",
                "content": [{"text": refusal}, {"text": refusal}],
            }

    monkeypatch.setitem(sys.modules, "strands", SimpleNamespace(Agent=FakeAgent))
    monkeypatch.setitem(sys.modules, "strands.models", SimpleNamespace(BedrockModel=FakeBedrockModel))
    monkeypatch.setitem(sys.modules, "strands.types.exceptions", SimpleNamespace())

    with pytest.raises(RuntimeError, match="repeated the guardrail refusal"):
        StrandsLLM().generate("system", "user")


def test_strands_adapter_does_not_normalize_programmer_error(monkeypatch: Any) -> None:
    from backend.app.agents.factory import StrandsLLM

    class FakeBedrockModel:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

    class FakeAgent:
        def __init__(self, *, model: object, system_prompt: str, **kwargs: object) -> None:
            del model, system_prompt, kwargs

        def __call__(self, user: str, **kwargs: object) -> object:
            del user, kwargs
            raise TypeError("adapter bug")

    monkeypatch.setitem(sys.modules, "strands", SimpleNamespace(Agent=FakeAgent))
    monkeypatch.setitem(sys.modules, "strands.models", SimpleNamespace(BedrockModel=FakeBedrockModel))
    monkeypatch.setitem(sys.modules, "strands.types.exceptions", SimpleNamespace())

    with pytest.raises(TypeError, match="adapter bug"):
        StrandsLLM().generate("system", "user")


def test_strands_provider_error_uses_pipeline_fallback(monkeypatch: Any) -> None:
    from backend.app.agents.factory import StrandsLLM

    class ModelThrottledException(Exception):
        pass

    class FakeBedrockModel:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

    class FakeAgent:
        def __init__(self, *, model: object, system_prompt: str, **kwargs: object) -> None:
            del model, system_prompt, kwargs

        def __call__(self, user: str, **kwargs: object) -> object:
            del user, kwargs
            raise ModelThrottledException("provider throttled")

    exceptions = SimpleNamespace(ModelThrottledException=ModelThrottledException)
    monkeypatch.setitem(sys.modules, "strands", SimpleNamespace(Agent=FakeAgent))
    monkeypatch.setitem(sys.modules, "strands.models", SimpleNamespace(BedrockModel=FakeBedrockModel))
    monkeypatch.setitem(sys.modules, "strands.types.exceptions", exceptions)

    result = AgentPipeline(llm=StrandsLLM(), store=MemoryStore()).run(
        "service credit", passages=_passages(),
    )

    assert len(result.claims) == 2
    assert result.analyses[0].classification == "contradiction"
    assert result.verified_conflicts[0].accepted is True


def test_aws_pipeline_defaults_to_authoritative_deterministic_mode(monkeypatch: Any) -> None:
    from backend.app import chat
    from backend.app.agents import factory

    provider_constructions = 0

    class UnexpectedStrandsLLM:
        def __init__(self) -> None:
            nonlocal provider_constructions
            provider_constructions += 1

    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.delenv("BEDROCK_GENERATION_ENABLED", raising=False)
    monkeypatch.setattr(factory, "strands_available", lambda: True)
    monkeypatch.setattr(factory, "StrandsLLM", UnexpectedStrandsLLM)

    pipeline = factory.create_pipeline()
    pipeline.store = MemoryStore()
    response = chat._agent_grounded_answer(
        pipeline.run("service credit", passages=_passages()),
        "service credit",
    )

    assert provider_constructions == 0
    assert pipeline.authoritative is True
    assert response.mode == "agent-grounded"
    assert response.citations


def test_aws_pipeline_allows_explicit_strands_opt_in(monkeypatch: Any) -> None:
    from backend.app.agents import factory

    sentinel = RecordingLLM()
    monkeypatch.setenv("BEDROCK_KB_ID", "KB1")
    monkeypatch.setenv("BEDROCK_GENERATION_ENABLED", "true")
    monkeypatch.setattr(factory, "strands_available", lambda: True)
    monkeypatch.setattr(factory, "StrandsLLM", lambda: sentinel)

    pipeline = factory.create_pipeline()

    assert pipeline.authoritative is True
    assert pipeline.llm is sentinel
