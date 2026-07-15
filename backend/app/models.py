from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


Role = Literal["employee", "reviewer"]


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    role: Role
    name: str


class Citation(BaseModel):
    id: int
    source: str
    section: str
    excerpt: str = ""


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)


class ConflictSignal(BaseModel):
    detected: bool
    sources: list[str] = Field(default_factory=list)
    guidance: str = ""
    conflict_id: int | str | None = None


class ChatResponse(BaseModel):
    answer_id: str = Field(default_factory=lambda: str(uuid4()))
    answer: str
    citations: list[Citation]
    conflict: ConflictSignal | None = None
    mode: Literal["local-index", "calibrated-static"] = "local-index"


class ResolutionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)


class ResolutionFinding(BaseModel):
    source: str
    section: str
    description: str


class ResolutionResponse(BaseModel):
    overlaps: list[ResolutionFinding] = Field(default_factory=list)
    duplicates: list[ResolutionFinding] = Field(default_factory=list)
    conflicts: list[ResolutionFinding] = Field(default_factory=list)
    recommendation: str
    mode: Literal["local-index", "calibrated-static"] = "local-index"


class TopicSummary(BaseModel):
    name: str
    count: int


class TopicChunk(BaseModel):
    source: str
    section: str
    excerpt: str


class TopicDetail(BaseModel):
    name: str
    chunks: list[TopicChunk]


ConflictStatus = Literal["Open", "Under review", "Resolved"]
ConflictId = int | str
FeedbackRating = Literal["helpful", "not_helpful"]
FeedbackIssueType = Literal[
    "incorrect", "missing_citation", "unclear", "outdated", "other"
]


class ConflictCreate(BaseModel):
    source_a: str
    source_b: str
    topic: str
    description: str
    status: ConflictStatus = "Open"


class ConflictUpdate(BaseModel):
    status: ConflictStatus | None = None
    resolution_note: str | None = None

    @model_validator(mode="after")
    def has_update(self) -> "ConflictUpdate":
        if self.status is None and self.resolution_note is None:
            raise ValueError("Provide status and/or resolution_note")
        return self


class ConflictRecord(ConflictCreate):
    id: ConflictId
    resolution_note: str = ""
    created_at: datetime
    updated_at: datetime


class FeedbackCreate(BaseModel):
    answer_id: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=4_000)
    rating: FeedbackRating
    comment: str | None = Field(default=None, max_length=4_000)
    issue_type: FeedbackIssueType | None = None
    role: Role | None = None
    citations_used: list[str] = Field(default_factory=list, max_length=50)
    provider: str | None = Field(default=None, max_length=100)


class FeedbackRecord(FeedbackCreate):
    feedback_id: str
    created_at: datetime


class RecurringQuestionRecord(BaseModel):
    question_id: str
    question_text: str
    normalized_text: str
    topic: str = "general"
    ask_count: int
    first_asked_at: datetime
    last_asked_at: datetime
    sample_answer_id: str | None = None
    sample_citations: list[str] = Field(default_factory=list)
    scope: str = "global"
    visibility: str = "published"
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    filename: str
    status: str
    chunks_added: int


class HealthResponse(BaseModel):
    status: str
    index_chunks: int
    provider: str
