from dataclasses import replace

import pytest

from app import ai_engine
from app.config import get_settings
from app.models import IntakeRequest


def make(symptoms, age=40, duration="2 days"):
    return IntakeRequest(patient_name="Test Patient", age=age, phone="0412345678", symptoms=symptoms, duration=duration)


@pytest.fixture()
def offline(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "offline")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def test_offline_routine_telehealth(offline):
    r = ai_engine.analyze_intake(make("mild cold with runny nose"), offline)
    assert r.urgency == "routine" and r.suggested_appointment == "telehealth"


def test_offline_urgent_fever(offline):
    assert ai_engine.analyze_intake(make("high fever and getting worse"), offline).urgency == "urgent"


def test_vulnerable_age_fever_is_urgent(offline):
    assert ai_engine.analyze_intake(make("fever since this morning", age=1), offline).urgency == "urgent"


def test_mental_health_gets_long_consult(offline):
    assert ai_engine.analyze_intake(make("anxiety and low mood"), offline).suggested_appointment == "long"


def test_parse_llm_json_strips_markdown_fences():
    raw = '```json\n{"urgency":"routine","summary":"s","suggested_appointment":"standard"}\n```'
    assert ai_engine.parse_llm_json(raw).urgency == "routine"


def test_safety_rules_override_ai(monkeypatch, offline):
    """Even if the LLM says 'routine', chest pain must become an emergency."""
    settings = replace(offline, ai_provider="openai", openai_api_key="fake")
    monkeypatch.setattr(
        ai_engine, "_call_openai",
        lambda s, p: '{"urgency":"routine","summary":"x","suggested_appointment":"standard","patient_message":"ok"}',
    )
    r = ai_engine.analyze_intake(make("chest pain spreading to my arm"), settings)
    assert r.urgency == "emergency"
    assert r.suggested_appointment == "emergency"
    assert r.ai_provider == "openai"
    assert "000" in r.patient_message


def test_falls_back_to_offline_when_ai_fails(monkeypatch, offline):
    settings = replace(offline, ai_provider="gemini", gemini_api_key="fake")

    def boom(s, p):
        raise ValueError("bad response")

    monkeypatch.setattr(ai_engine, "_call_gemini", boom)
    r = ai_engine.analyze_intake(make("sore throat"), settings)
    assert r.ai_provider == "offline"


def test_ai_cannot_book_emergency_slot_for_non_emergency(monkeypatch, offline):
    settings = replace(offline, ai_provider="openai", openai_api_key="fake")
    monkeypatch.setattr(
        ai_engine, "_call_openai",
        lambda s, p: '{"urgency":"routine","summary":"x","suggested_appointment":"emergency"}',
    )
    assert ai_engine.analyze_intake(make("itchy skin"), settings).suggested_appointment == "standard"
