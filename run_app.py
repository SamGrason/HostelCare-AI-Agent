import streamlit as st

# First Streamlit call – guarantees detection
st.set_page_config(page_title="HostelCare AI", layout="wide")
st.title("HostelCare AI – Loading…")

# Import the real UI (all logic lives in app.py)
import app
