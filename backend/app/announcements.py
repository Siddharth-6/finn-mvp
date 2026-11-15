"""NSE corporate-announcement ingestion.

Uses the public NSE filings JSON endpoint with the exchange's public RSS feed
as a fallback. These endpoints are not a licensed market-data API; upstream
availability and access controls may change. No access-control bypass is used.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")
NSE_HOME = "https://www.nseindia.com"
NSE_API = "https://www.nseindia.com/api/corporate-announcements"
NSE_RSS = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Category labels follow ENAM's companion reference. Keyword matching is a
# transparent first-pass classifier, not a claim that the exchange assigned it.
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("results", ("financial results", "quarterly results", "annual results", "outcome of board meeting", "unaudited financial", "audited financial")),
    ("M&A", ("acquisition", "merger", "amalgamation", "demerger", "joint venture", "subsidiary", "stake sale")),
    ("fund_raise", ("qip", "qualified institutions placement", "preferential issue", "rights issue", "commercial paper", "fund raising", "buyback", "buy-back", "debenture")),
    ("management_change", ("change in management", "resignation", "appointment of", "cessation", "chief executive", "chief financial officer", "managing director", "independent director")),
    ("litigation", ("litigation", "court", "tribunal", "penalty", "fine", "show cause", "insolvency", "regulatory order", " sebi ")),
    ("insider_trading", ("insider trading", "trading by designated person", "disclosure under regulation 7", "trading window")),
    ("earnings_call", ("conference call", "earnings call", "analyst call", "investor call", "transcript of", "audio recording")),
    ("investor_meetings", ("investor meet", "investor meeting", "analyst meet", "investor conference")),
    ("credit_rating", ("credit rating", "rating rationale", "rating assigned", "rating upgrade", "rating downgrade")),
    ("dividend", ("dividend", "interim dividend", "final dividend")),
    ("bonus_split", ("bonus issue", "stock split", "sub-division of equity")),
    ("capex", ("capacity expansion", "capital expenditure", "new plant", "new facility", "capex")),
    ("press_release", ("press release", "order win", "work order", "partnership", "product launch", "business update")),
    ("postal_ballot", ("postal ballot",)),
    ("agm_egm", ("annual general meeting", "extraordinary general meeting", "agm", "egm")),
    ("pledging", ("pledge", "pledging", "release of pledge")),
]

HIGH = {"results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading", "pledging"}
MEDIUM = {"earnings_call", "credit_rating", "dividend", "bonus_split", "capex"}
LOW = {"investor_meetings", "press_release", "postal_ballot", "agm_egm", "unclassified"}


def classify_announcement(text: str) -> tuple[str, str]:
    normalized = f" {re.sub(r'[^a-z0-9]+', ' ', text.lower())} "
    for category, keywords in CATEGORY_RULES:
        if any(keyword in normalized for keyword in keywords):
            return category, "high" if category in HIGH else "medium" if category in MEDIUM else "low"
    return "unclassified", "low"


def _safe_attachment(value: str | None) -> str | None:
    if not value:
        return None
    url = value.strip()
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if parsed.scheme != "https" or not (
        parsed.hostname == "nsearchives.nseindia.com"
        or parsed.hostname == "www.nseindia.com"
        or parsed.hostname == "nseindia.com"
    ):
        return None
    return url


def _parse_nse_datetime(row: dict[str, Any]) -> datetime | None:
    for key in ("sort_date", "exchdisstime", "an_dt", "dt"):
        raw = str(row.get(key) or "").strip()
        if not raw:
            continue
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%Y",
            "%d%m%Y%H%M%S",
        ):
            try:
                parsed = datetime.strptime(raw, fmt)
                return parsed.replace(tzinfo=IST)
            except ValueError:
                continue
    return None


def _normalize_nse_row(row: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(row.get("symbol") or "").upper().strip()
    if not symbol:
        return None
    subject = str(row.get("desc") or row.get("subject") or "Corporate announcement").strip()
    details = str(row.get("attchmntText") or row.get("summary") or "").strip()
    company = str(row.get("sm_name") or row.get("companyName") or symbol).strip()
    category, priority = classify_announcement(f"{subject} {details}")
    published = _parse_nse_datetime(row)
    attachment = _safe_attachment(str(row.get("attchmntFile") or row.get("attachmentUrl") or ""))
    raw_id = str(row.get("seq_id") or row.get("id") or "")
    identity = raw_id or f"{symbol}|{subject}|{published.isoformat() if published else ''}|{attachment or ''}"
    item_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return {
        "id": item_id,
        "exchange": "NSE",
        "ticker": symbol,
        "company": company,
        "category": category,
        "exchange_category": str(row.get("desc") or ""),
        "title": subject,
        "summary": details or subject,
        "priority": priority,
        "published_at": published.isoformat() if published else None,
        "source_url": attachment,
        "source_page": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        "source_name": "NSE corporate filings",
        "is_demo": False,
        "classification_method": "keyword_rules_v1",
    }


def _fetch_nse_json(start: datetime, end: datetime, symbols: set[str]) -> list[dict[str, Any]]:
    params = {
        "index": "equities",
        "from_date": start.astimezone(IST).strftime("%d-%m-%Y"),
        "to_date": end.astimezone(IST).strftime("%d-%m-%Y"),
    }
    with httpx.Client(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        },
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        # Establish a normal public-site session/cookie jar before the JSON call.
        landing = client.get(NSE_HOME)
        landing.raise_for_status()
        response = client.get(NSE_API, params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("NSE announcements endpoint returned an unexpected response")
    normalized = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        if symbol not in symbols:
            continue
        item = _normalize_nse_row(row)
        if item:
            normalized.append(item)
    return normalized


def _fetch_nse_rss(symbols: set[str]) -> list[dict[str, Any]]:
    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"},
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        response = client.get(NSE_RSS)
        response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "Corporate announcement").strip()
        description = (node.findtext("description") or "").strip()
        link = (node.findtext("link") or "").strip()
        combined = f"{title} {description} {link}"
        symbol_match = re.search(r"\b([A-Z][A-Z0-9&-]{1,19})\b", title)
        symbol = symbol_match.group(1) if symbol_match else ""
        if symbol not in symbols:
            continue
        raw_date = node.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(raw_date).astimezone(IST)
        except (TypeError, ValueError):
            published = None
        category, priority = classify_announcement(combined)
        safe_link = _safe_attachment(link)
        identity = f"{symbol}|{title}|{raw_date}|{link}"
        items.append({
            "id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
            "exchange": "NSE",
            "ticker": symbol,
            "company": symbol,
            "category": category,
            "exchange_category": "NSE RSS",
            "title": title,
            "summary": description or title,
            "priority": priority,
            "published_at": published.isoformat() if published else None,
            "source_url": safe_link,
            "source_page": NSE_RSS,
            "source_name": "NSE official RSS",
            "is_demo": False,
            "classification_method": "keyword_rules_v1",
        })
    return items


def fetch_portfolio_announcements(
    tickers: list[str],
    hours: int = 24,
    include_routine: bool = True,
) -> dict[str, Any]:
    """Fetch and normalize real NSE announcements for the requested portfolio."""
    end = datetime.now(IST)
    start = end - timedelta(hours=hours)
    symbols = {re.sub(r"\.(NS|BO)$", "", ticker.upper().strip()) for ticker in tickers}
    errors: list[str] = []
    source = "NSE corporate announcements JSON"

    try:
        items = _fetch_nse_json(start, end, symbols)
    except Exception as exc:
        errors.append(f"NSE JSON: {type(exc).__name__}: {str(exc)[:180]}")
        source = "NSE official RSS fallback"
        try:
            items = _fetch_nse_rss(symbols)
        except Exception as rss_exc:
            errors.append(f"NSE RSS: {type(rss_exc).__name__}: {str(rss_exc)[:180]}")
            return {
                "items": [],
                "mode": "source_unavailable",
                "source": None,
                "window_hours": hours,
                "fetched_at": end.isoformat(),
                "portfolio_symbols": sorted(symbols),
                "errors": errors,
                "note": "Live NSE sources could not be reached. No demo items are substituted.",
            }

    filtered = []
    for item in items:
        # Enforce portfolio membership again after source normalization so
        # fallback feeds and mocked/test adapters cannot leak other issuers.
        if str(item.get("ticker") or "").upper() not in symbols:
            continue
        timestamp = item.get("published_at")
        if timestamp:
            try:
                parsed = datetime.fromisoformat(timestamp)
                if parsed < start or parsed > end + timedelta(minutes=5):
                    continue
            except ValueError:
                continue
        else:
            continue
        if not include_routine and item["priority"] == "low":
            continue
        filtered.append(item)

    # Deduplicate by stable filing ID and sort newest/highest priority first.
    unique = {item["id"]: item for item in filtered}
    priority_order = {"high": 0, "medium": 1, "low": 2}
    result = sorted(
        unique.values(),
        key=lambda item: (
            priority_order.get(item["priority"], 3),
            -datetime.fromisoformat(item["published_at"]).timestamp(),
        ),
    )
    return {
        "items": result,
        "mode": "live",
        "source": source,
        "window_hours": hours,
        "fetched_at": end.isoformat(),
        "portfolio_symbols": sorted(symbols),
        "errors": errors,
        "note": "NSE filings are real exchange disclosures. Categories and priority are FINN's rule-based first-pass classification, not exchange-assigned labels.",
    }
