from __future__ import annotations

from backend.app.agents import Claim, ConflictAnalysis, GroundedPassage, PipelineResult, VerifiedConflict
from backend.app.agents.variance import (
    SOFT_SUMMARY,
    VARIANCE_ESCALATION,
    VarianceReport,
    classify_severity,
    detect_variance,
    log_variance,
    soft_language,
)
from backend.app.chat import _agent_grounded_answer, _local_index_answer, shape_response_for_role
from backend.app.retrieval import INDEX, SearchResult, reload_index


def _claim(
    source: str,
    span: str,
    modality: str = "must",
    *,
    subject: str = "policy subject",
    section: str = "Section 1",
    topic: str = "workload",
    value_threshold: str | None = None,
    scope: str | None = None,
) -> Claim:
    return Claim(
        subject=subject,
        modality=modality,  # type: ignore[arg-type]
        value_threshold=value_threshold,
        scope=scope,
        citation_span=span,
        source=source,
        section=section,
        topic=topic,
    )


def _analysis(
    classification: str,
    claim_a: Claim | None,
    claim_b: Claim | None,
    *,
    typology: str = "none",
    topic: str = "workload",
    explanation: str = "",
) -> ConflictAnalysis:
    return ConflictAnalysis(
        classification=classification,  # type: ignore[arg-type]
        typology=typology,  # type: ignore[arg-type]
        topic=topic,
        claim_a=claim_a,
        claim_b=claim_b,
        explanation=explanation,
    )


class MemoryStore:
    def __init__(self) -> None:
        self.created: list[object] = []

    def create_or_get(self, payload: object) -> object:
        self.created.append(payload)
        from types import SimpleNamespace

        return SimpleNamespace(id=len(self.created))


class RaisingStore:
    def create_or_get(self, payload: object) -> object:
        raise RuntimeError("DynamoDB unavailable")


# --- Severity classification (pure, no AWS) — spec §13 cases 1-7 -------------


def test_classify_direct_contradiction() -> None:
    analysis = _analysis(
        "contradiction",
        _claim("CBA", "Faculty must file the grievance within ten days.", "must"),
        _claim("Handbook", "Faculty must not file the grievance late.", "must_not"),
        typology="direct_contradiction",
    )
    assert classify_severity(analysis) == "DIRECT_CONTRADICTION"


def test_classify_deadline_mismatch_silent_vs_three_months() -> None:
    analysis = _analysis(
        "contradiction",
        _claim("Unit 3 CBA", "No additional time shall be granted for WPAF submission.", "must_not"),
        _claim("Faculty Handbook", "Faculty may request up to three months of additional time.", "may"),
        topic="WPAF submission timeline",
    )
    assert classify_severity(analysis) == "DEADLINE_MISMATCH"


def test_classify_omission_of_right_when_one_source_silent() -> None:
    analysis = _analysis(
        "gap",
        _claim("Faculty Handbook", "Faculty may request a leave of absence for family care.", "may", value_threshold="one semester"),
        None,
        topic="leave",
    )
    assert classify_severity(analysis) == "OMISSION_OF_RIGHT_OR_PROTECTION"


def test_classify_numeric_mismatch() -> None:
    analysis = _analysis(
        "contradiction",
        _claim("Catalog 2024", "Degrees require 120 units.", "must", value_threshold="120 units"),
        _claim("Catalog 2025", "Degrees require 126 units.", "must", value_threshold="126 units"),
        typology="numeric_mismatch",
        topic="degree requirements",
    )
    assert classify_severity(analysis) == "NUMERIC_MISMATCH"


def test_classify_authority_mismatch_cba_vs_handbook() -> None:
    analysis = _analysis(
        "contradiction",
        _claim("Unit 3 CBA", "The President may grant probationary service credit.", "may"),
        _claim("University Handbook", "The department chair must decide service credit.", "must"),
        typology="cba_vs_handbook_jurisdiction",
        topic="service credit",
    )
    assert classify_severity(analysis) == "AUTHORITY_MISMATCH"


