from fastapi.testclient import TestClient

from app.main import app, market_data

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_portfolio_has_eighteen_companies():
    response = client.get("/api/portfolio")
    assert response.status_code == 200
    assert response.json()["count"] == 18


def test_alert_manual_observations_do_not_call_market_provider(monkeypatch):
    def fail_if_called(_ticker):
        raise AssertionError("Manual alert evaluation must not call market data")

    monkeypatch.setattr("app.main.market_data", fail_if_called)
    response = client.post(
        "/api/alerts/evaluate",
        json={
            "ticker": "TCS.NS",
            "price_change_pct": 3,
            "volume_multiple": 2,
            "observed_price_change_pct": 4.5,
            "observed_volume_multiple": 2.8,
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["triggered"] is True
    assert result["evaluation_mode"] == "test_observations"
    assert len(result["reasons"]) == 2


def test_alert_manual_observations_no_trigger():
    response = client.post(
        "/api/alerts/evaluate",
        json={
            "ticker": "TCS.NS",
            "price_change_pct": 3,
            "volume_multiple": 2,
            "observed_price_change_pct": 1.2,
            "observed_volume_multiple": 1.4,
        },
    )
    assert response.status_code == 200
    assert response.json()["triggered"] is False


def test_announcement_examples_are_labelled_demo():
    response = client.get("/api/announcements")
    assert response.status_code == 200
    assert all(item["is_demo"] for item in response.json()["items"])
