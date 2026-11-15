from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_alert_evaluation_uses_configured_average_days(monkeypatch):
    seen = {}

    def fake_market_data(ticker, average_days=20):
        seen["ticker"] = ticker
        seen["average_days"] = average_days
        return {
            "ticker": ticker,
            "price_change_pct": 4.2,
            "volume_multiple": 2.4,
            "source": "test",
        }

    monkeypatch.setattr(main, "market_data", fake_market_data)
    response = client.post(
        "/api/alerts/evaluate",
        json={
            "ticker": "TCS.NS",
            "price_change_pct": 3,
            "volume_multiple": 2,
            "average_days": 10,
        },
    )
    assert response.status_code == 200
    assert seen == {"ticker": "TCS.NS", "average_days": 10}
    assert response.json()["triggered"] is True


def test_alert_evaluation_supports_deterministic_simulation():
    response = client.post(
        "/api/alerts/evaluate",
        json={
            "ticker": "INFY.NS",
            "price_change_pct": 3,
            "volume_multiple": 2,
            "observed_price_change_pct": -4.5,
            "observed_volume_multiple": 1.1,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["triggered"] is True
    assert payload["evaluation_mode"] == "test_observations"
    assert payload["market_data"]["is_simulated"] is True


def test_market_average_days_validation():
    response = client.get("/api/market/TCS.NS?average_days=1")
    assert response.status_code == 400


def test_results_endpoint_requires_uploaded_primary_source():
    main.DOCUMENTS.clear()
    response = client.post("/api/results/analyze", json={"ticker": "TCS.NS"})
    assert response.status_code == 200
    assert response.json()["status"] == "needs_documents"


def test_results_filing_rejects_non_nse_url_before_network_access():
    response = client.post(
        "/api/results/analyze-filing",
        json={"ticker": "TCS.NS", "source_url": "https://example.com/results.pdf"},
    )
    assert response.status_code == 400
