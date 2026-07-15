from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import APIRouter

from .conflicts import create_or_get_conflict
from .models import ChatRequest, ChatResponse, Citation, ConflictCreate, ConflictSignal
from .retrieval import SearchResult, search
from .stores import get_recurring_question_store


router = APIRouter(prefix="/api", tags=["chat"])


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
    if not results:
        return ChatResponse(
            answer="The local policy index is empty or has no matching passages. Build the index or ask one of the calibrated demo questions.",
            citations=[],
            mode="local-index",
        )
    selected = results[:3]
    summary = " ".join(result.text[:360].strip() for result in selected)
    citations = [Citation(id=index, source=result.source, section=result.section, excerpt=result.text[:280]) for index, result in enumerate(selected, start=1)]
    return ChatResponse(
        answer=f"The most relevant supplied policy passages state: {summary}",
        citations=citations,
        mode="local-index",
    )


def _record_recurring_question(question: str, response: ChatResponse) -> None:
    """Persist question frequency without allowing storage failures to affect chat."""
    try:
        get_recurring_question_store().record_question(
            question_text=question,
            answer_id=response.answer_id,
            citations=[f"{citation.source} — {citation.section}" for citation in response.citations],
        )
    except Exception:
        # Chat answers remain available when optional application-memory storage is offline.
        return


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    fixture = _calibrated(payload.question)
    if fixture is None:
        response = _local_index_answer(search(payload.question, k=6))
    else:
        signal: ConflictSignal | None = None
        if fixture.conflict is not None:
            source_a, source_b, topic, description = fixture.conflict
            record = create_or_get_conflict(
                ConflictCreate(source_a=source_a, source_b=source_b, topic=topic, description=description),
                origin="chat",
            )
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
        )
    _record_recurring_question(payload.question, response)
    return response
