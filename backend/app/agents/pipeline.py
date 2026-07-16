from __future__ import annotations

import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from pydantic import ValidationError

from ..models import AgentTraceStep, Citation, ConflictCreate
from ..retrieval import SearchResult, search
from ..stores import ConflictStore, conflict_store
from .schemas import (
    Claim,
    ConflictAnalysis,
    GroundedPassage,
    PipelineFinding,
    PipelineResult,
    ResolutionPipelineOutput,
    VerifiedConflict,
)
from .verification import span_is_grounded


ESCALATION = "Multiple answers — consult your dean or the Provost's office."


class LLM(Protocol):
    def generate(self, system: str, user: str, json_mode: bool = False) -> str: ...


class ModuleLLM:
    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        from ..llm import generate
        return generate(system, user, json_mode=json_mode)


def _citation(index: int, passage: GroundedPassage) -> Citation:
    return Citation(
        id=index, source=passage.source, section=passage.section, excerpt=passage.span,
        canonical_url=passage.canonical_url, section_url=passage.section_url,
    )


class AgentPipeline:
    """Six-stage pipeline. Extractor calls are source-isolated and may run concurrently."""

    def __init__(
        self, llm: LLM | None = None, store: ConflictStore | None = None, *, authoritative: bool = False,
    ) -> None:
        self.llm = llm or ModuleLLM()
        self.store = store
        self.authoritative = authoritative

    def run(self, topic: str, *, draft: bool = False, passages: list[GroundedPassage] | None = None) -> PipelineResult:
        trace = [AgentTraceStep(agent="orchestrator", label="Plan policy analysis", status="complete", detail=f"Planned {'resolution' if draft else 'question'} analysis for: {topic[:160]}")]
        grounded = passages if passages is not None else self._retrieve(topic)
        citations = [_citation(index, item) for index, item in enumerate(grounded, 1)]
        trace.append(AgentTraceStep(agent="retrieval", label="Retrieve grounded passages", status="complete" if grounded else "warning", detail=f"Retrieved {len(grounded)} verbatim passage(s)." if grounded else "No relevant passages; abstaining.", citations=citations or None))
        analysis_passages = list(grounded)
        if draft:
            analysis_passages.insert(0, GroundedPassage(
                text=topic, span=topic, source="Submitted draft", section="Draft", topic="resolution draft",
            ))
        claims = self._extract_blind(analysis_passages)
        trace.append(AgentTraceStep(agent="extractor", label="Extract source claims independently", status="complete" if claims else "warning", detail=f"Extracted {len(claims)} grounded normative claim(s) from {len({item.source for item in analysis_passages})} isolated source context(s)."))
        analyses = self._detect(topic, claims, draft=draft)
        contradictions = [item for item in analyses if item.classification == "contradiction"]
        trace.append(AgentTraceStep(agent="conflict", label="Compare same-topic claims", status="warning" if contradictions else "complete", detail=self._analysis_detail(analyses)))
        verified = [self._verify(item, analysis_passages) for item in contradictions]
        accepted = [item for item in verified if item.accepted]
        trace.append(AgentTraceStep(agent="verifier", label="Verify quotes and adjudicate context", status="warning" if contradictions and not accepted else "complete", detail=f"Accepted {len(accepted)} of {len(contradictions)} candidate conflict(s); ungrounded claims were rejected."))
        escalation = ESCALATION if accepted or (contradictions and not accepted) else None
        if accepted:
            self._persist(accepted)
        trace.append(AgentTraceStep(agent="escalation", label="Escalate without choosing a winner", status="warning" if escalation else "complete", detail=escalation or "No confirmed conflict required escalation."))
        return PipelineResult(passages=grounded, claims=claims, analyses=analyses, verified_conflicts=verified, abstained=not grounded or not claims or bool(contradictions and not accepted), escalation=escalation, agent_trace=trace)

    @staticmethod
    def _retrieve(topic: str) -> list[GroundedPassage]:
        return [AgentPipeline._passage(item) for item in search(topic, k=10)]

    @staticmethod
    def _passage(item: SearchResult) -> GroundedPassage:
        return GroundedPassage(
            text=item.text, span=item.text, source=item.source, section=item.section,
            doc_type=item.doc_type, topic=item.topic, page=item.page,
            canonical_url=item.canonical_url, section_url=item.section_url,
        )

    def _extract_blind(self, passages: list[GroundedPassage]) -> list[Claim]:
        by_source: dict[str, list[GroundedPassage]] = defaultdict(list)
        for passage in passages:
            by_source[passage.source].append(passage)
        if not by_source:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(by_source))) as executor:
            batches = list(executor.map(self._extract_source, by_source.values()))
        return [claim for batch in batches for claim in batch]

    def _extract_source(self, passages: list[GroundedPassage]) -> list[Claim]:
        payload = [{"text": item.text, "source": item.source, "section": item.section, "topic": item.topic} for item in passages]
        system = "You are one blind policy claim extractor. You see exactly one source. Return JSON array only. Never infer unstated fields. Schema: subject, modality (must|may|must_not), condition, value_threshold, scope, citation_span, source, section, topic. citation_span must quote the supplied source verbatim. Return [] when uncertain."
        try:
            raw = self.llm.generate(system, json.dumps(payload), json_mode=True)
            values = json.loads(raw)
            if not isinstance(values, list):
                return []
            claims = [Claim.model_validate(value) for value in values]
        except (RuntimeError, ValueError, TypeError, json.JSONDecodeError, ValidationError):
            claims = self._deterministic_claims(passages)
        return [claim for claim in claims if any(claim.source == passage.source and claim.section == passage.section and span_is_grounded(claim.citation_span, passage.text) for passage in passages)]

    @staticmethod
    def _deterministic_claims(passages: list[GroundedPassage]) -> list[Claim]:
        claims: list[Claim] = []
        pattern = re.compile(r"\b(must\s+not|shall\s+not|may\s+not|must|shall|required to|may|permitted to)\b", re.I)
        for passage in passages:
            for sentence in re.split(r"(?<=[.!?])\s+", passage.text):
                match = pattern.search(sentence)
                if not match:
                    continue
                token = match.group(1).lower()
                modality = "must_not" if "not" in token else ("may" if token in {"may", "permitted to"} else "must")
                threshold_match = re.search(r"\b(?:up to|no more than|at least|exactly)\s+[^,.;]+", sentence, re.I)
                claims.append(Claim(subject=sentence[:match.start()].strip(" ,:;-") or "policy subject", modality=modality, value_threshold=threshold_match.group(0) if threshold_match else None, citation_span=sentence.strip(), source=passage.source, section=passage.section, topic=passage.topic or None))
        return claims

    def _detect(self, topic: str, claims: list[Claim], *, draft: bool) -> list[ConflictAnalysis]:
        if len(claims) < 2:
            return [ConflictAnalysis(classification="gap", topic=topic, explanation="Fewer than two grounded claims; abstaining.", abstained=True)]
        prompt = {"topic": topic, "draft": draft, "claims": [item.model_dump() for item in claims]}
        try:
            raw = self.llm.generate("Compare only claims on the supplied topic. Return a JSON array using classification agreement|redundant_overlap|contradiction|gap and typology direct_contradiction|numeric_mismatch|scope_overlap|cba_vs_handbook_jurisdiction|none. Include claim_a and claim_b verbatim. Never choose a winner; abstain when uncertain.", json.dumps(prompt), json_mode=True)
            values = json.loads(raw)
            analyses = [ConflictAnalysis.model_validate(value) for value in values] if isinstance(values, list) else []
            grounded_analyses = [item for item in analyses if self._analysis_uses_grounded_claims(item, claims)]
            return grounded_analyses or [ConflictAnalysis(
                classification="gap", topic=topic,
                explanation="Detector returned no grounded cross-source claim pair; abstaining.", abstained=True,
            )]
        except (RuntimeError, ValueError, TypeError, json.JSONDecodeError, ValidationError):
            return self._deterministic_compare(topic, claims)

    @staticmethod
    def _analysis_uses_grounded_claims(analysis: ConflictAnalysis, claims: list[Claim]) -> bool:
        if analysis.classification == "gap":
            return analysis.claim_a is None and analysis.claim_b is None
        if analysis.claim_a is None or analysis.claim_b is None:
            return False
        known = {json.dumps(item.model_dump(), sort_keys=True) for item in claims}
        first = json.dumps(analysis.claim_a.model_dump(), sort_keys=True)
        second = json.dumps(analysis.claim_b.model_dump(), sort_keys=True)
        return first in known and second in known and first != second and analysis.claim_a.source != analysis.claim_b.source

    @staticmethod
    def _deterministic_compare(topic: str, claims: list[Claim]) -> list[ConflictAnalysis]:
        output: list[ConflictAnalysis] = []
        for index, first in enumerate(claims):
            for second in claims[index + 1:]:
                if first.source == second.source:
                    continue
                first_numbers = re.findall(r"\d+(?:\.\d+)?", first.value_threshold or first.citation_span)
                second_numbers = re.findall(r"\d+(?:\.\d+)?", second.value_threshold or second.citation_span)
                opposite = {first.modality, second.modality} in ({"must", "must_not"}, {"may", "must_not"})
                numeric = bool(first_numbers and second_numbers and first_numbers != second_numbers)
                classification = "contradiction" if opposite or numeric else ("agreement" if first.modality == second.modality else "redundant_overlap")
                typology = "numeric_mismatch" if numeric else ("direct_contradiction" if opposite else "none")
                if classification == "contradiction" and {"cba", "handbook"}.issubset({first.source.lower(), second.source.lower()}):
                    typology = "cba_vs_handbook_jurisdiction"
                elif classification == "contradiction" and (("cba" in first.source.lower() and "handbook" in second.source.lower()) or ("handbook" in first.source.lower() and "cba" in second.source.lower())):
                    typology = "cba_vs_handbook_jurisdiction"
                output.append(ConflictAnalysis(classification=classification, typology=typology, topic=topic, claim_a=first, claim_b=second, explanation="Deterministic comparison of modality and explicit thresholds."))
        return output or [ConflictAnalysis(classification="gap", topic=topic, explanation="No cross-source claim pair.", abstained=True)]

    def _verify(self, analysis: ConflictAnalysis, passages: list[GroundedPassage]) -> VerifiedConflict:
        claims = [claim for claim in (analysis.claim_a, analysis.claim_b) if claim is not None]
        grounded = len(claims) == 2 and all(any(claim.source == passage.source and claim.section == passage.section and span_is_grounded(claim.citation_span, passage.text) for passage in passages) for claim in claims)
        context_valid = False
        if grounded:
            try:
                answer = self.llm.generate("Re-read the complete supplied passages. Return JSON {context_valid: boolean, confidence: 0..1}. A conflict is valid only when both quoted claims apply to the same topic and conditions.", json.dumps({"analysis": analysis.model_dump(), "passages": [item.model_dump() for item in passages]}), json_mode=True)
                parsed = json.loads(answer)
                context_valid = parsed.get("context_valid") is True
                confidence = float(parsed.get("confidence", 0.0))
            except (RuntimeError, ValueError, TypeError, json.JSONDecodeError):
                context_valid, confidence = True, 0.75
        else:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        accepted = grounded and context_valid and confidence >= 0.5
        return VerifiedConflict(analysis=analysis, span_verified=grounded, context_valid=context_valid, confidence=confidence, accepted=accepted, reason="Grounded and context-valid." if accepted else "Rejected: quote grounding or full-context validity failed.")

    def _persist(self, conflicts: list[VerifiedConflict]) -> None:
        store = self.store or conflict_store()
        for verified in conflicts:
            analysis = verified.analysis
            if analysis.claim_a is None or analysis.claim_b is None:
                continue
            store.create_or_get(ConflictCreate(source_a=analysis.claim_a.source, source_b=analysis.claim_b.source, topic=analysis.topic, description=analysis.explanation or f"Confirmed {analysis.typology.replace('_', ' ')}."))

    @staticmethod
    def _analysis_detail(analyses: list[ConflictAnalysis]) -> str:
        counts = {kind: sum(item.classification == kind for item in analyses) for kind in ("agreement", "redundant_overlap", "contradiction", "gap")}
        return ", ".join(f"{value} {kind.replace('_', ' ')}" for kind, value in counts.items() if value) or "No comparable claims; abstaining."


