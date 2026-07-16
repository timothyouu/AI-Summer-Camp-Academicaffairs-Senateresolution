from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header

from .agents import GroundedPassage, PipelineResult, create_pipeline
from .agents.pipeline import ESCALATION, LLM
from .agents.variance import detect_variance, log_variance, soft_language
from .auth import request_role, require_authenticated
from .conflicts import create_or_get_conflict
from .models import ChatRequest, ChatResponse, Citation, ConflictCreate, ConflictSignal, Role
from .retrieval import SearchResult, search
from .stores import ConflictStore, recurring_question_store


router = APIRouter(prefix="/api", tags=["chat"])

logger = logging.getLogger(__name__)


EMPLOYEE_CONFLICT_GUIDANCE = (
    "More than one official source addresses this topic and they do not fully agree. "
    "For guidance that applies to your situation, contact your dean or the Provost's office."
)


def resolve_request_role(authorization: str | None, x_role: str | None) -> Role:
    """Cognito claims are authoritative when configured; otherwise trust the demo header.

    The local default is 'reviewer' so existing header-less calls (tests, curl,
    the pre-gating frontend) keep today's full-detail behavior.
    """
    return request_role(authorization, x_role)


def shape_response_for_role(response: ChatResponse, role: Role) -> ChatResponse:
    """Employees get an escalation-oriented message instead of raw conflict detail."""
    if role != "employee" or response.conflict is None or not response.conflict.detected:
        return response
    answer = response.answer.replace(f"\n\n{ESCALATION}", "").replace(f"\n\n{response.conflict.guidance}", "")
    trace = [
        step.model_copy(update={"detail": EMPLOYEE_CONFLICT_GUIDANCE})
        if step.agent == "escalation" and step.status == "warning"
        else step
        for step in response.agent_trace
    ]
    return response.model_copy(update={
        "answer": answer,
        "conflict": ConflictSignal(
            detected=True,
            sources=[],
            guidance=EMPLOYEE_CONFLICT_GUIDANCE,
            conflict_id=None,
        ),
        "agent_trace": trace,
    })


@dataclass(frozen=True)
class CalibratedAnswer:
    terms: tuple[str, ...]
    answer: str
    citations: tuple[tuple[str, str, str], ...]
    conflict: tuple[str, str, str, str] | None = None


