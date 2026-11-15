from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pymupdf
import httpx
import yfinance as yf
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.announcements import _safe_attachment, fetch_portfolio_announcements
from app.financials import build_results_prompt, parse_model_json, rank_financial_chunks, validate_results_payload
from app.sources import extract_primary_document_links
from app.screener_fundamentals import company_brief, enrich_management_change
from app.promises import promises_vs_delivery

load_dotenv()

app = FastAPI(
    title="FINN API",
    version="0.2.0",
    description="Financial Investment Intelligence prototype",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://finn-mvp.vercel.app",
    ],
    # GitHub Codespaces + Vercel preview deployments.
    allow_origin_regex=r"https://([a-zA-Z0-9-]+-3000\.app\.github\.dev|finn[a-zA-Z0-9-]*\.vercel\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DOC_DIR = DATA_DIR / "documents"
DOC_DIR.mkdir(parents=True, exist_ok=True)

PORTFOLIO = [
    {"ticker": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy & Retail"},
    {"ticker": "TCS.NS", "name": "Tata Consultancy Services", "sector": "IT Services"},
    {"ticker": "INFY.NS", "name": "Infosys", "sector": "IT Services"},
    {"ticker": "HDFCBANK.NS", "name": "HDFC Bank", "sector": "Banking"},
    {"ticker": "ICICIBANK.NS", "name": "ICICI Bank", "sector": "Banking"},
    {"ticker": "SBIN.NS", "name": "State Bank of India", "sector": "Banking"},
    {"ticker": "HCLTECH.NS", "name": "HCL Technologies", "sector": "IT Services"},
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel", "sector": "Telecom"},
    {"ticker": "LT.NS", "name": "Larsen & Toubro", "sector": "Infrastructure"},
    {"ticker": "SUNPHARMA.NS", "name": "Sun Pharmaceutical", "sector": "Pharma"},
    {"ticker": "MARUTI.NS", "name": "Maruti Suzuki", "sector": "Auto"},
    {"ticker": "TATAMOTORS.NS", "name": "Tata Motors", "sector": "Auto"},
    {"ticker": "HINDUNILVR.NS", "name": "Hindustan Unilever", "sector": "FMCG"},
    {"ticker": "ITC.NS", "name": "ITC", "sector": "FMCG"},
    {"ticker": "TITAN.NS", "name": "Titan Company", "sector": "Consumer"},
    {"ticker": "ULTRACEMCO.NS", "name": "UltraTech Cement", "sector": "Cement"},
    {"ticker": "ONGC.NS", "name": "ONGC", "sector": "Energy"},
    {"ticker": "DRREDDY.NS", "name": "Dr. Reddy's Laboratories", "sector": "Pharma"},
]

# These cards are deliberately marked as examples, never real disclosures.
DEMO_ANNOUNCEMENTS = [
    {"id": "demo-1", "ticker": "TCS.NS", "company": "Tata Consultancy Services", "category": "results", "title": "Quarterly results announcement", "summary": "Illustrative filing card. A verified NSE/BSE filing connector is not configured.", "priority": "high", "published_at": "Demo data", "source_url": None, "is_demo": True},
    {"id": "demo-2", "ticker": "RELIANCE.NS", "company": "Reliance Industries", "category": "capex", "title": "Capacity expansion update", "summary": "Illustrative announcement. No claim is made that this event occurred.", "priority": "medium", "published_at": "Demo data", "source_url": None, "is_demo": True},
    {"id": "demo-3", "ticker": "INFY.NS", "company": "Infosys", "category": "unclassified", "title": "Routine compliance disclosure", "summary": "Illustrative low-priority item used to demonstrate digest filtering.", "priority": "low", "published_at": "Demo data", "source_url": None, "is_demo": True},
]

# Process-local cache. A production deployment should use shared persistent cache.
MARKET_CACHE: dict[str, dict[str, Any]] = {}
MARKET_FAILURE_UNTIL: dict[str, float] = {}
MARKET_CACHE_TTL_SECONDS = 15 * 60
MARKET_FAILURE_TTL_SECONDS = 90
MARKET_LOCK = threading.Lock()

DOCUMENTS: list[dict[str, Any]] = []


class ResearchRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=30)
    question: str = Field(min_length=5, max_length=2000)


class ResultsAnalysisRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=30)


class ResultsFilingRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=30)
    source_url: str = Field(min_length=10, max_length=2048)


class AlertConfig(BaseModel):
    ticker: str = Field(min_length=1, max_length=30)
    # These are user-configured trigger thresholds.
    price_change_pct: float = Field(default=3.0, gt=0)
    volume_multiple: float = Field(default=2.0, gt=0)
    average_days: int = Field(default=20, ge=2, le=250)
    # Optional observed values enable deterministic tests without external APIs.
    observed_price_change_pct: float | None = None
    observed_volume_multiple: float | None = None


def _ticker(value: str) -> str:
    symbol = value.upper().strip()
    if not re.fullmatch(r"[A-Z0-9&.-]{1,30}", symbol):
        raise HTTPException(400, "Invalid ticker format")
    return symbol


@app.get("/")
def root():
    return {"service": "FINN API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "FINN API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/portfolio")
def get_portfolio():
    return {
        "items": PORTFOLIO,
        "count": len(PORTFOLIO),
        "mode": "configured_mock_portfolio",
    }


def _fetch_market_data(symbol: str, average_days: int = 20) -> dict[str, Any]:
    hist = yf.Ticker(symbol).history(
        period="1y", interval="1d", auto_adjust=False
    )
    if hist.empty:
        raise ValueError(f"No market data returned for {symbol}")
    hist = hist.dropna(subset=["Close"])
    if hist.empty:
        raise ValueError(f"No valid closing prices found for {symbol}")

    latest = hist.iloc[-1]
    previous = hist.iloc[-2] if len(hist) > 1 else latest
    # Compare today's volume with prior sessions only; including today's
    # volume in its own baseline dampens genuine spikes.
    baseline_volumes = hist["Volume"].iloc[:-1].tail(average_days)
    avg_vol = float(baseline_volumes.mean()) if not baseline_volumes.empty else 0.0
    latest_volume = int(latest["Volume"])
    volume_multiple = latest_volume / avg_vol if avg_vol > 0 else None
    price_change = (
        (float(latest["Close"]) / float(previous["Close"]) - 1) * 100
        if float(previous["Close"]) else 0.0
    )
    return {
        "ticker": symbol,
        "currency": "INR",
        "latest_close": round(float(latest["Close"]), 2),
        "previous_close": round(float(previous["Close"]), 2),
        "price_change_pct": round(price_change, 2),
        "latest_volume": latest_volume,
        "average_volume_baseline": int(avg_vol),
        "baseline_days": average_days,
        "volume_multiple": round(volume_multiple, 2) if volume_multiple is not None else None,
        "as_of": hist.index[-1].isoformat(),
        "history": [
            {
                "date": idx.strftime("%Y-%m-%d"),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
            for idx, row in hist.tail(30).iterrows()
        ],
        "source": "Yahoo Finance via yfinance",
        "provider_note": "Unofficial upstream data; may be delayed or rate-limited.",
    }


@app.get("/api/market/{ticker}")
def market_data(ticker: str, average_days: int = 20):
    symbol = _ticker(ticker)
    if average_days < 2 or average_days > 250:
        raise HTTPException(400, "average_days must be between 2 and 250")
    cache_key = f"{symbol}:{average_days}"
    now = time.monotonic()

    with MARKET_LOCK:
        cached = MARKET_CACHE.get(cache_key)
        if cached and now - cached["fetched_at"] < MARKET_CACHE_TTL_SECONDS:
            return {**cached["data"], "cache_status": "fresh_cache"}

        if now < MARKET_FAILURE_UNTIL.get(symbol, 0):
            if cached:
                return {
                    **cached["data"],
                    "cache_status": "stale_cache",
                    "warning": "Provider temporarily unavailable; serving last successful data.",
                }
            raise HTTPException(
                503,
                "Market data provider is temporarily rate-limited. Retry later.",
            )

    try:
        result = _fetch_market_data(symbol, average_days=average_days)
        with MARKET_LOCK:
            MARKET_CACHE[cache_key] = {"fetched_at": time.monotonic(), "data": result}
            MARKET_FAILURE_UNTIL.pop(symbol, None)
        return {**result, "cache_status": "live_fetch"}
    except Exception as exc:
        message = str(exc)
        rate_limited = any(
            marker in message.lower()
            for marker in ("too many requests", "rate limit", "429")
        )
        with MARKET_LOCK:
            MARKET_FAILURE_UNTIL[symbol] = time.monotonic() + MARKET_FAILURE_TTL_SECONDS
            cached = MARKET_CACHE.get(cache_key)
        if cached:
            return {
                **cached["data"],
                "cache_status": "stale_cache",
                "warning": message[:180],
            }
        status = 503 if rate_limited else 502
        detail = (
            "Market data provider is rate-limited. Please retry later."
            if rate_limited else f"Market data provider error: {message[:180]}"
        )
        raise HTTPException(status, detail)


@app.post("/api/alerts/evaluate")
def evaluate_alert(config: AlertConfig):
    symbol = _ticker(config.ticker)
    manual_mode = (
        config.observed_price_change_pct is not None
        or config.observed_volume_multiple is not None
    )

    if manual_mode:
        # Explicit test/simulation mode. No external provider call is made.
        price_change = config.observed_price_change_pct
        volume_multiple = config.observed_volume_multiple
        data = {
            "source": "caller_supplied_test_observations",
            "price_change_pct": price_change,
            "volume_multiple": volume_multiple,
            "is_simulated": True,
        }
    else:
        data = market_data(symbol, average_days=config.average_days)
        price_change = data["price_change_pct"]
        volume_multiple = data["volume_multiple"]

    reasons = []
    if price_change is not None and abs(price_change) >= config.price_change_pct:
        reasons.append(
            f"Daily price move {price_change}% crossed ±{config.price_change_pct}% threshold"
        )
    if volume_multiple is not None and volume_multiple >= config.volume_multiple:
        reasons.append(
            f"Volume is {volume_multiple}x the recent average "
            f"(threshold {config.volume_multiple}x)"
        )

    return {
        "ticker": symbol,
        "triggered": bool(reasons),
        "reasons": reasons,
        "evaluation_mode": "test_observations" if manual_mode else "provider_data",
        "market_data": data,
    }


ANNOUNCEMENT_CACHE: dict[str, dict[str, Any]] = {}
ANNOUNCEMENT_CACHE_TTL_SECONDS = 5 * 60
SOURCE_CACHE: dict[str, dict[str, Any]] = {}
SOURCE_CACHE_TTL_SECONDS = 6 * 60 * 60


@app.get("/api/announcements")
def announcements(
    hours: int = 24,
    include_routine: bool = True,
    demo: bool = False,
):
    """Return a portfolio-scoped, time-windowed NSE announcement digest.

    Live mode is the default. Demo cards are returned only when explicitly
    requested with demo=true, and are always labelled as illustrative.
    """
    if hours < 1 or hours > 720:
        raise HTTPException(400, "hours must be between 1 and 720")

    if demo:
        return {
            "items": DEMO_ANNOUNCEMENTS,
            "mode": "demo_examples",
            "source": None,
            "window_hours": hours,
            "note": "Illustrative examples only; these are not real company disclosures.",
        }

    cache_key = f"{hours}:{include_routine}"
    now = time.monotonic()
    cached = ANNOUNCEMENT_CACHE.get(cache_key)
    if cached and now - cached["cached_at"] < ANNOUNCEMENT_CACHE_TTL_SECONDS:
        return {**cached["payload"], "cache_status": "fresh_cache"}

    result = fetch_portfolio_announcements(
        tickers=[company["ticker"] for company in PORTFOLIO],
        hours=hours,
        include_routine=include_routine,
    )
    # Attach Push enrichments for the ENAM "love" examples.
    name_by_ticker = {c["ticker"]: c["name"] for c in PORTFOLIO}
    for item in result.get("items", []):
        cat = item.get("category")
        full = item["ticker"] if str(item.get("ticker", "")).endswith(".NS") else f"{item.get('ticker')}.NS"
        company_name = name_by_ticker.get(full) or name_by_ticker.get(item.get("ticker")) or item.get("company") or ""
        try:
            if cat == "results" and item.get("priority") == "high":
                brief = company_brief(full)
                if brief.get("results"):
                    item["enrichment"] = {"type": "results", "results": brief["results"]}
            elif cat == "management_change":
                item["enrichment"] = {
                    "type": "management_change",
                    "mgmt": enrich_management_change(
                        item.get("title", ""),
                        item.get("summary", ""),
                        company_name,
                    ),
                }
        except Exception:
            continue
    result["cache_status"] = "live_fetch"
    ANNOUNCEMENT_CACHE[cache_key] = {
        "cached_at": now,
        "payload": result,
    }
    return result


@app.get("/api/sources/{ticker}")
async def discover_company_sources(ticker: str):
    """Find annual reports, concall transcripts and results links indexed by Screener."""
    symbol = _ticker(ticker)
    cached = SOURCE_CACHE.get(symbol)
    now = time.monotonic()
    if cached and now - cached["cached_at"] < SOURCE_CACHE_TTL_SECONDS:
        return {**cached["payload"], "cache_status": "fresh_cache"}

    slug = re.sub(r"\.(NS|BO)$", "", symbol, flags=re.IGNORECASE)
    page_url = f"https://www.screener.in/company/{quote(slug, safe='&-')}/"
    try:
        async with httpx.AsyncClient(
            timeout=25,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 FINN research prototype/1.0"},
        ) as client:
            response = await client.get(page_url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Screener source discovery unavailable: {str(exc)[:160]}")

    links = extract_primary_document_links(response.text, str(response.url))
    payload = {
        "ticker": symbol,
        "company_page": str(response.url),
        "items": links,
        "count": len(links),
        "mode": "screener_index",
        "note": "Screener is used as a document index. Opened links may point to company or exchange-hosted primary sources; verify the publisher before using a document for Pull research.",
    }
    SOURCE_CACHE[symbol] = {"cached_at": now, "payload": payload}
    return {**payload, "cache_status": "live_fetch"}


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...), ticker: str = ""):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            400, "Upload a PDF annual report, results filing, or earnings-call transcript."
        )
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(413, "PDF must be 25 MB or smaller")

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename).name)
    path = DOC_DIR / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    path.write_bytes(content)
    try:
        pdf = pymupdf.open(path)
        chunks = []
        for page_no, page in enumerate(pdf, start=1):
            page_text = page.get_text("text").strip()
            words = page_text.split()
            for start in range(0, len(words), 450):
                excerpt = " ".join(words[start:start + 450])
                if excerpt:
                    chunks.append({
                        "text": excerpt,
                        "page": page_no,
                        "filename": file.filename,
                        "ticker": ticker.upper().strip(),
                    })
        if not chunks:
            raise HTTPException(
                422,
                "No selectable text found. This PDF may be scanned; OCR is not enabled.",
            )
        DOCUMENTS.extend(chunks)
        return {
            "filename": file.filename,
            "ticker": ticker.upper().strip(),
            "pages": len(pdf),
            "chunks_added": len(chunks),
            "message": "Document indexed for this backend session.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Could not parse PDF: {str(exc)[:160]}")


