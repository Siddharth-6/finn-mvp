import pytest

from app.financials import parse_model_json, rank_financial_chunks, validate_results_payload


def test_results_extraction_calculates_qoq_and_yoy_from_source_values():
    sources = [
        {"filename": "results.pdf", "page": 4, "text": "Revenue 1200"},
        {"filename": "results.pdf", "page": 5, "text": "Revenue 1000"},
        {"filename": "results.pdf", "page": 6, "text": "Revenue 900"},
    ]
    payload = {
        "basis": "consolidated",
        "unit": "INR crore",
        "periods": {
            "current_quarter": "Q2 FY27",
            "previous_quarter": "Q1 FY27",
            "year_ago_quarter": "Q2 FY26",
        },
        "metrics": {
            "revenue": {
                "current_quarter": {"value": 1200, "page": 4, "evidence": "Revenue 1200"},
                "previous_quarter": {"value": 1000, "page": 5, "evidence": "Revenue 1000"},
                "year_ago_quarter": {"value": 900, "page": 6, "evidence": "Revenue 900"},
            }
        },
    }
    result = validate_results_payload(payload, "TCS.NS", sources)
    assert result["metrics"]["revenue"]["qoq_change_pct"] == 20.0
    assert result["metrics"]["revenue"]["yoy_change_pct"] == 33.33
    assert result["basis"] == "consolidated"


def test_results_extraction_discards_observations_from_uncited_pages():
    sources = [{"filename": "results.pdf", "page": 2, "text": "PAT 80"}]
    payload = {
        "metrics": {
            "pat": {
                "current_quarter": {"value": 80, "page": 99, "evidence": "PAT 80"},
                "previous_quarter": {"value": 40, "page": 2, "evidence": "PAT 40"},
            }
        }
    }
    result = validate_results_payload(payload, "INFY.NS", sources)
    assert result["metrics"]["pat"]["current_quarter"] is None
    assert result["metrics"]["pat"]["qoq_change_pct"] is None


def test_results_extraction_handles_zero_comparison_without_division():
    sources = [{"filename": "results.pdf", "page": 1, "text": "PAT 10"}]
    payload = {
        "metrics": {
            "pat": {
                "current_quarter": {"value": 10, "page": 1, "evidence": "PAT 10"},
                "previous_quarter": {"value": 0, "page": 1, "evidence": "PAT 0"},
            }
        }
    }
    result = validate_results_payload(payload, "SBIN.NS", sources)
    assert result["metrics"]["pat"]["qoq_change_pct"] is None


def test_model_json_parser_accepts_fenced_json():
    assert parse_model_json('```json\n{"ok": true}\n```') == {"ok": True}


def test_model_json_parser_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_model_json("not json")


def test_financial_chunk_ranker_prioritizes_statement_pages():
    sources = [
        {"filename": "annual.pdf", "page": 1, "text": "Company overview and management letter."},
        {"filename": "annual.pdf", "page": 42, "text": "Consolidated statement: Revenue from operations EBITDA Profit before tax Profit after tax for quarter ended."},
        {"filename": "annual.pdf", "page": 3, "text": "Board members and registered office."},
    ]
    ranked = rank_financial_chunks(sources, limit=2)
    assert [item["page"] for item in ranked] == [42, 1]
