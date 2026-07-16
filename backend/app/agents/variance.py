"""Policy-variance layer over the existing conflict pipeline.

This module never re-implements retrieval or verification. It reads a
``PipelineResult`` produced by ``AgentPipeline.run`` and re-labels its output
with a softer, customer-facing "policy variance" vocabulary (lambdaspec.md §7-9).
Every function here is pure and unit-testable with zero AWS; logging degrades to
a CloudWatch warning when the datastore is not ready (lambdaspec.md §11).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from ..models import ConflictCreate
from .schemas import Claim, ConflictAnalysis, GroundedPassage, PipelineResult


logger = logging.getLogger(__name__)


VarianceSeverity = Literal[
    "DIRECT_CONTRADICTION",
    "AUTHORITY_MISMATCH",
    "ELIGIBILITY_MISMATCH",
    "DEADLINE_MISMATCH",
    "NUMERIC_MISMATCH",
    "OMISSION_OF_RIGHT_OR_PROTECTION",
    "TERMINOLOGY_MISMATCH",
]

# Display / log-sort order, most severe first (lambdaspec.md §8).
SEVERITY_ORDER: tuple[VarianceSeverity, ...] = (
    "DIRECT_CONTRADICTION",
    "AUTHORITY_MISMATCH",
    "ELIGIBILITY_MISMATCH",
    "DEADLINE_MISMATCH",
    "NUMERIC_MISMATCH",
    "OMISSION_OF_RIGHT_OR_PROTECTION",
    "TERMINOLOGY_MISMATCH",
)

# Customer-supplied soft phrasing (lambdaspec.md §9). Never says "conflict".
SOFT_SUMMARY = "The available policy sources appear to vary on this point."

# Escalation wording is the PRD's denied-topic string, NOT the customer's
# "Faculty Affairs / Labor Relations" ask, which contradicts the governing PRD
# (lambdaspec.md §9/§15 Q2; resolved in claude-handoff.md §9).
VARIANCE_ESCALATION = (
    "Because this may affect an employment or procedural decision, please "
    "consult your dean, the Provost's office, or the appropriate office."
)

# Authority weight by document type (higher = more authoritative). Derived from
# doc_type only — no LLM pass (lambdaspec.md §6 item 2a). Reviewer-only.
AUTHORITY_RANK: dict[str, int] = {
    "cba": 100,
    "handbook": 60,
    "policystat": 40,
    "catalog": 20,
}
_DEFAULT_AUTHORITY_RANK = 10

# Deadline/time-window markers. Deliberately excludes "year"/"semester"/"term",
# which are common in eligibility/service-credit language and would misfire.
_TIME_PATTERN = re.compile(
    r"\b(day|days|week|weeks|month|months|hour|hours|deadline|extension|timeline)\b"
    r"|additional time",
    re.IGNORECASE,
)


class VarianceItem(BaseModel):
    severity: VarianceSeverity
    topic: str
    source_a: str
    section_a: str = ""
    span_a: str = ""
    authority_rank_a: int = _DEFAULT_AUTHORITY_RANK
    source_b: str
    section_b: str = ""
    span_b: str = ""
    authority_rank_b: int = _DEFAULT_AUTHORITY_RANK
    confidence: float = 0.0
    verified: bool = False
    variance_kind: Literal["contradiction", "variance", "omission"] = "variance"


class VarianceReport(BaseModel):
    question: str
    variance_detected: bool = False
    items: list[VarianceItem] = Field(default_factory=list)
    soft_summary: str = ""
    escalation: str = ""


class _VarianceStore(Protocol):
    def create_or_get(self, payload: ConflictCreate) -> object: ...


def _has_time(claim: Claim | None) -> bool:
    if claim is None:
        return False
    haystack = " ".join(filter(None, (claim.citation_span, claim.value_threshold, claim.topic)))
    return bool(_TIME_PATTERN.search(haystack))


def _numbers(claim: Claim | None) -> list[str]:
    if claim is None:
        return []
    return re.findall(r"\d+(?:\.\d+)?", claim.value_threshold or claim.citation_span or "")


def _eligibility_signal(analysis: ConflictAnalysis) -> bool:
    a, b = analysis.claim_a, analysis.claim_b
    if a is None or b is None:
        return False
    text = " ".join(
        filter(None, (analysis.explanation, a.scope, b.scope, a.citation_span, b.citation_span))
    ).lower()
    if "eligib" in text or "qualif" in text:
        return True
    return bool(a.scope and b.scope and a.scope.strip().casefold() != b.scope.strip().casefold())


def _subjects_differ(a: Claim | None, b: Claim | None) -> bool:
    if a is None or b is None:
        return False
    return a.subject.strip().casefold() != b.subject.strip().casefold()


def classify_severity(analysis: ConflictAnalysis) -> VarianceSeverity:
    """Map a ``ConflictAnalysis`` onto one of the seven severities (lambdaspec.md §8).

    Pure function: no I/O, no AWS. Ordering matters — the typology the pipeline
    already assigns is trusted first, then softer signals (time windows,
    eligibility scope, renamed terms) drive the newer categories.
    """
    a, b = analysis.claim_a, analysis.claim_b

    # Silence-vs-permitted (the customer's headline case): one side grants, the
    # other is absent. A time-window omission reads as a deadline mismatch.
    if analysis.classification == "gap" or a is None or b is None:
        present = a or b
        return "DEADLINE_MISMATCH" if _has_time(present) else "OMISSION_OF_RIGHT_OR_PROTECTION"

    if analysis.typology == "cba_vs_handbook_jurisdiction":
        return "AUTHORITY_MISMATCH"
    if analysis.typology == "direct_contradiction":
        return "DIRECT_CONTRADICTION"
    if analysis.typology == "numeric_mismatch":
        return "DEADLINE_MISMATCH" if (_has_time(a) or _has_time(b)) else "NUMERIC_MISMATCH"

    # typology == "none" | "scope_overlap": lean on softer signals.
    if _has_time(a) or _has_time(b):
        return "DEADLINE_MISMATCH"
    if _eligibility_signal(analysis):
        return "ELIGIBILITY_MISMATCH"
    if analysis.classification == "redundant_overlap" and _subjects_differ(a, b):
        return "TERMINOLOGY_MISMATCH"

    # Fallback for verified contradictions with no distinguishing signal.
    if {a.modality, b.modality} in ({"must", "must_not"}, {"may", "must_not"}):
        return "DIRECT_CONTRADICTION"
    if _numbers(a) and _numbers(b) and _numbers(a) != _numbers(b):
        return "NUMERIC_MISMATCH"
    return "OMISSION_OF_RIGHT_OR_PROTECTION"


def _passage_index(result: PipelineResult) -> dict[str, GroundedPassage]:
    """First passage seen per source, used to derive doc_type / section / span."""
    index: dict[str, GroundedPassage] = {}
    for passage in result.passages:
        index.setdefault(passage.source, passage)
    return index


def _authority_rank(source: str, index: dict[str, GroundedPassage]) -> int:
    passage = index.get(source)
    doc_type = (passage.doc_type if passage else "").casefold()
    return AUTHORITY_RANK.get(doc_type, _DEFAULT_AUTHORITY_RANK)


def _section(claim: Claim, index: dict[str, GroundedPassage]) -> str:
    if claim.section:
        return claim.section
    passage = index.get(claim.source)
    return passage.section if passage else ""


def _build_item(
    severity: VarianceSeverity,
    a: Claim,
    b: Claim,
    index: dict[str, GroundedPassage],
    *,
    topic: str,
    confidence: float,
    verified: bool,
    variance_kind: Literal["contradiction", "variance", "omission"],
) -> VarianceItem:
    return VarianceItem(
        severity=severity,
        topic=topic,
        source_a=a.source,
        section_a=_section(a, index),
        span_a=a.citation_span,
        authority_rank_a=_authority_rank(a.source, index),
        source_b=b.source,
        section_b=_section(b, index),
        span_b=b.citation_span,
        authority_rank_b=_authority_rank(b.source, index),
        confidence=confidence,
        verified=verified,
        variance_kind=variance_kind,
    )


def _omission_items(result: PipelineResult, index: dict[str, GroundedPassage]) -> list[VarianceItem]:
    """Guarded silent-vs-permitted rule (lambdaspec.md §7 Step E, §15 Q5).

    Fire only when one source affirmatively grants something (a ``may`` claim)
    while another source is present on the *same topic* yet extracted no claim
    there. This deliberately does not touch catalog-edition gaps handled by
    retrieval down-ranking — those never reach here as a second live source.
    """
    claim_topics = {(claim.topic or "", claim.source) for claim in result.claims}
    sources_by_topic: dict[str, set[str]] = defaultdict(set)
    for passage in result.passages:
        sources_by_topic[passage.topic or ""].add(passage.source)

    items: list[VarianceItem] = []
    for claim in result.claims:
        if claim.modality != "may":  # only affirmative grants count
            continue
        topic = claim.topic or ""
        for other in sorted(sources_by_topic.get(topic, set())):
            if other == claim.source:
                continue
            if (topic, other) in claim_topics:
                continue  # other source has its own claim -> handled elsewhere
            silent = index.get(other)
            severity: VarianceSeverity = (
                "DEADLINE_MISMATCH" if _has_time(claim) else "OMISSION_OF_RIGHT_OR_PROTECTION"
            )
            items.append(
                VarianceItem(
                    severity=severity,
                    topic=topic,
                    source_a=claim.source,
                    section_a=_section(claim, index),
                    span_a=claim.citation_span,
                    authority_rank_a=_authority_rank(claim.source, index),
                    source_b=other,
                    section_b=silent.section if silent else "",
                    span_b="",
                    authority_rank_b=_authority_rank(other, index),
                    confidence=0.5,
                    verified=False,
                    variance_kind="omission",
                )
            )
    return items


def detect_variance(question: str, result: PipelineResult) -> VarianceReport:
    """Read pipeline output and re-label it as policy variance (lambdaspec.md §7).

    Surfaces accepted verified contradictions plus the guarded omission rule.
    Same-source pairs are ignored; nothing unverified is invented.
    """
    index = _passage_index(result)
    items: list[VarianceItem] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(item: VarianceItem) -> None:
        key = (item.source_a, item.source_b, item.topic)
        mirror = (item.source_b, item.source_a, item.topic)
        if key in seen or mirror in seen:
            return
        seen.add(key)
        items.append(item)

    for verified in result.verified_conflicts:
        if not verified.accepted:
            continue
        analysis = verified.analysis
        a, b = analysis.claim_a, analysis.claim_b
        if a is None or b is None or a.source == b.source:
            continue
        _add(
            _build_item(
                classify_severity(analysis),
                a,
                b,
                index,
                topic=analysis.topic,
                confidence=verified.confidence,
                verified=True,
                variance_kind="contradiction",
            )
        )

    for item in _omission_items(result, index):
        _add(item)

    items.sort(key=lambda value: SEVERITY_ORDER.index(value.severity))
    detected = bool(items)
    return VarianceReport(
        question=question,
        variance_detected=detected,
        items=items,
        soft_summary=SOFT_SUMMARY if detected else "",
        escalation=VARIANCE_ESCALATION if detected else "",
    )


def soft_language(report: VarianceReport, role: str) -> str:
    """Build the user-facing variance text (lambdaspec.md §9).

    Employees get only the soft summary + escalation — never source names,
    section ids, spans, severity labels, or authority ranks. Reviewers get the
    full detail including severity and authority ranking.
    """
    if not report.variance_detected:
        return ""
    if role != "reviewer":
        return f"{report.soft_summary}\n\n{report.escalation}"
    lines = [report.soft_summary, ""]
    for item in report.items:
        lines.append(
            f"[{item.severity}] {item.topic}: "
            f"{item.source_a} ({item.section_a}, authority {item.authority_rank_a}) vs "
            f"{item.source_b} ({item.section_b}, authority {item.authority_rank_b})."
        )
    lines.extend(["", report.escalation])
    return "\n".join(lines)


def log_variance(report: VarianceReport, store: _VarianceStore | None = None) -> list[int | str]:
    """Persist each variance item to the conflict log (lambdaspec.md §10).

    Reuses the idempotent ``conflict_store().create_or_get`` so repeated
    questions about the same variance do not spam the log. A datastore failure
    is swallowed with a warning — a logging failure must never fail the chat
    response (lambdaspec.md §11).
    """
    if not report.variance_detected:
        return []
    if store is None:
        from ..stores import conflict_store

        store = conflict_store()
    ids: list[int | str] = []
    for item in report.items:
        payload = ConflictCreate(
            source_a=item.source_a,
            source_b=item.source_b,
            topic=item.topic,
            description=f"Potential policy variance ({item.severity.replace('_', ' ').lower()}).",
        )
        try:
            record = store.create_or_get(payload)
        except Exception:  # noqa: BLE001 — log-and-continue; chat must still return.
            logger.warning(
                "Variance log write failed for topic %r; continuing without persisting.",
                item.topic,
                exc_info=True,
            )
            continue
        record_id = getattr(record, "id", None)
        if record_id is not None:
            ids.append(record_id)
    return ids
