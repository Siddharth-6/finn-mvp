# ENAM submission — covering note (paste into email)

**To:** assessment@enam.com  
**Subject:** IIT Delhi – AI Engineer - 2027

## Links
- Prototype: https://finn-mvp.vercel.app/
- Repository: https://github.com/Siddharth-6/finn-mvp
- AI build history: <attach Cursor / ChatGPT export or share links>

## What I built
FINN is a mobile-first investment agent with Push and Pull:

**Push**
- Smart Digest: time-windowed portfolio filings (24h–30d), prioritised (high/medium/low), routine filter.
- When NSE blocks cloud IPs, FINN falls back to exchange filings indexed via screener.in (still primary exchange documents).
- Results filings expand into Revenue / EBITDA / PBT / PAT with QoQ and YoY.
- Management-change filings expand into person/role + LinkedIn lookup (no invented bios).
- Alerts: configurable ±% price and volume× thresholds; portfolio-wide scan also watches material filing categories.

**Pull**
- Research any NSE ticker (not hard-wired to the demo set).
- Structured brief from filing-derived standardised statements: snapshot, trajectory, balance sheet, cash quality, bull/bear.
- Eight research angles as prompts + “promised vs delivered” from concall transcripts vs latest reported quarter.
- PDF upload path remains available for page-cited deep research; Pull never uses news/broker notes.

## Key decisions / trade-offs
- Rules-first announcement classification (transparent, free, testable); LLM optional via GEMINI_API_KEY.
- Prefer empty/error over fake filings when live sources fail; demo cards only when explicitly requested.
- Screener used as an index / standardised-statement layer derived from filings — not as secondary commentary.
- Split deploy: FastAPI on Render, Next.js on Vercel with server-side `/api` rewrite.

## Deliberately left out
- True push notifications / email when the browser is closed.
- OCR for scanned PDFs.
- Persistent multi-user document store (in-memory index resets on backend restart).
- Fully automated management biographies (LinkedIn link only; no invented CV).

## Next
1. Stronger promise-hit scoring across quarters.
2. Durable document index + re-index on boot.
3. Cheaper model routing for bulk PDF extraction vs reasoning.