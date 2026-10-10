# agent.py – Core Agentic logic for HostelCare AI

"""Agent module that receives a raw complaint string, extracts structured
information using Google Gemini (or a deterministic fallback), and decides
which authority should handle the ticket.

Public entry point: ``process_complaint(text: str) -> dict`` which returns a
dictionary with at least the keys:
    - category
    - block
    - priority
    - assigned_role
    - summary (optional short description)

If the Gemini API fails (no key, network error, quota), the function falls
back to a simple keyword‑based parser defined in ``_fallback_parse``.
"""

import os
import json
import re
from typing import Dict

from google import genai
from dotenv import load_dotenv

# Load environment variables (Gemini API key) from .env in the project root
load_dotenv()

API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")

if API_KEY:
    client = genai.Client(api_key=API_KEY)
else:
    client = None

# ---------------------------------------------------------------------------
# Helper: deterministic fallback parser (keyword based)
# ---------------------------------------------------------------------------

def _fallback_parse(text: str) -> Dict[str, str]:
    """Simple rule‑based extraction used when the LLM is unavailable.
    It looks for keywords to guess ``category``, ``block`` and ``priority``.
    """
    lowered = text.lower()

    # Category mapping – extend as needed
    categories = {
        "water": "Water",
        "plumb": "Water",
        "leak": "Water",
        "electrical": "Electrical",
        "power": "Electrical",
        "electric": "Electrical",
        "light": "Electrical",
        "clean": "Housekeeping",
        "trash": "Housekeeping",
        "security": "Security",
        "theft": "Security",
    }
    category = "Other"
    for kw, cat in categories.items():
        if kw in lowered:
            category = cat
            break

    # Block detection – pattern "block X" where X is a letter/number
    block_match = re.search(r"block\s*([a-zA-Z0-9]+)", lowered)
    block = block_match.group(1).upper() if block_match else "Unknown"

    # Priority heuristics – keywords indicating urgency
    if any(word in lowered for word in ["urgent", "immediate", "asap", "critical", "danger", "spark", "fire"]):
        priority = "Critical"
    elif any(word in lowered for word in ["no water", "no power", "leak", "broken"]):
        priority = "High"
    else:
        priority = "Medium"

    return {
        "category": category,
        "block": block,
        "priority": priority,
        "summary": text.strip(),
    }

# ---------------------------------------------------------------------------
# LLM based parsing
# ---------------------------------------------------------------------------

def _llm_parse(text: str) -> Dict[str, str]:
    """Send the complaint to Gemini and ask for a JSON response.
    The prompt enforces a strict schema so parsing is reliable.
    """
    prompt = (
        "You are a helpful assistant that extracts structured information from a hostel complaint."
        " Return a JSON object with exactly these keys:"
        "\n  - category (Water, Electrical, Housekeeping, Security, Other)"
        "\n  - block (e.g., 'A', 'B2')"
        "\n  - priority (Low, Medium, High, Critical)"
        "\n  - summary (short 1‑2 sentence version of the complaint)"
        "\nOnly output the JSON and nothing else."
        f"\n\nComplaint: {text}\n"
    )
    # Force deterministic fallback parsing – Gemini API call disabled
    data = _fallback_parse(text)
    return data

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_complaint(text: str) -> Dict[str, str]:
    """Main entry point used by the Streamlit UI.
    Returns a dict with ``category``, ``block``, ``priority`` and ``assigned_role``.
    """
    if not text:
        raise ValueError("Complaint text cannot be empty")

    # 1️⃣ Parse – LLM if available, else fallback
    parsed = _llm_parse(text) if client else _fallback_parse(text)

    # 2️⃣ Routing – determine initial authority
    from routing import route_complaint

    assigned_role = route_complaint(
        category=parsed["category"],
        block=parsed["block"],
        priority=parsed["priority"],
    )

    parsed["assigned_role"] = assigned_role
    return parsed



