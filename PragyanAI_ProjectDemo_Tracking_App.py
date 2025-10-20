import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import hashlib
import json
import uuid
import datetime
import base64
import os
import logging

# --- LOGGING SETUP ---
def setup_logger():
    """Sets up a logger to write to app_log.txt."""
    logger = logging.getLogger('pragyanai_app')
    logger.setLevel(logging.INFO)
    
    # Prevent logs from propagating to the root logger
    logger.propagate = False
    
    # Avoid adding handlers if they already exist
    if not logger.handlers:
        # Create a file handler to write to a file, mode 'w' overwrites the file on each run
        handler = logging.FileHandler('app_log.txt', mode='w')
        handler.setLevel(logging.INFO)
        
        # Create a logging format
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        # Add the handler to the logger
        logger.addHandler(handler)
        
    return logger

logger = setup_logger()
logger.info("Application starting up.")


# --- LLM & RAG Imports ---
# NOTE: You need to install the following packages:
# pip install groq langchain langchain-groq langchain_community faiss-cpu sentence-transformers unstructured langchain-text-splitters
try:
    from groq import Groq
    from langchain_groq import ChatGroq
    from langchain_community.document_loaders import WebBaseLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.output_parsers import StrOutputParser
    logger.info("Successfully imported LLM & RAG libraries.")
except ImportError as e:
    st.error("LLM dependencies are not installed. Please run: pip install -r requirements.txt")
    logger.error(f"Failed to import LLM libraries: {e}")


# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="PragyanAI ProjectDemo Tracking Platform",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- UI ENHANCEMENTS & STYLING ---
def load_css():
    """Injects custom CSS for a beautiful UI."""
    st.markdown("""
    <style>
        /* General Body and Font */
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }

        /* Main App container */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            padding-left: 5rem;
            padding-right: 5rem;
        }

        /* Sidebar Styling */
        .st-emotion-cache-16txtl3 {
            background: #F0F2F6;
        }

        /* Card-like containers */
        .card {
            background: #FFFFFF;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 4px 8px 0 rgba(0,0,0,0.1);
            transition: 0.3s;
        }
        .card:hover {
            box-shadow: 0 8px 16px 0 rgba(0,0,0,0.2);
        }
        
        /* Button Styling */
        .stButton>button {
            border-radius: 8px;
            border: 1px solid transparent;
            padding: 0.8em 1.5em;
            font-size: 1em;
            font-weight: 500;
            font-family: inherit;
            background-color: #1a73e8;
            color: white;
            cursor: pointer;
            transition: border-color 0.25s, background-color 0.25s;
        }
        .stButton>button:hover {
            background-color: #155cb0;
        }
        .stButton>button:focus, .stButton>button:focus-visible {
            outline: 4px auto -webkit-focus-ring-color;
        }
        
        /* Page Title */
        h1 {
            color: #1a73e8;
            font-weight: bold;
        }

    </style>
    """, unsafe_allow_html=True)

# Function to get image as base64
def get_image_as_base64(path):
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode()

# --- GOOGLE SHEETS & DATABASE SETUP ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file"
]

# --- Centralized Sheet Keys ---
USERS_ADMIN_SPREADSHEET_KEY = "127cStafn9skL4LAcLGYe6bgOd43o3rOU5AuqaxcB8R4"
EVENTS_SPREADSHEET_KEY = "1RBF58bTPuWgCH-WpgTKlqxUz3yK84G7MN8xQa7BowCM"
EVENT_TEMPLATE_SPREADSHEET_KEY = "1ha-zXkVS-YtTgJmYYqVUXPeZ0TXO-6sblkRkepMXW5U"


@st.cache_resource
def connect_to_google_sheets():
    """
    Establishes a connection to the Google Sheets API.
    It first tries to use Streamlit's secrets management (for deployment)
    and falls back to a local JSON file (for local development).
    """
    creds = None
    try:
        # Try connecting using Streamlit secrets (for deployment)
        creds_json = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
        logger.info("Connecting to Google Sheets using Streamlit Secrets.")
    except Exception:
        # Fallback to a local file if secrets are not found (for local development)
        local_creds_path = "gcp_creds.json"
        if os.path.exists(local_creds_path):
            creds = Credentials.from_service_account_file(local_creds_path, scopes=SCOPES)
            logger.info("Connecting to Google Sheets using local 'gcp_creds.json' file.")
        else:
            st.error("Google Sheets credentials not found. Please configure your Streamlit secrets or add a 'gcp_creds.json' file.")
            logger.error("Google Sheets credentials not found in Streamlit secrets or local 'gcp_creds.json'.")
            return None
    
    try:
        client = gspread.authorize(creds)
        logger.info("Successfully authorized with Google Sheets.")
        return client
    except Exception as e:
        st.error(f"Failed to authorize with Google Sheets. Error: {e}")
        logger.error(f"Failed to authorize with Google Sheets: {e}")
        return None

