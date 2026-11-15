"""Promised vs delivered: guidance quotes from concall transcripts vs next quarter numbers."""
from __future__ import annotations

import io
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote

import httpx
import pymupdf

from app.announcements import _safe_attachment
from app.screener_fundamentals import company_brief

UA = "Mozilla/5.0 FINN research prototype/1.0"
FUTURE = r"expect|aim|target|guid|outlook|confident|aspir|going forward|next (year|quarter)|will (grow|be|see|deliver|invest)|ambition|plan to|on track"
NUMERIC = r"\d+(\.\d+)?\s?(%|per ?cent|bps|basis points|crore)|double[- ]digit|low[- ]teens|mid[- ]teens|high[- ]teens|single[- ]digit"
DISCLAIM = r"forward-looking|safe harbo|disclaimer|risks? (that|which)|replay|recording|moderator"


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"Page \d+ of \d+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+(?=[A-Z])", text)]


def guidance_quotes(text: str, k: int = 3) -> dict[str, Any]:
    sents = _sentences(text)
    no_guid = next(
        (s for s in sents if re.search(r"(don'?t|do not|does not|not) (provide|give)[^.]{0,60}guidance", s, re.I)),
        None,
    )
    scored = []
    for s in sents:
        if not (55 <= len(s) <= 340) or re.search(DISCLAIM, s, re.I) or s.rstrip().endswith("?"):
            continue
        if re.search(FUTURE, s, re.I) and re.search(NUMERIC, s, re.I):
            sc = 2 + bool(re.search(r"guid|target|aim|aspir|ambition|expect", s, re.I)) * 2
            scored.append((sc, re.sub(r"^[A-Z][\w\.]+(?: [A-Z][\w\.]+){1,3}: ", "", s)))
    scored.sort(key=lambda x: -x[0])
    return {"quotes": [s for _, s in scored[:k]], "no_explicit_guidance": no_guid}


def _pdf_text(url: str) -> str:
    with httpx.Client(
        headers={"User-Agent": UA, "Referer": "https://www.screener.in/"},
        timeout=35,
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        content = response.content
    if not content.startswith(b"%PDF"):
        raise ValueError("Not a PDF")
    pdf = pymupdf.open(stream=content, filetype="pdf")
    return "\n".join(page.get_text("text") for page in pdf)


def _transcript_links(ticker: str, limit: int = 4) -> list[dict[str, str]]:
    slug = re.sub(r"\.(NS|BO)$", "", ticker.upper())
    with httpx.Client(headers={"User-Agent": UA}, timeout=25, follow_redirects=True) as client:
        response = client.get(f"https://www.screener.in/company/{quote(slug)}/consolidated/")
        if response.status_code == 404:
            response = client.get(f"https://www.screener.in/company/{quote(slug)}/")
        response.raise_for_status()
        html = response.text
    # Concalls block: Oct 2026 ... Transcript href
    block = html
    if "Concalls" in html:
        block = html[html.index("Concalls"): html.index("Concalls") + 8000]
    out = []
    for match in re.finditer(
        r'<div[^>]*>\s*([A-Z][a-z]{2} \d{4})\s*</div>.*?href="([^"]+)"[^>]*>\s*Transcript',
        block,
        re.I | re.S,
    ):
        label, href = match.group(1), match.group(2).replace("&amp;", "&")
        safe = _safe_attachment(href) or href
        out.append({"label": label, "url": safe})
        if len(out) >= limit:
            break
    return out


def promises_vs_delivery(ticker: str) -> dict[str, Any]:
    brief = company_brief(ticker)
    results = brief.get("results") or {}
    links = _transcript_links(ticker, limit=4)

    def work(item: dict[str, str]) -> dict[str, Any]:
        try:
            text = _pdf_text(item["url"])
            g = guidance_quotes(text)
            return {
                "call": item["label"],
                "transcript": item["url"],
                "quotes": g["quotes"],
                "no_explicit_guidance": g["no_explicit_guidance"],
                "error": None,
            }
        except Exception as exc:
            return {
                "call": item["label"],
                "transcript": item["url"],
                "quotes": [],
                "no_explicit_guidance": None,
                "error": str(exc)[:120],
            }

    with ThreadPoolExecutor(max_workers=3) as pool:
        calls = list(pool.map(work, links))

    return {
        "ticker": ticker.upper(),
        "latest_reported": results,
        "calls": calls,
        "note": "Quotes extracted verbatim from concall transcripts. Latest reported quarter shown for comparison.",
        "grounding": "Primary transcripts + standardised quarterly financials.",
    }