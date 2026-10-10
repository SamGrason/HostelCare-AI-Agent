# HostelCare AI – Intelligent Hostel Complaint & Escalation Agent

## Overview

**HostelCare AI** is an AI-powered hostel complaint management system that helps students report issues in natural language and routes complaints to the appropriate authority.

The system combines conversational AI, structured complaint management, ticket tracking, and escalation logic to improve how hostel issues are reported and followed up.

### Key Features

- **Conversational AI:** Uses Google Gemini to understand complaints and guide students through the submission process.
- **Natural-language understanding:** Extracts information such as complaint category, hostel block, room number, priority, and summary when available.
- **Confirmation before submission:** Prepares a complaint summary for the student to review before creating a ticket.
- **Department routing:** Maps complaint categories to departments and assigns an initial authority.
- **Authority hierarchy:** Supports escalation through Technician, Supervisor, Warden, and Director.
- **Automatic escalation:** Checks complaint age and escalates eligible unresolved tickets after 30 minutes.
- **Manual escalation:** Allows administrators to escalate complaints when required.
- **SQLite database:** Stores user accounts, complaints, assignment details, timestamps, and audit logs.
- **Complaint history:** Records status changes, notes, and other relevant updates.
- **Ticket tracking:** Supports viewing complaints and monitoring their status.
- **Admin dashboard:** Provides administrative visibility into tickets and escalation activity.
- **CSV reporting:** Supports downloading complaint reports through the interface.

The application is built with Python and Streamlit, with Google Gemini providing the conversational AI capabilities.

---

## Repository Structure

```text
HostelCare-AI-Agent/
├── app.py                 # Streamlit application and user interface
├── agent.py               # Gemini integration and complaint understanding
├── database.py            # SQLite operations, migrations, and history
├── routing.py             # Department mapping and escalation logic
├── schema.sql             # Initial database schema and seed data
├── requirements.txt       # Python dependencies
├── .gitignore             # Git exclusions
└── README.md               # Project documentation
```

---

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application logic |
| Streamlit | Web interface |
| Google Gemini API | Conversational AI and complaint understanding |
| SQLite | Complaint and user data storage |
| SQL | Database queries and schema management |
| GitHub | Source control and project hosting |
| Streamlit Community Cloud | Application deployment |

---

## Application Workflow

1. **Student describes an issue:** The student explains the problem in natural language.
2. **AI gathers details:** The conversational agent asks follow-up questions when necessary.
3. **Complaint preparation:** The system prepares a structured summary with the available complaint details.
4. **Student confirmation:** The student confirms whether to submit the complaint.
5. **Ticket creation:** The application saves the complaint and its initial status in SQLite.
6. **Authority assignment:** The routing module determines the initial authority based on the complaint priority and routing rules.
7. **Tracking and updates:** Students and administrators can monitor tickets through the available interface.
8. **Escalation:** Eligible unresolved tickets can be escalated automatically after 30 minutes or manually by an administrator.

### Authority Hierarchy

```text
Technician
    ↓
Supervisor
    ↓
Warden
    ↓
Director
```

Critical complaints are initially assigned to the Supervisor according to the current routing rules. Other complaints start with the Technician.

The current implementation uses a 30-minute age threshold. Further escalation depends on the ticket's current assigned role and the escalation logic.

---

## Complaint Categories

The current routing configuration includes:

| Complaint category | Department |
|---|---|
| Water | Plumbing |
| Electrical | Electrical |
| Housekeeping | Housekeeping |
| Security | Security |
| Other | Housekeeping (fallback) |

These mappings can be extended in `routing.py` as additional complaint categories and departments are introduced.

---

## Database Design

HostelCare AI uses SQLite to manage application data.

### Main tables

- **`users`** – user accounts and roles.
- **`departments`** – departments responsible for complaints.
- **`authorities`** – authority roles and hierarchy levels.
- **`complaints`** – complaint descriptions, category, block, priority, status, assignment, timestamps, and optional additional details.
- **`action_logs`** – audit records for creation, assignment, escalation, and other actions.
- **`complaint_updates`** – complaint status history, update notes, and timestamps.

The complaint fields support storing additional information such as room number, duration, impact, escalation level, resolution notes, and resolution timestamp.