def test_classify_terminology_mismatch_same_body_renamed() -> None:
    analysis = _analysis(
        "redundant_overlap",
        _claim("Handbook 2018", "The General Education Committee reviews courses.", "must", subject="General Education Committee"),
        _claim("Handbook 2025", "The General Education and Curriculum Committee reviews courses.", "must", subject="General Education and Curriculum Committee"),
        topic="committees",
    )
    assert classify_severity(analysis) == "TERMINOLOGY_MISMATCH"


def test_classify_eligibility_mismatch() -> None:
    analysis = _analysis(
        "contradiction",
        _claim("CBA", "Only tenured faculty are eligible for sabbatical.", "may", scope="tenured faculty"),
        _claim("Handbook", "All faculty are eligible for sabbatical after six years.", "may", scope="all faculty"),
        topic="sabbatical",
        explanation="The eligibility scope differs across sources.",
    )
    assert classify_severity(analysis) == "ELIGIBILITY_MISMATCH"


# --- detect_variance + report shape -----------------------------------------


def _accepted_result() -> PipelineResult:
    first = _claim("Unit 3 CBA", "Prior service credit may count for two years.", "may", topic="service credit")
    second = _claim("University Handbook", "Prior service credit must not count for two years.", "must_not", topic="service credit")
    analysis = _analysis("contradiction", first, second, typology="cba_vs_handbook_jurisdiction", topic="service credit")
    return PipelineResult(
        passages=[
            GroundedPassage(text=first.citation_span, span=first.citation_span, source="Unit 3 CBA", section="13.4", doc_type="cba", topic="service credit"),
            GroundedPassage(text=second.citation_span, span=second.citation_span, source="University Handbook", section="304.4.1", doc_type="handbook", topic="service credit"),
        ],
        claims=[first, second],
        analyses=[analysis],
        verified_conflicts=[VerifiedConflict(analysis=analysis, span_verified=True, context_valid=True, confidence=0.9, accepted=True)],
    )


def test_detect_variance_reports_accepted_contradiction() -> None:
    report = detect_variance("Does service credit count?", _accepted_result())
    assert report.variance_detected
    assert len(report.items) == 1
    item = report.items[0]
    assert item.severity == "AUTHORITY_MISMATCH"
    assert item.authority_rank_a == 100  # cba
    assert item.authority_rank_b == 60  # handbook


def test_detect_variance_abstains_without_enough_claims() -> None:
    lonely = _claim("Handbook", "This section is historical background.", "must")
    result = PipelineResult(
        passages=[GroundedPassage(text=lonely.citation_span, span=lonely.citation_span, source="Handbook", section="1", topic="workload")],
        claims=[lonely],
        analyses=[_analysis("gap", None, None)],
    )
    report = detect_variance("q", result)
    assert not report.variance_detected
    assert report.items == []


def test_normal_informational_question_reports_no_variance() -> None:
    # Regression for the reported 500 / false positive on a no-variance prompt:
    # "What is the purpose of the University Handbook?" A live model extracts one
    # benign `may` claim from the Handbook; a second source merely has a passage
    # under the same coarse topic but no comparable claim. With < 2 grounded
    # claims this must NOT surface variance, must NOT log, and must NOT add soft
    # language — the answer stays a normal informational answer.
    only_claim = _claim(
        "CSUB University_Handbook_2025",
        "The Handbook may be amended by the Academic Senate.",
        "may",
        topic="senate procedures",
        section="Preface",
    )
    result = PipelineResult(
        passages=[
            GroundedPassage(text=only_claim.citation_span, span=only_claim.citation_span, source="CSUB University_Handbook_2025", section="Preface", doc_type="handbook", topic="senate procedures"),
            GroundedPassage(text="The Agreement governs labor relations terms.", span="The Agreement governs labor relations terms.", source="Unit 3 CBA 2022-2026", section="1", doc_type="cba", topic="senate procedures"),
        ],
        claims=[only_claim],
    )
    store = MemoryStore()
    report = detect_variance("What is the purpose of the University Handbook?", result)
    assert not report.variance_detected
    assert report.items == []
    assert report.soft_summary == ""
    assert report.escalation == ""

    # No variance event is logged.
    assert log_variance(report, store=store) == []
    assert store.created == []

    # The chat response builder returns a normal answer with no conflict object
    # and no soft variance language.
    response = _agent_grounded_answer(result, "What is the purpose of the University Handbook?", store=store)
    assert response.conflict is None
    assert SOFT_SUMMARY not in response.answer
    assert VARIANCE_ESCALATION not in response.answer
    assert store.created == []


