from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.chat import EMPLOYEE_CONFLICT_GUIDANCE, resolve_request_role, shape_response_for_role
from backend.app.main import app
from backend.app.models import ChatResponse, Citation, ConflictSignal


def _conflicted_response() -> ChatResponse:
    return ChatResponse(
        answer="Full answer.\n\nMultiple answers — consult your dean or the Provost's office.",
        citations=[Citation(id=1, source="Handbook", section="G", excerpt="…")],
        conflict=ConflictSignal(detected=True, sources=["Handbook", "RES 252644"], guidance="Full reviewer guidance.", conflict_id=7),
    )


def test_default_role_is_reviewer_locally() -> None:
    assert resolve_request_role(None, None) == "reviewer"
    assert resolve_request_role(None, "employee") == "employee"
    assert resolve_request_role(None, "not-a-role") == "reviewer"


def test_reviewer_response_is_untouched() -> None:
    response = _conflicted_response()
    assert shape_response_for_role(response, "reviewer") is response


def test_employee_conflict_is_softened() -> None:
    shaped = shape_response_for_role(_conflicted_response(), "employee")
    assert shaped.conflict is not None and shaped.conflict.detected
    assert shaped.conflict.sources == []
    assert shaped.conflict.conflict_id is None
    assert shaped.conflict.guidance == EMPLOYEE_CONFLICT_GUIDANCE
    assert "Multiple answers — consult" not in shaped.answer
    assert shaped.citations


def test_chat_endpoint_softens_for_employee_header() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"question": "What are the WPAF binder rules?"},
            headers={"X-Role": "employee"},
        )
        assert response.status_code == 200
        body = response.json()
        if body.get("conflict") is not None and body["conflict"]["detected"]:
            assert body["conflict"]["sources"] == []
            assert "contact" in body["conflict"]["guidance"].lower()