# --- HELPER FUNCTIONS ---
def get_worksheet_by_key(client, key, worksheet_name):
    """Safely opens a worksheet by spreadsheet key and worksheet name."""
    try:
        spreadsheet = client.open_by_key(key)
        worksheet = spreadsheet.worksheet(worksheet_name)
        logger.info(f"Successfully opened worksheet '{worksheet_name}' from spreadsheet key '{key}'.")
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet with key '{key}' not found. Please check the key and sharing settings.")
        logger.error(f"Spreadsheet with key '{key}' not found.")
        return None
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Worksheet '{worksheet_name}' not found in the spreadsheet.")
        logger.error(f"Worksheet '{worksheet_name}' not found in spreadsheet key '{key}'.")
        return None
    except Exception as e:
        st.error(f"An error occurred while accessing the sheet: {e}")
        logger.error(f"An error occurred while accessing worksheet '{worksheet_name}': {e}")
        return None


def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_password(hashed_password, user_password):
    return hashed_password == hashlib.sha256(str.encode(user_password)).hexdigest()

# --- USER MANAGEMENT ---
def create_user(details):
    client = connect_to_google_sheets()
    if not client: return False, "Database connection failed."
    users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
    if not users_sheet: return False, "Users sheet not accessible."

    users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
    logger.info(f"Debug (Create User): Columns read from 'User' sheet: {users_df.columns.tolist()}")
    if not users_df.empty and (details['UserName'] in users_df['UserName'].values or str(details['Phone(login)']) in users_df['Phone(login)'].astype(str).values):
        logger.warning(f"Attempt to create existing user: {details['UserName']} or phone: {details['Phone(login)']}")
        return False, "Username or Login Phone already exists."

    new_user_data = [
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        details['FullName'], details['CollegeName'], details['Branch'],
        details['RollNO(UniversityRegNo)'], details['YearofPassing_Passed'],
        str(details['Phone(login)']), str(details['Phone(Whatsapp)']), details['UserName'],
        hash_password(details['Password']), 'NotApproved', 'Student'
    ]
    users_sheet.append_row(new_user_data)
    logger.info(f"New user created: {details['UserName']}. Pending approval.")
    return True, "Account created! Please wait for admin approval."

def authenticate_user(login_identifier, password):
    """
    Authenticates a user against the 'User' sheet.
    Returns:
    - pd.Series object: On successful authentication.
    - "not_found": If the user does not exist.
    - "invalid_password": If the password is incorrect.
    - "pending": If the password is correct but the account is not approved.
    - None: On connection or other critical errors.
    """
    client = connect_to_google_sheets()
    if not client: return None
    users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
    if not users_sheet: return None
    
    users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
    logger.info(f"Debug (Authenticate User): Columns read from 'User' sheet: {users_df.columns.tolist()}")
    if users_df.empty: 
        logger.warning("Authentication attempt on empty 'User' sheet.")
        return "not_found"

    required_cols = ['UserName', 'Phone(login)', 'Password', 'Status(Approved/NotApproved)']
    if not all(col in users_df.columns for col in required_cols):
        st.error("The 'User' sheet is missing required columns. Please check headers.")
        logger.error(f"Missing required columns in 'User' sheet. Required: {required_cols}")
        return None

    user_record_df = users_df[(users_df['UserName'] == login_identifier) | (users_df['Phone(login)'].astype(str) == str(login_identifier))]
    
    if user_record_df.empty:
        logger.warning(f"Login attempt failed: User '{login_identifier}' not found.")
        return "not_found"
    
    user_data = user_record_df.iloc[0]
    
    if check_password(user_data['Password'], password):
        if str(user_data['Status(Approved/NotApproved)']).strip().lower() == 'approved':
            logger.info(f"Successful login for user: '{login_identifier}'.")
            return user_data  # Success
        else:
            logger.warning(f"Login attempt for '{login_identifier}' failed: Account not approved.")
            st.warning("Your account is not approved or is pending approval.")
            return "pending"
    else:
        logger.warning(f"Login attempt for '{login_identifier}' failed: Invalid password.")
        return "invalid_password"

def authenticate_admin(username, password):
    client = connect_to_google_sheets()
    if not client: return None
    admin_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "Admin")
    if not admin_sheet: return None
    
    admins_df = pd.DataFrame(admin_sheet.get_all_records(head=1))
    logger.info(f"Debug (Authenticate Admin): Columns read from 'Admin' sheet: {admins_df.columns.tolist()}")
    if admins_df.empty: 
        logger.error("Admin authentication attempt on empty 'Admin' sheet.")
        return None

    if 'UserName' not in admins_df.columns or 'Password' not in admins_df.columns:
        st.error("The 'Admin' sheet is missing required columns ('UserName', 'Password').")
        logger.error("Missing 'UserName' or 'Password' columns in 'Admin' sheet.")
        return None

    admin_record = admins_df[admins_df['UserName'] == username]
    if not admin_record.empty:
        admin_data = admin_record.iloc[0]
        if admin_data['Password'] == password:
            logger.info(f"Successful admin login for: '{username}'.")
            return admin_data
    logger.warning(f"Failed admin login attempt for user: '{username}'.")
    return None