def test_detect_variance_ignores_same_source_pair() -> None:
    first = _claim("Handbook", "Faculty may take one semester of leave.", "may", topic="leave")
    second = _claim("Handbook", "Faculty must request leave in writing.", "must", topic="leave")
    analysis = _analysis("contradiction", first, second, typology="direct_contradiction", topic="leave")
    result = PipelineResult(
        passages=[GroundedPassage(text=first.citation_span, span=first.citation_span, source="Handbook", section="1", topic="leave")],
        claims=[first, second],
        analyses=[analysis],
        verified_conflicts=[VerifiedConflict(analysis=analysis, span_verified=True, context_valid=True, confidence=0.9, accepted=True)],
    )
    report = detect_variance("q", result)
    assert not report.variance_detected


def test_detect_variance_surfaces_guarded_omission() -> None:
    # The customer's headline case: the Handbook grants a three-month extension
    # on the WPAF-timeline topic; the CBA is a second grounded source (it has a
    # claim elsewhere) but is silent on that topic. Two grounded claims from two
    # sources satisfy the guardrail, and the silence surfaces as an omission.
    grant = _claim("Faculty Handbook", "Faculty may request up to three months of additional time.", "may", topic="WPAF timeline", value_threshold="three months")
    elsewhere = _claim("Unit 3 CBA", "Sabbatical eligibility requires six years of service.", "must", topic="leave", section="9")
    result = PipelineResult(
        passages=[
            GroundedPassage(text=grant.citation_span, span=grant.citation_span, source="Faculty Handbook", section="App D", doc_type="handbook", topic="WPAF timeline"),
            GroundedPassage(text="The WPAF submission window closes on the posted date.", span="The WPAF submission window closes on the posted date.", source="Unit 3 CBA", section="15", doc_type="cba", topic="WPAF timeline"),
            GroundedPassage(text=elsewhere.citation_span, span=elsewhere.citation_span, source="Unit 3 CBA", section="9", doc_type="cba", topic="leave"),
        ],
        claims=[grant, elsewhere],
    )
    report = detect_variance("Do I get extra time for my WPAF?", result)
    assert report.variance_detected
    assert report.items[0].severity in ("DEADLINE_MISMATCH", "OMISSION_OF_RIGHT_OR_PROTECTION")


# --- soft language -----------------------------------------------------------


def test_soft_summary_matches_approved_phrasing() -> None:
    assert SOFT_SUMMARY == "The available policy sources appear to vary on this point."


def test_variance_escalation_uses_prd_offices_not_faculty_affairs() -> None:
    assert "consult your dean" in VARIANCE_ESCALATION
    assert "the appropriate office" in VARIANCE_ESCALATION
    assert "Faculty Affairs" not in VARIANCE_ESCALATION


def test_soft_language_avoids_aggressive_words() -> None:
    report = detect_variance("Does service credit count?", _accepted_result())
    text = soft_language(report, "employee")
    assert SOFT_SUMMARY in text
    assert VARIANCE_ESCALATION in text
    lowered = text.lower()
    for aggressive in ("conflict", "wrong", "violation", "winner"):
        assert aggressive not in lowered


