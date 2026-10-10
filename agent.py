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

# End of agent.py
