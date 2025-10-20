import streamlit as st
import pandas as pd
import base64

from utils import logger, load_css
from auth import show_login_page
from admin_dashboard import show_admin_dashboard
from lead_dashboard import show_leader_dashboard
from student_dashboard import show_student_dashboard, show_evaluator_ui
from peer_learning import show_peer_learning_page
from student_profile import show_student_profile

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="PragyanAI ProjectDemo Tracking Platform",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- MAIN APP LOGIC ---
def main():
    load_css()
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        show_login_page()
    else:
        with st.sidebar:
            try:
                # You can use a direct path or a URL for the logo
                st.image("PragyanAI_Transperent.png", width=80)
            except Exception:
                logger.warning("Logo image 'PragyanAI_Transperent.png' not found.")
            
            st.sidebar.markdown("<h2 style='text-align: center; color: #1a73e8;'>PragyanAI Platform</h2>", unsafe_allow_html=True)
            st.sidebar.divider()
            st.sidebar.subheader("API Configuration")
            st.session_state['groq_api_key'] = st.sidebar.text_input(
                "Enter Your GROQ API Key", 
                type="password", 
                help="Get your free API key from https://console.groq.com/keys"
            )
            st.sidebar.divider()
            # Navigation based on user role
            role = st.session_state.get('role')
            if role == 'Admin':
                page = st.sidebar.radio("Navigation", ["Admin Dashboard", "Leader Dashboard", "Student Dashboard", "My Profile", "Peer Learning", "Evaluate Peer Project"], key='admin_nav')
            elif role == 'Lead':
                page = st.sidebar.radio("Navigation", ["Leader Dashboard", "Student Dashboard", "My Profile", "Peer Learning", "Evaluate Peer Project"], key='lead_nav')
            else: # Student
                page = st.sidebar.radio("Navigation", ["Student Dashboard", "My Profile", "Peer Learning", "Evaluate Peer Project"], key='student_nav')

            st.sidebar.divider()
            if st.sidebar.button("Logout"):
                logger.info(f"User '{st.session_state.get('username', 'unknown')}' logged out.")
                st.session_state.clear()
                st.rerun()

        # Page rendering
        if page == "Admin Dashboard":
            show_admin_dashboard()
        elif page == "Leader Dashboard":
            show_leader_dashboard()
        elif page == "Student Dashboard":
            show_student_dashboard()
        elif page == "Peer Learning":
            show_peer_learning_page()
        elif page == "Evaluate Peer Project":
            show_evaluator_ui()
        elif page == "My Profile":
            show_student_profile()
        else: # Default page
            if role in ['Student', 'Lead']:
                show_student_dashboard()
            elif role == 'Admin':
                show_admin_dashboard()
            else:
                show_login_page()

if __name__ == "__main__":
    main()
