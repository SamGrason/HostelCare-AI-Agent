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

    conversation = json.dumps(history[-12:], ensure_ascii=False)

    prompt = f"""
You are HostelCare AI, a helpful hostel support assistant.

Talk naturally with the student. Ask one relevant follow-up question
at a time. Remember details already given. Do not behave like a form.

Gather:
- What the problem is
- Hostel block and room/location, when relevant
- Any safety risk
- Enough information to summarize the complaint

Categories: Water, Electrical, Housekeeping, Security, Other.
Priorities: Low, Medium, High, Critical.

If the student reports sparks, fire, exposed wires, or water near
electrical equipment, advise them to stay away and alert hostel staff
immediately. Never claim that help has arrived or a ticket was created
unless the application confirms it.

Set ready_to_submit=true only when you understand the problem and
have enough location information to prepare a ticket. The app will
ask the student for confirmation before creating it.

Previous conversation:
{conversation}

Latest student message:
{user_message}

Return ONLY valid JSON with these keys:
{{
  "reply": "Your next conversational response",
  "ready_to_submit": false,
  "category": "Other",
  "block": "Unknown",
  "priority": "Medium",
  "summary": "Short description of the complaint"
}}
"""

    if client:
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )

            raw = (response.text or "").strip()
            raw = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                raw,
                flags=re.IGNORECASE,
            )
            result = json.loads(raw)

            categories = {
                "Water", "Electrical", "Housekeeping", "Security", "Other"
            }
            priorities = {"Low", "Medium", "High", "Critical"}

            if result.get("category") not in categories:
                result["category"] = "Other"

            if result.get("priority") not in priorities:
                result["priority"] = "Medium"

            result["block"] = str(result.get("block", "Unknown"))[:40]
            result["summary"] = str(
                result.get("summary", user_message)
            )[:500]
            result["reply"] = str(
                result.get("reply", "Could you tell me a little more?")
            )
            result["ready_to_submit"] = (
                result.get("ready_to_submit") is True
                and bool(result["summary"].strip())
                and result["block"].lower() != "unknown"
            )

            result["assigned_role"] = route_complaint(
                category=result["category"],
                block=result["block"],
                priority=result["priority"],
            )
            return result

        except Exception:
            # Continue with a basic fallback if the API call fails.
            pass

    # Basic fallback when Gemini is unavailable.
    combined = " ".join(
        str(item.get("content", ""))
        for item in history
        if item.get("role") == "user"
    ) + " " + user_message

    parsed = _fallback_parse(combined)

    # Recognize both "Block B" and "B Block".
    location_match = re.search(
        r"\b(?:block\s*([a-z0-9]+)|([a-z0-9]+)\s*block)\b",
        combined,
        re.IGNORECASE,
    )
    if location_match:
        parsed["block"] = (
            location_match.group(1) or location_match.group(2)
        ).upper()

    location_known = parsed["block"] != "Unknown"
    enough_detail = len(combined.split()) >= 5
    ready = location_known and enough_detail

    parsed["assigned_role"] = route_complaint(
        category=parsed["category"],
        block=parsed["block"],
        priority=parsed["priority"],
    )
    parsed["ready_to_submit"] = ready
    parsed["reply"] = (
        f"Here's my understanding: {parsed['summary']}. "
        "Would you like me to submit this complaint?"
        if ready
        else
        "I'm here to help. Could you tell me which hostel block "
        "you're in and describe where the problem is happening?"
    )
    return parsed

# End of agent.py
