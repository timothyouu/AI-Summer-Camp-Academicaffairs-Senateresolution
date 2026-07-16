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


AgentName = Literal["orchestrator", "retrieval", "extractor", "conflict", "verifier", "escalation"]
AgentTraceStatus = Literal["pending", "running", "complete", "warning", "failed"]


class AgentTraceStep(BaseModel):
    agent: AgentName
    label: str
    status: AgentTraceStatus
    detail: str | None = None
    citations: list[Citation] | None = None


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
    mode: Literal["local-index", "calibrated-static", "agent-grounded"] = "local-index"
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)


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
    mode: Literal["local-index", "calibrated-static", "agent-grounded"] = "local-index"
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)


class DraftReviseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    draft_id: str | None = None


class DraftVersion(BaseModel):
    draft_id: str
    version: int
    text: str
    suggestion: str = ""
    created_at: datetime


class DraftReviseResponse(BaseModel):
    draft_id: str
    version: int
    revised_text: str
    rationale: str
    overlaps: list[ResolutionFinding] = Field(default_factory=list)
    duplicates: list[ResolutionFinding] = Field(default_factory=list)
    conflicts: list[ResolutionFinding] = Field(default_factory=list)
    recommendation: str
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)


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
    upload_url: str | None = None


IngestionStatus = Literal["pending", "ingesting", "ready", "failed"]


class PresignedUploadRequest(BaseModel):
    filename: str
    content_type: str


class PresignedUploadResponse(BaseModel):
    upload_id: str
    upload_url: str
    headers: dict[str, str] | None = None


class IngestionResponse(BaseModel):
    upload_id: str
    status: IngestionStatus
    chunks_added: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    index_chunks: int
    provider: str


SourceType = Literal["handbook", "cba", "policystat", "catalog", "uploads"]
SourceLifecycleStatus = Literal["active", "archived"]


class PermissionUpdate(BaseModel):
    user_email: str = Field(min_length=3, max_length=254)
    source_type: SourceType
    can_add: bool
    can_edit: bool


class PermissionRecord(PermissionUpdate):
    granted_by: str = ""
    updated_at: datetime


class SourceUpsert(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    title: str
    source_type: SourceType
    status: SourceLifecycleStatus = "archived"
    canonical_url: str = ""
    edition_year: int | None = None
    is_current: bool = True
    s3_key: str = ""
    passages: int = 0


class SourceRecord(SourceUpsert):
    updated_at: datetime


class SourceStatusUpdate(BaseModel):
    status: SourceLifecycleStatus
