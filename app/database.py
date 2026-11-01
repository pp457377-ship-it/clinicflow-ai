"""Tiny SQLite data layer (Python built-in sqlite3, no ORM needed)."""

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
CREATE TABLE IF NOT EXISTS admin_users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE,
    pass_hash   TEXT NOT NULL,
    salt        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_sessions (
    token       TEXT PRIMARY KEY,
    admin_id    INTEGER NOT NULL REFERENCES admin_users(id),
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
"""

SESSION_TTL_HOURS = 12
EDITABLE_INTAKE_FIELDS = {
    "patient_name", "age", "gender", "phone", "email", "symptoms", "duration", "status",
}


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
    if admin_count() == 0:
        create_admin("admin", get_settings().admin_password)


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


def update_intake(intake_id: int, fields: Dict[str, Any]) -> bool:
    cols = {k: v for k, v in fields.items() if k in EDITABLE_INTAKE_FIELDS}
    if not cols:
        with get_conn() as conn:
            row = conn.execute("SELECT 1 FROM intakes WHERE id = ?", (intake_id,)).fetchone()
        return row is not None
    sets = ", ".join(f"{k} = ?" for k in cols)
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE intakes SET {sets} WHERE id = ?", (*cols.values(), intake_id))
        return cur.rowcount > 0


def update_intake_triage(intake_id: int, urgency: str, triage: Dict[str, Any]) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE intakes SET urgency = ?, triage_json = ? WHERE id = ?",
            (urgency, json.dumps(triage), intake_id),
        )
        return cur.rowcount > 0


def delete_intake(intake_id: int) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM appointments WHERE intake_id = ?", (intake_id,))
        cur = conn.execute("DELETE FROM intakes WHERE id = ?", (intake_id,))
        return cur.rowcount > 0


# ---------------------------------------------------------------- admin users

def _hash_password(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def admin_count() -> int:
    with get_conn() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0])


def create_admin(username: str, password: str) -> int:
    salt = secrets.token_hex(16)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO admin_users (username, pass_hash, salt, created_at) VALUES (?, ?, ?, ?)",
            (username, _hash_password(password, salt), salt, _now()),
        )
        return int(cur.lastrowid)


def verify_admin(username: str, password: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    if not secrets.compare_digest(_hash_password(password, row["salt"]), row["pass_hash"]):
        return None
    return {"id": row["id"], "username": row["username"]}


def list_admins() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, created_at FROM admin_users ORDER BY username"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_admin(admin_id: int) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE admin_id = ?", (admin_id,))
        cur = conn.execute("DELETE FROM admin_users WHERE id = ?", (admin_id,))
        return cur.rowcount > 0


def set_admin_password(admin_id: int, password: str) -> bool:
    salt = secrets.token_hex(16)
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE admin_users SET pass_hash = ?, salt = ? WHERE id = ?",
            (_hash_password(password, salt), salt, admin_id),
        )
        conn.execute("DELETE FROM admin_sessions WHERE admin_id = ?", (admin_id,))
        return cur.rowcount > 0


# ------------------------------------------------------------- admin sessions

def create_session(admin_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(hours=SESSION_TTL_HOURS)).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM admin_sessions WHERE expires_at < ?", (now.isoformat(timespec="seconds"),)
        )
        conn.execute(
            "INSERT INTO admin_sessions (token, admin_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, admin_id, now.isoformat(timespec="seconds"), expires),
        )
    return token


def get_session_admin(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        row = conn.execute(
            """SELECT u.id, u.username FROM admin_sessions s
               JOIN admin_users u ON u.id = s.admin_id
               WHERE s.token = ? AND s.expires_at >= ?""",
            (token, now),
        ).fetchone()
    return dict(row) if row else None


def delete_session(token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE token = ?", (token,))
