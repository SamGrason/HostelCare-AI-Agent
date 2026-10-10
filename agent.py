
"""HostelCare AI — conversational complaint and routing agent."""

import os
import json
import re
from typing import Dict

from google import genai
from dotenv import load_dotenv
from routing import route_complaint

load_dotenv()

# Read the API key from environment variables or Streamlit Cloud Secrets.
API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")

if not API_KEY:
    try:
        import streamlit as st
        API_KEY = st.secrets.get("GOOGLE_GEMINI_API_KEY")
    except Exception:
        API_KEY = None

client = genai.Client(api_key=API_KEY) if API_KEY else None

MODEL = "gemini-2.5-flash"

VALID_CATEGORIES = {
    "Water", "Electrical", "Housekeeping", "Security", "Other"
}

VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}


# ---------------------------------------------------------
# BASIC FALLBACK PARSER
# ---------------------------------------------------------

def _fallback_parse(text: str) -> Dict[str, str]:
    """Basic complaint parser used when Gemini is unavailable."""

    value = text.lower()

    if re.search(
        r"\b(water|plumbing|leak|tap|toilet|restroom|washroom)\b",
        value,
    ):
        category = "Water"
    elif re.search(
        r"\b(electricity|electrical|electric|power|current|"
        r"light|fan|socket|switch|short circuit)\b",
        value,
    ):
        category = "Electrical"
    elif re.search(
        r"\b(cleaning|dirty|garbage|rubbish|dustbin|"
        r"housekeeping|smell)\b",
        value,
    ):
        category = "Housekeeping"
    elif re.search(
        r"\b(security|theft|stolen|intruder|harassment)\b",
        value,
    ):
        category = "Security"
    else:
        category = "Other"

    block = "Unknown"
    match = re.search(
        r"\b(?:block\s+([a-z0-9]+)|"
        r"([a-z0-9]+)\s+block)\b",
        value,
    )
    if match:
        block = (match.group(1) or match.group(2)).upper()

    if re.search(
        r"\b(fire|electrocution|exposed live wire|"
        r"person trapped|immediate danger)\b",
        value,
    ):
        priority = "Critical"
    elif re.search(
        r"\b(no power|no electricity|no current|"
        r"power outage|no water|overflow|urgent)\b",
        value,
    ):
        priority = "High"
    else:
        priority = "Medium"

    return {
        "category": category,
        "block": block,
        "priority": priority,
        "summary": text.strip(),
    }


# ---------------------------------------------------------
# PUBLIC COMPLAINT PROCESSING
# ---------------------------------------------------------

def _llm_parse(text: str) -> Dict[str, str]:
    """Extract complaint details from a standalone description."""

    if not client:
        return _fallback_parse(text)

    prompt = f"""
Extract structured information from this hostel complaint.

Return a JSON object with:
- category: Water, Electrical, Housekeeping, Security, or Other
- block: block identifier, or Unknown
- priority: Low, Medium, High, or Critical
- summary: concise standalone description of the complaint

Never invent missing details.

Complaint:
{text}
"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        data = json.loads(response.text or "{}")

        if data.get("category") not in VALID_CATEGORIES:
            data["category"] = "Other"

        if data.get("priority") not in VALID_PRIORITIES:
            data["priority"] = "Medium"

        data.setdefault("block", "Unknown")
        data.setdefault("summary", text.strip())

        return data

    except Exception as exc:
        print(f"Complaint parsing fallback: {type(exc).__name__}")
        return _fallback_parse(text)


def process_complaint(text: str) -> Dict[str, str]:
    """Parse a complaint and identify the responsible authority."""

    if not text or not text.strip():
        raise ValueError("Complaint text cannot be empty")

    data = _llm_parse(text)

    data["assigned_role"] = route_complaint(
        category=data["category"],
        block=data["block"],
        priority=data["priority"],
    )

    return data


# ---------------------------------------------------------
# CONVERSATIONAL AGENT
# ---------------------------------------------------------

def chat_with_agent(history, user_message):
    """
    Have a natural conversation, collect relevant details,
    and prepare a complaint for the app's confirmation flow.
    """

    user_message = str(user_message or "").strip()

    if not user_message:
        return {
            "reply": "Tell me a little about the issue you're facing.",
            "ready_to_submit": False,
            "category": "Other",
            "block": "Unknown",
            "priority": "Medium",
            "summary": "",
            "assigned_role": "Hostel Administration",
        }

    # Keep the conversation in its original order.
    messages = list(history or []) + [
        {"role": "user", "content": user_message}
    ]

    # The latest message is included only once in this transcript.
    transcript = []
    for item in messages[-20:]:
        role = item.get("role", "")
        content = str(item.get("content", "")).strip()

        if role in ("user", "assistant") and content:
            speaker = "Student" if role == "user" else "HostelCare AI"
            transcript.append(f"{speaker}: {content}")

    conversation = "\n".join(transcript)

    # -----------------------------------------------------
    # GEMINI: NATURAL CONVERSATION + STRUCTURED STATE
    # -----------------------------------------------------

    if client:
        prompt = f"""
