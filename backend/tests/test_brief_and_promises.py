from app.screener_fundamentals import enrich_management_change, company_brief
from app.promises import guidance_quotes


def test_mgmt_enrichment_extracts_name():
    out = enrich_management_change(
        "Announcement under Regulation 30 (LODR)-Change in Management",
        "Shri Shrirang Anilrao Kothe appointed CEO of Helicopter Complex on 13 November 2026.",
        "HAL",
    )
    assert out["name"]
    assert out["linkedin"] and "linkedin.com" in out["linkedin"]


def test_guidance_quotes_and_disclaimer():
    text = (
        "This call may contain forward-looking statements. "
        "We expect revenue growth of 12% to 14% in the next fiscal year. "
        "We do not provide any specific revenue guidance as a matter of policy."
    )
    g = guidance_quotes(text)
    assert any("12% to 14%" in q for q in g["quotes"])
    assert g["no_explicit_guidance"]


def test_company_brief_tcs_smoke():
    brief = company_brief("TCS.NS")
    assert brief["name"]
    assert brief["financial"]["cards"]
    assert brief["results"] is None or brief["results"]["metrics"]