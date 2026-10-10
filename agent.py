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
    """
    Conduct a context-aware conversation.

    Gemini decides which follow-up question is useful.
    Application checks prevent submission without a known block
    and a sufficiently specific location.
    """

    # Collect previous student messages.
    previous_user_messages = [
        str(item.get("content", ""))
        for item in history
        if item.get("role") == "user"
    ]

    messages = previous_user_messages + [user_message]

    combined = re.sub(
        r"\s+",
        " ",
        " ".join(messages),
    ).strip()

    conversation = json.dumps(
        history[-16:],
        ensure_ascii=False,
    )

    # -----------------------------------------------------
    # DETECT HOSTEL BLOCK
    # -----------------------------------------------------

    block = "Unknown"

    for message in messages:
        match = re.search(
            r"\bblock\s*([a-z0-9]+)\b|"
            r"\b([a-z0-9]+)\s*(?:block|blocl)\b",
            message,
            re.IGNORECASE,
        )

        if match:
            block = (
                match.group(1) or match.group(2)
            ).upper()

    # -----------------------------------------------------
    # DETECT FLOOR, INCLUDING A SHORT ANSWER LIKE "8"
    # -----------------------------------------------------

    floor_known = False
    floor_label = ""

    floor_words = (
        r"ground|basement|first|second|third|fourth|fifth|"
        r"sixth|seventh|eighth|ninth|tenth"
    )

    ordinal = r"\d{1,2}(?:st|nd|rd|th)?"

    for index, message in enumerate(messages):
        text = message.strip().lower()

        match = re.search(
            rf"\b({floor_words})\s+floor\b|"
            rf"\b({ordinal})\s+floor\b|"
            rf"\bfloor\s*({ordinal})\b",
            text,
            re.IGNORECASE,
        )

        # Interpret "8" or "8th" as a floor when answering
        # a question asking which floor.
        if not match and re.fullmatch(ordinal, text):
            assistant_messages = [
                str(item.get("content", ""))
                for item in history
                if item.get("role") == "assistant"
            ]

            if assistant_messages and re.search(
                r"which floor|what floor|floor is",
                assistant_messages[-1],
                re.IGNORECASE,
            ):
                match = re.match(rf"({ordinal})", text)

        if match:
            floor_known = True

            floor_label = next(
                (group for group in match.groups() if group),
                text,
            )

            # Normalize a numeric floor to a readable ordinal.
            if floor_label.isdigit():
                number = int(floor_label)
                suffix = (
                    "th" if 10 <= number % 100 <= 20
                    else {1: "st", 2: "nd", 3: "rd"}.get(
                        number % 10, "th"
                    )
                )
                floor_label = f"{number}{suffix}"

    # -----------------------------------------------------
    # DETECT ROOM AND WHOLE-BLOCK LOCATIONS
    # -----------------------------------------------------

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

    location_detail_known = (
        floor_known or room_known or whole_block
    )

    # -----------------------------------------------------
    # DETECT CATEGORY
    # -----------------------------------------------------

    text = combined.lower()

    if re.search(
        r"\b(no water|water shortage|water supply|"
        r"water leak|plumbing|tap|toilet flush)\b",
        text,
    ):
        category = "Water"

    elif re.search(
        r"\b(electricity|no power|power outage|power cut|"
        r"electrical|sparks|exposed wire)\b",
        text,
    ):
        category = "Electrical"

    elif re.search(
        r"\b(cleaning|dirty|garbage|rubbish|unclean|"
        r"restroom cleaning)\b",
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

    issue_known = category != "Other"

    # -----------------------------------------------------
    # DETECT DURATION AND IMPACT
    # -----------------------------------------------------

    duration_known = bool(re.search(
        r"\b\d+\s*(?:minutes?|mins?|hours?|hrs?|days?)\b|"
        r"\bsince (?:morning|afternoon|yesterday|last night)\b",
        text,
        re.IGNORECASE,
    ))

    impact_known = bool(re.search(
        r"\b(entire floor|whole floor|multiple floors|"
        r"all restrooms|all toilets|several rooms|"
        r"one restroom|one toilet|only my room)\b",
        text,
        re.IGNORECASE,
    ))

    # Determine urgency from available evidence.
    priority = "Medium"

    if re.search(
        r"\b(fire|sparks|electrocution|exposed live wire)\b",
        text,
        re.IGNORECASE,
    ):
        priority = "Critical"

    elif category == "Electrical" and re.search(
        r"\b(no power|no electricity|power outage|power cut)\b",
        text,
        re.IGNORECASE,
    ) and (
        duration_known
        or re.search(
            r"\b(entire floor|whole floor|multiple floors|"
            r"whole block|entire block)\b",
            text,
            re.IGNORECASE,
        )
    ):
        priority = "High"

    elif category == "Water" and duration_known:
        priority = "High"

    # -----------------------------------------------------
    # GEMINI CONVERSATION
    # -----------------------------------------------------

    ready = False
    reply = ""

    if client:
        try:
            prompt = f"""
You are HostelCare AI, an intelligent hostel support agent.

Have a real conversation, not a rigid form interaction.

Your goals:
- Understand the student's actual problem.
- Ask relevant follow-up questions.
- Remember all previously supplied information.
- Acknowledge answers naturally.
- Never repeat questions that have already been answered.
- Ask only ONE question per response.
- Do not ask for a room number if a floor is affected.
- Do not submit simply because a block and floor are known.
- Consider duration, impact, severity, and safety when relevant.
- Avoid asking unnecessary questions when the complaint is already clear.
- If the student asks why you need more details, explain briefly.
- If the student wants to add information, continue the conversation.
- Never claim a ticket was created before the application confirms it.

Examples of useful reasoning:
- A water shortage: determine whether one or several restrooms
  are affected and how long supply has been unavailable.
- An electrical issue: establish scope and duration.
- A cleaning issue: understand what needs cleaning and where.
- A security issue: determine what happened and whether danger is ongoing.

Do not rigidly follow these examples. Use judgment.

Submission:
- Ask follow-up questions until you understand the issue well enough
  to create a useful complaint.
- For ordinary facilities issues, consider the affected location,
  duration, and impact. If a detail is not relevant or the student
  cannot provide it, do not keep asking forever.
- Once ready, prepare a short, accurate summary and ask for confirmation.
- ready_to_submit must be true only when the complaint is sufficiently
  understood and the block is known.
- Categories: Water, Electrical, Housekeeping, Security, Other.
- Priorities: Low, Medium, High, Critical.
- Never invent details.

Known extracted facts:
Block: {block}
Specific floor identified: {floor_known}
Floor: {floor_label or "Unknown"}
Room identified: {room_known}
Duration provided: {duration_known}
Affected scope described: {impact_known}
Detected category: {category}

Conversation:
{conversation}

Latest student message:
{user_message}

Return ONLY valid JSON:
{{
  "reply": "Natural response",
  "ready_to_submit": false,
  "category": "Other",
  "block": "Unknown",
  "priority": "Medium",
  "summary": "Short standalone complaint summary"
}}
"""

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

            valid_categories = {
                "Water", "Electrical", "Housekeeping",
                "Security", "Other",
            }

            valid_priorities = {
                "Low", "Medium", "High", "Critical",
            }

            category = result.get("category", category)

            if category not in valid_categories:
                category = "Other"

            priority = result.get("priority", priority)

            if priority not in valid_priorities:
                priority = "Medium"

            summary = str(result.get("summary", "")).strip()
            reply = str(result.get("reply", "")).strip()

            # Use our independently detected block.
            # Do not trust a model-invented block.
            ready = (
                result.get("ready_to_submit") is True
                and block != "Unknown"
                and location_detail_known
                and bool(summary)
                and bool(reply)
            )

        except Exception as exc:
            print(
                f"Gemini chat error: {type(exc).__name__}: {exc}"
            )

    # -----------------------------------------------------
    # FALLBACK WHEN GEMINI IS UNAVAILABLE
    # -----------------------------------------------------

    if not client or not reply:
        parsed = _fallback_parse(combined)
        category = parsed.get("category", category)

        if block == "Unknown":
            reply = "Which hostel block is affected?"

        elif not location_detail_known:
            reply = (
                "Which floor is affected?"
                if re.search(
                    r"\b(restroom|toilet|bathroom|washroom)\b",
                    text,
                )
                else "Which specific floor, room, or area is affected?"
            )

        elif not duration_known:
            reply = (
                "How long has this been happening?"
            )

        elif not impact_known:
            reply = (
                "Is the issue affecting just this restroom, "
                "or are other restrooms affected too?"
            )

        else:
            reply = (
                "I understand the issue. Would you like me to "
                "submit this complaint?"
            )

        ready = (
            block != "Unknown"
            and location_detail_known
            and duration_known
            and impact_known
        )

    # -----------------------------------------------------
    # BUILD A USEFUL COMPLAINT SUMMARY
    # -----------------------------------------------------

    if category == "Water":
        location = (
            f"the {floor_label} floor restroom"
            if floor_known
            else "the affected restroom"
            if not room_known
            else "the affected room"
        )

        duration_match = re.search(
            r"\b(?:for|past)\s+(\d+\s*(?:minutes?|mins?|hours?|hrs?|days?))",
            text,
            re.IGNORECASE,
        )

        duration = (
            f" for {duration_match.group(1)}"
            if duration_match
            else ""
        )

        summary = (
            f"No water supply in {location}, {block} Block{duration}."
        )

        if impact_known and re.search(
            r"\b(all restrooms|all toilets|multiple floors|"
            r"entire floor|whole floor|several rooms)\b",
            text,
        ):
            summary = (
                f"Water supply interruption affecting multiple "
                f"facilities in {block} Block{duration}."
            )

    else:
        summary = (
            str(locals().get("summary", "")).strip()
            or combined[:500]
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
