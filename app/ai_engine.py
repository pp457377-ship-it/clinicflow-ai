"""AI triage engine.

Flow:  patient text -> safety rules -> LLM (Gemini or OpenAI) -> validate JSON
                     -> if AI fails, offline rule engine -> safety override -> result
"""

import json
import logging
import re
from typing import Optional

import httpx
from pydantic import ValidationError

from .config import Settings, get_settings
from .models import IntakeRequest, TriageResult
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .safety import CRISIS_MESSAGE, EMERGENCY_MESSAGE, detect_red_flags

logger = logging.getLogger("clinicflow.ai")


# ---------------------------------------------------------------- LLM providers
def _call_gemini(settings: Settings, user_prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    resp = httpx.post(
        url, json=body, headers={"x-goog-api-key": settings.gemini_api_key}, timeout=settings.ai_timeout_seconds
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_openai(settings: Settings, user_prompt: str) -> str:
    body = {
        "model": settings.openai_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    resp = httpx.post(
        f"{settings.openai_base_url}/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        timeout=settings.ai_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def parse_llm_json(raw: str) -> TriageResult:
    """Models sometimes wrap JSON in ```json fences or add text around it - strip that."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in AI response")
    data = json.loads(match.group(0))
    data.pop("ai_provider", None)
    return TriageResult(**data)


def _ask_llm(settings: Settings, intake: IntakeRequest) -> Optional[TriageResult]:
    provider = settings.active_provider
    if provider == "offline":
        return None
    prompt = build_user_prompt(intake.age, intake.gender, intake.symptoms, intake.duration)
    call = _call_gemini if provider == "gemini" else _call_openai
    for attempt in (1, 2):
        try:
            result = parse_llm_json(call(settings, prompt))
            result.ai_provider = provider
            return result
        except (httpx.HTTPError, KeyError, IndexError, ValueError, ValidationError) as exc:
            logger.warning("AI call failed (attempt %s, %s): %s", attempt, provider, exc)
    return None


# ----------------------------------------------------------- offline fallback
SYMPTOM_WORDS = [
    "fever", "cough", "sore throat", "runny nose", "headache", "migraine", "rash", "vomiting", "nausea",
    "diarrhoea", "diarrhea", "abdominal pain", "stomach pain", "back pain", "earache", "ear pain", "dizziness",
    "fatigue", "tired", "anxiety", "depression", "low mood", "insomnia", "can't sleep", "burning urination",
    "joint pain", "swelling", "wheezing", "shortness of breath", "chest pain", "bleeding", "itching",
]
URGENT_PATTERNS = [
    r"high (fever|temperature)", r"\b(39|40|41)(\.\d)?\s*(°|degrees|c\b)", r"severe", r"worsening", r"getting worse",
    r"shortness of breath", r"wheez", r"can'?t keep (anything|fluids) down", r"blood in", r"infected", r"pus",
    r"unbearable", r"dehydrat", r"stiff neck",
]
TELEHEALTH_PATTERNS = [
    r"repeat (script|prescription)", r"prescription", r"medical certificate", r"certificate", r"test results",
    r"blood results", r"referral", r"runny nose", r"mild cold",
]
LONG_PATTERNS = [
    r"anxiety", r"depress", r"low mood", r"mental health", r"stress", r"diabetes", r"blood pressure",
    r"chronic", r"several (issues|problems)", r"multiple (issues|problems)", r"care plan",
]
QUESTION_BANK = {
    "fever": "What is the highest temperature recorded?",
    "cough": "Is the cough dry or producing phlegm?",
    "pain": "How severe is the pain on a scale of 0-10, and where exactly is it?",
    "headache": "Is this headache different from usual headaches?",
    "rash": "Is the rash spreading, raised or itchy?",
    "vomiting": "Are you able to keep fluids down?",
    "dizziness": "Does the dizziness happen when standing up?",
    "anxiety": "How is this affecting your sleep, work and daily life?",
}


def _matches(patterns, text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def offline_analyze(intake: IntakeRequest) -> TriageResult:
    text = f"{intake.symptoms} {intake.duration}".lower()
    vulnerable = intake.age < 2 or intake.age > 75

    if detect_red_flags(text):
        urgency = "emergency"
    elif _matches(URGENT_PATTERNS, text) or (vulnerable and "fever" in text):
        urgency = "urgent"
    else:
        urgency = "routine"

    if urgency == "emergency":
        appointment = "emergency"
    elif urgency == "routine" and _matches(TELEHEALTH_PATTERNS, text):
        appointment = "telehealth"
    elif _matches(LONG_PATTERNS, text):
        appointment = "long"
    else:
        appointment = "standard"

    symptoms = [w for w in SYMPTOM_WORDS if w in text] or [intake.symptoms.strip()[:60]]
    questions = [q for key, q in QUESTION_BANK.items() if key in text][:3]
    questions.append("Any relevant medical history, current medicines or allergies?")

    follow_ups = [q for key, q in QUESTION_BANK.items() if key in text][:2]
    follow_ups.append("Is it getting better, getting worse or staying the same?")
    follow_ups = follow_ups[:3]

    sex = {"female": "female", "male": "male"}.get(intake.gender, "patient")
    duration = intake.duration.strip() or "unspecified duration"
    summary = f"{intake.age}-year-old {sex} presenting with {', '.join(symptoms)} ({duration})."

    messages = {
        "emergency": EMERGENCY_MESSAGE,
        "urgent": "Thanks for the details. We recommend seeing a GP today - please choose the earliest "
        "available time below. If your symptoms suddenly get worse, call 000.",
        "routine": "Thanks for the details. A GP can review this at a normal appointment - please choose a "
        "time that suits you below.",
    }
    return TriageResult(
        urgency=urgency,
        summary=summary,
        key_symptoms=symptoms,
        red_flags=[],
        suggested_appointment=appointment,
        questions_for_doctor=questions,
        follow_up_questions=follow_ups,
        patient_message=messages[urgency],
        ai_provider="offline",
    )


# ------------------------------------------------------------------ main entry
def analyze_intake(intake: IntakeRequest, settings: Optional[Settings] = None) -> TriageResult:
    settings = settings or get_settings()
    red_flags = detect_red_flags(f"{intake.symptoms} {intake.duration}")

    result = _ask_llm(settings, intake) or offline_analyze(intake)

    # Safety override: rules always win over the AI.
    if red_flags:
        result.urgency = "emergency"
        result.suggested_appointment = "emergency"
        result.red_flags = sorted(set(result.red_flags) | set(red_flags))
        message = CRISIS_MESSAGE if "Mental health crisis" in red_flags else EMERGENCY_MESSAGE
        if message not in result.patient_message:
            result.patient_message = f"{message} {result.patient_message}".strip()
    if result.urgency == "emergency":
        result.suggested_appointment = "emergency"
    elif result.suggested_appointment == "emergency":
        result.suggested_appointment = "standard"
    return result