# --- UI PAGES ---
def show_login_page():
    try:
        st.image("PragyanAI_Transperent.png", width=150)
    except Exception as e:
        st.warning("Logo image 'PragyanAI_Transperent.png' not found. Please add it to the root directory.")
        logger.warning(f"Could not load logo image: {e}")
        
    st.title("🏆 PragyanAI Project Demo Tracking Platform")
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        user_tab, signup_tab, admin_tab = st.tabs(["**Student/Lead Sign In**", "**Sign Up**", "**Admin Sign In**"])

        with user_tab:
            with st.form("login_form"):
                st.subheader("Login to your Account")
                login_identifier = st.text_input("Username or Phone Number", key="login_id")
                login_password = st.text_input("Password", type="password", key="login_pass")
                st.markdown("<br>", unsafe_allow_html=True)
                login_button = st.form_submit_button("Login", use_container_width=True)

                if login_button:
                    user_data = authenticate_user(login_identifier, login_password)

                    if isinstance(user_data, pd.Series):
                        # Successful login
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = user_data['UserName']
                        st.session_state['role'] = user_data['Role(Student/Lead)']
                        st.session_state['is_admin'] = False
                        st.session_state['user_details'] = user_data.to_dict()
                        st.rerun()
                    elif user_data == "not_found":
                        st.error("User does not exist. Please check your username/phone or sign up.")
                    elif user_data == "invalid_password":
                        st.error("Invalid credentials. Please check your password.")
                    # The 'pending' case is handled by a warning inside authenticate_user.
                    # The 'None' case indicates a sheet connection error, already handled.
        
        with signup_tab:
            with st.form("signup_form"):
                st.subheader("Create a New Account")
                full_name = st.text_input("Full Name")
                college = st.text_input("College Name")
                branch = st.text_input("Branch")
                roll_no = st.text_input("University Reg. No.")
                pass_year = st.text_input("Year of Passing")
                phone_login = st.text_input("Phone (for login)")
                phone_whatsapp = st.text_input("Phone (for WhatsApp)")
                username = st.text_input("Choose a Username")
                password = st.text_input("Choose a Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                st.markdown("<br>", unsafe_allow_html=True)
                signup_button = st.form_submit_button("Create Account", use_container_width=True)

                if signup_button:
                    if not all([full_name, college, branch, roll_no, pass_year, phone_login, username, password]):
                        st.error("Please fill all the fields.")
                    elif password != confirm_password:
                        st.error("Passwords do not match.")
                    else:
                        details = {
                            "FullName": full_name, "CollegeName": college, "Branch": branch,
                            "RollNO(UniversityRegNo)": roll_no, "YearofPassing_Passed": pass_year,
                            "Phone(login)": phone_login, "Phone(Whatsapp)": phone_whatsapp,
                            "UserName": username, "Password": password
                        }
                        success, message = create_user(details)
                        if success:
                            st.success(message)
                        else:
                            st.error(message)

        with admin_tab:
            with st.form("admin_login_form"):
                st.subheader("Admin Login")
                admin_user = st.text_input("Admin Username", key="admin_user")
                admin_pass = st.text_input("Admin Password", type="password", key="admin_pass")
                st.markdown("<br>", unsafe_allow_html=True)
                admin_login_button = st.form_submit_button("Admin Login", use_container_width=True)
                if admin_login_button:
                    admin_data = authenticate_admin(admin_user, admin_pass)
                    if admin_data is not None:
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = admin_data['UserName']
                        st.session_state['role'] = 'Admin'
                        st.session_state['is_admin'] = True
                        st.session_state['user_details'] = admin_data.to_dict()
                        st.rerun()
                    else:
                        st.error("Invalid Admin credentials.")

        st.markdown('</div>', unsafe_allow_html=True)

def show_admin_dashboard():
    st.title(f"👑 PragyanAI - Admin Dashboard")
    
    client = connect_to_google_sheets()
    if not client: return

    tab1, tab2, tab3 = st.tabs(["👤 User Management", "🗓️ Event Management", "⚙️ System Logs"])

    with tab1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Approve New Users")
        users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
        if not users_sheet: return
        users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
        logger.info(f"Debug (Admin User Mgt): Columns read from 'User' sheet: {users_df.columns.tolist()}")
        
        status_col = 'Status(Approved/NotApproved)'
        role_col = 'Role(Student/Lead)'
        
        if status_col not in users_df.columns or role_col not in users_df.columns:
            st.error(f"Critical Error: Your 'User' sheet is missing required columns.")
            st.info(f"Please ensure the headers '{status_col}' and '{role_col}' exist exactly as written.")
            st.write("Columns found in your sheet:", users_df.columns.tolist())
            return
        
        pending_users = users_df[users_df[status_col] == 'NotApproved']
        if not pending_users.empty:
            users_to_approve = st.multiselect("Select users to approve", options=pending_users['UserName'].tolist())
            if st.button("Approve Selected Users"):
                for user in users_to_approve:
                    cell = users_sheet.find(user)
                    users_sheet.update_cell(cell.row, 11, 'Approved')
                logger.info(f"Admin '{st.session_state['username']}' approved users: {users_to_approve}")
                st.success("Selected users approved.")
                st.rerun()
        else:
            st.info("No users are pending approval.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Manage Leaders")
        approved_users = users_df[users_df[status_col] == 'Approved']
        students = approved_users[approved_users[role_col] == 'Student']
        if not students.empty:
            user_to_make_leader = st.selectbox("Select user to promote to Leader", options=students['UserName'].tolist())
            if st.button("Promote to Leader"):
                cell = users_sheet.find(user_to_make_leader)
                users_sheet.update_cell(cell.row, 12, 'Lead')
                logger.info(f"Admin '{st.session_state['username']}' promoted '{user_to_make_leader}' to Leader.")
                st.success(f"{user_to_make_leader} is now a Leader.")
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Revoke User Access")
        if not approved_users.empty:
            user_to_revoke = st.selectbox("Select user to revoke access", options=approved_users['UserName'].tolist())
            if st.button("Revoke Access", type="primary"):
                cell = users_sheet.find(user_to_revoke)
                users_sheet.update_cell(cell.row, 11, 'Revoked')
                logger.warning(f"Admin '{st.session_state['username']}' revoked access for '{user_to_revoke}'.")
                st.warning(f"Access for {user_to_revoke} has been revoked.")
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Approve New Project Demo Events")
        events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
        if not events_sheet: return
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        logger.info(f"Debug (Admin Event Mgt): Columns read from 'Project_Demos_List' sheet: {events_df.columns.tolist()}")
        
        if 'Approved_Status' not in events_df.columns:
            st.error("Critical Error: 'Approved_Status' column not found in 'Project_Demos_List' sheet.")
            return

        pending_events = events_df[events_df['Approved_Status'] == 'No']
        if not pending_events.empty:
            event_to_approve = st.selectbox("Select event to approve", options=pending_events['ProjectDemo_Event_Name'].tolist())
            if st.button("Approve Event"):
                cell = events_sheet.find(event_to_approve)
                events_sheet.update_cell(cell.row, 6, 'Yes')
                logger.info(f"Admin '{st.session_state['username']}' approved event '{event_to_approve}'.")
                st.success(f"Event '{event_to_approve}' approved.")
                st.rerun()
        else:
            st.info("No events pending approval.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Modify Existing Event")
        if 'ProjectDemo_Event_Name' not in events_df.columns:
            st.error("Critical Error: 'ProjectDemo_Event_Name' column not found in 'Project_Demos_List' sheet.")
            return
            
        all_events = events_df['ProjectDemo_Event_Name'].tolist()
        if all_events:
            event_to_modify = st.selectbox("Select event to modify", options=all_events, key="modify_event_select")
            event_details = events_df[events_df['ProjectDemo_Event_Name'] == event_to_modify].iloc[0]

            with st.form("admin_modify_event"):
                whatsapp_link = st.text_input("WhatsApp Link", value=event_details.get('WhatsappLink', ''))
                conducted_status = st.selectbox("Conducted Status", options=["No", "Yes"], index=["No", "Yes"].index(event_details.get('Conducted_State', 'No')))
                
                submitted = st.form_submit_button("Update Event Details")
                if submitted:
                    cell = events_sheet.find(event_to_modify)
                    events_sheet.update_cell(cell.row, 8, whatsapp_link)
                    events_sheet.update_cell(cell.row, 7, conducted_status)
                    logger.info(f"Admin '{st.session_state['username']}' updated event '{event_to_modify}'.")
                    st.success("Event updated.")
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
    with tab3:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Application Log")
        log_file = 'app_log.txt'
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                log_content = f.read()
            st.code(log_content, language='log')
            st.download_button(
                label="Download Log File",
                data=log_content,
                file_name="pragyanai_app_log.txt",
                mime="text/plain"
            )
        else:
            st.info("Log file not found. It will be created when the application performs actions.")
        st.markdown('</div>', unsafe_allow_html=True)

def show_leader_dashboard():
    st.title(f"🧑‍🏫 PragyanAI - Lead Dashboard")

    client = connect_to_google_sheets()
    if not client: return

    tab1, tab2 = st.tabs(["🚀 Create Project Demo", "📋 Manage My Demos"])

    with tab1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.header("Create New Project Demo Event")
        with st.form("leader_create_event"):
            st.write("Provide details for the new demo event. It will require Admin approval before it's visible to students.")
            event_name = st.text_input("Project Event Name")
            demo_date = st.date_input("Demo Date")
            domain = st.text_input("Domain (e.g., AI/ML, Web Development, IoT)")
            description = st.text_area("Brief Description")
            external_url = st.text_input("URL (Optional, for external resources)")
            whatsapp = st.text_input("WhatsApp Group Link")

            submitted = st.form_submit_button("Submit for Approval")
            if submitted:
                if not all([event_name, demo_date, domain, description]):
                    st.error("Please fill all required fields.")
                else:
                    with st.spinner("Creating event and new sheet..."):
                        try:
                            new_sheet_copy = client.copy(EVENT_TEMPLATE_SPREADSHEET_KEY, title=f"Event - {event_name}", copy_permissions=True)
                            events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
                            
                            new_event_data = [
                                str(demo_date), event_name, domain, description, external_url,
                                'No', 'No', whatsapp, new_sheet_copy.url
                            ]
                            events_sheet.append_row(new_event_data)
                            logger.info(f"Leader '{st.session_state['username']}' created new event '{event_name}' for approval.")
                            st.success("Event submitted for admin approval!")
                            st.info(f"A new Google Sheet for this event has been created: {new_sheet_copy.url}")
                        except Exception as e:
                            st.error(f"An error occurred: {e}. Ensure the template sheet ID is correct and shared with the service account.")
                            logger.error(f"Failed to create new event sheet for '{event_name}': {e}")
        st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.header("Your Created Events")
        events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
        if not events_sheet: return
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        logger.info(f"Debug (Leader Mgt): Columns read from 'Project_Demos_List' sheet: {events_df.columns.tolist()}")
        my_events = events_df
        st.dataframe(my_events, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

def show_student_dashboard():
    st.title(f"🎓 PragyanAI - Student Dashboard")
    st.write(f"Welcome, {st.session_state['user_details']['FullName']}!")
    
    client = connect_to_google_sheets()
    if not client: return
    
    events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if not events_sheet: 
        return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=0))
    logger.info(f"Debug (Student Dashboard): Columns read from 'Project_Demos_List' sheet: {events_df.columns.tolist()}")
    #st.write(events_df.head(), len(events_df))
    #st.write(events_df.columns)
    approved_col = 'Approved_Status'
    conducted_col = 'Conducted_State'
    
    if approved_col not in events_df.columns or conducted_col not in events_df.columns:
        st.error(f"Critical Error: Your 'Project_Demos_List' sheet is missing required columns.")
        st.info(f"Please ensure the headers '{approved_col}' and '{conducted_col}' exist exactly as written.")
        st.write("Columns found in your sheet:", events_df.columns.tolist())
        return
    
    active_events = events_df[(events_df[approved_col] == 'Yes') & (events_df[conducted_col] == 'No')]
    
    if active_events.empty:
        st.info("There are no active project demo events to enroll in right now.")
        return

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Enroll For a Project Demo")
    event_choice = st.selectbox("Select an active event", options=active_events['ProjectDemo_Event_Name'].tolist())

    if event_choice:
        event_details = active_events[active_events['ProjectDemo_Event_Name'] == event_choice].iloc[0]
        sheet_url = event_details.get('Project_Demo_Sheet_Link')
        if not sheet_url:
            st.error("Event sheet link not found. Please contact an admin.")
            return

        try:
            event_workbook = client.open_by_url(sheet_url)
            submission_sheet = event_workbook.worksheet("Project_List") 
            submissions_df = pd.DataFrame(submission_sheet.get_all_records(head=1))
            logger.info(f"Debug (Student Enrollment): Columns read from '{event_choice}' -> 'Project_List' sheet: {submissions_df.columns.tolist()}")
        except Exception as e:
            st.error(f"Could not open the event sheet. Please check the URL, permissions, and ensure a 'Project_List' worksheet exists. Error: {e}")
            logger.error(f"Failed to open event sheet for '{event_choice}': {e}")
            return
            
        my_submission = pd.DataFrame()
        if 'StudentFullName' in submissions_df.columns:
            my_submission = submissions_df[submissions_df['StudentFullName'] == st.session_state['user_details']['FullName']]
        
        with st.form("enrollment_form"):
            st.header(f"Your Submission for: '{event_choice}'")
            project_title = st.text_input("Project Title", value=my_submission['ProjectTitle'].iloc[0] if not my_submission.empty else "")
            description = st.text_area("Description", value=my_submission['Description'].iloc[0] if not my_submission.empty else "")
            keywords = st.text_input("KeyWords (comma-separated)", value=my_submission['KeyWords'].iloc[0] if not my_submission.empty else "")
            tools_list = st.text_input("ToolsList (comma-separated)", value=my_submission['ToolsList'].iloc[0] if not my_submission.empty else "")
            
            st.subheader("Project Links")
            report_link = st.text_input("Report Link", value=my_submission['ReportLink'].iloc[0] if not my_submission.empty else "")
            ppt_link = st.text_input("Presentation Link", value=my_submission['PresentationLink'].iloc[0] if not my_submission.empty else "")
            github_link = st.text_input("GitHub Link", value=my_submission['GitHubLink'].iloc[0] if not my_submission.empty else "")
            youtube_link = st.text_input("YouTube Link", value=my_submission['YouTubeLink'].iloc[0] if not my_submission.empty else "")
            linkedin_link = st.text_input("Linkedin Project Post Link", value=my_submission['Linkedin_Project_Post_Link'].iloc[0] if not my_submission.empty else "")

            submitted = st.form_submit_button("Submit / Update Enrollment")
            if submitted:
                user_info = st.session_state['user_details']
                submission_data = [
                    user_info['FullName'], user_info['CollegeName'], user_info['Branch'],
                    project_title, description, keywords, tools_list,
                    report_link, ppt_link, github_link, youtube_link, linkedin_link,
                    'No', '', '', '', '', '', '', ''
                ]
                
                if not my_submission.empty:
                    cell = submission_sheet.find(user_info['FullName'])
                    submission_sheet.update(f'A{cell.row}:T{cell.row}', [submission_data])
                    logger.info(f"User '{user_info['FullName']}' updated their project '{project_title}' in event '{event_choice}'.")
                    st.success("Your project details have been updated!")
                else:
                    submission_sheet.append_row(submission_data)
                    logger.info(f"User '{user_info['FullName']}' enrolled with project '{project_title}' in event '{event_choice}'.")
                    st.success("You have successfully enrolled in the event!")
    st.markdown('</div>', unsafe_allow_html=True)

