from app.sources import extract_primary_document_links


def test_screener_source_parser_keeps_primary_document_links():
    html = """
    <a href="https://www.example.com/investor/annual-report-2025.pdf">Annual Report 2025</a>
    <a href="/company/TCS/concall/">Concall Transcripts</a>
    <a href="https://news.example.com/story">News</a>
    <a href="javascript:alert(1)">Investor Presentation</a>
    """
    links = extract_primary_document_links(html, "https://www.screener.in/company/TCS/")
    assert len(links) == 2
    assert {item["category"] for item in links} == {"annual_report", "concall_transcript"}
    assert next(item for item in links if item["category"] == "annual_report")["host"] == "www.example.com"


def test_screener_source_parser_allows_pdf_link_on_screener_host():
    html = '<a href="/uploads/annual-report.pdf">Annual Report PDF</a>'
    links = extract_primary_document_links(html, "https://www.screener.in/company/TCS/")
    assert len(links) == 1
    assert links[0]["url"].endswith("annual-report.pdf")