def test_soft_language_hides_sources_and_authority_from_employees() -> None:
    report = detect_variance("Does service credit count?", _accepted_result())
    text = soft_language(report, "employee")
    assert "Unit 3 CBA" not in text
    assert "University Handbook" not in text
    assert "100" not in text  # authority_rank never leaks to employees


def test_soft_language_gives_reviewers_detail() -> None:
    report = detect_variance("Does service credit count?", _accepted_result())
    text = soft_language(report, "reviewer")
    assert "AUTHORITY_MISMATCH" in text


# --- response shaping via chat (employee vs reviewer) -----------------------


def test_agent_grounded_response_softens_for_employee() -> None:
    response = _agent_grounded_answer(_accepted_result(), "Does service credit count?", store=MemoryStore())
    assert response.conflict is not None and response.conflict.detected
    shaped = shape_response_for_role(response, "employee")
    assert shaped.conflict is not None
    # Conflict attribution, ids, and authority/severity are stripped for employees;
    # cited grounded statements themselves remain (those are normal citations).
    assert shaped.conflict.sources == []
    assert shaped.conflict.conflict_id is None
    assert "AUTHORITY_MISMATCH" not in shaped.conflict.guidance
    assert "authority" not in shaped.conflict.guidance.lower()
    assert "AUTHORITY_MISMATCH" not in shaped.answer


def test_agent_grounded_response_keeps_reviewer_detail() -> None:
    store = MemoryStore()
    response = _agent_grounded_answer(_accepted_result(), "Does service credit count?", store=store)
    assert response.conflict is not None
    assert set(response.conflict.sources) == {"Unit 3 CBA", "University Handbook"}
    assert response.conflict.conflict_id is not None
    assert len(store.created) == 1


# --- final answer assembly (synthesis vs raw chunks) ------------------------


