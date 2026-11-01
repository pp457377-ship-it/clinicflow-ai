# ClinicFlow AI - AI Patient Intake & Appointment Automation for GP Clinics

> Patients describe symptoms in their own words -> AI writes a structured note for the doctor and sets the urgency
> -> safety rules catch emergencies -> the patient books the right appointment -> staff see a queue sorted by urgency.

Built for the **Gokul Infocare - AI Growth & Automation Associate** assessment (Task 1). Domain: **Healthcare**.
Areas covered: **Web application + AI automation + innovation**.

![Patient AI assessment](docs/screenshots/2-ai-assessment.png)

## Features
- **AI triage**: Google Gemini (or OpenAI/Groq) turns free text into JSON: urgency, clinical summary, key symptoms,
  suggested appointment type, questions for the doctor and a friendly patient message.
- **Adaptive AI interview**: the AI asks the patient 1-3 follow-up questions, then re-triages with the answers -
  a red flag revealed in an answer still escalates to emergency. Answers are shown to staff on the dashboard.
- **Safety first**: rule-based red-flag detector (chest pain, stroke, breathing, bleeding, anaphylaxis, suicide)
  always overrides the AI, shows "Call 000" and blocks online booking.
- **Smart booking**: urgent patients only see today's and tomorrow's slots; no double-booking.
- **Email confirmations**: staff approve a booking in the dashboard -> the patient gets a confirmation email (SMTP).
- **Staff dashboard**: staff accounts with login, stats, queue sorted by urgency, patient detail,
  add/edit/delete records and status updates.
- **Reliable AI**: JSON mode + schema validation + retry + offline fallback engine. Works even without an API key.
- **Prompt-injection defence** and a **prompt evaluation script** (12 cases, unsafe under-triage must be 0).
- **Production basics**: Docker (non-root, health check), `render.yaml` one-click deploy, GitHub Actions CI, 28 tests.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env            # optional: add GEMINI_API_KEY (free at https://aistudio.google.com/app/apikey)
uvicorn app.main:app --reload
```
- Patient app: http://localhost:8000
- Staff dashboard: http://localhost:8000/admin (log in as `admin` / `ADMIN_PASSWORD`, default `admin123`)
- API docs: http://localhost:8000/docs

Or with Docker: `docker compose up --build`

Run tests and the prompt evaluation:
```bash
pytest -q
python scripts/evaluate.py
```

## Architecture
```mermaid
flowchart LR
    P[Patient web form] --> API[FastAPI]
    API --> R[Safety rules]
    API --> AI{Gemini / OpenAI / offline}
    AI --> V[Validate JSON]
    R --> O[Safety override]
    V --> O --> DB[(SQLite)]
    O --> P
    P -->|book slot| DB
    DB --> D[Staff dashboard]
```
Tech: Python 3.12, FastAPI, Pydantic, httpx, SQLite, vanilla HTML/CSS/JS, Docker. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

```
app/
  main.py        API endpoints + pages
  ai_engine.py   LLM calls, JSON parsing, fallback, safety override
  prompts.py     versioned system prompt (v3)
  safety.py      red-flag rules
  database.py    SQLite
  slots.py       appointment slots (clinic time zone)
  config.py      env-based settings
static/          patient page + staff dashboard
tests/           pytest suite
scripts/         prompt evaluation
docs/            architecture, deployment, screenshots
```

## Screenshots
| Intake | Emergency detected | Staff dashboard |
|---|---|---|
| ![](docs/screenshots/1-intake-form.png) | ![](docs/screenshots/4-emergency-detected.png) | ![](docs/screenshots/5-staff-dashboard.png) |

## Documentation
- [Architecture](docs/ARCHITECTURE.md)
- [Deployment guide](docs/DEPLOYMENT.md) (local, Docker, Render)

## Disclaimer
ClinicFlow AI does not diagnose and is not a medical device. In an emergency in Australia call **000**.
