"""Request / response shapes. Pydantic validates every input automatically."""

from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field

Urgency = Literal["emergency", "urgent", "routine"]
AppointmentType = Literal["emergency", "long", "standard", "telehealth"]
IntakeStatus = Literal["new", "booked", "reviewed", "closed"]


class IntakeRequest(BaseModel):
    patient_name: str = Field(..., min_length=2, max_length=80)
    age: int = Field(..., ge=0, le=120)
    gender: Literal["female", "male", "other", "prefer_not_to_say"] = "prefer_not_to_say"
    phone: str = Field(..., min_length=6, max_length=20, pattern=r"^[0-9+()\-\s]+$")
    email: Optional[EmailStr] = None
    symptoms: str = Field(..., min_length=5, max_length=2000)
    duration: str = Field("", max_length=100)


class TriageResult(BaseModel):
    urgency: Urgency
    summary: str = Field(..., description="Short clinical summary written for the doctor")
    key_symptoms: List[str] = []
    red_flags: List[str] = []
    suggested_appointment: AppointmentType = "standard"
    questions_for_doctor: List[str] = []
    patient_message: str = ""
    ai_provider: str = "offline"


class IntakeResponse(BaseModel):
    intake_id: int
    triage: TriageResult


class BookingRequest(BaseModel):
    intake_id: int
    slot: str = Field(..., description="ISO datetime of the chosen slot")


class BookingResponse(BaseModel):
    appointment_id: int
    intake_id: int
    slot: str
    appointment_type: AppointmentType
    confirmation_message: str


class StatusUpdate(BaseModel):
    status: IntakeStatus
