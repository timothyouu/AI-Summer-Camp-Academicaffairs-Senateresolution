from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..models import AgentTraceStep


Modality = Literal["must", "may", "must_not"]
ConflictKind = Literal["agreement", "redundant_overlap", "contradiction", "gap"]
ConflictTypology = Literal[
    "direct_contradiction", "numeric_mismatch", "scope_overlap", "cba_vs_handbook_jurisdiction", "none",
]


class GroundedPassage(BaseModel):
    text: str
    source: str
    section: str
    span: str
    doc_type: str = "document"
    topic: str = ""
    page: int | None = None


class Claim(BaseModel):
    subject: str
    modality: Modality
    condition: str | None = None
    value_threshold: str | None = None
    scope: str | None = None
    citation_span: str
    source: str
    section: str
    topic: str | None = None


class ConflictAnalysis(BaseModel):
    classification: ConflictKind
    typology: ConflictTypology = "none"
    topic: str
    claim_a: Claim | None = None
    claim_b: Claim | None = None
    explanation: str = ""
    abstained: bool = False


class VerifiedConflict(BaseModel):
    analysis: ConflictAnalysis
    span_verified: bool
    context_valid: bool
    confidence: float = Field(ge=0.0, le=1.0)
    accepted: bool
    reason: str = ""


class PipelineResult(BaseModel):
    passages: list[GroundedPassage] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    analyses: list[ConflictAnalysis] = Field(default_factory=list)
    verified_conflicts: list[VerifiedConflict] = Field(default_factory=list)
    abstained: bool = False
    escalation: str | None = None
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)