@app.get("/api/documents")
def list_documents():
    grouped: dict[tuple[str, str], int] = {}
    for document in DOCUMENTS:
        key = (document["filename"], document["ticker"])
        grouped[key] = grouped.get(key, 0) + 1
    return {
        "documents": [
            {"filename": key[0], "ticker": key[1], "chunks": count}
            for key, count in grouped.items()
        ],
        "chunk_count": len(DOCUMENTS),
    }


def retrieve(question: str, ticker: str, limit: int = 5):
    terms = {word.lower() for word in re.findall(r"[A-Za-z0-9]{3,}", question)}
    scored = []
    for document in DOCUMENTS:
        if document["ticker"] and document["ticker"] != ticker.upper():
            continue
        words = {
            word.lower()
            for word in re.findall(r"[A-Za-z0-9]{3,}", document["text"])
        }
        score = len(terms & words)
        if score:
            scored.append((score, document))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [document for _, document in scored[:limit]]


@app.post("/api/results/analyze")
async def analyze_quarterly_results(req: ResultsAnalysisRequest):
    """Extract quarterly headline metrics only from uploaded primary-source PDFs."""
    ticker = _ticker(req.ticker)
    sources = [
        item for item in DOCUMENTS
        if item.get("ticker", "").upper() == ticker
    ]
    if not sources:
        return {
            "ticker": ticker,
            "status": "needs_documents",
            "message": "Upload this company's quarterly results filing or annual report PDF first.",
            "metrics": {},
            "sources": [],
        }

    # Keep the prompt bounded while retaining page-level source labels.
    selected = rank_financial_chunks(sources, limit=30)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "ticker": ticker,
            "status": "retrieved_only",
            "message": "Relevant uploaded source text is available, but GEMINI_API_KEY is not configured for structured extraction.",
            "metrics": {},
            "sources": [
                {"document": item["filename"], "page": item["page"], "excerpt": item["text"][:700]}
                for item in selected[:12]
            ],
        }

    prompt = build_results_prompt(ticker, selected)
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0,
                    "maxOutputTokens": 3000,
                    "responseMimeType": "application/json",
                },
            },
        )
    if response.status_code >= 400:
        raise HTTPException(502, f"Financial extraction provider error: {response.text[:250]}")
    try:
        model_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        extracted = parse_model_json(model_text)
        result = validate_results_payload(extracted, ticker, selected)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(502, f"Could not validate financial extraction: {str(exc)[:180]}")
    result["status"] = "extracted"
    return result


