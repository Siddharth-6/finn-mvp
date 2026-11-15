from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app import announcements as feed
from app.main import app

client = TestClient(app)


def test_classifier_maps_enam_categories():
    assert feed.classify_announcement("Board approved quarterly financial results")[0] == "results"
    assert feed.classify_announcement("Appointment of Chief Financial Officer")[0] == "management_change"
    assert feed.classify_announcement("Routine compliance certificate")[0] == "unclassified"


def test_normalize_nse_row_creates_real_source_metadata():
    row = {
        "symbol": "TCS",
        "sm_name": "Tata Consultancy Services",
        "desc": "Outcome of Board Meeting - Financial Results",
        "attchmntText": "The board considered quarterly results.",
        "sort_date": "14-Nov-2026 18:30:00",
        "attchmntFile": "https://nsearchives.nseindia.com/corporate/x.pdf",
        "seq_id": "12345",
    }
    item = feed._normalize_nse_row(row)
    assert item is not None
    assert item["ticker"] == "TCS"
    assert item["category"] == "results"
    assert item["priority"] == "high"
    assert item["is_demo"] is False
    assert item["source_url"].startswith("https://nsearchives.nseindia.com/")


def test_reject_non_nse_attachment_url():
    assert feed._safe_attachment("https://example.com/file.pdf") is None
    assert feed._safe_attachment("javascript:alert(1)") is None


def test_digest_filters_to_portfolio_and_time_window(monkeypatch):
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    rows = [
        {
            "id": "new",
            "exchange": "NSE",
            "ticker": "TCS",
            "company": "Tata Consultancy Services",
            "category": "results",
            "title": "Quarterly results",
            "summary": "Results filed",
            "priority": "high",
            "published_at": (now - timedelta(hours=2)).isoformat(),
            "source_url": None,
            "source_name": "NSE corporate filings",
            "is_demo": False,
        },
        {
            "id": "old",
            "exchange": "NSE",
            "ticker": "INFY",
            "company": "Infosys",
            "category": "results",
            "title": "Old results",
            "summary": "Old filing",
            "priority": "high",
            "published_at": (now - timedelta(hours=50)).isoformat(),
            "source_url": None,
            "source_name": "NSE corporate filings",
            "is_demo": False,
        },
        {
            "id": "other",
            "exchange": "NSE",
            "ticker": "UNKNOWN",
            "company": "Unknown",
            "category": "results",
            "title": "Other company",
            "summary": "Not in portfolio",
            "priority": "high",
            "published_at": (now - timedelta(hours=1)).isoformat(),
            "source_url": None,
            "source_name": "NSE corporate filings",
            "is_demo": False,
        },
    ]
    monkeypatch.setattr(feed, "_fetch_nse_json", lambda start, end, symbols: rows)
    result = feed.fetch_portfolio_announcements(["TCS.NS", "INFY.NS"], hours=24)
    assert result["mode"] == "live"
    assert [item["id"] for item in result["items"]] == ["new"]


def test_live_digest_is_default_and_does_not_substitute_demo(monkeypatch):
    from app import main

    monkeypatch.setattr(
        main,
        "fetch_portfolio_announcements",
        lambda **kwargs: {
            "items": [],
            "mode": "source_unavailable",
            "source": None,
            "errors": ["upstream unavailable"],
        },
    )
    main.ANNOUNCEMENT_CACHE.clear()
    response = client.get("/api/announcements?hours=24")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "source_unavailable"
    assert payload["items"] == []
    assert not any(item.get("is_demo") for item in payload["items"])


def test_demo_cards_require_explicit_opt_in():
    response = client.get("/api/announcements?demo=true")
    assert response.status_code == 200
    assert response.json()["mode"] == "demo_examples"
    assert all(item["is_demo"] for item in response.json()["items"])


def test_announcement_window_validation():
    assert client.get("/api/announcements?hours=0").status_code == 400
    assert client.get("/api/announcements?hours=721").status_code == 400
