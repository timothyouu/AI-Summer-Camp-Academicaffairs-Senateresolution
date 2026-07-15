from __future__ import annotations

from backend.app.config import CORPUS_DIR
from backend.app.ingest import build_index, discover_corpus_files


def main() -> None:
    files = discover_corpus_files(CORPUS_DIR)
    if not files:
        raise SystemExit(f"No supported documents found in {CORPUS_DIR}")
    chunk_count = build_index(files)
    print(f"Indexed {chunk_count} chunks from {len(files)} documents.")


if __name__ == "__main__":
    main()