def chat_with_agent(history, user_message):
    """Handle one turn of a conversational hostel support chat."""

    from routing import route_complaint

    # Combine previous student messages with the latest message.
    previous_user_messages = [
        str(item.get("content", ""))
        for item in history
        if item.get("role") == "user"
    ]

    all_user_text = " ".join(
        previous_user_messages + [user_message]
    ).strip()

    conversation = json.dumps(
        history[-12:],
        ensure_ascii=False
    )

    # ---------------------------------------------------------
    # LOCATION CHECKS: enforced regardless of Gemini's answer.
    # ---------------------------------------------------------

    block_match = re.search(
        r"\bblock\s*([a-z0-9]+)\b|"
        r"\b([a-z0-9]+)\s*(?:block|blocl)\b",
        all_user_text,
        re.IGNORECASE,
    )

    block = "Unknown"
    if block_match:
        block = (
            block_match.group(1) or block_match.group(2)
        ).upper()

    floor_pattern = (
        r"\b(?:ground|basement|first|second|third|fourth|"
        r"fifth|sixth|seventh|eighth|ninth|tenth|"
        r"\d{1,2}(?:st|nd|rd|th)?)\s+floor\b|"
        r"\bfloor\s*(?:no\.?\s*)?\d{1,2}\b"
    )

    floor_known = bool(
        re.search(floor_pattern, all_user_text, re.IGNORECASE)
    )

    room_known = bool(re.search(
        r"\b(?:room|rm\.?)\s*(?:no\.?\s*)?"
        r"[a-z]?\d{1,4}[a-z]?\b",
        all_user_text,
        re.IGNORECASE,
    ))

    entire_block_affected = bool(re.search(
        r"\b(?:entire|whole)\s+(?:hostel\s+)?block\b|"
        r"\bthroughout\s+(?:the\s+)?block\b",
        all_user_text,
        re.IGNORECASE,
    ))

    location_detail_known = (
        floor_known or room_known or entire_block_affected
    )

    # ---------------------------------------------------------
    # GEMINI PROMPT
    # ---------------------------------------------------------

    prompt = f"""
You are HostelCare AI, a friendly hostel support assistant.

CONVERSATION STYLE:
- Be empathetic, natural, concise, and helpful.
- Ask only ONE relevant question at a time.
- Remember information already given.
- Never repeat a question already answered.
- Acknowledge the problem before asking a follow-up.
- Do not behave like a form or repeat the whole complaint.

INFORMATION TO COLLECT:
1. The problem and affected facility.
2. Hostel block.
3. Specific floor or room when relevant.
4. Duration or extent of the problem when useful.
5. Immediate safety risks.

CATEGORIES:
Water, Electrical, Housekeeping, Security, Other.

PRIORITIES:
Low, Medium, High, Critical.

PRIORITY GUIDANCE:
- Low: minor inconvenience.
- Medium: ordinary issue affecting a small area.
- High: prolonged outage or serious problem affecting a floor
  or multiple rooms.
- Critical: immediate danger or a serious safety threat.

SAFETY:
For fire, sparks, exposed wires, or water near electrical
equipment, tell the student to stay away and alert hostel staff.
Never claim that staff have been contacted.

SUBMISSION RULES:
- Do not guess missing information.
- Do not ask for a room number if an entire floor is affected.
- Create a clean, standalone summary, not a concatenation of messages.
- Set ready_to_submit=true only when the issue and location are clear.
- The application will independently validate the location and
  ask the student for confirmation before creating a ticket.
- If the block is unknown, ask which block is affected.
- If the floor/room is unknown and the issue affects a specific
  facility, ask which floor or room is affected.
- Ask for duration only when it would materially help assess the issue.

PREVIOUS CONVERSATION:
{conversation}

LATEST STUDENT MESSAGE:
{user_message}

Return ONLY valid JSON with these keys:
{{
  "reply": "Natural response to the student",
  "ready_to_submit": false,
  "category": "Other",
  "block": "Unknown",
  "priority": "Medium",
  "summary": "Short standalone complaint summary"
}}
"""

    valid_categories = {
        "Water", "Electrical", "Housekeeping", "Security", "Other"
    }
    valid_priorities = {"Low", "Medium", "High", "Critical"}

    result = None

    # ---------------------------------------------------------
    # CALL GEMINI
    # ---------------------------------------------------------

    if client:
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )

            raw = (response.text or "").strip()
            raw = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                raw,
                flags=re.IGNORECASE,
            )

            result = json.loads(raw)

        except Exception as exc:
            print(
                f"Gemini chat error: {type(exc).__name__}: {exc}"
            )

    # ---------------------------------------------------------
    # FALLBACK IF GEMINI FAILS
    # ---------------------------------------------------------

    if not isinstance(result, dict):
        parsed = _fallback_parse(all_user_text)

        result = {
            "reply": "",
            "ready_to_submit": False,
            "category": parsed.get("category", "Other"),
            "block": block,
            "priority": parsed.get("priority", "Medium"),
            "summary": "",
        }

    category = result.get("category", "Other")
    priority = result.get("priority", "Medium")

    if category not in valid_categories:
        category = _fallback_parse(all_user_text).get(
            "category", "Other"
        )

    if priority not in valid_priorities:
        priority = "Medium"

    # Trust the block found in the student's messages first.
    if block == "Unknown":
        model_block = str(result.get("block", "Unknown")).strip()

        model_match = re.search(
            r"\bblock\s*([a-z0-9]+)\b|"
            r"\b([a-z0-9]+)\s*(?:block|blocl)\b",
            model_block,
            re.IGNORECASE,
        )

        if model_match:
            block = (
                model_match.group(1) or model_match.group(2)
            ).upper()

    # Recognize issue descriptions without depending entirely on Gemini.
    issue_known = (
        category != "Other"
        or bool(re.search(
            r"\b(water|leak|electricity|power|light|"
            r"clean|dirty|garbage|security|broken|"
            r"not working|overflow|clogged|blocked|"
            r"restroom|bathroom|washroom|toilet)\b",
            all_user_text,
            re.IGNORECASE,
        ))
    )

    # ---------------------------------------------------------
    # MANDATORY SUBMISSION VALIDATION
    # ---------------------------------------------------------

    ready = (
        issue_known
        and block != "Unknown"
        and location_detail_known
        and bool(str(result.get("summary", "")).strip())
        and result.get("ready_to_submit") is True
    )

    # Use an appropriate follow-up if required details are missing.
    if not issue_known:
        reply = (
            "Of course, I'll help you with that. "
            "Could you describe the problem you're experiencing?"
        )

    elif block == "Unknown":
        reply = (
            "I'm sorry you're dealing with this. "
            "Which hostel block is affected?"
        )

    elif not location_detail_known:
        if re.search(
            r"\b(floor|restroom|bathroom|toilet|washroom)\b",
            all_user_text,
            re.IGNORECASE,
        ):
            reply = "Got it. Which floor is that restroom on?"
        else:
            reply = (
                "Thanks for explaining. Which specific floor, "
                "room, or area is affected?"
            )

    elif ready:
        reply = (
            "Thanks, I understand the issue and where it's happening. "
            "Would you like me to submit this complaint?"
        )

    else:
        # Do not offer submission until all checks pass.
        reply = str(result.get("reply", "")).strip()

        if not reply:
            reply = (
                "Thanks for explaining. Could you tell me a little "
                "more about the issue?"
            )

    # ---------------------------------------------------------
    # BUILD A CLEAN SUMMARY
    # ---------------------------------------------------------

    summary = str(result.get("summary", "")).strip()

    if not summary:
        summary = all_user_text[:500]

    # Remove accidental duplicate whitespace.
    summary = re.sub(r"\s+", " ", summary).strip()

    # ---------------------------------------------------------
    # ROUTE THE COMPLAINT
    # ---------------------------------------------------------

    assigned_role = route_complaint(
        category=category,
        block=block,
        priority=priority,
    )

    return {
        "reply": reply,
        "ready_to_submit": ready,
        "category": category,
        "block": block,
        "priority": priority,
        "summary": summary[:500],
        "assigned_role": assigned_role,
    }


# End of agent.py
