"""Tiny SQLite data layer (Python built-in sqlite3, no ORM needed)."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS intakes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    patient_name  TEXT NOT NULL,
    age           INTEGER NOT NULL,
    gender        TEXT NOT NULL,
    phone         TEXT NOT NULL,
    email         TEXT,
    symptoms      TEXT NOT NULL,
    duration      TEXT,
    urgency       TEXT NOT NULL,
    triage_json   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'new'
);
CREATE TABLE IF NOT EXISTS appointments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    intake_id   INTEGER NOT NULL UNIQUE REFERENCES intakes(id),
    slot        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    path = get_settings().database_path
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)  # cheap no-op if tables exist; recreates them if the DB file was removed
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_intake(data: Dict[str, Any], triage: Dict[str, Any]) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO intakes (created_at, patient_name, age, gender, phone, email, symptoms, duration,
                                    urgency, triage_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _now(), data["patient_name"], data["age"], data["gender"], data["phone"], data.get("email"),
                data["symptoms"], data.get("duration", ""), triage["urgency"], json.dumps(triage),
            ),
        )
        return int(cur.lastrowid)


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    item["triage"] = json.loads(item.pop("triage_json"))
    return item


def get_intake(intake_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT i.*, a.slot AS appointment_slot FROM intakes i
               LEFT JOIN appointments a ON a.intake_id = i.id WHERE i.id = ?""",
            (intake_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_intakes() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT i.*, a.slot AS appointment_slot FROM intakes i
               LEFT JOIN appointments a ON a.intake_id = i.id
               ORDER BY CASE i.urgency WHEN 'emergency' THEN 0 WHEN 'urgent' THEN 1 ELSE 2 END,
                        i.created_at DESC"""
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_status(intake_id: int, status: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("UPDATE intakes SET status = ? WHERE id = ?", (status, intake_id))
        return cur.rowcount > 0


def booked_slots() -> List[str]:
    with get_conn() as conn:
        return [r["slot"] for r in conn.execute("SELECT slot FROM appointments").fetchall()]


def create_appointment(intake_id: int, slot: str) -> int:
    """Raises sqlite3.IntegrityError if the slot or the intake is already booked."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO appointments (intake_id, slot, created_at) VALUES (?, ?, ?)", (intake_id, slot, _now())
        )
        conn.execute("UPDATE intakes SET status = 'booked' WHERE id = ?", (intake_id,))
        return int(cur.lastrowid)


def stats() -> Dict[str, Any]:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM intakes").fetchone()[0]
        by_urgency = {
            r["urgency"]: r["n"]
            for r in conn.execute("SELECT urgency, COUNT(*) AS n FROM intakes GROUP BY urgency").fetchall()
        }
        booked = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    return {
        "total_intakes": total,
        "emergency": by_urgency.get("emergency", 0),
        "urgent": by_urgency.get("urgent", 0),
        "routine": by_urgency.get("routine", 0),
        "appointments_booked": booked,
    }
