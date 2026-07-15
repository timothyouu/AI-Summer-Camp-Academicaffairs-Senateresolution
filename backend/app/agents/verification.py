from __future__ import annotations

import re
import unicodedata


def normalize_span(value: str) -> str:
    """Normalize presentation differences without weakening word-for-word grounding."""
    value = unicodedata.normalize("NFKC", value).replace("\u00ad", "")
    value = value.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", value).strip().casefold()


def span_is_grounded(quote: str, source_text: str) -> bool:
    normalized_quote = normalize_span(quote).strip(" \"'")
    return bool(normalized_quote) and normalized_quote in normalize_span(source_text)
