"""EventBridge/manual Lambda: scrape a catalog edition into the raw S3 corpus prefix."""
from __future__ import annotations

import os
from typing import Any

from app.catalog import ingest_catalog, scrape_edition


def handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    url = str(event.get("url") or os.environ["CATALOG_URL"])
    year = int(event.get("year") or os.environ["CATALOG_YEAR"])
    is_current = bool(event.get("is_current", os.environ.get("CATALOG_IS_CURRENT") == "true"))
    pages = scrape_edition(
        url,
        edition_year=year,
        is_current=is_current,
        max_pages=int(event.get("max_pages", 40)),
    )
    added = ingest_catalog(pages, edition_year=year, is_current=is_current)
    return {"pages": len(pages), "chunks": added, "edition_year": year, "is_current": is_current}