CALIBRATED_ANSWERS: tuple[CalibratedAnswer, ...] = (
    CalibratedAnswer(
        ("service credit", "tenure clock", "prior service"),
        "The supplied CSUB University Handbook section 304.4.1 addresses prior-service credit, and Unit 3 CBA Article 13.4 addresses probationary service credit; each refers to up to two years. Credit is not automatic; confirm the written appointment record with Faculty Affairs before calculating a tenure-review date.",
        (
            ("CSUB University Handbook 2025", "Section 304.4.1", "A candidate may request up to two years of credit toward tenure for previous service."),
            ("Unit 3 Collective Bargaining Agreement", "Article 13.4", "The President may grant up to two years of probationary service credit based on qualifying prior experience."),
        ),
    ),
    CalibratedAnswer(
        ("960 hour", "960-hour", "ferp work", "how much can i work"),
        "Two cumulative limits matter. CBA Article 29.8 limits the FERP appointment to one academic term and no more than 90 workdays or 50% of the prior regular timebase. CalPERS separately applies a 960-hour or 50%-of-prior-hours ceiling, whichever is less, across CalPERS employers. Follow the most restrictive applicable limit and confirm the individual appointment with Faculty Affairs and CalPERS.",
        (
            ("Unit 3 Collective Bargaining Agreement", "Article 29.8-29.9", "FERP period-of-employment and timebase limits."),
            ("CalPERS Employment After Retirement", "960-Hour Limit, p. 9", "Retired-annuitant hours are combined across CalPERS employers."),
            ("CSUB FERP FAQs", "FAQs 18 and 21", "Campus guidance dated July 8, 2026; subject to change."),
        ),
    ),
    CalibratedAnswer(
        ("180 day", "waiting period"),
        "CalPERS lists qualifying CSU FERP participation as an exception to the general 180-day waiting period. Separate bona fide separation, age, incentive, and appointment rules may still apply, so confirm the individual facts with CalPERS and Faculty Affairs.",
        (
            ("CalPERS Employment After Retirement", "Eligibility Requirements, pp. 10-11", "FERP is listed among the qualifying exceptions to the general wait."),
            ("CSUB FERP FAQs", "FAQ 20", "Campus guidance dated July 8, 2026; subject to change."),
        ),
    ),
    CalibratedAnswer(
        ("wpaf", "personnel action file", "binder"),
        "The 2025 Handbook Appendix G describes the WPAF contents and organization. Supplied RES 252644 updates paper-era size guidance by emphasizing organized, representative electronic evidence aligned to the review type. Confirm the resolution's adoption/effective metadata before operational use.",
        (
            ("CSUB University Handbook 2025", "Appendix G, pp. 154-158", "Baseline WPAF contents and organization."),
            ("RES 252644", "WPAF Contents and Timelines", "Supplied later resolution replacing physical-binder guidance."),
        ),
        ("CSUB University Handbook Appendix G", "RES 252644", "WPAF evidence format", "Paper-era binder limits conflict with the supplied later electronic-evidence guidance."),
    ),
    CalibratedAnswer(
        ("accessibility", "imap", "instructional technology"),
        "Handbook Appendix K assigns shared accessibility responsibilities. Faculty must make LMS content accessible; Solutions Consulting and the Technology Accessibility Review teams evaluate campus-purchased software and hardware; curriculum-review bodies incorporate accessibility compliance into review and remediation.",
        (
            ("CSUB University Handbook 2025", "Appendix K, Goals 4-6, pp. 153-154", "LMS content, technology review, and curriculum accessibility responsibilities."),
        ),
    ),
    CalibratedAnswer(
        ("gecco", "general education curriculum committee"),
        "The supplied Handbook identifies the GECCo Director as a university-wide faculty director subject to third-year review, but it does not define the committee's complete charge. Use the linked GECCo resource or current Academic Senate committee documentation for the authoritative charge.",
        (
            ("CSUB University Handbook 2025", "Section 313, p. 111", "The GECCo Director is included among university-wide faculty directors and coordinators."),
            ("Foundational Resource List - URLs", "GECCo resource link", "Use the current linked committee resource for the complete charge."),
        ),
    ),
)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _calibrated(question: str) -> CalibratedAnswer | None:
    normalized = _normalize(question)
    for fixture in CALIBRATED_ANSWERS:
        if any(term in normalized for term in fixture.terms):
            return fixture
    return None


def _citations(values: tuple[tuple[str, str, str], ...]) -> list[Citation]:
    return [Citation(id=index, source=source, section=section, excerpt=excerpt) for index, (source, section, excerpt) in enumerate(values, start=1)]


# Shown when no generation model is available to synthesize an answer from the
# retrieved passages. Honest and helpful — never a raw-chunk dump. The retrieved
# sources are still attached as citations after this message.
_NO_SYNTHESIS_MESSAGE = (
    "I found related policy sources but can't confidently summarize an answer here "
    "right now. Please review the cited source sections below, or contact your dean "
    "or the Provost's office for guidance."
)


def _local_index_answer(
    results: list[SearchResult], question: str = "", llm: LLM | None = None,
) -> ChatResponse:
    pipeline = create_pipeline()
    pipeline_result = pipeline.run(
        " ".join(result.topic for result in results[:3]) or "policy question",
        passages=[GroundedPassage(
            text=result.text, span=result.text, source=result.source, section=result.section,
            doc_type=result.doc_type, topic=result.topic, page=result.page,
            canonical_url=result.canonical_url, section_url=result.section_url,
        ) for result in results],
    )
    if not results:
        return ChatResponse(
            answer="The local policy index is empty or has no matching passages. Build the index or ask one of the calibrated demo questions.",
            citations=[],
            mode="local-index",
            agent_trace=pipeline_result.agent_trace,
        )
    selected = results[:3]
    citations = [Citation(
        id=index, source=result.source, section=result.section, excerpt=result.text[:280],
        canonical_url=result.canonical_url, section_url=result.section_url,
    ) for index, result in enumerate(selected, start=1)]
    # Synthesize a natural-language answer from the retrieved passages when a
    # generation model is available; otherwise return a safe, honest message.
    # The user-facing answer is never a raw dump of retrieved chunk text.
    grounded = [
        {"statement": result.text, "source": result.source, "section": result.section}
        for result in selected
    ]
    answer = _synthesize(
        question, grounded, llm if llm is not None else getattr(pipeline, "llm", None),
    )
    return ChatResponse(
        answer=answer or _NO_SYNTHESIS_MESSAGE,
        citations=citations,
        mode="local-index",
        agent_trace=pipeline_result.agent_trace,
    )


