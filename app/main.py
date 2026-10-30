"""FastAPI application: JSON API + the static web pages."""

import logging
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, database
from .ai_engine import analyze_intake
from .config import get_settings
from .models import BookingRequest, BookingResponse, IntakeRequest, IntakeResponse, StatusUpdate
from .prompts import PROMPT_VERSION
from .slots import generate_slots

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("clinicflow")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
APPOINTMENT_LABELS = {
    "long": "Long consultation (30 min)",
    "standard": "Standard consultation (15 min)",
    "telehealth": "Telehealth video/phone consultation",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    logger.info("ClinicFlow AI started - AI provider: %s", get_settings().active_provider)
    yield


app = FastAPI(title="ClinicFlow AI", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def require_admin(x_admin_key: Optional[str] = Header(default=None)) -> None:
    if not x_admin_key or not secrets.compare_digest(x_admin_key, get_settings().admin_password):
        raise HTTPException(status_code=401, detail="Invalid admin password")


# ------------------------------------------------------------------- pages
@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


# --------------------------------------------------------------- public API
@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/api/config")
def public_config():
    s = get_settings()
    return {"clinic_name": s.clinic_name, "ai_provider": s.active_provider, "prompt_version": PROMPT_VERSION}


@app.post("/api/intake", response_model=IntakeResponse)
def submit_intake(intake: IntakeRequest):
    triage = analyze_intake(intake)
    intake_id = database.create_intake(intake.model_dump(), triage.model_dump())
    logger.info("Intake %s triaged as %s by %s", intake_id, triage.urgency, triage.ai_provider)
    return IntakeResponse(intake_id=intake_id, triage=triage)


@app.get("/api/slots")
def available_slots(intake_id: int):
    intake = database.get_intake(intake_id)
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")
    if intake["urgency"] == "emergency":
        return {"slots": [], "message": "Emergency cases cannot be booked online. Please call 000."}
    return {"slots": generate_slots(database.booked_slots(), intake["urgency"])}


@app.post("/api/appointments", response_model=BookingResponse)
def book_appointment(req: BookingRequest):
    intake = database.get_intake(req.intake_id)
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")
    if intake["urgency"] == "emergency":
        raise HTTPException(status_code=400, detail="Emergency cases cannot be booked online. Please call 000.")
    if intake["appointment_slot"]:
        raise HTTPException(status_code=409, detail="This intake already has an appointment")
    if req.slot not in generate_slots(database.booked_slots(), intake["urgency"]):
        raise HTTPException(status_code=409, detail="That time is no longer available - please pick another")
    try:
        appointment_id = database.create_appointment(req.intake_id, req.slot)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="That time was just taken - please pick another")

    appt_type = intake["triage"]["suggested_appointment"]
    when = datetime.fromisoformat(req.slot).strftime("%A %d %B at %I:%M %p")
    first_name = intake["patient_name"].split()[0]
    message = (
        f"Hi {first_name}, your {APPOINTMENT_LABELS.get(appt_type, 'appointment')} at "
        f"{get_settings().clinic_name} is confirmed for {when}. Your doctor has already received a summary "
        "of your symptoms. If your symptoms get worse before then, call 000 in an emergency."
    )
    return BookingResponse(
        appointment_id=appointment_id,
        intake_id=req.intake_id,
        slot=req.slot,
        appointment_type=appt_type,
        confirmation_message=message,
    )


# ---------------------------------------------------------------- admin API
@app.get("/api/admin/intakes", dependencies=[Depends(require_admin)])
def admin_list_intakes():
    return {"intakes": database.list_intakes()}


@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    return database.stats()


@app.patch("/api/admin/intakes/{intake_id}", dependencies=[Depends(require_admin)])
def admin_update_status(intake_id: int, update: StatusUpdate):
    if not database.update_status(intake_id, update.status):
        raise HTTPException(status_code=404, detail="Intake not found")
    return {"intake_id": intake_id, "status": update.status}