class SynthesizingLLM:
    """Stands in for the pipeline's selected (authoritative) LLM.

    Returns a natural-language summary that quotes none of the grounded spans
    verbatim and never uses agreement/alignment language.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str, json_mode: bool = False) -> str:
        self.calls.append((system, user))
        return (
            "In short, prior service may be recognized toward your review timeline, "
            "but it is not automatic. Confirm the specifics with Faculty Affairs."
        )


def _no_variance_result() -> PipelineResult:
    """One benign grounded claim plus an unrelated second source: no variance."""
    only_claim = _claim(
        "CSUB University_Handbook_2025",
        "The Handbook may be amended by the Academic Senate.",
        "may",
        topic="senate procedures",
        section="Preface",
    )
    return PipelineResult(
        passages=[
            GroundedPassage(text=only_claim.citation_span, span=only_claim.citation_span, source="CSUB University_Handbook_2025", section="Preface", doc_type="handbook", topic="senate procedures"),
        ],
        claims=[only_claim],
    )


def test_no_variance_answer_is_natural_language_not_raw_chunks() -> None:
    llm = SynthesizingLLM()
    response = _agent_grounded_answer(
        _no_variance_result(), "What is the purpose of the University Handbook?",
        store=MemoryStore(), llm=llm,
    )
    # The synthesized summary is used, not the verbatim grounded span.
    assert llm.calls
    assert "In short, prior service may be recognized" in response.answer
    assert "The Handbook may be amended by the Academic Senate." not in response.answer
    assert "Based on the supplied policy sources" not in response.answer


def test_no_variance_answer_has_no_agreement_or_alignment_language() -> None:
    response = _agent_grounded_answer(
        _no_variance_result(), "What is the purpose of the University Handbook?",
        store=MemoryStore(), llm=SynthesizingLLM(),
    )
    assert response.conflict is None
    lowered = response.answer.lower()
    for forbidden in ("both documents agree", "documents align", "sources align", "align", "agree"):
        assert forbidden not in lowered
    # No unsolicited variance/conflict commentary on a normal question.
    assert SOFT_SUMMARY not in response.answer
    assert VARIANCE_ESCALATION not in response.answer


def test_variance_answer_has_no_agreement_or_alignment_language() -> None:
    response = _agent_grounded_answer(
        _accepted_result(), "Does service credit count?",
        store=MemoryStore(), llm=SynthesizingLLM(),
    )
    lowered = response.answer.lower()
    for forbidden in ("both documents agree", "documents align", "sources align", "align", "agree"):
        assert forbidden not in lowered


def test_variance_answer_still_includes_soft_variance_language() -> None:
    response = _agent_grounded_answer(
        _accepted_result(), "Does service credit count?",
        store=MemoryStore(), llm=SynthesizingLLM(),
    )
    assert response.conflict is not None and response.conflict.detected
    assert SOFT_SUMMARY in response.answer
    assert VARIANCE_ESCALATION in response.answer


# --- informational questions (no extracted claims) must still answer --------


def _informational_result() -> PipelineResult:
    """Retrieval succeeds but no normative (must/may) claim is extracted —
    the common shape of an informational question ('what is the purpose of...').
    """
    long_passage = (
        "The University Handbook is the primary reference documenting academic "
        "governance at CSUB, the Academic Senate's role, campus policies, and "
        "personnel procedures for faculty. " * 4
    ).strip()
    return PipelineResult(
        passages=[
            GroundedPassage(text=long_passage, span=long_passage, source="CSUB University Handbook 2025", section="Section 101", doc_type="handbook", topic="governance"),
            GroundedPassage(text="Curriculum review and committee responsibilities are described in the Handbook.", span="x", source="CSUB University Handbook 2025", section="Section 102", doc_type="handbook", topic="governance"),
        ],
        claims=[],  # informational question: no normative claim extracted
    )


def test_informational_question_synthesizes_instead_of_abstaining() -> None:
    llm = SynthesizingLLM()
    response = _agent_grounded_answer(
        _informational_result(), "What is the purpose of the University Handbook?",
        store=MemoryStore(), llm=llm,
    )
    # The claimless path must NOT emit the old abstention message; it synthesizes.
    assert llm.calls
    assert "In short, prior service may be recognized" in response.answer
    assert "could not extract a grounded policy claim" not in response.answer
    assert "abstained" not in response.answer.lower()


def test_informational_question_cites_retrieved_passages() -> None:
    # With no claims, citations fall back to the retrieved passages so the answer
    # still has real sources after it (not instead of it).
    response = _agent_grounded_answer(
        _informational_result(), "What is the purpose of the University Handbook?",
        store=MemoryStore(), llm=SynthesizingLLM(),
    )
    assert len(response.citations) >= 1
    assert response.citations[0].source == "CSUB University Handbook 2025"
    assert response.conflict is None


def test_informational_answer_never_dumps_raw_passage_text() -> None:
    result = _informational_result()
    long_passage = result.passages[0].text
    response = _agent_grounded_answer(
        result, "What is the purpose of the University Handbook?",
        store=MemoryStore(), llm=SynthesizingLLM(),
    )
    assert long_passage not in response.answer


def test_claimless_question_without_llm_returns_safe_message_not_dump() -> None:
    # No generation model (local mode) and no claims: safe message, never a dump.
    from backend.app.chat import _NO_SYNTHESIS_MESSAGE

    result = _informational_result()
    long_passage = result.passages[0].text
    response = _agent_grounded_answer(
        result, "What is the purpose of the University Handbook?",
        store=MemoryStore(), llm=None,
    )
    assert response.answer == _NO_SYNTHESIS_MESSAGE
    assert long_passage not in response.answer


# --- local-index final answer (no raw-chunk dump) --------------------------


_HANDBOOK_CHUNK = (
    "The University Handbook serves as the primary reference for academic "
    "governance, campus policies, procedures, and personnel processes. It "
    "documents which bodies are responsible for university decisions and where "
    "official procedures are recorded. " * 3
).strip()


def _handbook_results() -> list[SearchResult]:
    return [
        SearchResult(
            text=_HANDBOOK_CHUNK, source="University Handbook", section="Section 101",
            doc_type="handbook", page=1, topic="governance", score=0.9,
        ),
        SearchResult(
            text="Unrelated collective bargaining language about FERP work limits.",
            source="Unit 3 CBA", section="Article 29", doc_type="cba", page=2,
            topic="retirement", score=0.4,
        ),
    ]


def test_local_index_answer_never_dumps_raw_chunks_without_llm() -> None:
    # No LLM available (local mode): the answer must be the safe message, not a
    # raw dump, and must not contain the long retrieved chunk text.
    response = _local_index_answer(_handbook_results(), "What is the purpose of the University Handbook?")
    assert "The most relevant supplied policy passages state" not in response.answer
    assert _HANDBOOK_CHUNK not in response.answer
    # Long raw document chunk must not leak into the user-facing answer.
    assert len(response.answer) < len(_HANDBOOK_CHUNK)
    # Citations still appear (after the answer), not instead of it.
    assert response.answer.strip()
    assert len(response.citations) >= 1
    assert response.citations[0].source == "University Handbook"


def test_local_index_answer_has_no_agreement_or_alignment_language() -> None:
    response = _local_index_answer(_handbook_results(), "What is the purpose of the University Handbook?")
    lowered = response.answer.lower()
    for forbidden in ("both documents agree", "documents align", "sources align", "align", "agree"):
        assert forbidden not in lowered
    # A local-index answer never carries variance/conflict commentary.
    assert response.conflict is None


def test_local_index_answer_synthesizes_when_llm_available() -> None:
    response = _local_index_answer(
        _handbook_results(), "What is the purpose of the University Handbook?",
        llm=SynthesizingLLM(),
    )
    assert "In short, prior service may be recognized" in response.answer
    assert "The most relevant supplied policy passages state" not in response.answer
    assert _HANDBOOK_CHUNK not in response.answer


def test_handbook_purpose_question_end_to_end(client) -> None:  # type: ignore[no-untyped-def]
    # The reported regression: this normal informational question must not return
    # a raw-chunk dump beginning with the banned phrase.
    response = client.post("/api/chat", json={"question": "What is the purpose of the University Handbook?"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"].strip()
    assert "The most relevant supplied policy passages state" not in payload["answer"]
    lowered = payload["answer"].lower()
    assert "both documents agree" not in lowered
    assert "documents align" not in lowered


# --- logging -----------------------------------------------------------------


def test_log_variance_is_idempotent_on_repeat() -> None:
    store = MemoryStore()
    report = detect_variance("Does service credit count?", _accepted_result())
    log_variance(report, store=store)
    log_variance(report, store=store)
    # MemoryStore records every call; create_or_get itself is the idempotency
    # boundary in production. Here we assert one item per report was attempted.
    assert len(store.created) == 2
    payloads = {(p.source_a, p.source_b, p.topic, p.description) for p in store.created}  # type: ignore[attr-defined]
    assert len(payloads) == 1  # identical payloads -> store would dedupe


def test_log_variance_survives_store_failure() -> None:
    report = detect_variance("Does service credit count?", _accepted_result())
    # Must not raise even when the datastore is down (CloudWatch-warn fallback).
    ids = log_variance(report, store=RaisingStore())
    assert ids == []


# --- retrieval breadth (spec §13 case 14a) ----------------------------------


def test_wide_k_returns_multiple_sources_for_variance_path() -> None:
    reload_index()
    if INDEX.size == 0:
        return  # local index not built in this environment; skip breadth guard
    results = INDEX.search("prior service credit tenure", k=12)
    assert len(results) >= 2