_SYNTHESIS_SYSTEM = (
    "You are a university policy assistant. Answer the employee's question in a "
    "helpful, plain-language summary using ONLY the supplied grounded policy "
    "statements. Do not quote passages verbatim; summarize them. Do not invent "
    "facts beyond the statements. Never claim the sources 'agree' or 'align'. "
    "Do not comment on conflicts, variance, or agreement between sources. Return "
    "only the answer prose — sources are cited separately."
)


def _synthesize(question: str, grounded: list[dict[str, str]], llm: LLM | None) -> str | None:
    """Synthesize a natural-language answer from grounded statements via the LLM.

    Returns None when no LLM is available (local mode, where ``generate`` raises
    by design), no grounded material is supplied, or synthesis fails — so callers
    keep their own safe fallback. The LLM must be the pipeline's selected one,
    never the module-level ``llm.generate`` (which always raises; cf. the
    drafting fe4cb1a fix).
    """
    if llm is None or not grounded:
        return None
    payload = {"question": question, "grounded_statements": grounded}
    try:
        answer = llm.generate(_SYNTHESIS_SYSTEM, json.dumps(payload)).strip()
    except Exception:  # noqa: BLE001 — degrade to safe message, but never silently.
        # This is THE failure that produces the safe fallback in production. If it
        # is swallowed without a trace, an operator who has set BEDROCK_KB_ID has
        # no way to tell model-access/region/model-id problems apart from "working
        # as intended". Log the cause (CloudWatch) so the tripwire is diagnosable.
        logger.warning(
            "Answer synthesis via %s failed; returning safe fallback message.",
            type(llm).__name__,
            exc_info=True,
        )
        return None
    return answer or None


def _agent_grounded_answer(
    result: PipelineResult, question: str, store: ConflictStore | None = None,
    llm: LLM | None = None,
) -> ChatResponse:
    claims = result.claims[:6]
    passage_links = {
        (passage.source, passage.section): (passage.canonical_url, passage.section_url)
        for passage in result.passages
    }
    # Citations prefer the verified claim spans; when a purely informational
    # question extracts no normative claim, fall back to the retrieved passages
    # so the answer is still cited with real sources.
    citations = [
        Citation(
            id=index, source=claim.source, section=claim.section, excerpt=claim.citation_span,
            canonical_url=passage_links.get((claim.source, claim.section), ("", ""))[0],
            section_url=passage_links.get((claim.source, claim.section), ("", ""))[1],
        )
        for index, claim in enumerate(claims, start=1)
        if claim.source != "Submitted draft"
    ]
    if not citations:
        citations = [
            Citation(
                id=index, source=passage.source, section=passage.section, excerpt=passage.text[:280],
                canonical_url=passage.canonical_url, section_url=passage.section_url,
            )
            for index, passage in enumerate(result.passages[:3], start=1)
            if passage.source != "Submitted draft"
        ]

    # Answer from the retrieved passages (the full grounded source text), not
    # only from extracted normative claims — informational questions ("what is
    # the purpose of...") rarely yield must/may claims and must still get a
    # helpful synthesized answer rather than an abstention. Conflict detection
    # continues to use claims; this only governs the user-facing prose.
    grounded = [
        {"statement": passage.text, "source": passage.source, "section": passage.section}
        for passage in result.passages if passage.source != "Submitted draft"
    ]
    if grounded:
        answer = _synthesize(question, grounded, llm)
        if answer is None and claims:
            # No generation model (test/local): summarize the short verified claim
            # spans — never a raw passage dump.
            statements = "\n\n".join(
                f"{claim.citation_span} ({claim.source}, {claim.section})"
                for claim in claims if claim.source != "Submitted draft"
            )
            answer = f"Based on the supplied policy sources:\n\n{statements}"
        if answer is None:
            answer = _NO_SYNTHESIS_MESSAGE
    else:
        answer = "No grounded policy sources were retrieved for this question, so no answer could be produced."

    # Re-label the pipeline's verified output with soft "policy variance"
    # language (lambdaspec.md §7-9). The pipeline itself is unchanged.
    report = detect_variance(question, result)
    signal: ConflictSignal | None = None
    if report.variance_detected:
        conflict_ids = log_variance(report, store=store)
        sources = sorted({item.source_a for item in report.items} | {item.source_b for item in report.items})
        signal = ConflictSignal(
            detected=True,
            sources=sources,
            guidance=soft_language(report, "reviewer"),
            conflict_id=conflict_ids[0] if conflict_ids else None,
        )
        answer = f"{answer}\n\n{report.soft_summary}\n\n{report.escalation}"
    elif result.abstained and result.escalation:
        answer = f"{answer}\n\n{result.escalation}"
    return ChatResponse(
        answer=answer,
        citations=citations,
        conflict=signal,
        mode="agent-grounded",
        agent_trace=result.agent_trace,
    )


