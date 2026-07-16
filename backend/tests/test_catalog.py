from __future__ import annotations

import json

from backend.app.catalog import (
    CatalogPage,
    _bedrock_metadata,
    _register_remote,
    discover_policy_links,
    html_to_markdown,
    ingest_catalog,
    scrape_edition,
)
from backend.app.registry import registry_store

HTML = """
<html><head><title>Academic Policies - CSUB Catalog</title></head><body>
<nav><a href="/misc/social.php">Follow us</a></nav>
<h1>Academic Policies</h1><h2>Grading</h2>
<p>Students <b>must</b> complete 120 units.</p>
<ul><li>First rule</li><li>Second rule</li></ul>
<a href="content.php?catoid=9&navoid=100">Grade Appeal Policy</a>
<a href="content.php?catoid=9&navoid=101">Degree Requirements</a>
<a href="/athletics.php">Basketball schedule</a>
</body></html>
"""


def test_html_to_markdown_keeps_structure_and_drops_tags() -> None:
    markdown = html_to_markdown(HTML)
    assert "# Academic Policies" in markdown
    assert "## Grading" in markdown
    assert "- First rule" in markdown
    assert "<p>" not in markdown and "<b>" not in markdown


def test_discover_policy_links_filters_by_keyword() -> None:
    links = discover_policy_links(HTML, "https://catalog.csub.edu/")
    assert "https://catalog.csub.edu/content.php?catoid=9&navoid=100" in links
    assert "https://catalog.csub.edu/content.php?catoid=9&navoid=101" in links
    assert all("athletics" not in link and "social" not in link for link in links)


def test_scrape_edition_crawls_with_fake_fetcher_and_respects_cap() -> None:
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        return HTML

    pages = scrape_edition(
        "https://catalog.csub.edu/",
        edition_year=2026,
        is_current=True,
        fetch=fetch,
        max_pages=2,
    )
    assert len(pages) == 2 and len(set(calls)) == 2


def test_bedrock_metadata_identifies_catalog_source_and_edition() -> None:
    page = CatalogPage(
        url="https://catalog.csub.edu/policy",
        title="Grade Appeal Policy",
        markdown="# Grade Appeal",
    )
    payload = json.loads(_bedrock_metadata(page, edition_year=2024, is_current=False))
    attributes = payload["metadataAttributes"]
    assert attributes["source"]["value"]["stringValue"] == "Grade Appeal Policy (2024 Catalog)"
    assert attributes["edition_year"]["value"]["stringValue"] == "2024"
    assert attributes["is_current"]["value"]["stringValue"] == "false"
    assert attributes["canonical_url"]["value"]["stringValue"] == page.url
    assert attributes["section_url"]["value"]["stringValue"] == page.url


def test_remote_catalog_reregistration_preserves_archived_status() -> None:
    page = CatalogPage(
        url="https://catalog.csub.edu/policy",
        title="Remote Policy",
        markdown="# Remote Policy",
    )
    _register_remote("catalog-2024-remote-policy", page, 2024, False)
    store = registry_store()
    store.set_status("catalog-2024-remote-policy", "archived")

    _register_remote("catalog-2024-remote-policy", page, 2024, False)

    record = store.get("catalog-2024-remote-policy")
    assert record is not None and record.status == "archived"


def test_ingest_catalog_registers_active_edition_tagged_sources() -> None:
    pages = [CatalogPage(
        url="https://catalog.csub.edu/x",
        title="Grade Appeal Policy",
        markdown="# Grade Appeal\nBody.",
    )]
    added = ingest_catalog(pages, edition_year=2024, is_current=False)
    assert added >= 1
    record = registry_store().get("catalog-2024-grade-appeal-policy")
    assert record is not None
    assert record.status == "active" and record.edition_year == 2024 and record.is_current is False
    assert record.canonical_url == "https://catalog.csub.edu/x"
    assert record.section_index == {"Grade Appeal Policy": "https://catalog.csub.edu/x"}
