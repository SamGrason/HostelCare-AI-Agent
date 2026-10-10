# app.py – Streamlit UI for HostelCare AI

import streamlit as st
import os
import uuid
import datetime
import sys
import pandas as pd

# Ensure the project directory is on the Python path
sys.path.append(os.path.dirname(__file__))

# Streamlit page configuration (must be first Streamlit call)
st.set_page_config(
    page_title="HostelCare AI",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from agent import process_complaint, chat_with_agent
from database import (
    init_db,
    add_complaint,
    get_all_complaints,
    update_ticket_status,
    get_complaint,
    log_action,
    get_action_logs,
    authenticate_user,
    create_user,
)
import database as db
from routing import manual_escalate, auto_escalate

# Initialise DB on first run and run automatic escalation
init_db()
auto_escalate(db)

# ------------------------------------------------------------
# Custom CSS for Authentic Gemini Look & Feel
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto:wght@300;400;500&display=swap');

    /* Global canvas & typography */
    html, body, [class*="css"], .stApp {
        background-color: #131314 !important;
        font-family: 'Google Sans', 'Roboto', sans-serif !important;
        color: #e3e3e3;
    }

    /* Ambient Gemini Radial Blue/Violet Glow */
    .stApp::before {
        content: "";
        position: fixed;
        top: 25%;
        left: 50%;
        transform: translate(-50%, -25%);
        width: 750px;
        height: 500px;
        background: radial-gradient(circle, rgba(30, 80, 160, 0.16) 0%, rgba(20, 30, 55, 0.08) 55%, transparent 75%);
        pointer-events: none;
        z-index: 0;
    }

    /* Top Bar Header */
    .gemini-top-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 16px;
        margin-bottom: 20px;
        position: relative;
        z-index: 10;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }

    .gemini-logo-text {
        font-size: 1.35rem;
        font-weight: 500;
        color: #e3e3e3;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .gemini-sparkle {
        font-size: 1.4rem;
        background: linear-gradient(135deg, #4285F4, #9B72CB, #D96570);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    /* Main Hero Title */
    .gemini-hero-title {
        text-align: center;
        font-size: 2.7rem;
        font-weight: 400;
        color: #e3e3e3;
        margin-top: 1.5rem;
        margin-bottom: 1.8rem;
        letter-spacing: -0.5px;
    }

    /* Gemini Input Pill Box */
    .stTextArea textarea {
        background-color: #1e1f20 !important;
        color: #e3e3e3 !important;
        border: 1px solid #3c4043 !important;
        border-radius: 28px !important;
        padding: 16px 24px !important;
        font-size: 1.05rem !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }

    .stTextArea textarea:focus {
        border-color: #8ab4f8 !important;
        box-shadow: 0 0 0 1px #8ab4f8, 0 8px 24px rgba(0, 0, 0, 0.4) !important;
    }

    /* Suggestion Prompt Chips */
    .prompt-chip {
        display: flex;
        align-items: center;
        gap: 12px;
        background-color: #1e1f20;
        border: 1px solid #3c4043;
        border-radius: 14px;
        padding: 12px 18px;
        color: #c4c7c5;
        font-size: 0.92rem;
        margin-bottom: 10px;
        transition: all 0.2s ease;
    }

    .prompt-chip:hover {
        background-color: #282a2d;
        border-color: #5f6368;
        color: #ffffff;
    }

    /* Navigation tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        justify-content: center;
        border-bottom: 1px solid #282a2c;
        padding-bottom: 6px;
        margin-bottom: 24px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 20px;
        padding: 6px 20px;
        font-weight: 500;
        font-size: 0.9rem;
        background-color: transparent;
        border: 1px solid transparent;
        color: #9aa0a6;
    }

    .stTabs [aria-selected="true"] {
        background-color: #282a2d !important;
        border-color: #3c4043 !important;
        color: #8ab4f8 !important;
    }

    /* Metric cards */
    .metric-card {
        background: #1e1f20;
        border: 1px solid #2f3133;
        border-radius: 16px;
        padding: 16px;
        text-align: center;
        margin-bottom: 12px;
    }

    .metric-value {
        font-size: 2rem;
        font-weight: 600;
        color: #8ab4f8;
    }

    .metric-label {
        font-size: 0.8rem;
        color: #9aa0a6;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }

    /* Login Card Box */
    .auth-card {
        background-color: #1e1f20;
        border: 1px solid #3c4043;
        border-radius: 24px;
        padding: 32px 36px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        margin-top: 10px;
        margin-bottom: 20px;
    }
    
    /* Text link for student registration */
    .register-link {
        color: #8ab4f8;
        font-size: 0.92rem;
        text-decoration: none;
        cursor: pointer;
    }
    
    .register-link:hover {
        color: #aecbfa;
        text-decoration: underline;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# ------------------------------------------------------------
# Authentication Session State Initialization
# ------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "user_name" not in st.session_state:
    st.session_state["user_name"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None

# ------------------------------------------------------------
# Top Header Bar (Pure Streamlit columns to prevent HTML leakage)
# ------------------------------------------------------------
header_left, header_right = st.columns([4, 2])

with header_left:
    st.markdown(
        """
        <div style="display:flex; align-items:center; gap:8px; padding-top:4px;">
            <span class="gemini-sparkle">✦</span>
            <span style="font-size:1.4rem; font-weight:600; color:#e3e3e3; letter-spacing:-0.3px;">HostelCare AI</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_right:
    if st.session_state["logged_in"]:
        r_col1, r_col2 = st.columns([3, 2])
        role_color = "#8ab4f8" if st.session_state["role"] == "Student" else "#f28b82"
        with r_col1:
            st.markdown(
                f"""
                <div style="text-align:right; padding-top:6px;">
                    <span style="font-size:0.88rem; color:#e3e3e3; font-weight:500;">{st.session_state['user_name']}</span>
                    <span style="background:rgba(255,255,255,0.08); color:{role_color}; padding:2px 8px; border-radius:10px; font-size:0.75rem; font-weight:600; margin-left:6px;">{st.session_state['role']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with r_col2:
            if st.button("🚪 Sign Out", key="sign_out_btn", use_container_width=True):
                st.session_state["logged_in"] = False
                st.session_state["user_id"] = None
                st.session_state["user_name"] = None
                st.session_state["role"] = None
                st.rerun()

st.markdown("<div style='border-bottom: 1px solid #282a2c; margin-bottom: 24px; margin-top: 8px;'></div>", unsafe_allow_html=True)


# ============================================================
# LOGIN / SIGNUP SCREEN
# ============================================================

if not st.session_state["logged_in"]:
    st.markdown(
        '<div class="gemini-hero-title">Welcome to HostelCare</div>',
        unsafe_allow_html=True,
    )

    col_l, col_center, col_r = st.columns([1, 2, 1])

    with col_center:
        # Registration mode is controlled by a text link.
        if "show_registration" not in st.session_state:
            st.session_state["show_registration"] = False

        if not st.session_state["show_registration"]:
            with st.container(border=True):
                st.markdown(
                    """
                    <h3 style="margin-top:0; font-weight:500;
                    font-size:1.25rem; color:#e3e3e3;">
                    Sign in
                    </h3>
                    """,
                    unsafe_allow_html=True,
                )

                st.caption(
                    "Sign in with your registered account to access "
                    "your HostelCare dashboard."
                )

                # Text link above the sign-in form.
                link_col, _ = st.columns([2, 3])
                with link_col:
                    if st.button(
                        "Register student account ↗",
                        key="open_registration",
                        type="tertiary",
                    ):
                        st.session_state["show_registration"] = True
                        st.rerun()

                with st.form("login_form"):
                    uid_input = st.text_input(
                        "Unique ID",
                        placeholder="Enter your student or staff ID",
                    )

                    pwd_input = st.text_input(
                        "Password",
                        type="password",
                        placeholder="Enter your password",
                    )

                    submit_login = st.form_submit_button(
                        "Sign In ✦",
                        use_container_width=True,
                    )

                    if submit_login:
                        if not uid_input.strip() or not pwd_input:
                            st.error(
                                "Please provide both your Unique ID "
                                "and password."
                            )
                        else:
                            # Authenticate against the account directory.
                            # The returned database record determines the role.
                            user = None

                            for expected_role in (
                                "Student",
                                "Warden",
                                "Staff",
                            ):
                                user = authenticate_user(
                                    uid_input.strip(),
                                    pwd_input,
                                    expected_role,
                                )
                                if user:
                                    break

                            if user:
                                st.session_state["logged_in"] = True
                                st.session_state["user_id"] = user["user_id"]
                                st.session_state["user_name"] = user["name"]
                                st.session_state["role"] = user["role"]

                                st.rerun()
                            else:
                                st.error(
                                    "Invalid Unique ID or password. "
                                    "Please check your credentials."
                                )

            with st.expander("ℹ️ Default Demo Accounts"):
                st.markdown(
                    """
                    **Student account**
                    - Unique ID: `STU101`
                    - Password: `student123`

                    **Warden account**
                    - Unique ID: `WARDEN01`
                    - Password: `admin123`
                    """
                )

        else:
            with st.container(border=True):
                st.markdown(
                    """
                    <h3 style="margin-top:0; font-weight:500;
                    font-size:1.25rem; color:#e3e3e3;">
                    Register student account
                    </h3>
                    """,
                    unsafe_allow_html=True,
                )

                st.caption(
                    "Create a student account to report and track "
                    "hostel complaints."
                )

                with st.form("register_form"):
                    reg_name = st.text_input(
                        "Full Name",
                        placeholder="Enter your full name",
                    )

                    reg_uid = st.text_input(
                        "Student Registration / Roll No. (Unique ID)",
                        placeholder="e.g. 21BCE1042",
                    )

                    reg_pwd = st.text_input(
                        "Create Password",
                        type="password",
                    )

                    reg_pwd_confirm = st.text_input(
                        "Confirm Password",
                        type="password",
                    )

                    submit_reg = st.form_submit_button(
                        "Create Student Account ✦",
                        use_container_width=True,
                    )

                    if submit_reg:
                        if (
                            not reg_name.strip()
                            or not reg_uid.strip()
                            or not reg_pwd
                        ):
                            st.error("All fields are mandatory.")

                        elif reg_pwd != reg_pwd_confirm:
                            st.error("Passwords do not match.")

                        elif len(reg_pwd) < 8:
                            st.error(
                                "Please choose a password with at least "
                                "8 characters."
                            )

                        else:
                            success = create_user(
                                reg_uid.strip(),
                                reg_name.strip(),
                                reg_pwd,
                                "Student",
                            )

                            if success:
                                st.success(
                                    "Student account created successfully! "
                                    "You can now sign in."
                                )
                                st.session_state["show_registration"] = False
                                st.rerun()
                            else:
                                st.error(
                                    f"Unique ID '{reg_uid}' is already "
                                    "registered."
                                )

                if st.button(
                    "← Back to Sign In",
                    key="back_to_signin",
                    type="tertiary",
                ):
                    st.session_state["show_registration"] = False
                    st.rerun()

# ============================================================
# MAIN APPLICATION INTERFACE (When user is logged in)
# ============================================================
else:
    current_role = st.session_state["role"]
    
    # ROLE-BASED ACCESS CONTROL:
    # Student view:
    #   - "✨ Report Issue"
    #   - "📋 My Tickets & Status"
    # Warden / Admin view:
    #   - "🛠️ Warden & Staff Portal"
    #   - "📊 All Tickets & Analytics"
    
    if current_role == "Warden":
        tab_admin, tab_tracker = st.tabs(["🛠️ Warden & Staff Portal", "📊 All Tickets & Analytics"])
        tab_student = None
    else:
        tab_student, tab_tracker = st.tabs(["✨ Ask / Report Issue", "📋 Track Tickets"])
        tab_admin = None
    
    # ============================================================
    # TAB: Conversational Student Support Agent
    # ============================================================
    if tab_student is not None:
        with tab_student:
            st.markdown(
                '<div class="gemini-hero-title">How can I help you today?</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Describe your hostel issue naturally. I'll help you "
                "understand it, prepare a complaint, and submit it "
                "after your confirmation."
            )

            uid = st.session_state["user_id"]
            chat_key = f"hostelcare_chat_{uid}"
            pending_key = f"hostelcare_pending_{uid}"
            confirm_key = f"hostelcare_confirm_{uid}"

            if chat_key not in st.session_state:
                st.session_state[chat_key] = []
            if pending_key not in st.session_state:
                st.session_state[pending_key] = None
            if confirm_key not in st.session_state:
                st.session_state[confirm_key] = False

            history = st.session_state[chat_key]

            if st.button("＋ New conversation"):
                history.clear()
                st.session_state[pending_key] = None
                st.session_state[confirm_key] = False
                st.rerun()

            
            # Display chat history like ChatGPT
            if not history:
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown("Hi! I'm HostelCare AI. What's happening in your hostel today?")
            
            for message in history:
                if message["role"] == "user":
                    with st.chat_message("user", avatar="🧑‍🎓"):
                        st.markdown(message["content"])
                else:
                    with st.chat_message("assistant", avatar="🤖"):
                        st.markdown(message["content"])


            user_message = st.chat_input(
                "Describe your hostel issue...",
                key=f"hostelcare_input_{uid}",
            )

            if user_message:
                history.append({
                    "role": "user",
                    "content": user_message,
                })

                answer = user_message.strip().lower()

                yes_words = {
                    "yes", "y", "yes submit", "confirm", "submit",
                    "go ahead", "please submit", "yes please",
                }
                no_words = {
                    "no", "n", "cancel", "don't submit",
                    "do not submit", "not yet", "no thanks",
                }

                if st.session_state[confirm_key] and answer in yes_words:
                    parsed = st.session_state[pending_key]

                    if parsed:
                        ticket_id = str(uuid.uuid4())[:8]
                        now = datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat()

                        add_complaint(
                            ticket_id=ticket_id,
                            description=parsed["summary"],
                            category=parsed["category"],
                            block=parsed["block"],
                            priority=parsed["priority"],
                            user_id=uid,
                            status="Open",
                            assigned_role=parsed["assigned_role"],
                            created_at=now,
                            updated_at=now,
                        )

                        log_action(
                            ticket_id=ticket_id,
                            action="Created",
                            from_role=None,
                            to_role=parsed["assigned_role"],
                            timestamp=now,
                        )

                        history.append({
                            "role": "assistant",
                            "content": (
                                f"Your complaint has been submitted! "
                                f"**Ticket ID:** #{ticket_id}\n\n"
                                f"- Category: {parsed['category']}\n"
                                f"- Block: {parsed['block']}\n"
                                f"- Priority: {parsed['priority']}\n"
                                f"- Assigned to: {parsed['assigned_role']}\n\n"
                                "You can track your ticket in the Track Tickets tab."
                            ),
                        })

                    st.session_state[pending_key] = None
                    st.session_state[confirm_key] = False

                elif st.session_state[confirm_key] and answer in no_words:
                    history.append({
                        "role": "assistant",
                        "content": (
                            "No problem. I haven't submitted anything. "
                            "Tell me what you'd like to change or add."
                        ),
                    })
                    st.session_state[pending_key] = None
                    st.session_state[confirm_key] = False

                else:
                    # Continue the conversation, even when confirmation
                    # was previously requested. The user may have more details.
                    with st.spinner("HostelCare AI is thinking..."):
                        result = chat_with_agent(
                            history[:-1],
                            user_message,
                        )

                    if result["ready_to_submit"]:
                        st.session_state[pending_key] = result
                        st.session_state[confirm_key] = True

                        reply = (
                            f"{result['reply']}\n\n"
                            f"**Complaint summary:** {result['summary']}\n\n"
                            f"- Category: {result['category']}\n"
                            f"- Block: {result['block']}\n"
                            f"- Priority: {result['priority']}\n"
                            f"- Assigned to: {result['assigned_role']}\n\n"
                            "Would you like me to submit this complaint? "
                            "Reply **yes** or **no**."
                        )
                    else:
                        # The agent still needs information; do not submit.
                        st.session_state[pending_key] = None
                        st.session_state[confirm_key] = False
                        reply = result["reply"]

                    history.append({
                        "role": "assistant",
                        "content": reply,
                    })
                st.rerun()

    # ============================================================
    # TAB: Ticket Tracker & Analytics
    # ============================================================
    with tab_tracker:
        tickets = get_all_complaints()
        
        if not tickets:
            st.info("No tickets recorded in the database yet.")
        else:
            df_all = pd.DataFrame(tickets)
            
            # Summary KPI Cards
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            total_tickets = len(df_all)
            open_tickets = len(df_all[df_all["status"] == "Open"])
            escalated_tickets = len(df_all[df_all["status"] == "Escalated"])
            resolved_tickets = len(df_all[df_all["status"] == "Resolved"])

            with kpi1:
                st.markdown(f'<div class="metric-card"><div class="metric-value">{total_tickets}</div><div class="metric-label">Total Tickets</div></div>', unsafe_allow_html=True)
            with kpi2:
                st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#8ab4f8;">{open_tickets}</div><div class="metric-label">Open</div></div>', unsafe_allow_html=True)
            with kpi3:
                st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#f28b82;">{escalated_tickets}</div><div class="metric-label">Escalated</div></div>', unsafe_allow_html=True)
            with kpi4:
                st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#81c995;">{resolved_tickets}</div><div class="metric-label">Resolved</div></div>', unsafe_allow_html=True)

            st.markdown("---")

            # Search Bar & Status Filter Controls
            col_search, col_filter, col_cat = st.columns([2, 1, 1])
            with col_search:
                search_query = st.text_input("🔍 Search tickets", placeholder="Search by ticket ID, keyword, or block...")
            with col_filter:
                status_filter = st.selectbox("Status Filter", ["All", "Open", "Escalated", "Resolved"])
            with col_cat:
                cat_list = ["All"] + sorted(df_all["category"].unique().tolist())
                cat_filter = st.selectbox("Category Filter", cat_list)

            # Apply filtering
            filtered_df = df_all.copy()
            if status_filter != "All":
                filtered_df = filtered_df[filtered_df["status"] == status_filter]
            if cat_filter != "All":
                filtered_df = filtered_df[filtered_df["category"] == cat_filter]
            if search_query.strip():
                q = search_query.strip().lower()
                filtered_df = filtered_df[
                    filtered_df["ticket_id"].str.lower().str.contains(q)
                    | filtered_df["description"].str.lower().str.contains(q)
                    | filtered_df["block"].str.lower().str.contains(q)
                    | filtered_df["assigned_role"].str.lower().str.contains(q)
                ]

            # Display Data Table
            st.subheader(f"📋 Records ({len(filtered_df)} matches)")
            if not filtered_df.empty:
                display_df = filtered_df.copy()
                display_df["created_at"] = display_df["created_at"].apply(lambda x: str(x)[:19].replace("T", " "))
                display_df["updated_at"] = display_df["updated_at"].apply(lambda x: str(x)[:19].replace("T", " "))
                st.dataframe(display_df, use_container_width=True)
                
                csv = display_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Export Filtered CSV",
                    data=csv,
                    file_name="hostelcare_tickets.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No tickets match the selected filters.")

            # Analytics Charts Section (Only on analytics view)
            st.markdown("---")
            st.subheader("📈 Insights & Trends")
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                st.markdown("**Complaints by Category**")
                category_counts = df_all["category"].value_counts().reset_index()
                category_counts.columns = ["Category", "Count"]
                st.bar_chart(category_counts.set_index("Category"))

            with chart_col2:
                st.markdown("**Complaints by Priority**")
                priority_counts = df_all["priority"].value_counts().reset_index()
                priority_counts.columns = ["Priority", "Count"]
                st.bar_chart(priority_counts.set_index("Priority"))

    # ============================================================
    # TAB: Admin Dashboard & Resolution Workflow (Warden Only)
    # ============================================================
    if tab_admin is not None:
        with tab_admin:
            st.subheader("🛠️ Hostel Warden Complaint & Escalation Dashboard")
            tickets = get_all_complaints()
            
            if not tickets:
                st.info("No tickets currently logged in the hostel system.")
            else:
                ticket_ids = [t["ticket_id"] for t in tickets]
                selected_id = st.selectbox("Select Ticket ID to Inspect & Action", ticket_ids)
                ticket = get_complaint(selected_id)
                
                if ticket:
                    card_col1, card_col2 = st.columns([2, 1])
                    with card_col1:
                        st.markdown(f"### Ticket #{ticket['ticket_id']}")
                        st.write(f"**Description:** {ticket['description']}")
                        m1, m2, m3, m4 = st.columns(4)
                        m1.write(f"**Category:** {ticket['category']}")
                        m2.write(f"**Block:** {ticket['block']}")
                        m3.write(f"**Priority:** {ticket['priority']}")
                        
                        status_color = "#8ab4f8" if ticket["status"] == "Open" else ("#f28b82" if ticket["status"] == "Escalated" else "#81c995")
                        m4.markdown(f"**Status:** <span style='color:{status_color}; font-weight:bold;'>{ticket['status']}</span>", unsafe_allow_html=True)
                        
                        st.write(f"**Current Responsible Authority:** `{ticket['assigned_role']}`")

                    with card_col2:
                        st.markdown("#### Staff Actions")
                        now = datetime.datetime.utcnow().isoformat()
                        
                        # Resolve Ticket Button
                        if ticket["status"] != "Resolved":
                            if st.button("✅ Mark as Resolved", use_container_width=True):
                                update_ticket_status(
                                    selected_id,
                                    status="Resolved",
                                    updated_at=now,
                                )
                                log_action(
                                    ticket_id=selected_id,
                                    action="Resolved",
                                    from_role=ticket["assigned_role"],
                                    to_role=ticket["assigned_role"],
                                    timestamp=now,
                                )
                                st.success(f"Ticket #{selected_id} has been marked as Resolved!")
                                st.rerun()

                        # Manual Escalation Button
                        if ticket["status"] != "Resolved":
                            if st.button("⚡ Escalate Manually", use_container_width=True):
                                new_role = manual_escalate(ticket)
                                if new_role:
                                    update_ticket_status(
                                        selected_id,
                                        status="Escalated",
                                        assigned_role=new_role,
                                        updated_at=now,
                                    )
                                    log_action(
                                        ticket_id=selected_id,
                                        action="Escalated",
                                        from_role=ticket["assigned_role"],
                                        to_role=new_role,
                                        timestamp=now,
                                    )
                                    st.warning(f"Ticket escalated from {ticket['assigned_role']} to **{new_role}**.")
                                    st.rerun()
                                else:
                                    st.info("Ticket is already at the highest authority level (Director).")

                    st.markdown("---")
                    st.subheader("📜 Audit Action Log")
                    logs = get_action_logs(selected_id)
                    if logs:
                        logs_df = pd.DataFrame(logs)
                        logs_df["timestamp"] = logs_df["timestamp"].apply(lambda x: str(x)[:19].replace("T", " "))
                        st.dataframe(logs_df, use_container_width=True)
                    else:
                        st.info("No audit logs found for this ticket.")

st.caption("© 2026 HostelCare AI • Built with Streamlit, SQLite, and Google Gemini.")



