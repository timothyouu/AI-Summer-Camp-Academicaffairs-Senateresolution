from __future__ import annotations

from fastapi import APIRouter, Query

from .models import RecurringQuestionRecord
from .stores import get_recurring_question_store


router = APIRouter(prefix="/api/recurring-questions", tags=["recurring questions"])


@router.get("", response_model=list[RecurringQuestionRecord])
def get_recurring_questions(
    topic: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=50),
) -> list[RecurringQuestionRecord]:
    return get_recurring_question_store().list_questions(topic=topic, limit=limit)
