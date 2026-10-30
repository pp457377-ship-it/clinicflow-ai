# Deployment Guide

## Option 1 - Run locally (2 minutes)
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
# optional: paste a free Gemini key into .env -> GEMINI_API_KEY=...
uvicorn app.main:app --reload
```
Open http://localhost:8000 (patient), http://localhost:8000/admin (staff, password from `ADMIN_PASSWORD`),
http://localhost:8000/docs (API docs).

Without a key the app runs in **offline demo mode** (rule engine). With a key the header shows `AI: gemini (prompt v3)`.

Get a free Gemini key: https://aistudio.google.com/app/apikey

## Option 2 - Docker
```bash
cp .env.example .env
docker compose up --build
```
Data is kept in the `clinicflow-data` Docker volume.

## Option 3 - Free public hosting on Render (live link for the submission)
1. Create a GitHub repository and push this folder:
   ```bash
   git remote add origin https://github.com/<you>/clinicflow-ai.git
   git push -u origin main
   ```
2. Go to https://dashboard.render.com -> **New +** -> **Blueprint** -> pick the repo. Render reads `render.yaml`.
3. When asked, paste your `GEMINI_API_KEY`. `ADMIN_PASSWORD` is generated automatically - copy it from the
   service's **Environment** tab.
4. Wait for the build (about 3 min). Your link looks like `https://clinicflow-ai-xxxx.onrender.com`.
5. Check `https://<your-url>/api/health` returns `{"status":"ok"}`.

Notes: the free plan sleeps after 15 min idle (first request takes ~30-50 s to wake up), and its disk is not
persistent, so the SQLite demo data resets on redeploy. That is fine for a demo. For production, add a Render disk
mounted at `/app/data` or switch to PostgreSQL.

Alternatives that also work with the Dockerfile: Railway, Fly.io, Google Cloud Run, Azure Container Apps.

## Environment variables
| Variable | Default | Meaning |
|---|---|---|
| `AI_PROVIDER` | `auto` | `auto`, `gemini`, `openai` or `offline` |
| `GEMINI_API_KEY` | - | Google AI Studio key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Any Gemini model name |
| `OPENAI_API_KEY` | - | OpenAI (or Groq) key |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Set to `https://api.groq.com/openai/v1` for Groq |
| `ADMIN_PASSWORD` | `admin123` | Staff dashboard password - **change it** |
| `DATABASE_PATH` | `data/clinicflow.db` | SQLite file |
| `CLINIC_NAME` | `Robina 7 Day Doctors (Demo)` | Shown in the header and confirmations |
| `CLINIC_TIMEZONE` | `Australia/Brisbane` | Time zone for appointment slots |
