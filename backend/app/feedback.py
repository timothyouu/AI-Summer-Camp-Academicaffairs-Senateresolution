from __future__ import annotations

from fastapi import APIRouter, Query, status

from .models import FeedbackCreate, FeedbackIssueType, FeedbackRating, FeedbackRecord
from .stores import get_feedback_store


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackRecord, status_code=status.HTTP_201_CREATED)
def create_feedback(payload: FeedbackCreate) -> FeedbackRecord:
    return get_feedback_store().create_feedback(payload)


@router.get("", response_model=list[FeedbackRecord])
def get_feedback(
    rating: FeedbackRating | None = Query(default=None),
    issue_type: FeedbackIssueType | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[FeedbackRecord]:
    return get_feedback_store().list_feedback(
        rating=rating,
        issue_type=issue_type,
        limit=limit,
    )
