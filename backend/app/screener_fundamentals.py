"""Pull-side fundamentals from screener.in standardised statements (filing-derived).

Used so research works cold without a manual PDF upload, while staying on
primary-derived numbers rather than news or broker notes.
"""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import quote, quote_plus

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
CACHE: dict[str, dict[str, Any]] = {}
TTL = 6 * 60 * 60


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").replace("₹", "").strip()
    if text in {"", "-", "—"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _slug(ticker: str) -> str:
    return re.sub(r"\.(NS|BO)$", "", ticker.upper().strip())


def _table(html: str, section_id: str) -> dict[str, Any]:
    start = html.find(f'id="{section_id}"')
    if start < 0:
        return {"cols": [], "rows": {}}
    # Screener wraps statements in div.card, not <section>.
    block = html[start:start + 40000]
    table_match = re.search(r"<table.*?</table>", block, re.I | re.S)
    if not table_match:
        return {"cols": [], "rows": {}}
    table = table_match.group(0)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.I | re.S):
        cells = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip()
            for cell in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.I | re.S)
        ]
        if cells:
            rows.append(cells)
    if not rows:
        return {"cols": [], "rows": {}}
    cols = rows[0][1:]
    out_rows: dict[str, list[float | None]] = {}
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        label = row[0].replace(" ", " ").replace("&nbsp;", " ")
        label = re.sub(r"\s*\+$", "", label).strip()
        out_rows[label] = [_num(x) for x in row[1:]]
    return {"cols": cols, "rows": out_rows}


def _year_idxs(cols: list[str]) -> list[int]:
    return [i for i, c in enumerate(cols) if c != "TTM"]


def _cagr(start: float | None, end: float | None, years: int) -> float | None:
    if start is None or end is None or start <= 0 or end <= 0 or years <= 0:
        return None
    return round(((end / start) ** (1 / years) - 1) * 100, 1)


def _load_html(ticker: str) -> str:
    slug = _slug(ticker)
    with httpx.Client(headers={"User-Agent": UA}, timeout=25, follow_redirects=True) as client:
        for path in (f"/company/{quote(slug)}/consolidated/", f"/company/{quote(slug)}/"):
            response = client.get(f"https://www.screener.in{path}")
            if response.status_code == 200 and "quarters" in response.text:
                return response.text
        response.raise_for_status()
        return response.text


