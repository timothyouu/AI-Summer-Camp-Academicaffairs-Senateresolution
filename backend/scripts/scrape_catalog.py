"""Scrape the CSUB course catalog into the policy corpus."""
from __future__ import annotations

import argparse

from app.catalog import ingest_catalog, scrape_edition


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--current", action="store_true")
    parser.add_argument("--max-pages", type=int, default=40)
    args = parser.parse_args()
    pages = scrape_edition(args.url, edition_year=args.year, is_current=args.current, max_pages=args.max_pages)
    added = ingest_catalog(pages, edition_year=args.year, is_current=args.current)
    print(f"Scraped {len(pages)} page(s), indexed {added} chunk(s) for the {args.year} catalog.")


if __name__ == "__main__":
    main()
