from __future__ import annotations

import re

from fastapi import APIRouter, Depends

from .agents import GroundedPassage, create_pipeline
from .auth import require_reviewer
from .conflicts import create_or_get_conflict
from .models import ConflictCreate, ResolutionFinding, ResolutionRequest, ResolutionResponse
from .retrieval import search


router = APIRouter(prefix="/api", tags=["resolution review"])


def _finding(source: str, section: str, description: str) -> ResolutionFinding:
    return ResolutionFinding(source=source, section=section, description=description)


@router.post("/check-resolution", response_model=ResolutionResponse)
def check_resolution(payload: ResolutionRequest, _: None = Depends(require_reviewer)) -> ResolutionResponse:
    normalized = re.sub(r"\s+", " ", payload.text.lower())
    retrieved = search(payload.text, k=8)
    pipeline_result = create_pipeline().run(
        payload.text,
        draft=True,
        passages=[GroundedPassage(text=result.text, span=result.text, source=result.source, section=result.section, doc_type=result.doc_type, topic=result.topic, page=result.page) for result in retrieved],
    )
    if any(term in normalized for term in ("generative ai", "artificial intelligence", "large language model")):
        return ResolutionResponse(
            overlaps=[_finding("Senate Resolution 2024-07 (Demo stand-in)", "Section 3", "Existing stand-in guidance already covers human review and disclosure.")],
            duplicates=[_finding("AI Acceptable Use Guidance (Demo stand-in)", "Acceptable use", "The proposed requirements substantially duplicate the calibrated stand-in source.")],
            conflicts=[_finding("Administrative AI Standard (Demo stand-in)", "Section 2", "The stand-in standard additionally requires prior approval for business-process use.")],
            recommendation="Static demo result: amend the disclosed stand-in policy instead of creating a duplicate resolution.",
            mode="calibrated-static",
            agent_trace=pipeline_result.agent_trace,
        )
    if any(term in normalized for term in ("ferp", "retired annuitant", "960 hours", "faculty early retirement")):
        return ResolutionResponse(
            overlaps=[
                _finding("Unit 3 CBA", "Article 29.8-29.9", "The draft overlaps the CBA's period-of-employment and timebase limits."),
                _finding("CalPERS Employment After Retirement", "p. 9", "The draft overlaps the 960-hour and 50%-of-prior-hours rules."),
            ],
            duplicates=[_finding("CSUB FERP FAQs", "FAQs 18, 21, and 26", "Campus guidance already addresses workload and additional employment.")],
            recommendation="State every cumulative limit and require individual confirmation by Faculty Affairs and CalPERS.",
            mode="calibrated-static",
            agent_trace=pipeline_result.agent_trace,
        )
    if "three-inch binder" in normalized or "three inch binder" in normalized:
        conflict = create_or_get_conflict(ConflictCreate(
            source_a="CSUB University Handbook Appendix G",
            source_b="RES 252644",
            topic="WPAF evidence format",
            description="The draft retains paper-era binder guidance that the supplied later resolution replaces with electronic organization.",
        ))
        return ResolutionResponse(
            conflicts=[_finding(conflict.source_b, "WPAF Contents and Timelines", conflict.description)],
            recommendation="Replace the physical binder limit with organized, representative electronic evidence and confirm the resolution's effective metadata.",
            mode="calibrated-static",
            agent_trace=pipeline_result.agent_trace,
        )
    results = retrieved[:5]
    overlaps = [_finding(result.source, result.section, result.text[:300]) for result in results[:3] if result.score > 0]
    return ResolutionResponse(
        overlaps=overlaps,
        recommendation="Review the retrieved local passages before advancing the draft. No generated legal or policy determination was made.",
        mode="local-index",
        agent_trace=pipeline_result.agent_trace,
    )
