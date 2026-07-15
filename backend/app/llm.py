from __future__ import annotations

import hashlib
import re

import numpy as np


EMBEDDING_DIMENSION = 384
PROVIDER_NAME = "local-hash-embedding"
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9'-]*")


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _token_bucket(token: str) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, byteorder="big", signed=False)
    bucket = value % EMBEDDING_DIMENSION
    sign = 1.0 if (value >> 1) % 2 == 0 else -1.0
    return bucket, sign


def embed_texts(texts: list[str]) -> np.ndarray:
    """Create deterministic local embeddings without AWS or external model calls."""
    embeddings = np.zeros((len(texts), EMBEDDING_DIMENSION), dtype=np.float32)
    for row, text in enumerate(texts):
        tokens = _tokenize(text)
        for token in tokens:
            bucket, sign = _token_bucket(token)
            embeddings[row, bucket] += sign
        norm = float(np.linalg.norm(embeddings[row]))
        if norm > 0:
            embeddings[row] /= norm
    return embeddings


def generate(system: str, user: str, json_mode: bool = False) -> str:
    """Document the intentionally unimplemented generative-provider seam.

    Bedrock generation/retrieval is excluded from this implementation. Backend
    routes use deterministic, source-backed local response builders instead.
    """
    del system, user, json_mode
    raise RuntimeError("Generative provider is not configured; local deterministic mode is active.")
