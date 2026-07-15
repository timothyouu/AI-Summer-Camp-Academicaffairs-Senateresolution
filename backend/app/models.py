from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    conflict_id: int | None = None


class ChatResponse(BaseModel):
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


class ConflictCreate(BaseModel):
    source_a: str
    source_b: str
    topic: str
    description: str
    status: ConflictStatus = "Open"


class ConflictUpdate(BaseModel):
    status: ConflictStatus
    resolution_note: str = ""


class ConflictRecord(ConflictCreate):
    id: int
    resolution_note: str = ""
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    filename: str
    status: str
    chunks_added: int
    upload_url: str | None = None


class HealthResponse(BaseModel):
    status: str
    index_chunks: int
    provider: str
