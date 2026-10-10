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

    conversation = json.dumps(
        history[-12:],
        ensure_ascii=False
    )

    prompt = f"""
You are HostelCare AI, a friendly and intelligent hostel support
assistant helping students report hostel problems.

CONVERSATION STYLE:
- Speak naturally, warmly, and concisely.
- Acknowledge the student's issue before asking a question.
- Ask only ONE relevant question at a time.
- Never ask for information already provided.
- Do not sound like a form or repeat the entire complaint.
- Do not ask unnecessary questions just to prolong the conversation.
- If you have enough information, summarize the issue and ask the
  student whether they want to submit the complaint.

INFORMATION TO COLLECT:
- The problem and affected facility.
- Hostel block.
- Room, floor, or affected area, when relevant.
- Duration and extent of the problem, when useful.
- Any immediate safety risk.

CATEGORIES:
Water, Electrical, Housekeeping, Security, Other.

PRIORITIES:
Low, Medium, High, Critical.

PRIORITY GUIDANCE:
- Low: minor inconvenience with little impact.
- Medium: ordinary issue affecting one room or a small area.
- High: prolonged outage, serious facility failure, or an issue
  affecting multiple rooms or an entire floor.
- Critical: immediate danger, fire, serious electrical hazards,
  or another urgent threat to people's safety.

SAFETY:
If there are sparks, exposed wires, fire, or water near electrical
equipment, tell the student to stay away and alert hostel staff
immediately. Never claim that staff have been contacted.

COMPLAINT HANDLING:
- Remember details from the entire conversation.
- Do not guess missing information.
- If the block is unknown, ask for the block naturally.
- Do not insist on a room number when an entire floor or block
  is affected.
- Once the issue and location are sufficiently clear, set
  ready_to_submit to true and ask for confirmation.
- The application will create the ticket only after confirmation.
- The summary must be a short, clean, standalone sentence.
- Do not concatenate the student's messages.
- Preserve important details such as location, duration, and scope.
- Use the actual hostel block identifier, such as A or B, in
  the block field, not the words "A Block".
- If information is still missing, set ready_to_submit to false
  and ask only for the most useful missing detail.

PREVIOUS CONVERSATION:
{conversation}

LATEST STUDENT MESSAGE:
{user_message}

Return ONLY valid JSON using exactly these keys:
{{
  "reply": "Natural response to the student",
  "ready_to_submit": false,
  "category": "Other",
  "block": "Unknown",
  "priority": "Medium",
  "summary": "Short, clear complaint summary"
}}
"""

    categories = {
        "Water", "Electrical", "Housekeeping", "Security", "Other"
    }
    priorities = {"Low", "Medium", "High", "Critical"}

    if client:
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                },
            )

            raw = (response.text or "").strip()
            raw = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                raw,
                flags=re.IGNORECASE,
            )

            result = json.loads(raw)

            category = result.get("category")
            priority = result.get("priority")
            block = str(result.get("block", "Unknown")).strip()
            summary = str(result.get("summary", "")).strip()
            reply = str(result.get("reply", "")).strip()

            if category not in categories:
                category = "Other"

            if priority not in priorities:
                priority = "Medium"

            block_match = re.search(
                r"\b(?:block\s*([a-z0-9]+)|"
                r"([a-z0-9]+)\s*block)\b",
                block,
                re.IGNORECASE,
            )

            if block_match:
                block = (
                    block_match.group(1) or block_match.group(2)
                ).upper()

            if not block:
                block = "Unknown"

            ready = (
                result.get("ready_to_submit") is True
                and bool(summary)
                and block.lower() != "unknown"
            )

            # Do not accidentally submit a ticket without a usable summary.
            if not summary:
                ready = False
                summary = user_message.strip()[:500]

            if not reply:
                reply = (
                    "Could you tell me a little more about the issue?"
                )

            result = {
                "reply": reply,
                "ready_to_submit": ready,
                "category": category,
                "block": block[:40],
                "priority": priority,
                "summary": summary[:500],
                "assigned_role": route_complaint(
                    category=category,
                    block=block,
                    priority=priority,
                ),
            }

            return result

        except Exception as exc:
            # This message appears in Streamlit Cloud logs.
            # It does not reveal your API key.
            print(
                f"Gemini chat error: {type(exc).__name__}: {exc}"
            )

    # ---------------------------------------------------------
    # FALLBACK: used if Gemini is unavailable or its call fails.
    # ---------------------------------------------------------

    previous_user_messages = [
        str(item.get("content", ""))
        for item in history
        if item.get("role") == "user"
    ]

    combined = " ".join(
        previous_user_messages + [user_message]
    ).strip()

    parsed = _fallback_parse(combined)

    # Recognize "Block A", "A Block", and "A block".
    location_match = re.search(
        r"\b(?:block\s*([a-z0-9]+)|"
        r"([a-z0-9]+)\s*block)\b",
        combined,
        re.IGNORECASE,
    )

    if location_match:
        parsed["block"] = (
            location_match.group(1) or location_match.group(2)
        ).upper()

    block = str(parsed.get("block", "Unknown"))
    category = parsed.get("category", "Other")
    priority = parsed.get("priority", "Medium")

    # Detect prolonged or widespread power outages.
    if category == "Electrical" and re.search(
        r"\b(power outage|no power|no electricity|"
        r"power cut|electricity is out)\b",
        combined,
        re.IGNORECASE,
    ):
        if re.search(
            r"\b(entire floor|whole floor|whole block|"
            r"entire block|multiple floors|"
            r"\d+\s*hours?|since morning)\b",
            combined,
            re.IGNORECASE,
        ):
            priority = "High"

    location_known = block.lower() != "unknown"
    enough_detail = len(combined.split()) >= 5
    ready = location_known and enough_detail

    # Create a cleaner fallback summary from the latest message.
    summary_source = " ".join(
        previous_user_messages + [user_message]
    )

    summary_source = re.sub(
        r"\s+",
        " ",
        summary_source,
    ).strip()

    summary = summary_source[:500]

    parsed["category"] = category
    parsed["priority"] = priority
    parsed["block"] = block
    parsed["summary"] = summary
    parsed["ready_to_submit"] = ready
    parsed["assigned_role"] = route_complaint(
        category=category,
        block=block,
        priority=priority,
    )

    if ready:
        parsed["reply"] = (
            "Thanks, I have the location and issue details. "
            "Would you like me to submit this complaint?"
        )
    elif not location_known:
        parsed["reply"] = (
            "I'm sorry you're dealing with this. "
            "Which hostel block is affected?"
        )
    else:
        parsed["reply"] = (
            "I understand. Could you tell me a little more "
            "about the problem and how much of the area is affected?"
        )

    return parsed


# End of agent.py