def show_peer_learning_page():
    st.title("🧑‍🎓 PragyanAI - Peer Learning Hub")
    st.write("Explore projects from past and present events.")
    
    client = connect_to_google_sheets()
    if not client: return
    
    @st.cache_data(ttl=600)
    def load_all_projects(_client):
        events_sheet = get_worksheet_by_key(_client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
        if not events_sheet: return pd.DataFrame()
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        logger.info(f"Debug (Peer Learning): Columns read from 'Project_Demos_List' sheet: {events_df.columns.tolist()}")
        
        all_projects = []
        for index, event in events_df.iterrows():
            sheet_url = event.get('Project_Demo_Sheet_Link')
            if sheet_url:
                try:
                    workbook = _client.open_by_url(sheet_url)
                    submissions = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
                    logger.info(f"Debug (Peer Learning): Columns from event '{event['ProjectDemo_Event_Name']}' -> 'Project_List': {submissions.columns.tolist()}")
                    if not submissions.empty:
                        submissions['EventName'] = event['ProjectDemo_Event_Name']
                        all_projects.append(submissions)
                except Exception as e:
                    logger.error(f"Failed to load projects from event '{event['ProjectDemo_Event_Name']}': {e}")
                    continue 
        if not all_projects:
            return pd.DataFrame()
        return pd.concat(all_projects, ignore_index=True)

    projects_df = load_all_projects(client)
    if projects_df.empty:
        st.warning("No projects found across any events.")
        return

    if 'ProjectTitle' not in projects_df.columns:
        st.error("Could not find 'ProjectTitle' column in the aggregated project data. Check your 'Project_List' sheets.")
        return

    project_choice = st.selectbox("Select a project to view", options=projects_df['ProjectTitle'].unique())
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if project_choice:
        project_details = projects_df[projects_df['ProjectTitle'] == project_choice].iloc[0]
        
        st.header(project_details.get('ProjectTitle', 'N/A'))
        st.caption(f"By {project_details.get('StudentFullName', 'N/A')} from {project_details.get('CollegeName', 'N/A')} | Event: {project_details.get('EventName', 'N/A')}")
        st.write(f"**Description:** {project_details.get('Description', 'No description available.')}")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if project_details.get('ReportLink'): st.link_button("📄 View Report", project_details['ReportLink'])
        with c2:
            if project_details.get('PresentationLink'): st.link_button("🖥️ View Presentation", project_details['PresentationLink'])
        with c3:
            if project_details.get('GitHubLink'): st.link_button("💻 View Code", project_details['GitHubLink'])
        with c4:
             if project_details.get('Linkedin_Project_Post_Link'): st.link_button("🔗 LinkedIn Post", project_details['Linkedin_Project_Post_Link'])

        if project_details.get('YouTubeLink'): 
            st.video(project_details['YouTubeLink'])
        
        st.markdown("---")
        st.subheader("🤖 RAG-Based Q&A")
        st.write("Ask questions about this project's report.")
        
        api_key = st.session_state.get("groq_api_key")
        if not api_key:
            st.warning("Please enter your GROQ API key in the sidebar to use this feature.")
            return

        report_url = project_details.get('ReportLink')
        if not report_url:
            st.info("This project does not have a report link for the Q&A bot.")
            return
            
        question = st.text_input("Your question about the report:")
        
        if question:
            with st.spinner("Analyzing document and generating answer..."):
                try:
                    logger.info(f"Starting RAG process for URL: {report_url} with question: '{question}'")
                    loader = WebBaseLoader(report_url)
                    docs = loader.load()
                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                    splits = text_splitter.split_documents(docs)
                    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                    vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)
                    llm = ChatGroq(temperature=0, groq_api_key=api_key, model_name="llama3-70b-8192")
                    
                    retriever = vectorstore.as_retriever()
                    
                    template = """Answer the question based only on the following context:
                    {context}
                    
                    Question: {question}
                    """
                    prompt = ChatPromptTemplate.from_template(template)

                    rag_chain = (
                        {"context": retriever, "question": RunnablePassthrough()}
                        | prompt
                        | llm
                        | StrOutputParser()
                    )
                    
                    response = rag_chain.invoke(question)
                    logger.info(f"RAG process completed successfully.")
                    st.success("Answer:")
                    st.write(response)
                except Exception as e:
                    st.error(f"Failed to process the document. Error: {e}")
                    logger.error(f"RAG process failed for URL {report_url}: {e}")
    st.markdown('</div>', unsafe_allow_html=True)


