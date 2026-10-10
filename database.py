# database.py – SQLite helper functions for HostelCare AI

"""Utility layer that abstracts all interactions with the SQLite database.

The database file ``hostelcare.db`` lives in the same directory as this module.
All functions return plain Python objects (dicts / list of dicts) that the
Streamlit UI can consume directly.
"""

import os
import sqlite3
from typing import List, Dict, Any

# Resolve the absolute path of the DB file (inside the project directory)
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "hostelcare.db")
SCHEMA_PATH = os.path.join(PROJECT_ROOT, "schema.sql")


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # enables dict‑like access
    return conn


def init_db() -> None:
    """Create the database and required tables based on ``schema.sql``.
    This function is idempotent – running it multiple times does not alter existing data.
    """
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn = _get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def authenticate_user(user_id: str, password: str, expected_role: str) -> Dict[str, Any] | None:
    """Validate credentials and role. Returns user record if valid, else None."""
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ? AND password = ? AND role = ?",
            (user_id.strip(), password.strip(), expected_role.strip()),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_user(user_id: str, name: str, password: str, role: str) -> bool:
    """Register a new user. Returns True if created, False if user_id exists."""
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO users (user_id, name, password, role) VALUES (?, ?, ?, ?)",
            (user_id.strip(), name.strip(), password.strip(), role.strip()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def add_complaint(
    *,
    ticket_id: str,
    user_id: str | None = None,
    description: str,
    category: str,
    block: str,
    priority: str,
    status: str,
    assigned_role: str,
    created_at: str,
    updated_at: str,
) -> None:
    """Insert a new complaint row.
    All fields correspond exactly to columns in ``complaints``.
    """
    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO complaints (
                ticket_id, user_id, description, category, block, priority,
                status, assigned_role, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                user_id,
                description,
                category,
                block,
                priority,
                status,
                assigned_role,
                created_at,
                updated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_complaints() -> List[Dict[str, Any]]:
    """Return a list of dictionaries – one per complaint.
    Columns are returned exactly as stored (including timestamps).
    """
    conn = _get_connection()
    try:
        rows = conn.execute("SELECT * FROM complaints ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_complaints_by_user(user_id: str) -> List[Dict[str, Any]]:
    """Return all complaints submitted by a specific user."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC",
            (user_id.strip(),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_complaint(ticket_id: str) -> Dict[str, Any] | None:
    conn = _get_connection()
    try:
        row = conn.execute("SELECT * FROM complaints WHERE ticket_id = ?", (ticket_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_ticket_status(
    ticket_id: str,
    *,
    status: str | None = None,
    assigned_role: str | None = None,
    updated_at: str | None = None,
) -> None:
    """Update mutable fields of a ticket.
    Only the columns passed as non‑None are updated.
    """
    fields = []
    params = []
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if assigned_role is not None:
        fields.append("assigned_role = ?")
        params.append(assigned_role)
    if updated_at is not None:
        fields.append("updated_at = ?")
        params.append(updated_at)
    if not fields:
        return  # nothing to do
    params.append(ticket_id)
    set_clause = ", ".join(fields)
    sql = f"UPDATE complaints SET {set_clause} WHERE ticket_id = ?"
    conn = _get_connection()
    try:
        conn.execute(sql, tuple(params))
        conn.commit()
    finally:
        conn.close()


def log_action(
    *,
    ticket_id: str,
    action: str,
    from_role: str | None,
    to_role: str | None,
    timestamp: str,
) -> None:
    """Insert a row into ``action_logs`` for audit / escalation history."""
    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO action_logs (ticket_id, action, from_role, to_role, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ticket_id, action, from_role, to_role, timestamp),
        )
        conn.commit()
    finally:
        conn.close()


def get_action_logs(ticket_id: str) -> List[Dict[str, Any]]:
    """Return all log entries for the given ticket, newest first."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM action_logs WHERE ticket_id = ? ORDER BY timestamp DESC",
            (ticket_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

# Ensure the DB directory exists when this module is imported
if not os.path.isdir(PROJECT_ROOT):
    os.makedirs(PROJECT_ROOT, exist_ok=True)
