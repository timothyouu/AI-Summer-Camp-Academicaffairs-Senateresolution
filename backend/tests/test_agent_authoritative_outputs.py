from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from backend.app import chat, resolution
from backend.app.agents import (
    Claim,
    ConflictAnalysis,
    GroundedPassage,
    PipelineResult,
    VerifiedConflict,
)


def _claim(source: str, section: str, span: str, modality: str = "must") -> Claim:
    return Claim(
        subject="policy use",
        modality=modality,  # type: ignore[arg-type]
        citation_span=span,
        source=source,
        section=section,
        topic="AI policy",
    )


class FakePipeline:
    authoritative = True

    def __init__(self, result: PipelineResult) -> None:
        self.result = result
        self.calls: list[tuple[str, bool]] = []

    def run(self, topic: str, *, draft: bool = False, passages: object = None) -> PipelineResult:
        assert passages is None
        self.calls.append((topic, draft))
        return self.result


def test_aws_chat_returns_grounded_pipeline_answer_and_conflict(client: TestClient, monkeypatch: Any) -> None:
    first = _claim("Unit 3 CBA", "13.4", "Prior service credit may count.", "may")
    second = _claim("University Handbook", "304.4.1", "Prior service credit must not count.", "must_not")
    analysis = ConflictAnalysis(
        classification="contradiction",
        typology="cba_vs_handbook_jurisdiction",
        topic="service credit",
        claim_a=first,
        claim_b=second,
        explanation="The grounded requirements conflict.",
    )
    result = PipelineResult(
        passages=[
            GroundedPassage(text=first.citation_span, span=first.citation_span, source=first.source, section=first.section),
            GroundedPassage(text=second.citation_span, span=second.citation_span, source=second.source, section=second.section),
        ],
        claims=[first, second],
        analyses=[analysis],
        verified_conflicts=[VerifiedConflict(
            analysis=analysis, span_verified=True, context_valid=True, confidence=0.95, accepted=True,
        )],
        escalation="Multiple answers — consult your dean or the Provost's office.",
    )
    pipeline = FakePipeline(result)
    monkeypatch.setattr(chat, "create_pipeline", lambda: pipeline)

    response = client.post("/api/chat", json={"question": "Does service credit count toward tenure?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "agent-grounded"
    assert "Prior service credit may count" in payload["answer"]
    assert payload["conflict"]["detected"] is True
    assert {item["source"] for item in payload["citations"]} == {"Unit 3 CBA", "University Handbook"}
    assert pipeline.calls == [("Does service credit count toward tenure?", False)]


def test_aws_resolution_maps_only_draft_to_policy_pipeline_findings(
    client: TestClient, monkeypatch: Any,
) -> None:
    draft = _claim("Submitted draft", "Draft", "Campus users must disclose AI use.")
    policy = _claim("Existing AI Policy", "Section 2", "Campus users must disclose AI use.")
    analysis = ConflictAnalysis(
        classification="redundant_overlap",
        topic="AI disclosure",
        claim_a=draft,
        claim_b=policy,
        explanation="The submitted requirement duplicates the grounded policy requirement.",
    )
    result = PipelineResult(claims=[draft, policy], analyses=[analysis])
    pipeline = FakePipeline(result)
    monkeypatch.setattr(resolution, "create_pipeline", lambda: pipeline)

    response = client.post("/api/check-resolution", json={"text": "A generative AI policy must require disclosure."})

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "agent-grounded"
    assert payload["overlaps"] == []
    assert payload["conflicts"] == []
    assert payload["duplicates"] == [{
        "source": "Existing AI Policy",
        "section": "Section 2",
        "description": "Campus users must disclose AI use.",
    }]
    assert "duplicate" in payload["recommendation"].lower()
    assert pipeline.calls == [("A generative AI policy must require disclosure.", True)]


def test_detector_rejects_fabricated_overlap_claims() -> None:
    from backend.app.agents import AgentPipeline

    grounded = _claim("Existing Policy", "1", "Campus users must disclose AI use.")
    second_grounded = _claim("Related Guidance", "2", "Campus users must document AI use.")
    fabricated = _claim("Invented Policy", "99", "Campus users must obtain prior approval.")

    class FabricatingLLM:
        def generate(self, system: str, user: str, json_mode: bool = False) -> str:
            assert json_mode
            if "blind policy claim extractor" in system:
                item = json.loads(user)[0]
                return json.dumps([{**grounded.model_dump(), "source": item["source"], "section": item["section"], "citation_span": item["text"]}])
            if "Compare only claims" in system:
                values = json.loads(user)
                return json.dumps([{
                    "classification": "redundant_overlap",
                    "topic": values["topic"],
                    "claim_a": values["claims"][0],
                    "claim_b": fabricated.model_dump(),
                    "explanation": "Fabricated overlap.",
                }])
            return "{}"

    result = AgentPipeline(llm=FabricatingLLM()).run(
        "AI policy",
        passages=[GroundedPassage(
            text=grounded.citation_span,
            span=grounded.citation_span,
            source=grounded.source,
            section=grounded.section,
        ), GroundedPassage(
            text=second_grounded.citation_span,
            span=second_grounded.citation_span,
            source=second_grounded.source,
            section=second_grounded.section,
        )],
    )

    assert result.analyses[0].classification == "gap"
    assert result.analyses[0].abstained
