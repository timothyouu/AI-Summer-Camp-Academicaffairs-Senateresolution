from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .config import CORPUS_DIR, ensure_data_directories, get_settings
from .ingest import append_to_index
from .registry import register_document
from .retrieval import reload_index

POLICY_LINK_KEYWORDS = (
    "polic", "academic", "regulation", "grade", "grading", "admission",
    "registration", "degree", "requirement", "standing", "probation", "withdraw",
)
USER_AGENT = "CSUB-Policy-Intelligence-Demo/1.0 (hackathon; contact: campus IT)"


@dataclass(frozen=True)
class CatalogPage:
    url: str
    title: str
    markdown: str


class _MarkdownExtractor(HTMLParser):
    """Minimal HTML-to-Markdown converter for catalog policy pages."""

    SKIP = {"script", "style", "nav", "header", "footer"}
    HEADINGS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._buffer: list[str] = []
        self._prefix = ""
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.HEADINGS or tag == "p":
            self._flush()
            self._prefix = self.HEADINGS.get(tag, "")
        elif tag == "li":
            self._flush()
            self._prefix = "- "
        elif tag == "br":
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.HEADINGS or tag in {"p", "li", "ul", "ol"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data.strip()
            return
        self._buffer.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
        self._buffer = []
        if text:
            self.lines.append(f"{self._prefix}{text}")
        self._prefix = ""


def html_to_markdown(html: str) -> str:
    extractor = _MarkdownExtractor()
    extractor.feed(html)
    extractor._flush()
    return "\n\n".join(extractor.lines)


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href") or None
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None


def discover_policy_links(html: str, base_url: str) -> list[str]:
    extractor = _LinkExtractor()
    extractor.feed(html)
    host = urlparse(base_url).netloc
    found: list[str] = []
    for href, text in extractor.links:
        absolute = urljoin(base_url, href)
        haystack = f"{text} {absolute}".lower()
        if urlparse(absolute).netloc != host:
            continue
        if any(keyword in haystack for keyword in POLICY_LINK_KEYWORDS) and absolute not in found:
            found.append(absolute)
    return found


def _http_fetch(url: str) -> str:
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20.0) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def scrape_edition(
    root_url: str,
    *,
    edition_year: int,
    is_current: bool,
    fetch: Callable[[str], str] = _http_fetch,
    max_pages: int = 40,
) -> list[CatalogPage]:
    queue: list[str] = [root_url]
    seen: set[str] = set()
    pages: list[CatalogPage] = []
    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = fetch(url)
        except Exception:
            continue
        markdown = html_to_markdown(html)
        extractor = _MarkdownExtractor()
        extractor.feed(html)
        title = extractor.title or url.rsplit("/", 1)[-1] or f"Catalog {edition_year}"
        if markdown.strip():
            pages.append(CatalogPage(url=url, title=title, markdown=markdown))
        for link in discover_policy_links(html, url):
            if link not in seen and link not in queue:
                queue.append(link)
    return pages


def _slug(title: str, edition_year: int, index: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or f"page-{index}"
    return f"catalog-{edition_year}-{base}"


def _bedrock_metadata(page: CatalogPage, edition_year: int, is_current: bool) -> bytes:
    """Build the companion metadata format consumed by Bedrock Knowledge Bases."""
    values: dict[str, str] = {
        "source": f"{page.title} ({edition_year} Catalog)",
        "section": page.title,
        "doc_type": "catalog",
        "topic": "campus policy",
        "edition_year": str(edition_year),
        "is_current": str(is_current).lower(),
    }
    payload = {
        "metadataAttributes": {
            key: {
                "value": {"type": "STRING", "stringValue": value},
                "includeForEmbedding": key in {"source", "doc_type", "topic"},
            }
            for key, value in values.items()
        }
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def ingest_catalog(pages: list[CatalogPage], *, edition_year: int, is_current: bool) -> int:
    """Write catalog pages to the corpus or S3, index them, and register them."""
    settings = get_settings()
    ensure_data_directories()
    added = 0
    for index, page in enumerate(pages):
        slug = _slug(page.title, edition_year, index)
        body = (
            f"---\ntitle: {page.title} ({edition_year} Catalog)\nsection: {page.title}\n"
            f"source_type: catalog\ncanonical_url: {page.url}\nedition_year: {edition_year}\n"
            f"is_current: {'true' if is_current else 'false'}\n---\n{page.markdown}\n"
        )
        if settings.corpus_aws:
            import boto3  # type: ignore[import-not-found]

            client = boto3.client("s3", region_name=settings.aws_region)
            key = f"raw/catalog/{edition_year}/{slug}.md"
            client.put_object(
                Bucket=settings.corpus_bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="text/markdown",
            )
            client.put_object(
                Bucket=settings.corpus_bucket,
                Key=f"{key}.metadata.json",
                Body=_bedrock_metadata(page, edition_year, is_current),
                ContentType="application/json",
            )
            chunks = 1
        else:
            destination = CORPUS_DIR / "catalog" / str(edition_year) / f"{slug}.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(body, encoding="utf-8")
            chunks = append_to_index(destination)
        if settings.corpus_aws:
            _register_remote(slug, page, edition_year, is_current)
        else:
            register_document(
                destination,
                status="active",
                source_type="catalog",
                canonical_url=page.url,
                edition_year=edition_year,
                is_current=is_current,
                passages=chunks,
            )
        added += chunks
    if not settings.corpus_aws:
        reload_index()
    return added


def _register_remote(slug: str, page: CatalogPage, edition_year: int, is_current: bool) -> None:
    from .models import SourceUpsert
    from .registry import registry_store

    store = registry_store()
    existing = store.get(slug)
    store.upsert(SourceUpsert(
        id=slug,
        title=f"{page.title} ({edition_year} Catalog)",
        source_type="catalog",
        status=existing.status if existing is not None else "active",
        canonical_url=page.url,
        edition_year=edition_year,
        is_current=is_current,
        s3_key=f"raw/catalog/{edition_year}/{slug}.md",
    ))
