# FINN — Financial Investment Intelligence

FINN is a mobile-first investment intelligence prototype for the ENAM AI Engineer Build Challenge. It separates **Push** workflows (portfolio monitoring, announcements and alerts) from **Pull** workflows (company research grounded in primary-source documents).

## Repository status

This repository is the canonical source for the project. The initial local prototype includes a Next.js frontend and FastAPI backend. The current MVP must clearly distinguish live provider data, cached data and illustrative demo content.

## Local development

### Backend (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. API docs: http://localhost:8000/docs.

## Data integrity

- Yahoo Finance through `yfinance` is an unofficial upstream source; it may rate-limit requests and does not guarantee real-time data.
- Announcement examples are illustrative until a verified NSE/BSE filing adapter is configured. Never present demo items as actual disclosures.
- Research answers must be grounded in uploaded primary-source documents, with page citations. Missing evidence must be stated.
- FINN is an engineering prototype, not investment advice.

## Planned engineering work

1. Cache and throttle market-data requests; expose freshness and provider status.
2. Keep alert evaluation independently testable using supplied observations, while retaining live evaluation mode.
3. Implement verified corporate-announcement ingestion with source URLs, timestamps and deduplication.
4. Persist uploaded documents and retrieval indexes.
5. Add automated tests and deployment configuration.

## Corporate announcement digest

The live digest is exposed at `GET /api/announcements`.

- `hours`: look-back window from 1 to 720 hours (default 24).
- `include_routine`: include low-priority/unclassified filings (default true).
- `demo=true`: explicitly request clearly labelled illustrative cards. Demo cards are never substituted into live mode.
- Live mode currently queries NSE's public corporate-announcements JSON endpoint and falls back to NSE's public RSS feed if the JSON source is unavailable.
- Results are restricted to the configured NSE portfolio, normalized, deduplicated, timestamp-filtered and sorted by FINN priority then recency.
- Each live item carries the exchange, source name, source page, and a validated NSE attachment URL when supplied.
- The first-pass category/priority classifier uses transparent keyword rules aligned to the ENAM companion reference. It is not an exchange label or an investment recommendation.
- The upstream endpoints are public website interfaces, not a guaranteed/licensed API. If both sources are unavailable, the API returns an empty result with `mode=source_unavailable`; it does not fabricate filings.

Example:

```text
GET http://localhost:8000/api/announcements?hours=24&include_routine=true
```

## Tests and CI

Run backend tests:

```powershell
cd backend
pip install -r requirements.txt
pytest -q
```

GitHub Actions runs backend tests and a frontend production build on pushes and pull requests to `main`.


## Quarterly results intelligence

1. Upload a company's quarterly results PDF in **Documents**, using its NSE/BSE ticker.
2. Select **Analyze uploaded quarterly results**.
3. When `GEMINI_API_KEY` is configured, FINN asks the configured Gemini model to extract Revenue, EBITDA, PBT and PAT for the current quarter, previous quarter and year-ago quarter.
4. FINN calculates QoQ and YoY percentage changes itself. Each observation is accepted only when the cited page exists in the uploaded document and the quoted evidence contains the reported number and matching source text.
5. Missing or unsupported periods remain blank. Verify every extracted value against the original filing before relying on it.

Without `GEMINI_API_KEY`, the endpoint returns relevant uploaded excerpts and does not invent extracted figures.

Endpoint: `POST /api/results/analyze` with JSON body `{"ticker":"TCS.NS"}`.

## Configurable market alerts

The Alerts screen lets the user select a portfolio ticker, configure a daily price-move threshold, a volume-multiple threshold, and a baseline window (2–250 trading days). Volume is compared with prior sessions only; the current session is excluded from its own baseline.

- `POST /api/alerts/evaluate` evaluates the selected ticker against the configured thresholds.
- `average_days` controls the volume baseline.
- Optional `observed_price_change_pct` and `observed_volume_multiple` fields provide deterministic simulation for testing; responses identify this as simulated data.
- This prototype evaluates on request; it does not yet run a persistent background watcher or send push notifications.

## Environment configuration

Set `GEMINI_API_KEY` in the backend environment to enable evidence-grounded synthesis and quarterly metric extraction. Optionally set `GEMINI_MODEL` to choose a supported Gemini model. Never commit API keys to Git.
