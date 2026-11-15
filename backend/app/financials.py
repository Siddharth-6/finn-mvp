"""Evidence-constrained extraction of quarterly headline financials."""
from __future__ import annotations

import json
import re
from typing import Any

METRICS = ("revenue", "ebitda", "pbt", "pat")
PERIODS = ("current_quarter", "previous_quarter", "year_ago_quarter")


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
Each non-null figure must include the source page number and a short verbatim evidence excerpt
that contains or directly labels the number. Use JSON null for unavailable values.
Return ONLY valid JSON with this schema:
{{
  "company": "{ticker}",
  "basis": "consolidated | standalone | unclear",
  "unit": "unit as printed, or null",
  "periods": {{
    "current_quarter": "period label or null",
    "previous_quarter": "period label or null",
    "year_ago_quarter": "period label or null"
  }},
  "metrics": {{
    "revenue": {{"current_quarter": {{"value": 0, "page": 1, "evidence": "..."}} or null, "previous_quarter": null, "year_ago_quarter": null}},
    "ebitda": {{"current_quarter": null, "previous_quarter": null, "year_ago_quarter": null}},
    "pbt": {{"current_quarter": null, "previous_quarter": null, "year_ago_quarter": null}},
    "pat": {{"current_quarter": null, "previous_quarter": null, "year_ago_quarter": null}}
  }}
}}

Source excerpts:
{excerpts}
"""


def _valid_observation(value: Any, allowed_pages: set[int]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    number = value.get("value")
    page = value.get("page")
    evidence = value.get("evidence")
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        return None
    if not isinstance(page, int) or page not in allowed_pages:
        return None
    if not isinstance(evidence, str) or len(evidence.strip()) < 5:
        return None
    return {"value": float(number), "page": page, "evidence": evidence.strip()[:500]}


def _pct_change(current: dict[str, Any] | None, comparison: dict[str, Any] | None) -> float | None:
    if not current or not comparison or comparison["value"] == 0:
        return None
    return round((current["value"] / comparison["value"] - 1) * 100, 2)


def validate_results_payload(payload: Any, ticker: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("The extraction response was not a JSON object.")
    allowed_pages = {int(source["page"]) for source in sources}
    raw_metrics = payload.get("metrics")
    if not isinstance(raw_metrics, dict):
        raise ValueError("The extraction response did not contain a metrics object.")

    metrics: dict[str, Any] = {}
    for metric in METRICS:
        raw = raw_metrics.get(metric, {})
        raw = raw if isinstance(raw, dict) else {}
        observations = {
            period: _valid_observation(raw.get(period), allowed_pages)
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
