
# database.py – SQLite helper functions for HostelCare AI

"""Utility layer for all SQLite database interactions.

The database file hostelcare.db lives beside this module.
Existing complaint records are preserved during schema migrations.
"""

import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Any


# --------------------------------------------------
# DATABASE CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "hostelcare.db")
SCHEMA_PATH = os.path.join(PROJECT_ROOT, "schema.sql")


def _get_connection() -> sqlite3.Connection:
    """Create a database connection with dictionary-like rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _timestamp() -> str:
    """Return the current local timestamp."""
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------
# DATABASE INITIALIZATION AND MIGRATION
# --------------------------------------------------

def init_db() -> None:
    """Create tables and add missing columns to existing databases."""

    if not os.path.isdir(PROJECT_ROOT):
        os.makedirs(PROJECT_ROOT, exist_ok=True)

    if not os.path.isfile(SCHEMA_PATH):
        raise FileNotFoundError(
            f"Database schema file not found: {SCHEMA_PATH}"
        )

    with open(SCHEMA_PATH, "r", encoding="utf-8") as file:
        schema_sql = file.read()

    conn = _get_connection()

    try:
        # Create tables and seed data defined in schema.sql.
        conn.executescript(schema_sql)

        # Check existing complaint columns.
        existing_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(complaints)"
            ).fetchall()
        }

        # Add new fields without deleting existing complaints.
        new_columns = {
            "room_number": "TEXT",
            "duration": "TEXT",
            "impact": "TEXT",
            "escalation_level": "INTEGER NOT NULL DEFAULT 1",
            "resolution_notes": "TEXT",
            "resolved_at": "TEXT",
        }

        for column, column_type in new_columns.items():
            if column not in existing_columns:
                conn.execute(
                    f"ALTER TABLE complaints ADD COLUMN "
                    f"{column} {column_type}"
                )

        # Detailed complaint history.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS complaint_updates (
                update_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                updated_by TEXT,
                old_status TEXT,
                new_status TEXT,
                update_note TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (ticket_id)
                    REFERENCES complaints(ticket_id)
            )
        """)

        conn.commit()

    finally:
        conn.close()


# --------------------------------------------------
# USER AUTHENTICATION
# --------------------------------------------------

def authenticate_user(
    user_id: str,
    password: str,
    expected_role: str,
) -> Dict[str, Any] | None:
    """Validate a user's credentials and role."""

    conn = _get_connection()

    try:
        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
              AND password = ?
              AND role = ?
            """,
            (
                user_id.strip(),
                password.strip(),
                expected_role.strip(),
            ),
        ).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()


def create_user(
    user_id: str,
    name: str,
    password: str,
    role: str,
) -> bool:
    """Create a user. Return False if the user ID already exists."""

    conn = _get_connection()

    try:
        conn.execute(
            """
            INSERT INTO users (user_id, name, password, role)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id.strip(),
                name.strip(),
                password.strip(),
                role.strip(),
            ),
        )

        conn.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        conn.close()


# --------------------------------------------------
# CREATE A COMPLAINT
# --------------------------------------------------

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
    room_number: str | None = None,
    duration: str | None = None,
    impact: str | None = None,
    escalation_level: int = 1,
    resolution_notes: str | None = None,
    resolved_at: str | None = None,
) -> None:
    """Insert a new complaint with optional structured details."""

    conn = _get_connection()

    try:
        conn.execute(
            """
            INSERT INTO complaints (
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
                room_number,
                duration,
                impact,
                escalation_level,
                resolution_notes,
                resolved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                room_number,
                duration,
                impact,
                escalation_level,
                resolution_notes,
                resolved_at,
            ),
        )

        # Record initial creation in the complaint timeline.
        conn.execute(
            """
            INSERT INTO complaint_updates (
                ticket_id,
                updated_by,
                old_status,
                new_status,
                update_note,
                timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                user_id,
                None,
                status,
                "Complaint created",
                created_at or _timestamp(),
            ),
        )

        conn.commit()

    finally:
        conn.close()


# --------------------------------------------------
# RETRIEVE COMPLAINTS
# --------------------------------------------------

def get_all_complaints() -> List[Dict[str, Any]]:
    """Return all complaints, newest first."""

    conn = _get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM complaints
            ORDER BY created_at DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


def get_complaints_by_user(
    user_id: str,
) -> List[Dict[str, Any]]:
    """Return complaints submitted by a specific user."""

    conn = _get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM complaints
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id.strip(),),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


