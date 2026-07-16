from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from pypdf import PdfReader

from .config import INDEX_DIR, ensure_data_directories
from .llm import EMBEDDING_DIMENSION, embed_texts


TOPICS = (
    "tenure & promotion",
    "hiring & appointments",
    "workload",
    "curriculum",
    "accessibility",
    "senate procedures",
    "committees",
    "cba & labor",
    "ferp & retirement",
)

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tenure & promotion": ("tenure", "promotion", "probation", "wpaf", "rtp"),
    "hiring & appointments": ("appointment", "hire", "recruit", "search committee"),
    "workload": ("workload", "office hours", "wtu", "assigned time"),
    "curriculum": ("curriculum", "course", "program review", "gecco"),
    "accessibility": ("accessibility", "accessible", "ada", "imap", "assistive"),
    "senate procedures": ("senate", "resolution", "quorum", "vote"),
    "committees": ("committee", "membership", "chair", "review committee"),
    "cba & labor": ("collective bargaining", "cba", "grievance", "labor"),
    "ferp & retirement": ("ferp", "retirement", "calpers", "retired annuitant"),
}


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str
    section: str
    doc_type: str
    page: int | None
    topic: str
    canonical_url: str = ""


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    closing = text.find("\n---\n", 4)
    if closing < 0:
        return {}, text
    metadata: dict[str, str] = {}
    for line in text[4:closing].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip().lower()] = value.strip().strip('"')
    return metadata, text[closing + 5 :]


def extract_document(path: Path) -> list[tuple[str, int | None]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return [(page.extract_text() or "", index + 1) for index, page in enumerate(reader.pages)]
    if suffix in {".md", ".txt"}:
        return [(path.read_text(encoding="utf-8", errors="replace"), None)]
    raise ValueError(f"Unsupported document type: {path.suffix}")


def chunk_text(text: str, chunk_words: int = 800, overlap_words: int = 150) -> list[str]:
    if chunk_words <= 0:
        raise ValueError("chunk_words must be positive")
    if overlap_words < 0 or overlap_words >= chunk_words:
        raise ValueError("overlap_words must be between zero and chunk_words - 1")
    words = text.split()
    if not words:
        return []
    step = chunk_words - overlap_words
    return [" ".join(words[start : start + chunk_words]) for start in range(0, len(words), step) if words[start : start + chunk_words]]


def assign_topic(text: str) -> str:
    lowered = text.lower()
    scores = {topic: sum(lowered.count(keyword) for keyword in keywords) for topic, keywords in TOPIC_KEYWORDS.items()}
    topic, score = max(scores.items(), key=lambda item: item[1])
    return topic if score > 0 else "senate procedures"


def build_chunks(paths: Iterable[Path]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in paths:
        try:
            pages = extract_document(path)
        except Exception:
            # A corrupt corpus file must not brick startup indexing; skip it.
            logging.getLogger(__name__).warning("Skipping unreadable corpus file: %s", path)
            continue
        for page_text, page in pages:
            metadata, body = _parse_front_matter(page_text)
            source = metadata.get("title", path.stem)
            section = metadata.get("section", f"Page {page}" if page is not None else "Document")
            doc_type = metadata.get("source_type", path.suffix.lower().lstrip("."))
            canonical_url = metadata.get("canonical_url", "")
            for index, text in enumerate(chunk_text(body)):
                chunk_id = f"{path.stem}:{page or 0}:{index}"
                chunks.append(Chunk(chunk_id, text, source, section, doc_type, page, assign_topic(text), canonical_url))
    return chunks


def persist_index(chunks: list[Chunk], embeddings: np.ndarray) -> None:
    ensure_data_directories()
    INDEX_DIR.joinpath("chunks.json").write_text(json.dumps([asdict(chunk) for chunk in chunks], indent=2), encoding="utf-8")
    np.save(INDEX_DIR / "embeddings.npy", embeddings)


def build_index(paths: Iterable[Path]) -> int:
    chunks = build_chunks(paths)
    embeddings = embed_texts([chunk.text for chunk in chunks])
    persist_index(chunks, embeddings)
    return len(chunks)


def append_to_index(path: Path) -> int:
    new_chunks = build_chunks([path])
    chunks_path = INDEX_DIR / "chunks.json"
    embeddings_path = INDEX_DIR / "embeddings.npy"
    existing_chunks: list[dict[str, object]] = []
    existing_embeddings = np.empty((0, EMBEDDING_DIMENSION), dtype=np.float32)
    if chunks_path.exists() and embeddings_path.exists():
        existing_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        existing_embeddings = np.load(embeddings_path)
    new_ids = {chunk.id for chunk in new_chunks}
    retained_indices = [index for index, chunk in enumerate(existing_chunks) if str(chunk.get("id", "")) not in new_ids]
    retained_chunks = [existing_chunks[index] for index in retained_indices]
    retained_embeddings = existing_embeddings[retained_indices] if retained_indices else np.empty((0, EMBEDDING_DIMENSION), dtype=np.float32)
    combined_chunks = retained_chunks + [asdict(chunk) for chunk in new_chunks]
    new_embeddings = embed_texts([chunk.text for chunk in new_chunks])
    combined_embeddings = np.vstack([retained_embeddings, new_embeddings]) if len(retained_embeddings) else new_embeddings
    ensure_data_directories()
    chunks_path.write_text(json.dumps(combined_chunks, indent=2), encoding="utf-8")
    np.save(embeddings_path, combined_embeddings)
    return len(new_chunks)


def discover_corpus_files(corpus_dir: Path) -> list[Path]:
    supported = {".pdf", ".md", ".txt"}
    return sorted(path for path in corpus_dir.rglob("*") if path.is_file() and path.suffix.lower() in supported)