You are HostelCare AI, a helpful, calm, natural-sounding hostel
support assistant. Speak like a good human support agent, not a form
or a rigid chatbot.

YOUR TASK
Understand the student's hostel issue, ask useful follow-up questions,
and prepare a complaint for the student to review and confirm.

CONVERSATION RULES
1. Read the ENTIRE conversation before replying.
2. Remember every reliable detail already provided. Never ask for
   information that the student has already given.
3. Understand informal language, spelling mistakes, shorthand, and
   natural answers. For example, "no current in my roomn" means
   there is an electricity/power problem.
4. Extract details from combined answers. For example, "A block 828"
   may provide both block A and room 828. Do not discard either detail.
5. Ask only ONE concise follow-up question at a time.
6. Ask questions relevant to the actual issue:
   - Electrical: outage, lights, fans, sockets, exposed wires.
   - Water: water supply, leakage, drainage, restroom issues.
   - Housekeeping: cleaning, garbage, hygiene.
   - Security: access, theft, intruders, safety.
   - Other: determine what is actually wrong before deciding.
   NEVER ask about restrooms during an electrical complaint unless
   the student actually mentioned a restroom-related issue.
7. Usually establish the issue, block, exact location (room/floor/area),
   duration, and scope or impact when relevant. Do not force irrelevant
   questions. If a detail is genuinely unnecessary, leave it unknown.
8. If the student asks "why?", "how is that related?", or requests an
   explanation, answer their question first. Explain briefly why the
   detail could help, then ask again only if it is still necessary.
9. "I don't know" and "I'm not sure" are valid answers. Do not get
   stuck repeating the same question. Accept uncertainty and move on
   if that detail is not essential.
10. If the student corrects a detail, use the correction. If their
    answer is ambiguous, ask a short clarifying question rather than
    making up an answer.
11. Be conversational and concise. Acknowledge frustration politely.
    Do not sound overly formal, repeatedly greet the student, or use
    the same canned sentence on every turn.
12. Never claim a complaint was submitted. The app submits it only
    after the student reviews the summary and confirms.
13. Set ready_to_submit to true only when you understand the issue,
    have enough location information to route it (at least the block
    and an affected room/area or clearly identified wider area), and
    can provide a useful summary. Do not wait for every optional detail.
14. For immediate danger such as fire, electrocution, or an exposed
    live wire, advise the student to stay away and contact campus
    security/emergency services immediately. Do not delay this advice
    while collecting details.
15. Do not infer a floor solely from a room number unless the student
    explicitly states it or confirms it.

OUTPUT FORMAT
Return ONLY valid JSON with these keys:
{{
  "reply": "The natural response to show the student",
  "ready_to_submit": false,
  "category": "Water",
  "block": "Unknown",
  "priority": "Medium",
  "summary": "A concise, standalone complaint summary",
  "assigned_role": "The role returned by the routing system"
}}

