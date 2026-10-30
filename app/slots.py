"""Generates bookable appointment slots in the clinic's local time zone."""

from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

from .config import get_settings

OPEN_HOUR, CLOSE_HOUR, SLOT_MINUTES, DAYS_AHEAD = 8, 20, 30, 3  # 7-day clinic, 8am-8pm


def generate_slots(booked: List[str], urgency: str = "routine", now: datetime = None) -> List[str]:
    tz = ZoneInfo(get_settings().clinic_timezone)
    now = now.astimezone(tz) if now else datetime.now(tz)
    days = 1 if urgency == "urgent" else DAYS_AHEAD  # urgent patients only see today and tomorrow
    booked_set = set(booked)
    slots: List[str] = []
    for day in range(days + 1):
        date = (now + timedelta(days=day)).date()
        start = datetime(date.year, date.month, date.day, OPEN_HOUR, tzinfo=tz)
        for i in range((CLOSE_HOUR - OPEN_HOUR) * 60 // SLOT_MINUTES):
            slot = start + timedelta(minutes=i * SLOT_MINUTES)
            iso = slot.isoformat(timespec="minutes")
            if slot > now + timedelta(minutes=15) and iso not in booked_set:
                slots.append(iso)
    return slots
