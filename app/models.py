"""Request / response shapes. Pydantic validates every input automatically."""

from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field

Urgency = Literal["emergency", "urgent", "routine"]
AppointmentType = Literal["emergency", "long", "standard", "telehealth"]
IntakeStatus = Literal["new", "booked", "confirmed", "reviewed", "closed"]


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
    follow_up_questions: List[str] = []
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


class FollowUpAnswer(BaseModel):
    question: str = Field(..., max_length=200)
    answer: str = Field(..., min_length=1, max_length=1000)


class FollowUpRequest(BaseModel):
    answers: List[FollowUpAnswer] = Field(..., max_length=5)


class StatusUpdate(BaseModel):
    status: IntakeStatus


class IntakeEdit(BaseModel):
    patient_name: Optional[str] = Field(None, min_length=2, max_length=80)
    age: Optional[int] = Field(None, ge=0, le=120)
    gender: Optional[Literal["female", "male", "other", "prefer_not_to_say"]] = None
    phone: Optional[str] = Field(None, min_length=6, max_length=20, pattern=r"^[0-9+()\-\s]+$")
    email: Optional[EmailStr] = None
    symptoms: Optional[str] = Field(None, min_length=5, max_length=2000)
    duration: Optional[str] = Field(None, max_length=100)
    status: Optional[IntakeStatus] = None


class AdminLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class AdminCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.\-]+$")
    password: str = Field(..., min_length=8, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