For category, use exactly one of: Water, Electrical, Housekeeping,
Security, Other.
For priority, use exactly one of: Low, Medium, High, Critical.
Use "Unknown" when the block is not known.
Do not invent facts. Keep the summary updated as new details arrive.
The reply should ask for the most useful missing detail, or explain
what is needed. Once ready_to_submit is true, the reply should tell
the student that you have prepared a summary for their review.

FULL CONVERSATION:
{conversation}
"""

        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )

            data = json.loads(response.text or "{}")

            category = data.get("category", "Other")
            if category not in VALID_CATEGORIES:
                category = "Other"

            block = str(data.get("block", "Unknown")).strip()
            if not block:
                block = "Unknown"

            priority = data.get("priority", "Medium")
            if priority not in VALID_PRIORITIES:
                priority = "Medium"

            summary = str(data.get("summary", "")).strip()
            reply = str(data.get("reply", "")).strip()

            # The routing module remains the source of assignment logic.
            assigned_role = route_complaint(
                category=category,
                block=block,
                priority=priority,
            )

            return {
                "reply": reply or "Could you tell me a little more about the issue?",
                "ready_to_submit": bool(data.get("ready_to_submit", False)),
                "category": category,
                "block": block,
                "priority": priority,
                "summary": summary,
                "assigned_role": assigned_role,
            }

        except Exception as exc:
            print(f"Conversational AI fallback: {type(exc).__name__}: {exc}")

    # -----------------------------------------------------
    # FALLBACK: SIMPLE, NON-GEMINI CONVERSATION
    # -----------------------------------------------------

    user_text = " ".join(
        str(m.get("content", ""))
        for m in messages
        if m.get("role") == "user"
    )
    lowered = user_text.lower()

    parsed = _fallback_parse(user_text)

    # Extract a block from any user response in the conversation.
    block = parsed["block"]

    # Try to preserve details when the student answers with shorthand.
    previous_assistant = ""
    if len(messages) >= 2:
        previous_assistant = str(
            messages[-2].get("content", "")
        ).lower()

    room_match = re.search(
        r"\broom\s*(?:no\.?\s*)?([a-z]?\d{1,4}[a-z]?)\b",
        lowered,
    )
    room = room_match.group(1).upper() if room_match else ""

    floor_match = re.search(
        r"\b(ground|basement|first|second|third|fourth|fifth|"
        r"sixth|seventh|eighth|ninth|tenth|\d{1,2}(?:st|nd|rd|th)?)"
        r"\s+floor\b",
        lowered,
    )
    floor = floor_match.group(1) if floor_match else ""

    duration_match = re.search(
        r"\b(?:for|past|since)\s+"
        r"(\d+\s*(?:minutes?|mins?|hours?|hrs?|days?|weeks?))\b",
        lowered,
    )
    duration = duration_match.group(1) if duration_match else ""

    issue_text = user_text
    category = parsed["category"]

    location = room or floor
    if floor and room:
        location = f"{floor} floor, room {room}"

    if block == "Unknown":
        reply = "Which hostel block is affected? For example, A Block or B Block."
        ready = False
    elif not issue_text.strip():
        reply = "Could you describe the issue?"
        ready = False
    elif not location:
        reply = (
            "Got it. Which room or area is affected? "
            "You can give me the room number and floor together."
        )
        ready = False
    elif not duration:
        reply = "Thanks, I have the location. How long has this been happening?"
        ready = False
    else:
        ready = True
        reply = "I've put the details together. Please review the complaint summary before submitting."

    summary_parts = [user_text.strip()]
    if block != "Unknown":
        summary_parts.append(f"Block: {block}")
    if location:
        summary_parts.append(f"Location: {location}")
    if duration:
        summary_parts.append(f"Duration: {duration}")

    summary = " | ".join(summary_parts)[:500]

    assigned_role = route_complaint(
        category=category,
        block=block,
        priority=parsed["priority"],
    )

    # A basic fallback should not pretend it understands more than it does.
    return {
        "reply": reply,
        "ready_to_submit": ready,
        "category": category,
        "block": block,
        "priority": parsed["priority"],
        "summary": summary,
        "assigned_role": assigned_role,
    }


# End of agent.py
