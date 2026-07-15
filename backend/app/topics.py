from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException, status

from .models import TopicChunk, TopicDetail, TopicSummary
from .retrieval import INDEX


router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.get("", response_model=list[TopicSummary])
def get_topics() -> list[TopicSummary]:
    counts = Counter(str(chunk.get("topic", "senate procedures")) for chunk in INDEX.chunks)
    return [TopicSummary(name=name, count=count) for name, count in sorted(counts.items())]


@router.get("/{name}", response_model=TopicDetail)
def get_topic(name: str) -> TopicDetail:
    normalized = name.replace("-", " ").lower()
    aliases = {"tenure promotion": "tenure & promotion", "cba labor": "cba & labor", "ferp retirement": "ferp & retirement"}
    normalized = aliases.get(normalized, normalized)
    chunks = [chunk for chunk in INDEX.chunks if str(chunk.get("topic", "")).lower() == normalized]
    if not chunks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return TopicDetail(
        name=normalized,
        chunks=[TopicChunk(source=str(chunk.get("source", "Unknown")), section=str(chunk.get("section", "Document")), excerpt=str(chunk.get("text", ""))[:500]) for chunk in chunks[:50]],
    )
