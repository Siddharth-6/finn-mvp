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