`database.py` includes a database initialization and migration routine that adds missing complaint columns and creates the complaint history table without intentionally deleting existing complaint records.

**Persistence note:** The database is stored in a local SQLite file named `hostelcare.db`. On Streamlit Community Cloud, local files may not persist reliably across certain redeployments or environment replacements. For production use, consider a managed external database.

---

## Setup Instructions (Local)

### 1. Clone the repository

```bash
git clone https://github.com/haseebahsan-n/HostelCare-AI-Agent.git
cd HostelCare-AI-Agent
```

### 2. Create a virtual environment

On Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

On macOS or Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the Gemini API key

Obtain an API key from Google AI Studio and configure it through an environment variable or Streamlit secrets.

For local development, create a `.env` file only if your application is configured to load environment variables from it:

```text
GOOGLE_GEMINI_API_KEY=YOUR_KEY_HERE
```

Make sure `.env` is excluded from Git. Do not commit or publish your actual API key.

For Streamlit Community Cloud, open the app's **Settings → Secrets** and configure:

```toml
GOOGLE_GEMINI_API_KEY = "YOUR_KEY_HERE"
```

The application must read the key using the same variable name.

### 5. Run the application

```bash
streamlit run app.py
```

Open the local URL shown in the terminal, usually:

`http://localhost:8501`

---

## Deployment to Streamlit Community Cloud

1. Push the latest project files to the GitHub repository.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create a new app and select the repository `haseebahsan-n/HostelCare-AI-Agent`.
4. Select `app.py` as the entry point.
5. Configure `GOOGLE_GEMINI_API_KEY` under the app's **Settings → Secrets**.
6. Deploy the application and check the logs if any errors occur.
7. Test complaint submission, ticket tracking, and escalation after deployment.

Subsequent commits to the configured branch generally trigger redeployment automatically.

**Live application:** https://hostelcare-ai-agent.streamlit.app/

**GitHub repository:** https://github.com/haseebahsan-n/HostelCare-AI-Agent

---

## Demo Scenarios

| # | Sample complaint | Expected behavior |
|---|---|---|
| 1 | "There is no water in Block B since this morning." | Identifies a water-related complaint, prepares a summary, and routes it to the Technician after confirmation. |
| 2 | "My electrical socket has been broken for an hour." | Identifies an electrical complaint and asks for any missing details required by the conversation flow. |
| 3 | "Sparks are coming from the electrical panel in Block C!" | Should identify a potentially critical electrical hazard and prioritize it appropriately. |
| 4 | "There is no electricity in Room 828, A Block." | Should capture the available block and room details and prepare a complaint summary. |
| 5 | "The bathroom tap has been leaking for two days." | Should identify a water/plumbing issue and capture its duration when supported by the parser. |
| 6 | An unresolved ticket remains open beyond 30 minutes. | The automatic escalation routine should attempt to promote it to the next authority. |
| 7 | An administrator manually escalates a ticket. | The ticket assignment and associated audit information should reflect the escalation. |

Actual category extraction, priority assignment, and follow-up behavior depend on the AI parser and application logic. The scenarios above are intended as test cases, not guarantees that every input will be classified perfectly.

---

## Security and Limitations

- Keep API keys and other secrets out of source control.
- The demo authentication implementation should be upgraded to use securely hashed passwords before real deployment.
- The local SQLite database is appropriate for a prototype but may not be sufficient for concurrent, long-term production use.
- Automatic escalation runs when the application invokes the escalation routine; it is not a guaranteed background scheduler.
- AI-generated complaint details and priorities should be reviewed and validated, especially for safety-critical complaints.
- The current implementation is a prototype and should be tested thoroughly before use in a real hostel environment.

---

## Future Enhancements

- Persistent cloud database integration.
- Secure password hashing and role-based access control.
- Real-time notifications to students and hostel authorities.
- Automated follow-ups for unresolved complaints.
- More detailed complaint analytics and resolution-time reports.
- Improved urgency detection and safety-oriented escalation rules.
- Full complaint timeline in the student and administrator dashboards.
- Department-specific assignment and configurable escalation thresholds.

---

## License

MIT License — see the repository for licensing details.
