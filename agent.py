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

# agent.py – Core Agentic logic for HostelCare AI

import os
import json
import re
from typing import Dict

from google import genai
from dotenv import load_dotenv

from routing import route_complaint

# ---------------------------------------------------------
# GEMINI CONFIGURATION
# ---------------------------------------------------------

load_dotenv()

API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")

if API_KEY:
    client = genai.Client(api_key=API_KEY)
else:
    client = None


# ---------------------------------------------------------
# FALLBACK COMPLAINT PARSER
# ---------------------------------------------------------

def _fallback_parse(text: str) -> Dict[str, str]:
    """Extract basic complaint information without Gemini."""

    lowered = text.lower()

    categories = {
        "water": "Water",
        "plumb": "Water",
        "leak": "Water",
        "electrical": "Electrical",
        "electricity": "Electrical",
        "power": "Electrical",
        "electric": "Electrical",
        "light": "Electrical",
        "clean": "Housekeeping",
        "trash": "Housekeeping",
        "garbage": "Housekeeping",
        "security": "Security",
        "theft": "Security",
    }

    category = "Other"

    for keyword, value in categories.items():
        if keyword in lowered:
            category = value
            break

    block_match = re.search(
        r"\bblock\s*([a-zA-Z0-9]+)\b|"
        r"\b([a-zA-Z0-9]+)\s*block\b",
        text,
        re.IGNORECASE,
    )

    block = (
        block_match.group(1) or block_match.group(2)
        if block_match
        else "Unknown"
    )

    if any(word in lowered for word in [
        "fire", "sparks", "electrocution",
        "exposed live wire", "immediate danger",
    ]):
        priority = "Critical"
    elif any(word in lowered for word in [
        "urgent", "no water", "no power",
        "power outage", "leak", "broken",
    ]):
        priority = "High"
    else:
        priority = "Medium"

    return {
        "category": category,
        "block": block.upper(),
        "priority": priority,
        "summary": text.strip(),
    }


# ---------------------------------------------------------
# GEMINI COMPLAINT PARSER
# ---------------------------------------------------------

