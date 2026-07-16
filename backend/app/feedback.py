from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from .auth import require_authenticated, require_reviewer
from .models import FeedbackCreate, FeedbackIssueType, FeedbackRating, FeedbackRecord
from .stores import feedback_store


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackRecord, status_code=status.HTTP_201_CREATED)
def create_feedback(payload: FeedbackCreate, _: None = Depends(require_authenticated)) -> FeedbackRecord:
    return feedback_store().create_feedback(payload)


@router.get("", response_model=list[FeedbackRecord])
def get_feedback(
    rating: FeedbackRating | None = Query(default=None),
    issue_type: FeedbackIssueType | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    _: None = Depends(require_reviewer),
) -> list[FeedbackRecord]:
    return feedback_store().list_feedback(
        rating=rating,
        issue_type=issue_type,
        limit=limit,
    )