@app.post("/api/results/analyze-filing")
async def analyze_results_filing(req: ResultsFilingRequest):
    """Fetch an NSE-hosted results PDF from a filing card, index it, then analyze it."""
    ticker = _ticker(req.ticker)
    safe_url = _safe_attachment(req.source_url)
    if not safe_url:
        raise HTTPException(400, "Only verified NSE/BSE-hosted filing URLs can be analyzed.")

    try:
        async with httpx.AsyncClient(
            timeout=40,
            follow_redirects=True,
            headers={"User-Agent": "FINN research prototype/1.0"},
        ) as client:
            response = await client.get(safe_url)
        response.raise_for_status()
        # Do not allow an NSE URL to redirect the backend to an arbitrary host.
        redirected_url = _safe_attachment(str(response.url))
        if not redirected_url:
            raise HTTPException(400, "Filing redirected outside approved exchange hosts.")
        safe_url = redirected_url
        content = response.content
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Could not retrieve the NSE filing: {str(exc)[:160]}")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(413, "Filing PDF exceeds the 25 MB processing limit.")
    if not content.startswith(b"%PDF"):
        raise HTTPException(422, "The NSE attachment did not return a PDF document.")

    try:
        pdf = pymupdf.open(stream=content, filetype="pdf")
        filename = f"NSE_{ticker}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        stored_path = DOC_DIR / filename
        stored_path.write_bytes(content)
        chunks = []
        for page_no, page in enumerate(pdf, start=1):
            words = page.get_text("text").strip().split()
            for start in range(0, len(words), 450):
                excerpt = " ".join(words[start:start + 450])
                if excerpt:
                    chunks.append({
                        "text": excerpt,
                        "page": page_no,
                        "filename": filename,
                        "ticker": ticker,
                    })
        if not chunks:
            raise HTTPException(422, "The filing has no selectable text; scanned-PDF OCR is not enabled.")
        DOCUMENTS.extend(chunks)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Could not parse the NSE filing: {str(exc)[:160]}")

    result = await analyze_quarterly_results(ResultsAnalysisRequest(ticker=ticker))
    result["filing"] = {
        "filename": filename,
        "source_url": safe_url,
        "pages": len(pdf),
        "chunks_added": len(chunks),
    }
    return result