def show_evaluator_ui():
    st.title("📝 PragyanAI - Peer Project Evaluation")
    
    client = connect_to_google_sheets()
    if not client: return
    
    events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if not events_sheet: return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
    logger.info(f"Debug (Evaluator UI): Columns read from 'Project_Demos_List' sheet: {events_df.columns.tolist()}")
    
    active_events = events_df[(events_df['Approved_Status'] == 'Yes') & (events_df['Conducted_State'] == 'No')]
    
    if active_events.empty:
        st.info("No active events available for evaluation.")
        return

    st.markdown('<div class="card">', unsafe_allow_html=True)
    event_choice = st.selectbox("Select Event to Evaluate", options=active_events['ProjectDemo_Event_Name'].tolist())
    if event_choice:
        event_details = active_events[active_events['ProjectDemo_Event_Name'] == event_choice].iloc[0]
        sheet_url = event_details.get('Project_Demo_Sheet_Link')
        if not sheet_url: 
            st.error("Event sheet URL is missing.")
            return
        
        try:
            workbook = client.open_by_url(sheet_url)
            submissions_df = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
            logger.info(f"Debug (Evaluator UI): Columns from event '{event_choice}' -> 'Project_List': {submissions_df.columns.tolist()}")
        except Exception as e:
            st.error(f"Could not open the event sheet. Please check the URL, permissions, and ensure a 'Project_List' worksheet exists. Error: {e}")
            logger.error(f"Failed to open sheet for evaluation in event '{event_choice}': {e}")
            return
        
        if 'StudentFullName' not in submissions_df.columns:
            st.error("Critical Error: 'StudentFullName' column not in the event's 'Project_List' sheet.")
            return

        candidate = st.selectbox("Select Candidate to Evaluate", options=submissions_df['StudentFullName'].tolist())
        
        if candidate:
            with st.form("evaluation_form"):
                st.header(f"Evaluating: {candidate}")
                score1 = st.slider("Presentation - Project Explanation", 0, 100, 50)
                score2 = st.slider("Technical Knowledge", 0, 100, 50)
                score3 = st.slider("Code Explanation and Project Demo", 0, 100, 50)
                score4 = st.slider("Q & A", 0, 100, 50)
                
                submitted = st.form_submit_button("Submit Evaluation")
                if submitted:
                    avg_score = (score1 + score2 + score3 + score4) / 4
                    eval_sheet = workbook.worksheet("ProjectEvaluation")
                    eval_data = [
                        candidate,
                        submissions_df[submissions_df['StudentFullName'] == candidate]['ProjectTitle'].iloc[0],
                        avg_score,
                        st.session_state['username']
                    ]
                    eval_sheet.append_row(eval_data)
                    logger.info(f"User '{st.session_state['username']}' submitted evaluation for '{candidate}' with score {avg_score}.")
                    st.success(f"Evaluation for {candidate} submitted with an average score of {avg_score:.2f}!")
    st.markdown('</div>', unsafe_allow_html=True)

