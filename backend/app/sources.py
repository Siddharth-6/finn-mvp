"""Discover company-primary document links indexed on Screener."""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urljoin, urlparse


KEYWORDS = {
    "annual report": "annual_report",
    "annual reports": "annual_report",
    "concall": "concall_transcript",
    "transcript": "concall_transcript",
    "earnings call": "concall_transcript",
    "investor presentation": "investor_presentation",
    "quarterly results": "quarterly_results",
    "financial results": "quarterly_results",
}


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current_href is not None:
            label = " ".join(" ".join(self.current_text).split())
            self.links.append((label, self.current_href))
            self.current_href = None
            self.current_text = []


def extract_primary_document_links(html: str, base_url: str) -> list[dict[str, Any]]:
    parser = _AnchorParser()
    parser.feed(html)
    found: dict[str, dict[str, Any]] = {}
    for label, href in parser.links:
        normalized_label = label.lower()
        category = next(
            (kind for keyword, kind in KEYWORDS.items() if keyword in normalized_label),
            None,
        )
        if not category or not href:
            continue
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            continue
        if parsed.hostname.endswith("screener.in") and not parsed.path.lower().endswith(".pdf"):
            continue
        if url in found:
            continue
        found[url] = {
            "label": label[:180] or category.replace("_", " ").title(),
            "category": category,
            "url": url,
            "host": parsed.hostname,
            "source_index": "Screener company page",
        }
    return list(found.values())
