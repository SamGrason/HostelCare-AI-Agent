# routing.py – Department mapping, hierarchy, and escalation for HostelCare AI

"""Routing module responsible for:
1️⃣ Mapping a complaint category to the appropriate department.
2️⃣ Selecting the initial authority (typically a Technician).
3️⃣ Providing manual escalation (to the next hierarchy level).
4️⃣ Automatic escalation based on ticket age (30 minutes).

All functions operate on simple strings; the database layer is handled by
``database.py``.
"""

from typing import Optional
from datetime import datetime, timezone
# ---------------------------------------------------------------------------
# Static configuration – can be extended later
# ---------------------------------------------------------------------------

# Mapping of complaint categories to department names (must match entries in ``departments`` table)
CATEGORY_DEPARTMENT = {
    "Water": "Plumbing",
    "Electrical": "Electrical",
    "Housekeeping": "Housekeeping",
    "Security": "Security",
    "Other": "Housekeeping",  # fallback department
}

# Authority hierarchy – lower ``level`` means lower in the chain.
# The ``authorities`` table already contains rows for each department, but the
# routing logic only needs the role name and its numeric level.
AUTHORITY_HIERARCHY = [
    {"role": "Technician", "level": 1},
    {"role": "Supervisor", "level": 2},
    {"role": "Warden", "level": 3},
    {"role": "Director", "level": 4},
]

# Helper to look up the next higher role given the current one.
def _next_role(current_role: str) -> Optional[str]:
    for idx, entry in enumerate(AUTHORITY_HIERARCHY):
        if entry["role"] == current_role:
            if idx + 1 < len(AUTHORITY_HIERARCHY):
                return AUTHORITY_HIERARCHY[idx + 1]["role"]
            else:
                return None  # already at top
    return None  # unknown role

# ---------------------------------------------------------------------------
# Public routing functions
# ---------------------------------------------------------------------------

def route_complaint(*, category: str, block: str, priority: str) -> str:
    """Return the initial authority role for a new ticket.
    * ``category`` – one of the keys in ``CATEGORY_DEPARTMENT``.
    * ``priority`` is currently used only for a small rule: if the priority is
      ``Critical`` we start at the ``Supervisor`` level to speed up handling.
    """
    # Normal tickets start with the lowest role (Technician).
    start_role = "Technician"
    if priority.lower() == "critical":
        start_role = "Supervisor"
    return start_role


def manual_escalate(ticket: dict) -> Optional[str]:
    """Escalate the ticket to the next authority in the hierarchy.
    ``ticket`` is a dict as returned by ``database.get_complaint``.
    Returns the new role name, or ``None`` if already at highest level.
    """
    current_role = ticket.get("assigned_role")
    if not current_role:
        return None
    return _next_role(current_role)

# ---------------------------------------------------------------------------
# Automatic escalation – called from the UI on each page load (lightweight).
# ---------------------------------------------------------------------------

def auto_escalate(database):
    """Iterate over open tickets and promote them if they are older than 30 min.
    ``database`` is the ``database`` module imported by the caller.
    The function updates the ticket status to "Escalated" and logs the action.
    """
    now = datetime.datetime.utcnow()
    tickets = database.get_all_complaints()
    for t in tickets:
        if t["status"] in ("Resolved", "Escalated"):
            continue
        created = datetime.datetime.fromisoformat(t["created_at"])
        created = _parse_created_at(complaint.get("created_at"))
        if created is None:
            continue
        now = datetime.now(created.tzinfo) if created.tzinfo else datetime.now()
        age_minutes = (now - created).total_seconds() / 60
        if age_minutes >= 30:
            # Perform escalation if possible
            new_role = _next_role(t["assigned_role"])
            if new_role:
                timestamp = now.isoformat()
                database.update_ticket_status(
                    ticket_id=t["ticket_id"],
                    status="Escalated",
                    assigned_role=new_role,
                    updated_at=timestamp,
                )
                database.log_action(
                    ticket_id=t["ticket_id"],
                    action="Escalated",
                    from_role=t["assigned_role"],
                    to_role=new_role,
                    timestamp=timestamp,
                )
    # No return value – changes are persisted in the DB.
def _parse_created_at(value):
    """Convert a stored timestamp into a datetime."""
    if isinstance(value, datetime):
        return value

    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None

# End of routing.py