def _llm_parse(text: str) -> Dict[str, str]:
    """Extract structured complaint details using Gemini."""

    if not client:
        return _fallback_parse(text)

    prompt = f"""
Extract the details from this hostel complaint.

Return JSON with:
- category: Water, Electrical, Housekeeping, Security, Other
- block: hostel block identifier, or Unknown
- priority: Low, Medium, High, Critical
- summary: short standalone complaint description

Do not invent information.

Complaint:
{text}
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )

        result = json.loads(response.text or "{}")

        if result.get("category") not in {
            "Water", "Electrical", "Housekeeping", "Security", "Other"
        }:
            result["category"] = "Other"

        if result.get("priority") not in {
            "Low", "Medium", "High", "Critical"
        }:
            result["priority"] = "Medium"

        result.setdefault("block", "Unknown")
        result.setdefault("summary", text.strip())

        return result

    except Exception as exc:
        print(f"Gemini parsing error: {type(exc).__name__}: {exc}")
        return _fallback_parse(text)


# ---------------------------------------------------------
# PUBLIC COMPLAINT PROCESSING FUNCTION
# ---------------------------------------------------------

def process_complaint(text: str) -> Dict[str, str]:
    """Parse a complaint and route it to the responsible authority."""

    if not text or not text.strip():
        raise ValueError("Complaint text cannot be empty")

    parsed = _llm_parse(text)

    parsed["assigned_role"] = route_complaint(
        category=parsed["category"],
        block=parsed["block"],
        priority=parsed["priority"],
    )

    return parsed


# ---------------------------------------------------------
# CONVERSATIONAL HOSTELCARE AGENT
# ---------------------------------------------------------

def chat_with_agent(history, user_message):
    """Maintain conversation context and collect complaint details reliably."""

    # Build the full conversation, including the latest user message.
    conversation_messages = list(history) + [
        {"role": "user", "content": user_message}
    ]

    user_messages = [
        str(m.get("content", "")).strip()
        for m in conversation_messages
        if m.get("role") == "user"
    ]

    combined = " ".join(user_messages)
    text = combined.lower()

    # Determine which question the student was answering each time.
    previous_question = {}
    last_assistant = ""

    for message in conversation_messages:
        if message.get("role") == "assistant":
            last_assistant = str(message.get("content", "")).lower()
        elif message.get("role") == "user":
            previous_question[message.get("content", "")] = last_assistant

    latest_question = previous_question.get(user_message, "")

    # -----------------------------------------------------
    # EXTRACT BLOCK
    # -----------------------------------------------------
    block = "Unknown"

    for message in user_messages:
        match = re.search(
            r"\bblock\s*([a-z0-9]+)\b|"
            r"\b([a-z0-9]+)\s*(?:block|blocl)\b",
            message,
            re.IGNORECASE,
        )
        if match:
            block = (match.group(1) or match.group(2)).upper()

    # -----------------------------------------------------
    # EXTRACT FLOOR, INCLUDING SHORT ANSWERS
    # -----------------------------------------------------
    floor_label = ""
    floor_words = {
        "ground": "Ground",
        "basement": "Basement",
        "first": "1st",
        "second": "2nd",
        "third": "3rd",
        "fourth": "4th",
        "fifth": "5th",
        "sixth": "6th",
        "seventh": "7th",
        "eighth": "8th",
        "ninth": "9th",
        "tenth": "10th",
    }

    for message in user_messages:
        value = message.strip().lower()
        question = previous_question.get(message, "")

        match = re.search(
            r"\b(ground|basement|first|second|third|fourth|fifth|"
            r"sixth|seventh|eighth|ninth|tenth)\s+floor\b|"
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+floor\b|"
            r"\bfloor\s*(\d{1,2})(?:st|nd|rd|th)?\b",
            value,
        )

        if match:
            word = match.group(1)
            number = match.group(2) or match.group(3)

            if word:
                floor_label = floor_words[word]
            elif number:
                n = int(number)
                suffix = (
                    "th" if 10 <= n % 100 <= 20
                    else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
                )
                floor_label = f"{n}{suffix}"

        # Interpret "8" or "8th" as a floor when answering a floor question.
        elif re.fullmatch(r"\d{1,2}(?:st|nd|rd|th)?", value) and (
            "which floor" in question
            or "what floor" in question
            or "floor is affected" in question
        ):
            n = int(re.match(r"\d+", value).group())
            suffix = (
                "th" if 10 <= n % 100 <= 20
                else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
            )
            floor_label = f"{n}{suffix}"

        elif value in floor_words and (
            "which floor" in question or "what floor" in question
        ):
            floor_label = floor_words[value]

    floor_known = bool(floor_label)

    # -----------------------------------------------------
    # DETECT ISSUE CATEGORY
    # -----------------------------------------------------
    if re.search(
        r"\b(no water|water shortage|water supply|water leak|"
        r"plumbing|tap|toilet flush|restroom|washroom)\b",
        text,
    ):
        category = "Water"
    elif re.search(
        r"\b(electricity|no power|power outage|power cut|"
        r"electrical|sparks|exposed wire|broken light)\b",
        text,
    ):
        category = "Electrical"
    elif re.search(
        r"\b(cleaning|dirty|garbage|rubbish|unclean)\b",
        text,
    ):
        category = "Housekeeping"
    elif re.search(
        r"\b(security|theft|stolen|intruder|harassment)\b",
        text,
    ):
        category = "Security"
    else:
        category = "Other"

    # -----------------------------------------------------
    # TRACK WHETHER FOLLOW-UP QUESTIONS HAVE BEEN ANSWERED
    # -----------------------------------------------------
    duration_known = bool(re.search(
        r"\b\d+\s*(?:minutes?|mins?|hours?|hrs?|days?|weeks?)\b|"
        r"\bsince (?:morning|afternoon|yesterday|last night)\b",
        text,
    ))

    impact_known = bool(re.search(
        r"\b(entire floor|whole floor|multiple floors|all restrooms|"
        r"all toilets|several rooms|one restroom|one toilet|"
        r"only my room|only this restroom|just this restroom)\b",
        text,
    ))

    uncertainty = {
        "don't know", "dont know", "do not know",
        "not sure", "unsure", "i don't know", "i dont know",
    }
    latest_answer = user_message.strip().lower()

    # "Don't know" is a valid response to the question asked.
    if latest_answer in uncertainty:
        if any(term in latest_question for term in (
            "affecting", "other restrooms", "scope",
        )):
            impact_known = True
        if any(term in latest_question for term in (
            "how long", "duration", "when did",
        )):
            duration_known = True

    # Also recognize an answer like "only this one" or "the whole floor".
    if latest_answer in {
        "only one", "just one", "this one", "only this one",
        "just this one", "one restroom", "one toilet",
        "whole floor", "entire floor", "multiple restrooms",
    }:
        if any(term in latest_question for term in (
            "affecting", "other restrooms", "scope",
        )):
            impact_known = True

    room_known = bool(re.search(
        r"\b(?:room|rm\.?)\s*(?:no\.?\s*)?[a-z]?\d{1,4}[a-z]?\b",
        text,
    ))

    whole_block = bool(re.search(
        r"\b(?:entire|whole)\s+(?:hostel\s+)?block\b|"
        r"\bthroughout (?:the )?block\b",
        text,
    ))

    location_known = floor_known or room_known or whole_block

    # -----------------------------------------------------
    # PRIORITY
    # -----------------------------------------------------
    if re.search(
        r"\b(fire|electrocution|exposed live wire)\b", text
    ):
        priority = "Critical"
    elif category == "Water" and duration_known:
        priority = "High"
    elif category == "Electrical" and re.search(
        r"\b(no power|no electricity|power outage|power cut)\b", text
    ):
        priority = "High"
    else:
        priority = "Medium"

    # -----------------------------------------------------
    # DECIDE THE NEXT CONVERSATION STEP
    # -----------------------------------------------------
    if block == "Unknown":
        reply = "Which hostel block is affected?"
        ready = False

    elif not location_known:
        if re.search(r"\b(restroom|toilet|bathroom|washroom)\b", text):
            reply = "Which floor is the affected restroom on?"
        else:
            reply = "Which floor, room, or specific area is affected?"
        ready = False

    elif not duration_known:
        reply = "How long has this been happening?"
        ready = False

    elif not impact_known:
        reply = (
            "Is this affecting only this restroom, or are other "
            "restrooms affected too? If you're unsure, that's okay."
        )
        ready = False

    else:
        ready = True
        reply = (
            "Thanks, I have enough information to prepare the complaint. "
            "Please review the summary below."
        )

    # -----------------------------------------------------
    # PREPARE SUMMARY AND AUTHORITY
    # -----------------------------------------------------
    if category == "Water":
        location = (
            f"the {floor_label} floor restroom"
            if floor_known
            else "the affected restroom"
        )

        duration_match = re.search(
            r"\b(?:for|past|since)\s+"
            r"(\d+\s*(?:minutes?|mins?|hours?|hrs?|days?|weeks?))\b",
            text,
        )

        duration = (
            f" for {duration_match.group(1)}"
            if duration_match and duration_match.group(1)
            else ""
        )

        summary = (
            f"No water supply in {location}, {block} Block{duration}."
        )
    else:
        summary = combined.strip()[:500]

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