# --- MAIN APP LOGIC ---
def main():
    load_css()
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        show_login_page()
    else:
        with st.sidebar:
            logo_base64 = "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAARKSURBVHhe7ZxLyBxFFMd/991Md6S7S1AUVFAU9I+gvygIIj6ABfGhCCKCj4LgQxAUxIcYCIqgCAp6CAqiDxAUxMcgCPLjbbJ7d2fu7s62z/Vv9kSS7s7Mzs7s7s7+fZM8ycx8+/nNN9/MvC0A/I8bAP+jBsA/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E_qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0A/54GMDMzc/rQ0JA9Pz/XHzx4oIeHh1pqaqrevXvXvXPnTvfs2bPu6OionpycqPT19dUDg4P6/v5+HTs6OkqXLl3qkydP6qWlpdqJEyc0c+bMKScmJuo1NTXqgUFBfZ8+fdq9e/eu3bdv33rBwcF6QkJCHjY1tXv16lVbWlqq3759qw8ODuo7duxQ7+zs1JcvX9ZLS0u1T58+1ejoqL5165Z+7949/fTp05qZmZnuoUOHNG/cuKE7d+5c5/3793V+fn565MiRRllZWb0oLy/XI0eO6JGRkTp//vwxZWdn/yUAvp0GMDMzc4Kenh7d0NBQt2rVqnrb2tr0wcFB/dGjRzV3d3d9w4YN+sKFC1rX1ta6Xbt2rY6NjdW7d+/WnZ2d9eXLl/XWrVt1dna2Pnv2rN6/f193dnbaM2fOaLZt26bZtWtXL4qLi/XIyEh99+5d/eHDh/rFixd1c3OzPnv2rB4dHdUTExP1pqam+qFDh3Tfvn3r/Pr1a/3Tp0/1//z5Q3Nycuri4uL00NBQfXx8XPenpKQ87OxsvXPnztUXL17Ut2/f1mtqalQ7Ozt1dHRU/9u3b/rJkyf12bNn9R8/ftTl5eXqmTNndPv27dO8ePFinZ6e/gMAfEcNYGRkpN6/f18fHh7Wl5aW6ksXL2pVVVX6xYsX9aenp/rSpUv69u1bvejoqD558qRevnxZ7+zs1MvLy/XVq1f15s2b+vbNm7qzs1P/4sUL/eLFC33hwoX6jh079IEDB/To6Kh+9epVfXJyUmfOnDldV1dXR0dH6/nz53Vzc7Pevn1bj46O6t7e3vq2trb6vXv39Hfv3tWDBw9qZmZmuu/evSvMzMzUm5ub9ebNm/Xhw4d63759evPmTX3//n3t6enplzNnzqirq6ujI0eO6PXr13VrayvdsGEDfXh4WF9cXKw3b96sx8fH/g4A/KcNQF5eXl5aWqqtra11cXFx6tixY/revXv63r172tvb2x89elRv3bpVr6+vV+3t7fXmzZu6o6NDR0dHa15eXh0fH69Hjx7VBwcHtbe3t37q1Ck9fvx4/fHjR/348WO9e/eunp6e1t26deunTp3Sffv2rXNra2v9lClTdPfu3XWhUql60dHR+vr1a/3582etqalR7+npej8/P/38+XN9eHiovrOzU/Py8mpvb2999+5dfePGDb1r1y6dPHnyx8vL69ixY/rSpUsaRUVFXqioqNDDwsJ6eHh49lQNAH8PAWBgYKDe2dmpe3p66snJST1+/Lju27dP/8WLF3rDhg06ffr06S5dupQzZ8_ovn371vnu3bv69evX2tWrV+vVq1f11KlT+sePH3VjY2MdHh6uf//+XT9+8FCvqalRx8fH66NHj+qjR4/qXl5eet68efqqVav0oUOHdLdu3brY1KlTdUJCgq6oqEivra3Vu3fv1g8PD/XW1tZ63759Ojk5uQ4LC/NpM/8f8Xj4E2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHw/7gB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0A/1MD4J/UAOjnAABKAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FN/AYzQ8T0eLo//AAAAAElFTkSuQmCC"

            st.markdown(f"""
                <div style="display: flex; justify-content: center; margin-bottom: 20px;">
                    <img src="data:image/png;base64,{logo_base64}" alt="PragyanAI Logo" style="width: 80px; height: 80px;">
                </div>
                """, unsafe_allow_html=True)
            st.sidebar.markdown("<h2 style='text-align: center; color: #1a73e8;'>PragyanAI Platform</h2>", unsafe_allow_html=True)

            st.sidebar.divider()
            
            st.sidebar.subheader("API Configuration")
            st.session_state['groq_api_key'] = st.sidebar.text_input(
                "Enter Your GROQ API Key", 
                type="password", 
                help="Get your free API key from https://console.groq.com/keys"
            )

            st.sidebar.divider()

            # Navigation
            if 'page' not in st.session_state:
                st.session_state.page = None

            if st.session_state.get('role') == 'Admin':
                st.session_state.page = st.sidebar.radio("Navigation", ["Admin Dashboard", "Leader Dashboard", "Student Dashboard", "Peer Learning", "Evaluate Peer Project"], key='admin_nav')
            elif st.session_state.get('role') == 'Lead':
                st.session_state.page = st.sidebar.radio("Navigation", ["Leader Dashboard", "Student Dashboard", "Peer Learning", "Evaluate Peer Project"], key='lead_nav')
            else: # Student
                st.session_state.page = st.sidebar.radio("Navigation", ["Student Dashboard", "Peer Learning", "Evaluate Peer Project"], key='student_nav')

            st.sidebar.divider()
            if st.sidebar.button("Logout"):
                st.session_state.clear()
                logger.info(f"User '{st.session_state.get('username', 'unknown')}' logged out.")
                st.rerun()

        # Page rendering
        page = st.session_state.get('page')

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
        else: # Default page
            if st.session_state.get('role') in ['Student', 'Lead']:
                show_student_dashboard()
            elif st.session_state.get('role') == 'Admin':
                show_admin_dashboard()
            else: # Fallback for any other case or initial load
                show_login_page()


if __name__ == "__main__":
    main()
