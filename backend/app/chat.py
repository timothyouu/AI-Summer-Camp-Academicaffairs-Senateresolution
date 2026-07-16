from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import URLError

from fastapi import APIRouter, Depends, Header

from .agents import GroundedPassage, PipelineResult, create_pipeline
from .agents.pipeline import ESCALATION
from .auth import decode_and_verify_token, require_authenticated, role_from_claims
from .config import get_settings
from .conflicts import create_or_get_conflict
from .models import ChatRequest, ChatResponse, Citation, ConflictCreate, ConflictSignal, Role
from .retrieval import SearchResult, search
from .stores import recurring_question_store


router = APIRouter(prefix="/api", tags=["chat"])


EMPLOYEE_CONFLICT_GUIDANCE = (
    "More than one official source addresses this topic and they do not fully agree. "
    "For guidance that applies to your situation, contact your dean or the Provost's office."
)


def resolve_request_role(authorization: str | None, x_role: str | None) -> Role:
    """Cognito claims are authoritative when configured; otherwise trust the demo header.

    The local default is 'reviewer' so existing header-less calls (tests, curl,
    the pre-gating frontend) keep today's full-detail behavior.
    """
    settings = get_settings()
    if settings.cognito_aws and authorization and authorization.startswith("Bearer "):
        try:
            return role_from_claims(decode_and_verify_token(authorization.removeprefix("Bearer ").strip(), settings))
        except (ValueError, URLError, KeyError, json.JSONDecodeError):
            return "employee"
    return "employee" if x_role == "employee" else "reviewer"


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
        "The supplied CSUB University Handbook section 304.4.1 and Unit 3 CBA Article 13.4 align: each permits up to two years of prior-service credit. Credit is not automatic; confirm the written appointment record with Faculty Affairs before calculating a tenure-review date.",
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


def _local_index_answer(results: list[SearchResult]) -> ChatResponse:
    pipeline_result = create_pipeline().run(
        " ".join(result.topic for result in results[:3]) or "policy question",
        passages=[GroundedPassage(text=result.text, span=result.text, source=result.source, section=result.section, doc_type=result.doc_type, topic=result.topic, page=result.page) for result in results],
    )
    if not results:
        return ChatResponse(
            answer="The local policy index is empty or has no matching passages. Build the index or ask one of the calibrated demo questions.",
            citations=[],
            mode="local-index",
            agent_trace=pipeline_result.agent_trace,
        )
    selected = results[:3]
    summary = " ".join(result.text[:360].strip() for result in selected)
    citations = [Citation(id=index, source=result.source, section=result.section, excerpt=result.text[:280]) for index, result in enumerate(selected, start=1)]
    return ChatResponse(
        answer=f"The most relevant supplied policy passages state: {summary}",
        citations=citations,
        mode="local-index",
        agent_trace=pipeline_result.agent_trace,
    )


def _agent_grounded_answer(result: PipelineResult) -> ChatResponse:
    claims = result.claims[:6]
    citations = [
        Citation(id=index, source=claim.source, section=claim.section, excerpt=claim.citation_span)
        for index, claim in enumerate(claims, start=1)
        if claim.source != "Submitted draft"
    ]
    accepted = [item for item in result.verified_conflicts if item.accepted]
    if claims:
        statements = "\n\n".join(
            f"{claim.citation_span} ({claim.source}, {claim.section})"
            for claim in claims if claim.source != "Submitted draft"
        )
        answer = f"The agent pipeline verified these grounded policy statements:\n\n{statements}"
    else:
        answer = "The agent pipeline could not extract a grounded policy claim from the retrieved passages, so it abstained."
    signal: ConflictSignal | None = None
    if accepted:
        sources = sorted({
            claim.source
            for item in accepted
            for claim in (item.analysis.claim_a, item.analysis.claim_b)
            if claim is not None
        })
        guidance = result.escalation or "Multiple grounded answers require human policy review."
        signal = ConflictSignal(detected=True, sources=sources, guidance=guidance)
        answer = f"{answer}\n\n{guidance}"
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
        response = _agent_grounded_answer(pipeline.run(payload.question))
    else:
        fixture = _calibrated(payload.question)
        if fixture is None:
            response = _local_index_answer(search(payload.question, k=6))
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
    _record_recurring_question(payload.question, response)
    return shape_response_for_role(response, role)
