# Deploy FINN

Recommended split deployment: FastAPI on Render and Next.js on Vercel.

## 1. Deploy the backend on Render

1. Push this repository to GitHub (the `render.yaml` Blueprint is at the repository root).
2. In Render, choose **New → Blueprint**, connect `Siddharth-6/finn-mvp`, and approve the detected `finn-api` web service.
3. Render will build from `backend/`, start Uvicorn on its assigned port, and check `/health`.
4. In the Render service settings, add `GEMINI_API_KEY` if you want AI-powered research synthesis and financial extraction. Keep the key secret; never commit it.
5. Wait for the service to become Live. Copy its public origin, e.g. `https://finn-api-xxxx.onrender.com`.
6. Verify `https://YOUR-RENDER-HOST/health` returns JSON with `"status":"ok"`.

## 2. Deploy the frontend on Vercel

1. In Vercel, choose **Add New → Project**, import `Siddharth-6/finn-mvp`.
2. Set **Root Directory** to `frontend`.
3. Keep the detected Next.js framework and default build command.
4. Add environment variable:
   - Name: `FINN_BACKEND_ORIGIN`
   - Value: the Render backend origin from step 1, without a trailing slash.
5. Deploy. The Next.js rewrite proxies `/health` and `/api/*` to FastAPI server-side, so the browser only needs the Vercel URL.

## 3. Verify

Open the Vercel URL and check:
- `/health` reports the backend is healthy.
- Overview loads portfolio data.
- Smart Digest clearly distinguishes live filings, demo examples, and upstream-source failures.
- Alerts, document upload, and research endpoints respond.

## Important prototype limitations

- Render's free service may sleep when idle; the first request after inactivity can be slow.
- Local uploaded-document storage and in-memory indexes are not durable across service restarts/redeploys on an ephemeral free instance. Do not use this deployment for important document storage.
- Yahoo Finance and NSE public interfaces are unofficial upstream sources and may rate-limit or change.
- The frontend is publicly accessible unless access protection is configured. Do not upload confidential company documents or expose API keys.
- FINN is an engineering prototype, not investment advice.
