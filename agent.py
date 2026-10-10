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
    """Conversational hostel agent with reliable detail tracking."""

    import json
    import re
    from routing import route_complaint

    # Collect the student's messages, not the assistant's replies.
    previous_user_messages = [
        str(item.get("content", ""))
        for item in history
        if item.get("role") == "user"
    ]

    messages = previous_user_messages + [user_message]
    combined = " ".join(messages)
    combined = re.sub(r"\s+", " ", combined).strip()
    conversation = json.dumps(
        history[-12:], ensure_ascii=False
    )

    # ---------------------------------------------------------
    # 1. Detect hostel block, including "A block" and "A blocl".
    # ---------------------------------------------------------

    block = "Unknown"

    for message in messages:
        match = re.search(
            r"\bblock\s*([a-z0-9]+)\b|"
            r"\b([a-z0-9]+)\s*(?:block|blocl)\b",
            message,
            re.IGNORECASE,
        )
        if match:
            block = (match.group(1) or match.group(2)).upper()

    # ---------------------------------------------------------
    # 2. Detect floor answers such as "8th", "8th floor",
    #    "second floor", and "ground floor".
    # ---------------------------------------------------------

    floor_known = False
    floor_label = ""

    floor_words = (
        r"ground|basement|first|second|third|fourth|fifth|"
        r"sixth|seventh|eighth|ninth|tenth"
    )
    ordinal = r"\d{1,2}(?:st|nd|rd|th)?"

    for message in messages:
        text = message.strip().lower()

        match = re.search(
            rf"\b({floor_words})\s+floor\b|"
            rf"\b({ordinal})\s+floor\b|"
            rf"\bfloor\s*({ordinal})\b",
            text,
        )

        # A short reply like "8th" is accepted as a floor answer
        # when the assistant previously asked which floor.
        if not match and re.fullmatch(ordinal, text):
            previous_assistant = [
                str(item.get("content", ""))
                for item in history
                if item.get("role") == "assistant"
            ]

            if previous_assistant and re.search(
                r"which floor|what floor|floor is",
                previous_assistant[-1],
                re.IGNORECASE,
            ):
                match = re.match(rf"({ordinal})", text)

        if match:
            floor_known = True
            floor_label = next(
                (group for group in match.groups() if group),
                text,
            )

    # ---------------------------------------------------------
    # 3. Detect room or whole-block locations.
    # ---------------------------------------------------------

    room_known = bool(re.search(
        r"\b(?:room|rm\.?)\s*(?:no\.?\s*)?"
        r"[a-z]?\d{1,4}[a-z]?\b",
        combined,
        re.IGNORECASE,
    ))

    whole_block = bool(re.search(
        r"\b(?:entire|whole)\s+(?:hostel\s+)?block\b|"
        r"\bthroughout\s+(?:the\s+)?block\b",
        combined,
        re.IGNORECASE,
    ))

    location_detail_known = floor_known or room_known or whole_block

    # ---------------------------------------------------------
    # 4. Identify complaint category from all student messages.
    # ---------------------------------------------------------

    text = combined.lower()

    if re.search(
        r"\b(no water|water shortage|water supply|"
        r"no drinking water|no water supply|water leak)\b",
        text,
    ):
        category = "Water"
    elif re.search(
        r"\b(electricity|no power|power outage|"
        r"power cut|electrical|sparks|exposed wire)\b",
        text,
    ):
        category = "Electrical"
    elif re.search(
        r"\b(cleaning|dirty|garbage|rubbish|"
        r"unclean|toilet cleaning|restroom cleaning)\b",
        text,
    ):
        category = "Housekeeping"
    elif re.search(
        r"\b(security|theft|stolen|intruder|"
        r"harassment|unsafe person)\b",
        text,
    ):
        category = "Security"
    else:
        category = "Other"

    # ---------------------------------------------------------
    # 5. Detect duration and affected area.
    # ---------------------------------------------------------

    duration_known = bool(re.search(
        r"\b\d+\s*(?:minutes?|mins?|hours?|hrs?|days?)\b|"
        r"\bsince (?:morning|afternoon|yesterday|last night)\b",
        text,
        re.IGNORECASE,
    ))

    issue_known = category != "Other"

    # High priority for prolonged water supply interruption.
    priority = "Medium"

    if category == "Water" and (
        duration_known
        or re.search(
            r"\b(entire floor|whole floor|multiple floors|"
            r"all restrooms|all toilets)\b",
            text,
        )
    ):
        priority = "High"

    if re.search(
        r"\b(fire|sparks|electrocution|exposed live wire)\b",
        text,
        re.IGNORECASE,
    ):
        priority = "Critical"

    # ---------------------------------------------------------
    # 6. Enforce information requirements.
    # ---------------------------------------------------------

    if not issue_known:
        ready = False
        reply = (
            "I can help with that. Could you describe the "
            "hostel problem you're experiencing?"
        )

    elif block == "Unknown":
        ready = False
        reply = "I'm sorry you're dealing with this. Which hostel block is affected?"

    elif not location_detail_known:
        ready = False
        reply = (
            "Got it. Which floor is the affected restroom on?"
            if re.search(
                r"\b(restroom|toilet|bathroom|washroom)\b",
                text,
            )
            else "Which specific floor, room, or area is affected?"
        )

    else:
        ready = True
        reply = (
            "Thanks, I understand. Would you like me to submit "
            "this complaint?"
        )

    # ---------------------------------------------------------
    # 7. Generate a clean summary from known facts.
    # ---------------------------------------------------------

    if category == "Water":
        location_description = (
            f"the {floor_label} floor restroom"
            if floor_known
            else "the affected restroom"
            if not room_known
            else "the affected room"
        )

        duration_match = re.search(
            r"\b(?:for|since)\s+(\d+\s*(?:minutes?|mins?|hours?|hrs?|days?))",
            text,
            re.IGNORECASE,
        )

        duration = (
            f" for {duration_match.group(1)}"
            if duration_match
            else ""
        )

        summary = (
            f"No water supply in {location_description}, "
            f"{block} Block{duration}."
        )

    else:
        summary = combined[:500]

    # ---------------------------------------------------------
    # 8. Ask Gemini to improve the conversational reply only
    #    when it is safe to do so. Required checks stay in control.
    # ---------------------------------------------------------

    if client and not ready:
        try:
            prompt = f"""
You are a friendly hostel support assistant.
Reply naturally in one or two short sentences.
Ask ONLY for the missing information identified below.
Do not repeat information the student has already supplied.
Do not ask multiple questions.

Conversation:
{conversation}

Student's latest message:
{user_message}

Missing information:
{
    "hostel block" if block == "Unknown"
    else "specific floor, room, or affected area"
    if not location_detail_known
    else "a clear description of the issue"
}

Return only the reply text. Do not return JSON.
"""
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            generated_reply = (response.text or "").strip()

            if generated_reply:
                reply = generated_reply

        except Exception as exc:
            print(
                f"Gemini chat error: {type(exc).__name__}: {exc}"
            )

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