def _record_recurring_question(question: str, response: ChatResponse) -> None:
    """Persist question frequency without allowing storage failures to affect chat."""
    try:
        recurring_question_store().record_question(
            question_text=question,
            answer_id=response.answer_id,
            citations=[f"{citation.source} — {citation.section}" for citation in response.citations],
        )
    except Exception:
        # Chat answers remain available when optional application-memory storage is offline.
        return


def _attach_registry_links(response: ChatResponse) -> ChatResponse:
    """Resolve calibrated and legacy citations through the shared source registry."""
    from .registry import registry_store

    try:
        records = registry_store().list()
    except Exception:
        return response
    by_title = {record.title.casefold(): record for record in records}
    linked: list[Citation] = []
    for citation in response.citations:
        record = by_title.get(citation.source.casefold())
        if record is None:
            linked.append(citation)
            continue
        canonical_url = citation.canonical_url or record.canonical_url
        section_url = citation.section_url or record.section_index.get(citation.section, "") or canonical_url
        linked.append(citation.model_copy(update={"canonical_url": canonical_url, "section_url": section_url}))
    return response.model_copy(update={"citations": linked})


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    authorization: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    _: None = Depends(require_authenticated),
) -> ChatResponse:
    role = resolve_request_role(authorization, x_role)
    pipeline = create_pipeline()
    if pipeline.authoritative:
        try:
            response = _agent_grounded_answer(
                pipeline.run(payload.question), payload.question, llm=getattr(pipeline, "llm", None),
            )
        except Exception:  # noqa: BLE001 — bounded Bedrock timeout / AWS error.
            # A Bedrock call (retrieval or an agent stage) failed or timed out.
            # Bounded client timeouts turn a former ~5-min hang into a fast error;
            # degrade to the safe message instead of a 500 so the user still gets
            # a coherent response. The cause is logged for diagnosis.
            logger.warning(
                "Authoritative chat pipeline failed for question %r; returning safe message.",
                payload.question[:160],
                exc_info=True,
            )
            response = ChatResponse(
                answer=_NO_SYNTHESIS_MESSAGE, citations=[], mode="agent-grounded",
            )
    else:
        fixture = _calibrated(payload.question)
        if fixture is None:
            # Wide k so both sides of a divergence enter the same result set;
            # a narrow top-k surfaces one source and misses variance (lambdaspec.md §6-7).
            response = _local_index_answer(search(payload.question, k=12), payload.question)
        else:
            pipeline_result = pipeline.run(
                payload.question,
                passages=[GroundedPassage(text=excerpt, span=excerpt, source=source, section=section, topic=payload.question) for source, section, excerpt in fixture.citations],
            )
            signal: ConflictSignal | None = None
            if fixture.conflict is not None:
                source_a, source_b, topic, description = fixture.conflict
                record = create_or_get_conflict(ConflictCreate(source_a=source_a, source_b=source_b, topic=topic, description=description))
                signal = ConflictSignal(
                    detected=True,
                    sources=[source_a, source_b],
                    guidance="Review the later source's adoption/effective status and consult Faculty Affairs before relying on superseded wording.",
                    conflict_id=record.id,
                )
            response = ChatResponse(
                answer=fixture.answer,
                citations=_citations(fixture.citations),
                conflict=signal,
                mode="calibrated-static",
                agent_trace=pipeline_result.agent_trace,
            )
    # Aggregate before role-shaping so a question records the same citations no
    # matter who asked it; only the returned copy is narrowed for employees.
    response = _attach_registry_links(response)
    _record_recurring_question(payload.question, response)
    return shape_response_for_role(response, role)
