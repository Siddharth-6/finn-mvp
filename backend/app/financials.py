"""Evidence-constrained extraction of quarterly headline financials."""
from __future__ import annotations

import json
import re
from typing import Any

METRICS = ("revenue", "ebitda", "pbt", "pat")
PERIODS = ("current_quarter", "previous_quarter", "year_ago_quarter")


def rank_financial_chunks(sources: list[dict[str, Any]], limit: int = 30) -> list[dict[str, Any]]:
    """Prefer statement pages containing headline metrics and period labels."""
    patterns = (
        r"revenue|income from operations|total income",
        r"ebitda|operating profit",
        r"profit before tax|\\bpbt\\b",
        r"profit after tax|\\bpat\\b|net profit",
        r"quarter ended|three months ended|year ended",
        r"consolidated|standalone",
    )
    ranked = []
    for index, source in enumerate(sources):
        text = source.get("text", "").lower()
        score = sum(len(re.findall(pattern, text, flags=re.IGNORECASE)) for pattern in patterns)
        ranked.append((score, -index, source))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    chosen = [item[2] for item in ranked[:limit]]
    return sorted(chosen, key=lambda item: (int(item.get("page", 0)), item.get("filename", "")))


def build_results_prompt(ticker: str, sources: list[dict[str, Any]]) -> str:
    excerpts = "\n\n".join(
        f"[SOURCE: {s['filename']} | PAGE: {s['page']}]\n{s['text']}"
        for s in sources
    )
    return f"""You extract reported financial figures from primary-source company documents.
Ticker: {ticker}

Extract only Revenue, EBITDA, PBT and PAT for the latest quarter explicitly reported in these excerpts.
For each metric, provide the current quarter, immediately previous quarter (QoQ comparator), and
same quarter one year earlier (YoY comparator), but ONLY when the exact figure is present in the
provided excerpts. Do not calculate or infer missing source values. Preserve the unit exactly as
reported (for example INR crore, INR million, or INR lakh). Do not mix standalone and consolidated
figures; prefer consolidated if clearly labelled, otherwise use the clearly identified statement
basis and state it in basis. If the basis is ambiguous, set basis to "unclear".
Each non-null figure must be an object with numeric value, source page number, and a short
verbatim evidence excerpt containing the number. Use JSON null for unavailable values.
Return ONLY valid JSON with this schema:
{{
  "company": "{ticker}",
  "basis": "consolidated",
  "unit": "INR crore",
  "periods": {{
    "current_quarter": "Q2 FY27",
    "previous_quarter": "Q1 FY27",
    "year_ago_quarter": "Q2 FY26"
  }},
  "metrics": {{
    "revenue": {{"current_quarter": null, "previous_quarter": null, "year_ago_quarter": null}},
    "ebitda": {{"current_quarter": null, "previous_quarter": null, "year_ago_quarter": null}},
    "pbt": {{"current_quarter": null, "previous_quarter": null, "year_ago_quarter": null}},
    "pat": {{"current_quarter": null, "previous_quarter": null, "year_ago_quarter": null}}
  }}
}}

Source excerpts:
{excerpts}
"""


def _valid_observation(value: Any, page_texts: dict[int, str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    number = value.get("value")
    page = value.get("page")
    evidence = value.get("evidence")
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        return None
    if not isinstance(page, int) or page not in page_texts:
        return None
    if not isinstance(evidence, str) or len(evidence.strip()) < 5:
        return None

    # Require the reported number and most evidence words to occur on the
    # cited uploaded page. This rejects unsupported model-generated values.
    digits = re.sub(r"\D", "", f"{number:g}")
    evidence_digits = re.sub(r"\D", "", evidence)
    if not digits or digits not in evidence_digits:
        return None
    evidence_words = set(re.findall(r"[a-z0-9]+", evidence.lower()))
    source_words = set(re.findall(r"[a-z0-9]+", page_texts[page].lower()))
    if len(evidence_words) < 2 or len(evidence_words & source_words) / len(evidence_words) < 0.5:
        return None
    return {"value": float(number), "page": page, "evidence": evidence.strip()[:500]}


def _pct_change(current: dict[str, Any] | None, comparison: dict[str, Any] | None) -> float | None:
    if not current or not comparison or comparison["value"] == 0:
        return None
    return round((current["value"] / comparison["value"] - 1) * 100, 2)


def validate_results_payload(payload: Any, ticker: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("The extraction response was not a JSON object.")
    page_texts: dict[int, str] = {}
    for source in sources:
        page = int(source["page"])
        page_texts[page] = page_texts.get(page, "") + " " + source["text"]
    raw_metrics = payload.get("metrics")
    if not isinstance(raw_metrics, dict):
        raise ValueError("The extraction response did not contain a metrics object.")

    metrics: dict[str, Any] = {}
    for metric in METRICS:
        raw = raw_metrics.get(metric, {})
        raw = raw if isinstance(raw, dict) else {}
        observations = {
            period: _valid_observation(raw.get(period), page_texts)
            for period in PERIODS
        }
        metrics[metric] = {
            **observations,
            "qoq_change_pct": _pct_change(observations["current_quarter"], observations["previous_quarter"]),
            "yoy_change_pct": _pct_change(observations["current_quarter"], observations["year_ago_quarter"]),
        }

    periods = payload.get("periods") if isinstance(payload.get("periods"), dict) else {}
    return {
        "ticker": ticker,
        "basis": payload.get("basis") if payload.get("basis") in {"consolidated", "standalone", "unclear"} else "unclear",
        "unit": payload.get("unit") if isinstance(payload.get("unit"), str) else None,
        "periods": {period: periods.get(period) if isinstance(periods.get(period), str) else None for period in PERIODS},
        "metrics": metrics,
        "source_documents": sorted({source["filename"] for source in sources}),
        "method": "llm_extraction_validated_against_uploaded_source_pages",
        "disclaimer": "Extracted figures are a first-pass aid. Verify every value against the cited original filing before relying on it.",
    }


def parse_model_json(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", cleaned, flags=re.IGNORECASE)
    return json.loads(cleaned)