@app.post("/api/research")
async def research(req: ResearchRequest):
    ticker = _ticker(req.ticker)
    sources = retrieve(req.question, ticker)
    if not sources:
        # Cold-start Pull: answer from filing-derived standardised statements.
        try:
            brief = company_brief(ticker)
        except Exception as exc:
            return {
                "ticker": ticker,
                "answer": (
                    "I don't have uploaded primary-source passages yet, and could not load "
                    f"standardised filings either ({str(exc)[:120]}). Upload an annual report "
                    "or transcript PDF to continue."
                ),
                "sources": [],
                "grounded": False,
                "status": "needs_documents",
                "brief": None,
            }
        q = req.question.lower()
        parts = [f"Research brief for {brief['name']} (filing-derived standardised statements)."]
        if any(k in q for k in ("business", "segment", "what does")):
            parts.append(brief["business"].get("about") or "Business description unavailable.")
        if any(k in q for k in ("financial", "snapshot", "ratio", "number", "revenue", "pat", "margin")):
            cards = ", ".join(
                f"{c['k']}: {c['v']}{c['u']}" for c in brief["financial"]["cards"] if c["v"] is not None
            )
            parts.append(f"Financial snapshot ({brief['financial'].get('year')}): {cards}")
        if any(k in q for k in ("trajectory", "trend", "growth", "history", "cagr")):
            parts.append("Trajectory: " + "; ".join(brief["trajectory"]["notes"] or ["n/a"]))
        if any(k in q for k in ("debt", "balance", "leverage", "borrow")):
            parts.append("Balance sheet: " + "; ".join(brief["balance"]["notes"] or ["n/a"]))
        if any(k in q for k in ("cash", "fcf", "conversion")):
            parts.append("Cash quality: " + "; ".join(brief["cash"]["notes"] or ["n/a"]))
        if any(k in q for k in ("bull", "bear", "risk", "thesis", "case")):
            parts.append("Bull: " + "; ".join(brief["bull_bear"]["bull"] or ["n/a"]))
            parts.append("Bear: " + "; ".join(brief["bull_bear"]["bear"] or ["n/a"]))
        if any(k in q for k in ("promis", "guid", "deliver", "narrative", "said", "management", "outlook")):
            try:
                promises = promises_vs_delivery(ticker)
                parts.append("Promised vs delivered (transcript quotes):")
                for call in promises.get("calls", [])[:3]:
                    if call.get("no_explicit_guidance"):
                        parts.append(f"- {call['call']}: management states it gives no explicit guidance.")
                    for quote in call.get("quotes", [])[:2]:
                        parts.append("- " + call["call"] + ': "' + quote + '"')
                    if call.get("error"):
                        parts.append(f"- {call['call']}: transcript unavailable ({call['error']})")
                if promises.get("latest_reported"):
                    m = promises["latest_reported"]
                    metrics = ", ".join(
                        f"{x['label']} {x['value']} (YoY {x['yoy']}%)"
                        for x in m.get("metrics", []) if x.get("yoy") is not None
                    )
                    parts.append(f"Latest reported {m.get('quarter')}: {metrics}")
            except Exception as exc:
                parts.append(f"Could not load concall transcripts yet: {str(exc)[:120]}")
        if len(parts) == 1:
            cards = ", ".join(
                f"{c['k']}: {c['v']}{c['u']}" for c in brief["financial"]["cards"] if c["v"] is not None
            )
            parts.append(brief["business"].get("about") or "")
            parts.append(f"Financial snapshot: {cards}")
            parts.append("Trajectory: " + "; ".join(brief["trajectory"]["notes"] or []))
            parts.append("Bull: " + "; ".join(brief["bull_bear"]["bull"] or []))
            parts.append("Bear: " + "; ".join(brief["bull_bear"]["bear"] or []))
        parts.append(
            "Grounding: standardised filing-derived statements / concall transcripts. "
            "Upload the original PDFs for page-cited deep research."
        )
        return {
            "ticker": ticker,
            "answer": "\n\n".join(p for p in parts if p),
            "sources": [{"document": "screener.in standardised filings", "page": "—", "excerpt": brief["grounding"]}],
            "grounded": True,
            "status": "brief_from_filings",
            "brief": brief,
        }

    context = "\n\n".join(
        f"[Source: {source['filename']}, page {source['page']}]\n{source['text']}"
        for source in sources
    )
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "ticker": ticker,
            "answer": (
                "Relevant source excerpts were retrieved. Add GEMINI_API_KEY to generate "
                "a synthesized answer. No unsupported conclusion has been generated."
            ),
            "sources": [
                {
                    "document": source["filename"],
                    "page": source["page"],
                    "excerpt": source["text"][:900],
                }
                for source in sources
            ],
            "grounded": True,
            "status": "retrieved_only",
        }

    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    prompt = (
        "You are FINN, an investment research assistant. Answer only from the primary-source "
        "excerpts below. Do not use outside knowledge or invent figures. If excerpts do not "
        "support an answer, say so. Distinguish management claims from reported facts. Cite "
        "every material claim using [filename, page N]. Do not give personalized buy/sell advice.\n\n"
        f"QUESTION: {req.question}\n\nPRIMARY SOURCES:\n{context}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
            },
        )
    if response.status_code >= 400:
        raise HTTPException(502, f"LLM provider error: {response.text[:250]}")
    body = response.json()
    answer = (
        body.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "No answer returned")
    )
    return {
        "ticker": ticker,
        "answer": answer,
        "sources": [
            {
                "document": source["filename"],
                "page": source["page"],
                "excerpt": source["text"][:500],
            }
            for source in sources
        ],
        "grounded": True,
        "status": "answered",
    }



