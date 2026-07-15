from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from .config import INDEX_DIR, get_settings
from .llm import EMBEDDING_DIMENSION, embed_texts


@dataclass(frozen=True)
class SearchResult:
    text: str
    source: str
    section: str
    doc_type: str
    page: int | None
    topic: str
    score: float


class IndexStore:
    def __init__(self) -> None:
        self._chunks: list[dict[str, object]] = []
        self._embeddings = np.empty((0, EMBEDDING_DIMENSION), dtype=np.float32)

    @property
    def size(self) -> int:
        return len(self._chunks)

    @property
    def chunks(self) -> list[dict[str, object]]:
        return [dict(chunk) for chunk in self._chunks]

    def load(self) -> None:
        chunks_path = INDEX_DIR / "chunks.json"
        embeddings_path = INDEX_DIR / "embeddings.npy"
        if not chunks_path.exists() or not embeddings_path.exists():
            self._chunks = []
            self._embeddings = np.empty((0, EMBEDDING_DIMENSION), dtype=np.float32)
            return
        chunks: list[dict[str, object]] = json.loads(chunks_path.read_text(encoding="utf-8"))
        embeddings = np.load(embeddings_path)
        if len(chunks) != len(embeddings):
            raise ValueError("Index metadata and embedding counts do not match")
        self._chunks = chunks
        self._embeddings = embeddings.astype(np.float32, copy=False)

    def search(self, query: str, k: int = 8) -> list[SearchResult]:
        if not query.strip() or self.size == 0:
            return []
        query_embedding = embed_texts([query])[0]
        scores = self._embeddings @ query_embedding
        limit = min(max(k, 1), self.size)
        indices = np.argsort(scores)[-limit:][::-1]
        results: list[SearchResult] = []
        for index in indices:
            chunk = self._chunks[int(index)]
            results.append(SearchResult(
                text=str(chunk.get("text", "")),
                source=str(chunk.get("source", "Unknown source")),
                section=str(chunk.get("section", "Document")),
                doc_type=str(chunk.get("doc_type", "document")),
                page=int(chunk["page"]) if chunk.get("page") is not None else None,
                topic=str(chunk.get("topic", "senate procedures")),
                score=float(scores[int(index)]),
            ))
        return results


INDEX = IndexStore()


def reload_index() -> None:
    INDEX.load()


def search(query: str, k: int = 8) -> list[SearchResult]:
    settings = get_settings()
    if settings.retrieval_aws:
        return _search_knowledge_base(query, k)
    return INDEX.search(query, k)


def _search_knowledge_base(query: str, k: int) -> list[SearchResult]:
    settings = get_settings()
    if not settings.retrieval_aws:
        return []
    import boto3  # type: ignore[import-not-found]  # Lazy: absent in local mode.

    client = boto3.client("bedrock-agent-runtime", region_name=settings.aws_region)
    response = client.retrieve(
        knowledgeBaseId=settings.bedrock_kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": max(1, k)}},
    )
    results: list[SearchResult] = []
    for item in response.get("retrievalResults", []):
        metadata = item.get("metadata", {})
        location = item.get("location", {})
        uri = location.get("s3Location", {}).get("uri", "Unknown source")
        page_value = metadata.get("page") or metadata.get("x-amz-bedrock-kb-document-page-number")
        results.append(SearchResult(
            text=str(item.get("content", {}).get("text", "")),
            source=str(metadata.get("source") or uri.rsplit("/", 1)[-1]),
            section=str(metadata.get("section", "Document")),
            doc_type=str(metadata.get("doc_type", "document")),
            page=int(page_value) if page_value is not None else None,
            topic=str(metadata.get("topic", "senate procedures")),
            score=float(item.get("score", 0.0)),
        ))
    return results
