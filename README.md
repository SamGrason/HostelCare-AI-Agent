# HostelCare AI – Intelligent Hostel Complaint & Escalation Agent

## Overview

**HostelCare AI** is an agentic AI system that lets hostel residents submit natural‑language complaints. The system:
- Uses **Google Gemini** (free tier) to extract structured data (category, block, priority, summary).
- Routes the ticket to the correct authority based on a department hierarchy.
- Persists tickets in a lightweight **SQLite** database.
- Performs **automatic escalation** after 30 minutes and also provides a manual escalation button for administrators.
- Provides a simple **Streamlit** web UI with three pages:
  - **Submit Complaint** – free‑text form for students.
  - **Ticket Tracker** – view all tickets and download a CSV report.
  - **Admin Dashboard** – view ticket details, audit log, and manual escalation.

The whole project is contained in a single Python package and can be deployed to **Streamlit Community Cloud** with a single click.

---

## Repository Structure
```
HostelCare-AI-Agent/
├─ app.py                 # Streamlit UI entry point
├─ agent.py               # LLM (Gemini) parsing + fallback
├─ database.py            # SQLite helper functions
├─ routing.py             # Department mapping, hierarchy, escalation logic
├─ schema.sql             # DB schema and seed data
├─ requirements.txt       # Python dependencies
├─ .gitignore             # Standard Python ignore file
└─ README.md              # This file
```

---

## Setup Instructions (local)
1. **Clone the repo** (already done for you).
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   venv\Scripts\activate   # on Windows
   pip install -r requirements.txt
   ```
3. Add your Gemini API key to a `.env` file (already present). Example:
   ```text
   GOOGLE_GEMINI_API_KEY=YOUR_KEY_HERE
   ```
4. Run the app locally:
   ```bash
   streamlit run app.py
   ```
   Open the URL shown in the terminal (usually `http://localhost:8501`).

---

## Deployment to Streamlit Community Cloud
1. Push the repository to GitHub (the CI step will be done automatically – see below).
2. In your Streamlit Cloud account, click **New app** and select the repository `haseebahsan-n/HostelCare-AI-Agent` and the file `app.py`.
3. The platform will install the dependencies from `requirements.txt` and launch the app.
4. Once the app is live, share the generated URL with your instructor.

---

## Demo Scenarios
| # | Complaint (user input) | Expected outcome |
|---|------------------------|------------------|
| 1 | "There is no water in Block B since this morning." | Category **Water**, assigned to **Technician**, ticket created. |
| 2 | "My electrical socket has been broken for an hour." | Category **Electrical**, assigned to **Technician**, high priority. |
| 3 | "Sparks are coming from the panel in Block C!" | Category **Electrical**, **Critical** priority → starts at **Supervisor**, escalation path flagged. |
| 4 | "Something is broken in my room." | Fallback parser asks for clarification (in a real UI you could add a follow‑up). |

---

## License
MIT – feel free to adapt for your own campus projects.
