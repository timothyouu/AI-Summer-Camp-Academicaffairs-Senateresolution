from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit

import numpy as np

from .config import INDEX_DIR, get_settings
from .llm import EMBEDDING_DIMENSION, embed_texts
from .models import SourceRecord


@dataclass(frozen=True)
class SearchResult:
    text: str
    source: str
    section: str
    doc_type: str
    page: int | None
    topic: str
    score: float
    canonical_url: str = ""
    section_url: str = ""


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
                canonical_url=str(chunk.get("canonical_url", "")),
                section_url=_section_link(
                    str(chunk.get("canonical_url", "")),
                    str(chunk.get("section", "Document")),
                    int(chunk["page"]) if chunk.get("page") is not None else None,
                ),
            ))
        return results


INDEX = IndexStore()


ARCHIVED_EDITION_WEIGHT = 0.5


def _section_link(
    canonical_url: str,
    section: str,
    page: int | None,
    section_index: dict[str, str] | None = None,
) -> str:
    indexed = (section_index or {}).get(section, "")
    if indexed:
        return indexed
    if not canonical_url or page is None:
        return canonical_url
    parts = urlsplit(canonical_url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, f"page={page}"))


def reload_index() -> None:
    INDEX.load()


def apply_registry_policy(results: list[SearchResult], k: int) -> list[SearchResult]:
    """Drop archived sources and down-rank non-current editions using the registry.

    Sources without a registry entry pass through untouched so local test
    corpora and pre-registry indexes keep working byte-for-byte.
    """
    from .registry import registry_store

    try:
        records: dict[str, SourceRecord] = {}
        for record in registry_store().list():
            keys = {record.id.casefold(), record.title.casefold()}
            if record.s3_key:
                path = PurePosixPath(record.s3_key)
                keys.update({path.name.casefold(), path.stem.casefold()})
            for key in keys:
                records[key] = record
    except Exception:
        # Deliberate availability trade-off: an unreachable registry must not
        # take chat down, but the pass-through means archived sources are not
        # filtered until it recovers — make that visible instead of silent.
        logging.getLogger(__name__).warning(
            "Registry unavailable; serving retrieval results without lifecycle filtering"
        )
        return results[:k]
    kept: list[SearchResult] = []
    for item in results:
        source_path = PurePosixPath(item.source)
        record = next(
            (
                records[key]
                for key in (item.source.casefold(), source_path.name.casefold(), source_path.stem.casefold())
                if key in records
            ),
            None,
        )
        if record is not None and record.status == "archived":
            continue
        if record is not None:
            canonical_url = record.canonical_url or item.canonical_url
            section_url = _section_link(canonical_url, item.section, item.page, record.section_index)
            item = replace(item, canonical_url=canonical_url, section_url=section_url)
        if record is not None and not record.is_current:
            item = replace(item, score=item.score * ARCHIVED_EDITION_WEIGHT)
        kept.append(item)
    return sorted(kept, key=lambda value: value.score, reverse=True)[:k]


def search(query: str, k: int = 8) -> list[SearchResult]:
    settings = get_settings()
    fetched = _search_knowledge_base(query, k * 2) if settings.retrieval_aws else INDEX.search(query, k * 2)
    return apply_registry_policy(fetched, k)


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
            canonical_url=str(metadata.get("canonical_url", "")),
            section_url=str(metadata.get("section_url") or _section_link(
                str(metadata.get("canonical_url", "")),
                str(metadata.get("section", "Document")),
                int(page_value) if page_value is not None else None,
            )),
        ))
    return results