class PortfolioAlertConfig(BaseModel):
    price_change_pct: float = Field(default=3.0, gt=0)
    volume_multiple: float = Field(default=2.0, gt=0)
    average_days: int = Field(default=20, ge=2, le=250)
    hours: int = Field(default=168, ge=1, le=720)
    filing_categories: list[str] = Field(
        default_factory=lambda: [
            "results", "M&A", "management_change", "fund_raise", "litigation", "dividend", "bonus_split", "pledging"
        ]
    )


@app.get("/api/research/brief/{ticker}")
def research_brief(ticker: str):
    """Structured Pull view for any NSE ticker from filing-derived statements."""
    symbol = _ticker(ticker)
    try:
        return company_brief(symbol)
    except Exception as exc:
        raise HTTPException(404, f"No fundamentals available for {symbol}: {str(exc)[:160]}")


@app.get("/api/research/promises/{ticker}")
def research_promises(ticker: str):
    symbol = _ticker(ticker)
    try:
        return promises_vs_delivery(symbol)
    except Exception as exc:
        raise HTTPException(502, f"Could not build promises vs delivery: {str(exc)[:180]}")


@app.post("/api/alerts/scan")
def scan_portfolio_alerts(config: PortfolioAlertConfig):
    """Portfolio-wide tripwires: unusual EOD moves + material filings."""
    alerts: list[dict[str, Any]] = []
    for company in PORTFOLIO:
        symbol = company["ticker"]
        try:
            data = market_data(symbol, average_days=config.average_days)
            reasons = []
            if abs(data["price_change_pct"]) >= config.price_change_pct:
                reasons.append(
                    f"Daily price move {data['price_change_pct']}% crossed ±{config.price_change_pct}%"
                )
            if data.get("volume_multiple") is not None and data["volume_multiple"] >= config.volume_multiple:
                reasons.append(
                    f"Volume {data['volume_multiple']}x vs {config.average_days}-day average"
                )
            if reasons:
                alerts.append({
                    "kind": "market",
                    "ticker": symbol,
                    "company": company["name"],
                    "reasons": reasons,
                    "score": 50 + 10 * len(reasons) + min(abs(data["price_change_pct"]), 10),
                    "market_data": data,
                })
        except Exception:
            continue

    digest = fetch_portfolio_announcements(
        tickers=[c["ticker"] for c in PORTFOLIO],
        hours=config.hours,
        include_routine=False,
    )
    watch = set(config.filing_categories)
    for item in digest.get("items", []):
        if item.get("category") in watch and item.get("priority") in {"high", "medium"}:
            full = item["ticker"] if str(item.get("ticker", "")).endswith(".NS") else f"{item.get('ticker')}.NS"
            alerts.append({
                "kind": "filing",
                "ticker": full,
                "company": item.get("company"),
                "reasons": [item.get("category")],
                "score": 70 if item.get("priority") == "high" else 55,
                "item": item,
            })
    alerts.sort(key=lambda a: -a["score"])
    return {"count": len(alerts), "alerts": alerts}