import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import hashlib
import os
import logging

# --- LOGGING SETUP ---
def setup_logger():
    """Sets up a logger to write to app_log.txt."""
    logger = logging.getLogger('pragyanai_app')
    logger.setLevel(logging.INFO)
    
    logger.propagate = False
    
    if not logger.handlers:
        handler = logging.FileHandler('app_log.txt', mode='w')
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

logger = setup_logger()

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
    """Establishes a connection to the Google Sheets API."""
    creds = None
    try:
        creds_json = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
        logger.info("Connecting to Google Sheets using Streamlit Secrets.")
    except Exception:
        local_creds_path = "gcp_creds.json"
        if os.path.exists(local_creds_path):
            creds = Credentials.from_service_account_file(local_creds_path, scopes=SCOPES)
            logger.info("Connecting to Google Sheets using local 'gcp_creds.json' file.")
        else:
            st.error("Google Sheets credentials not found. Configure Streamlit secrets or add a 'gcp_creds.json' file.")
            logger.error("GSheets credentials not found in secrets or local file.")
            return None
    
    try:
        client = gspread.authorize(creds)
        logger.info("Successfully authorized with Google Sheets.")
        return client
    except Exception as e:
        st.error(f"Failed to authorize with Google Sheets. Error: {e}")
        logger.error(f"Failed to authorize with Google Sheets: {e}")
        return None

def get_worksheet_by_key(client, key, worksheet_name):
    """Safely opens a worksheet by spreadsheet key and worksheet name."""
    try:
        spreadsheet = client.open_by_key(key)
        worksheet = spreadsheet.worksheet(worksheet_name)
        logger.info(f"Successfully opened worksheet '{worksheet_name}' from key '{key}'.")
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet with key '{key}' not found.")
        logger.error(f"Spreadsheet with key '{key}' not found.")
        return None
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Worksheet '{worksheet_name}' not found in the spreadsheet.")
        logger.error(f"Worksheet '{worksheet_name}' not found in spreadsheet key '{key}'.")
        return None
    except Exception as e:
        st.error(f"An error occurred accessing sheet: {e}")
        logger.error(f"Error accessing worksheet '{worksheet_name}': {e}")
        return None

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_password(hashed_password, user_password):
    return hashed_password == hashlib.sha256(str.encode(user_password)).hexdigest()

def load_css():
    """Injects custom CSS for a beautiful UI."""
    st.markdown("""
    <style>
        body { font-family: 'Segoe UI', sans-serif; }
        .main .block-container { padding: 2rem 5rem; }
        .st-emotion-cache-16txtl3 { background: #F0F2F6; }
        .card { background: #FFFFFF; border-radius: 10px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 8px 0 rgba(0,0,0,0.1); }
        .card:hover { box-shadow: 0 8px 16px 0 rgba(0,0,0,0.2); }
        .stButton>button { border-radius: 8px; border: 1px solid transparent; padding: 0.8em 1.5em; font-size: 1em; font-weight: 500; background-color: #1a73e8; color: white; cursor: pointer; }
        .stButton>button:hover { background-color: #155cb0; }
        h1 { color: #1a73e8; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=600)
def load_all_projects(_client):
    """Loads all projects from all event sheets."""
    events_sheet = get_worksheet_by_key(_client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if not events_sheet: return pd.DataFrame()
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
    logger.info(f"Debug (Load All Projects): Columns read from 'Project_Demos_List': {events_df.columns.tolist()}")
    
    all_projects = []
    for index, event in events_df.iterrows():
        sheet_url = event.get('Project_Demo_Sheet_Link')
        if sheet_url and event.get('Approved_Status', 'No').strip().lower() == 'yes':
            try:
                workbook = _client.open_by_url(sheet_url)
                submissions = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
                if not submissions.empty:
                    submissions['EventName'] = event['ProjectDemo_Event_Name']
                    all_projects.append(submissions)
            except Exception as e:
                logger.error(f"Failed to load projects from event '{event['ProjectDemo_Event_Name']}': {e}")
                continue 
    if not all_projects:
        return pd.DataFrame()
    return pd.concat(all_projects, ignore_index=True)