def company_brief(ticker: str) -> dict[str, Any]:
    symbol = ticker.upper().strip()
    cached = CACHE.get(symbol)
    now = time.time()
    if cached and now - cached["at"] < TTL:
        return cached["data"]

    html = _load_html(symbol)
    name_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    name = re.sub(r"<[^>]+>", "", name_match.group(1)).strip() if name_match else _slug(symbol)
    about_match = re.search(r'class="[^"]*about[^"]*"[^>]*>(.*?)</div>', html, re.I | re.S)
    about = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", about_match.group(1))).strip() if about_match else ""

    top: dict[str, float | None] = {}
    for li in re.findall(r"<li[^>]*>\s*<span[^>]*class=\"name\"[^>]*>(.*?)</span>\s*<span[^>]*class=\"value\"[^>]*>(.*?)</span>", html, re.I | re.S):
        label = re.sub(r"<[^>]+>", "", li[0]).strip()
        number = re.search(r'class="number"[^>]*>(.*?)<', li[1], re.I | re.S)
        top[label] = _num(number.group(1) if number else re.sub(r"<[^>]+>", "", li[1]))

    quarters = _table(html, "quarters")
    annual = _table(html, "profit-loss")
    balance = _table(html, "balance-sheet")
    cashflow = _table(html, "cash-flow")
    ratios = _table(html, "ratios")

    yidx = _year_idxs(annual.get("cols", []))
    li = yidx[-1] if yidx else None
    sales = annual.get("rows", {}).get("Sales") or annual.get("rows", {}).get("Revenue") or []
    pat = annual.get("rows", {}).get("Net Profit") or []
    opm = annual.get("rows", {}).get("OPM %") or []
    eps = annual.get("rows", {}).get("EPS in Rs") or []

    financial = {
        "year": annual["cols"][li] if li is not None else None,
        "cards": [
            {"k": "Revenue", "v": sales[li] if li is not None and li < len(sales) else None, "u": "Rs Cr"},
            {"k": "EBITDA margin", "v": opm[li] if li is not None and li < len(opm) else None, "u": "%"},
            {"k": "PAT", "v": pat[li] if li is not None and li < len(pat) else None, "u": "Rs Cr"},
            {"k": "EPS", "v": eps[li] if li is not None and li < len(eps) else None, "u": "Rs"},
            {"k": "ROCE", "v": top.get("ROCE"), "u": "%"},
            {"k": "ROE", "v": top.get("ROE"), "u": "%"},
            {"k": "P/E", "v": top.get("Stock P/E"), "u": "x"},
            {"k": "Div yield", "v": top.get("Dividend Yield"), "u": "%"},
        ],
    }

    use = yidx[-6:] if yidx else []
    cols = [annual["cols"][i] for i in use]
    series = {
        "Revenue": [sales[i] if i < len(sales) else None for i in use],
        "PAT": [pat[i] if i < len(pat) else None for i in use],
        "EBITDA margin %": [opm[i] if i < len(opm) else None for i in use],
    }
    years = max(len(use) - 1, 1)
    notes = []
    if len(series["Revenue"]) > 1:
        c = _cagr(series["Revenue"][0], series["Revenue"][-1], years)
        if c is not None:
            notes.append(f"Revenue CAGR {c}% over {years}y")
    if len(series["PAT"]) > 1:
        c = _cagr(series["PAT"][0], series["PAT"][-1], years)
        if c is not None:
            notes.append(f"PAT CAGR {c}% over {years}y")
    if len(series["EBITDA margin %"]) > 1 and None not in (series["EBITDA margin %"][0], series["EBITDA margin %"][-1]):
        dm = series["EBITDA margin %"][-1] - series["EBITDA margin %"][0]
        notes.append(
            f"EBITDA margin {'expanded' if dm > 0 else 'compressed'} {abs(dm):.1f}pp "
            f"({series['EBITDA margin %'][0]:.0f}% to {series['EBITDA margin %'][-1]:.0f}%)"
        )

    bcols = balance.get("cols", [])
    brows = balance.get("rows", {})
    bi = len(bcols) - 1 if bcols else -1
    def cell(series, idx):
        if idx < 0 or not series or idx >= len(series):
            return None
        return series[idx]
    equity_cap = cell(brows.get("Equity Capital") or [], bi) or 0
    reserves = cell(brows.get("Reserves") or [], bi) or 0
    equity = equity_cap + reserves
    debt = cell(brows.get("Borrowings") or [], bi) if bi >= 0 else None
    de = round(debt / equity, 2) if debt is not None and equity else None
    ccc = ratios.get("rows", {}).get("Cash Conversion Cycle") or []
    balance_out = {
        "year": bcols[bi] if bi >= 0 else None,
        "borrowings": debt,
        "net_worth": round(equity) if equity else None,
        "debt_to_equity": de,
        "debtor_days": (ratios.get("rows", {}).get("Debtor Days") or [None])[-1:],
        "ccc_trend": ccc[-5:],
        "cols": bcols[-5:],
        "notes": (
            ["Effectively debt-free" if de is not None and de < 0.1 else f"Debt/equity {de}x"]
            if de is not None else []
        ),
    }

    cf_cols = cashflow.get("cols", [])
    cfo = cashflow.get("rows", {}).get("Cash from Operating Activity") or []
    fcf = cashflow.get("rows", {}).get("Free Cash Flow") or []
    n = min(5, len(cf_cols))
    conv = []
    for c, v in zip(cf_cols[-n:], cfo[-n:]):
        p = None
        if c in annual.get("cols", []):
            idx = annual["cols"].index(c)
            p = pat[idx] if idx < len(pat) else None
        conv.append(round(v / p * 100) if v is not None and p else None)
    valid = [x for x in conv if x is not None]
    cash_notes = []
    if valid:
        avg = sum(valid) / len(valid)
        cash_notes.append(
            f"Operating cash flow averaged {avg:.0f}% of PAT over {len(valid)}y: "
            + ("profits convert well to cash." if avg >= 85 else "weak conversion." if avg < 60 else "adequate conversion.")
        )
    if fcf[-n:] and all(x is not None and x > 0 for x in fcf[-n:]):
        cash_notes.append("Free cash flow positive every year in the window.")

    bull, bear = [], []
    roce = top.get("ROCE")
    if roce and roce >= 20:
        bull.append(f"High return on capital: ROCE {roce:.0f}%.")
    if de is not None and de < 0.2:
        bull.append("Balance sheet is clean: negligible debt.")
    if valid and sum(valid) / len(valid) >= 90:
        bull.append(f"Earnings are real: operating cash ~{sum(valid)/len(valid):.0f}% of PAT.")
    pe = top.get("Stock P/E")
    rev_cagr = _cagr(series["Revenue"][0], series["Revenue"][-1], years) if len(series["Revenue"]) > 1 else None
    if pe and pe > 50:
        bear.append(f"Priced for perfection: P/E {pe:.0f}x.")
    if pe and pe < 18 and rev_cagr and rev_cagr > 10:
        bull.append(f"Growth at a modest price: P/E {pe:.0f}x.")
    if rev_cagr is not None and rev_cagr < 8:
        bear.append(f"Slow top line: revenue CAGR only {rev_cagr}% over {years}y.")
    if de is not None and de > 1:
        bear.append(f"Leverage: debt/equity {de}x.")

    # Latest quarterly results card (for Push enrichment / Pull financial snapshot)
    qcols = quarters.get("cols", [])
    qrows = quarters.get("rows", {})
    results = None
    if qcols:
        qi = len(qcols) - 1
        def qget(keys: list[str]):
            for key in keys:
                if key in qrows:
                    return qrows[key]
            return []
        def pct(a, b):
            if a is None or b in (None, 0):
                return None
            return round((a / abs(b) - 1) * 100, 1)
        rev = qget(["Sales", "Revenue"])
        ebitda = qget(["Operating Profit", "Financing Profit"])
        pbt = qget(["Profit before tax"])
        qpat = qget(["Net Profit"])
        metrics = []
        for key, label, series_ in [
            ("revenue", "Revenue", rev),
            ("ebitda", "EBITDA", ebitda),
            ("pbt", "PBT", pbt),
            ("pat", "PAT", qpat),
        ]:
            if not series_ or qi >= len(series_):
                continue
            cur = series_[qi]
            metrics.append({
                "key": key,
                "label": label,
                "value": cur,
                "qoq": pct(cur, series_[qi - 1] if qi >= 1 else None),
                "yoy": pct(cur, series_[qi - 4] if qi >= 4 else None),
            })
        results = {
            "quarter": qcols[qi],
            "unit": "Rs Cr",
            "metrics": metrics,
            "source": "screener.in standardised quarterly financials (filing-derived)",
        }

    payload = {
        "ticker": symbol,
        "name": name,
        "business": {"about": about},
        "financial": financial,
        "trajectory": {"cols": cols, "series": series, "notes": notes},
        "balance": balance_out,
        "cash": {
            "cols": cf_cols[-n:],
            "cfo": cfo[-n:],
            "fcf": fcf[-n:],
            "cfo_to_pat_pct": conv,
            "notes": cash_notes,
        },
        "bull_bear": {"bull": bull[:4], "bear": bear[:4]},
        "results": results,
        "grounding": "Standardised statements derived from filings via screener.in. No news or broker notes.",
    }
    CACHE[symbol] = {"at": now, "data": payload}
    return payload


def enrich_management_change(title: str, summary: str, company: str) -> dict[str, Any]:
    text = f"{title}. {summary}"
    match = re.search(
        r"(?:appoint\w*|approved|reappointed|named)\s+(?:of\s+)?((?:Shri|Mr\.?|Ms\.?|Dr\.?|Smt\.?)?\s*[A-Z][\w\.]+(?:\s+[A-Z][\w\.]+){0,3})\s+(?:as|to)\s+([^.,;]+)",
        text,
    )
    name = match.group(1).strip() if match else None
    role = match.group(2).strip() if match else None
    if not name:
        match = re.search(r"([A-Z][\w\.]+(?:\s+[A-Z][\w\.]+){1,3})\s+(?:resign|appointed|reappointed)", text)
        name = match.group(1) if match else None
    linkedin = None
    if name:
        linkedin = "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(f"{name} {company}")
    return {
        "name": name,
        "role": role,
        "linkedin": linkedin,
        "bio_note": "Open LinkedIn to verify background. FINN does not invent biographies.",
    }