from __future__ import annotations

import json
from threading import Lock

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
