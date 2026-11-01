"""FastAPI application: JSON API + the static web pages."""

import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, database, mailer
from .ai_engine import analyze_intake
from .config import get_settings
from .models import (
    AdminCreate,
    AdminLogin,
    BookingRequest,
    BookingResponse,
    FollowUpRequest,
    IntakeEdit,
    IntakeRequest,
    IntakeResponse,
    PasswordChange,
    StatusUpdate,
)
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


def require_admin(x_admin_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    admin = database.get_session_admin(x_admin_key)
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return admin


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


@app.post("/api/intakes/{intake_id}/follow-up")
def intake_follow_up(intake_id: int, req: FollowUpRequest):
    intake = database.get_intake(intake_id)
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")
    if intake["appointment_slot"]:
        raise HTTPException(status_code=409, detail="This intake already has an appointment")
    qa_text = " ".join(f"Q: {a.question} A: {a.answer}" for a in req.answers)
    enriched = IntakeRequest(
        patient_name=intake["patient_name"],
        age=intake["age"],
        gender=intake["gender"],
        phone=intake["phone"],
        email=intake.get("email"),
        duration=intake.get("duration") or "",
        symptoms=f"{intake['symptoms']}\nFollow-up answers: {qa_text}"[:2000],
    )
    result = analyze_intake(enriched)
    triage = result.model_dump()
    triage["patient_answers"] = [a.model_dump() for a in req.answers]
    database.update_intake_triage(intake_id, result.urgency, triage)
    logger.info("Intake %s re-triaged as %s after follow-up answers", intake_id, result.urgency)
    return {"intake_id": intake_id, "triage": triage}


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
    confirm_note = (
        f"A confirmation email will be sent to {intake['email']} once the clinic approves it."
        if intake.get("email")
        else "The clinic will contact you shortly to confirm it."
    )
    message = (
        f"Hi {first_name}, your {APPOINTMENT_LABELS.get(appt_type, 'appointment')} at "
        f"{get_settings().clinic_name} is booked for {when}. {confirm_note} "
        "If your symptoms get worse before then, call 000 in an emergency."
    )
    return BookingResponse(
        appointment_id=appointment_id,
        intake_id=req.intake_id,
        slot=req.slot,
        appointment_type=appt_type,
        confirmation_message=message,
    )


# ---------------------------------------------------------------- admin API
@app.post("/api/admin/login")
def admin_login(creds: AdminLogin):
    admin = database.verify_admin(creds.username, creds.password)
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": database.create_session(admin["id"]), "username": admin["username"]}


@app.post("/api/admin/logout")
def admin_logout(x_admin_key: Optional[str] = Header(default=None)):
    if x_admin_key:
        database.delete_session(x_admin_key)
    return {"ok": True}


@app.get("/api/admin/intakes", dependencies=[Depends(require_admin)])
def admin_list_intakes():
    return {"intakes": database.list_intakes()}


@app.post("/api/admin/intakes", dependencies=[Depends(require_admin)])
def admin_create_intake(intake: IntakeRequest):
    triage = analyze_intake(intake)
    intake_id = database.create_intake(intake.model_dump(), triage.model_dump())
    logger.info("Admin added intake %s triaged as %s", intake_id, triage.urgency)
    return database.get_intake(intake_id)


@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    return database.stats()


@app.patch("/api/admin/intakes/{intake_id}", dependencies=[Depends(require_admin)])
def admin_update_status(intake_id: int, update: StatusUpdate):
    if not database.update_status(intake_id, update.status):
        raise HTTPException(status_code=404, detail="Intake not found")
    return {"intake_id": intake_id, "status": update.status}


@app.put("/api/admin/intakes/{intake_id}", dependencies=[Depends(require_admin)])
def admin_edit_intake(intake_id: int, edit: IntakeEdit):
    if not database.update_intake(intake_id, edit.model_dump(exclude_unset=True)):
        raise HTTPException(status_code=404, detail="Intake not found")
    return database.get_intake(intake_id)


@app.delete("/api/admin/intakes/{intake_id}", dependencies=[Depends(require_admin)])
def admin_delete_intake(intake_id: int):
    if not database.delete_intake(intake_id):
        raise HTTPException(status_code=404, detail="Intake not found")
    return {"deleted": intake_id}


@app.post("/api/admin/intakes/{intake_id}/confirm", dependencies=[Depends(require_admin)])
def admin_confirm_appointment(intake_id: int):
    intake = database.get_intake(intake_id)
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")
    if not intake["appointment_slot"]:
        raise HTTPException(status_code=400, detail="This intake has no appointment to confirm")
    email_sent = False
    if intake.get("email"):
        clinic = get_settings().clinic_name
        appt_type = intake["triage"]["suggested_appointment"]
        when = datetime.fromisoformat(intake["appointment_slot"]).strftime("%A %d %B at %I:%M %p")
        first_name = intake["patient_name"].split()[0]
        email_sent = mailer.send_email(
            intake["email"],
            f"Appointment confirmed - {clinic}",
            f"Hi {first_name},\n\n"
            f"Your {APPOINTMENT_LABELS.get(appt_type, 'appointment').lower()} at {clinic} "
            f"is confirmed for {when} (clinic time).\n\n"
            "If you need to reschedule, please call the clinic. "
            "If your symptoms get worse before your visit, call 000 in an emergency.\n\n"
            f"- {clinic}",
        )
    database.update_status(intake_id, "confirmed")
    logger.info("Intake %s appointment confirmed; email_sent=%s", intake_id, email_sent)
    return {"intake_id": intake_id, "status": "confirmed", "email_sent": email_sent}


# ----------------------------------------------------------- admin accounts
@app.get("/api/admin/admins")
def admin_list_admins(_: Dict[str, Any] = Depends(require_admin)):
    return {"admins": database.list_admins()}


@app.post("/api/admin/admins")
def admin_create_admin(req: AdminCreate, _: Dict[str, Any] = Depends(require_admin)):
    try:
        admin_id = database.create_admin(req.username, req.password)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="That username is already taken")
    return {"id": admin_id, "username": req.username}


@app.delete("/api/admin/admins/{admin_id}")
def admin_delete_admin(admin_id: int, admin: Dict[str, Any] = Depends(require_admin)):
    if admin["id"] == admin_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if database.admin_count() <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last admin account")
    if not database.delete_admin(admin_id):
        raise HTTPException(status_code=404, detail="Admin not found")
    return {"deleted": admin_id}


@app.post("/api/admin/password")
def admin_change_password(req: PasswordChange, admin: Dict[str, Any] = Depends(require_admin)):
    if not database.verify_admin(admin["username"], req.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    database.set_admin_password(admin["id"], req.new_password)
    return {"ok": True}