def get_complaint(
    ticket_id: str,
) -> Dict[str, Any] | None:
    """Return one complaint by ticket ID."""

    conn = _get_connection()

    try:
        row = conn.execute(
            """
            SELECT *
            FROM complaints
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()


# --------------------------------------------------
# UPDATE A COMPLAINT
# --------------------------------------------------

def update_ticket_status(
    ticket_id: str,
    *,
    status: str | None = None,
    assigned_role: str | None = None,
    updated_at: str | None = None,
    updated_by: str | None = None,
    update_note: str | None = None,
    resolution_notes: str | None = None,
    escalation_level: int | None = None,
) -> None:
    """Update a complaint and record relevant changes in its history."""

    conn = _get_connection()

    try:
        row = conn.execute(
            """
            SELECT status, assigned_role, escalation_level
            FROM complaints
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        ).fetchone()

        if row is None:
            return

        old_status = row["status"]
        old_role = row["assigned_role"]
        old_level = row["escalation_level"]

        timestamp = updated_at or _timestamp()

        fields = ["updated_at = ?"]
        params: list[Any] = [timestamp]

        if status is not None:
            fields.append("status = ?")
            params.append(status)

        if assigned_role is not None:
            fields.append("assigned_role = ?")
            params.append(assigned_role)

        if resolution_notes is not None:
            fields.append("resolution_notes = ?")
            params.append(resolution_notes)

        if escalation_level is not None:
            fields.append("escalation_level = ?")
            params.append(escalation_level)

        # Set resolution timestamp when resolved; clear it if reopened.
        if status == "Resolved":
            fields.append("resolved_at = ?")
            params.append(timestamp)
        elif status is not None:
            fields.append("resolved_at = NULL")

        params.append(ticket_id)

        conn.execute(
            f"""
            UPDATE complaints
            SET {", ".join(fields)}
            WHERE ticket_id = ?
            """,
            tuple(params),
        )

        new_status = status if status is not None else old_status
        new_role = (
            assigned_role if assigned_role is not None else old_role
        )
        new_level = (
            escalation_level
            if escalation_level is not None
            else old_level
        )

        # Record meaningful changes in the complaint timeline.
        status_changed = new_status != old_status
        role_changed = new_role != old_role
        level_changed = new_level != old_level

        if (
            status_changed
            or role_changed
            or level_changed
            or update_note
            or resolution_notes
        ):
            notes = []

            if update_note:
                notes.append(update_note)

            if resolution_notes:
                notes.append(f"Resolution: {resolution_notes}")

            if role_changed:
                notes.append(
                    f"Assignment changed: {old_role} -> {new_role}"
                )

            if level_changed:
                notes.append(
                    f"Escalation level changed: "
                    f"{old_level} -> {new_level}"
                )

            conn.execute(
                """
                INSERT INTO complaint_updates (
                    ticket_id,
                    updated_by,
                    old_status,
                    new_status,
                    update_note,
                    timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket_id,
                    updated_by,
                    old_status,
                    new_status,
                    "; ".join(notes) or "Complaint updated",
                    timestamp,
                ),
            )

        conn.commit()

    finally:
        conn.close()


# --------------------------------------------------
# COMPLAINT HISTORY
# --------------------------------------------------

def get_complaint_updates(
    ticket_id: str,
) -> List[Dict[str, Any]]:
    """Return a complaint's history, oldest first."""

    conn = _get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM complaint_updates
            WHERE ticket_id = ?
            ORDER BY timestamp ASC, update_id ASC
            """,
            (ticket_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


# --------------------------------------------------
# ACTION LOGS / ESCALATION AUDIT
# --------------------------------------------------

def log_action(
    *,
    ticket_id: str,
    action: str,
    from_role: str | None,
    to_role: str | None,
    timestamp: str,
) -> None:
    """Record assignment, escalation, and other audit actions."""

    conn = _get_connection()

    try:
        conn.execute(
            """
            INSERT INTO action_logs (
                ticket_id,
                action,
                from_role,
                to_role,
                timestamp
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                action,
                from_role,
                to_role,
                timestamp,
            ),
        )

        conn.commit()

    finally:
        conn.close()


def get_action_logs(
    ticket_id: str,
) -> List[Dict[str, Any]]:
    """Return audit logs for a ticket, newest first."""

    conn = _get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM action_logs
            WHERE ticket_id = ?
            ORDER BY timestamp DESC
            """,
            (ticket_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


# --------------------------------------------------
# INITIALIZE DATABASE
# --------------------------------------------------

# Run the initialization when this module is imported.
init_db()