def resolution_output(result: PipelineResult) -> ResolutionPipelineOutput:
    """Map grounded draft-vs-policy analyses into the resolution API contract."""
    overlaps: list[PipelineFinding] = []
    duplicates: list[PipelineFinding] = []
    conflicts: list[PipelineFinding] = []
    accepted = {
        json.dumps(item.analysis.model_dump(), sort_keys=True)
        for item in result.verified_conflicts if item.accepted
    }

    for analysis in result.analyses:
        claims = (analysis.claim_a, analysis.claim_b)
        if any(item is None for item in claims):
            continue
        first, second = claims
        assert first is not None and second is not None
        if first.source == "Submitted draft":
            policy_claim = second
        elif second.source == "Submitted draft":
            policy_claim = first
        else:
            continue
        finding = PipelineFinding(
            source=policy_claim.source,
            section=policy_claim.section,
            description=policy_claim.citation_span,
        )
        if analysis.classification == "agreement":
            overlaps.append(finding)
        elif analysis.classification == "redundant_overlap":
            duplicates.append(finding)
        elif (
            analysis.classification == "contradiction"
            and json.dumps(analysis.model_dump(), sort_keys=True) in accepted
        ):
            conflicts.append(finding)

    overlaps = _unique_findings(overlaps)
    duplicates = _unique_findings(duplicates)
    conflicts = _unique_findings(conflicts)
    if conflicts:
        recommendation = result.escalation or ESCALATION
    elif duplicates:
        recommendation = "The draft may duplicate grounded policy language. Review the cited source and amend existing policy where appropriate."
    elif overlaps:
        recommendation = "The draft overlaps grounded policy language. Reconcile it with the cited source before advancing."
    else:
        recommendation = "The agent pipeline found no verified draft-to-policy relationship. Review the cited corpus manually; no policy determination was made."
    return ResolutionPipelineOutput(
        overlaps=overlaps,
        duplicates=duplicates,
        conflicts=conflicts,
        recommendation=recommendation,
        abstained=not (overlaps or duplicates or conflicts),
    )


def _unique_findings(findings: list[PipelineFinding]) -> list[PipelineFinding]:
    unique: dict[tuple[str, str, str], PipelineFinding] = {}
    for finding in findings:
        unique[(finding.source, finding.section, finding.description)] = finding
    return list(unique.values())
