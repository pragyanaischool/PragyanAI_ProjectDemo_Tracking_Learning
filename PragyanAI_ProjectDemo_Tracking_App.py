import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import hashlib
import json
import uuid
import datetime
import base64
from groq import Groq
from langchain_groq import ChatGroq
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
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
    from langchain.chains import RetrievalQA
except ImportError:
    st.error("LLM dependencies are not installed. Please run: pip install -r requirements.txt")


# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="PragyanAI Project Platform",
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

@st.cache_resource
def connect_to_google_sheets():
    """Establishes a connection to the Google Sheets API."""
    try:
        creds_json = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets. Ensure your secrets are configured correctly. Error: {e}")
        return None

# --- Centralized Sheet Naming ---
USERS_SHEET_NAME = "Users" 
EVENTS_MASTER_SHEET_NAME = "Project_Demo_Events" 
EVENT_TEMPLATE_SHEET_ID = st.secrets.get("gcp_service_account", {}).get("event_template_sheet_id", "YOUR_TEMPLATE_SHEET_ID_HERE")


# --- HELPER FUNCTIONS ---
def get_sheet(client, sheet_name):
    """Safely opens a sheet by name."""
    try:
        return client.open(sheet_name).sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet '{sheet_name}' not found. Please create it and share it with the service account.")
        return None

def get_sheet_by_id(client, sheet_id):
    """Opens a sheet by its ID."""
    try:
        return client.open_by_key(sheet_id)
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
        return None

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_password(hashed_password, user_password):
    return hashed_password == hashlib.sha256(str.encode(user_password)).hexdigest()

# --- USER MANAGEMENT ---
def create_user(details):
    client = connect_to_google_sheets()
    if not client: return False, "Database connection failed."
    users_sheet = get_sheet(client, USERS_SHEET_NAME)
    if not users_sheet: return False, "Users sheet not accessible."

    users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
    if not users_df.empty and (details['UserName'] in users_df['UserName'].values or str(details['Phone(login)']) in users_df['Phone(login)'].astype(str).values):
        return False, "Username or Login Phone already exists."

    new_user_data = [
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        details['FullName'], details['CollegeName'], details['Branch'],
        details['RollNO(UniversityRegNo)'], details['YearofPassing_Passed'],
        str(details['Phone(login)']), str(details['Phone(Whatsapp)']), details['UserName'],
        hash_password(details['Password']), 'NotApproved', 'Student'
    ]
    users_sheet.append_row(new_user_data)
    return True, "Account created! Please wait for admin approval."

def authenticate_user(login_identifier, password):
    client = connect_to_google_sheets()
    if not client: return None
    users_sheet = get_sheet(client, USERS_SHEET_NAME)
    if not users_sheet: return None
    
    users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
    if users_df.empty: return None

    user_record_df = users_df[(users_df['UserName'] == login_identifier) | (users_df['Phone(login)'].astype(str) == str(login_identifier))]
    
    if not user_record_df.empty:
        user_data = user_record_df.iloc[0]
        if check_password(user_data['Password'], password):
            if user_data['Status(Approved/NotApproved)'] == 'Approved':
                return user_data
            else:
                st.warning("Your account is pending approval.")
                return "pending"
    return None

# --- UI PAGES ---
def show_login_page():
    st.title("🏆 Welcome to the PragyanAI Project Platform")
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        login_tab, signup_tab = st.tabs(["**Sign In**", "**Sign Up**"])

        with login_tab:
            with st.form("login_form"):
                st.subheader("Login to your Account")
                login_identifier = st.text_input("Username or Phone Number", key="login_id")
                login_password = st.text_input("Password", type="password", key="login_pass")
                st.markdown("<br>", unsafe_allow_html=True)
                login_button = st.form_submit_button("Login", use_container_width=True)

                if login_button:
                    user_data = authenticate_user(login_identifier, login_password)
                    if user_data is not None and user_data != "pending":
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = user_data['UserName']
                        st.session_state['role'] = user_data['Role(Student/Lead)']
                        st.session_state['user_details'] = user_data.to_dict()
                        st.rerun()
                    elif user_data is None:
                        st.error("Invalid credentials.")
        
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
                    if password != confirm_password:
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
        st.markdown('</div>', unsafe_allow_html=True)

def show_admin_dashboard():
    st.title(f"👑 Admin Dashboard")
    
    client = connect_to_google_sheets()
    if not client: return

    tab1, tab2 = st.tabs(["👤 User Management", "🗓️ Event Management"])

    with tab1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Approve New Users")
        users_sheet = get_sheet(client, USERS_SHEET_NAME)
        if not users_sheet: return
        users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
        
        pending_users = users_df[users_df['Status(Approved/NotApproved)'] == 'NotApproved']
        if not pending_users.empty:
            users_to_approve = st.multiselect("Select users to approve", options=pending_users['UserName'].tolist())
            if st.button("Approve Selected Users"):
                for user in users_to_approve:
                    cell = users_sheet.find(user)
                    users_sheet.update_cell(cell.row, 11, 'Approved') # Column K
                st.success("Selected users approved.")
                st.rerun()
        else:
            st.info("No users are pending approval.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Manage Leaders")
        approved_users = users_df[users_df['Status(Approved/NotApproved)'] == 'Approved']
        students = approved_users[approved_users['Role(Student/Lead)'] == 'Student']
        if not students.empty:
            user_to_make_leader = st.selectbox("Select user to promote to Leader", options=students['UserName'].tolist())
            if st.button("Promote to Leader"):
                cell = users_sheet.find(user_to_make_leader)
                users_sheet.update_cell(cell.row, 12, 'Lead') # Column L
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
                st.warning(f"Access for {user_to_revoke} has been revoked.")
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Approve New Project Demo Events")
        events_sheet = get_sheet(client, EVENTS_MASTER_SHEET_NAME)
        if not events_sheet: return
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        
        pending_events = events_df[events_df['Approved_Status'] == 'No']
        if not pending_events.empty:
            event_to_approve = st.selectbox("Select event to approve", options=pending_events['ProjectDemo_Event_Name'].tolist())
            if st.button("Approve Event"):
                cell = events_sheet.find(event_to_approve)
                events_sheet.update_cell(cell.row, 6, 'Yes') # Column F
                st.success(f"Event '{event_to_approve}' approved.")
                st.rerun()
        else:
            st.info("No events pending approval.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Modify Existing Event")
        all_events = events_df['ProjectDemo_Event_Name'].tolist()
        if all_events:
            event_to_modify = st.selectbox("Select event to modify", options=all_events, key="modify_event_select")
            event_details = events_df[events_df['ProjectDemo_Event_Name'] == event_to_modify].iloc[0]

            with st.form("admin_modify_event"):
                whatsapp_link = st.text_input("WhatsApp Link", value=event_details.get('WhatsappLink', ''))
                eval_form_link = st.text_input("Project Evaluation Google Form Link", value=event_details.get('Project_Evaluation_GoogleFormLink', ''))
                sheet_link = st.text_input("Project Demo Sheet Link", value=event_details.get('Project_Demo_Sheet_Link', ''))
                conducted_status = st.selectbox("Conducted Status", options=["No", "Yes"], index=["No", "Yes"].index(event_details.get('Conducted_State', 'No')))
                
                submitted = st.form_submit_button("Update Event Details")
                if submitted:
                    cell = events_sheet.find(event_to_modify)
                    events_sheet.update_cell(cell.row, 8, whatsapp_link) # Column H
                    events_sheet.update_cell(cell.row, 7, conducted_status) # Column G
                    events_sheet.update_cell(cell.row, 9, sheet_link)
                    st.success("Event updated.")
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

def show_leader_dashboard():
    st.title(f"🧑‍🏫 Lead Dashboard")

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
                with st.spinner("Creating event and new sheet..."):
                    try:
                        new_sheet = client.copy(EVENT_TEMPLATE_SHEET_ID, title=f"Event - {event_name}", copy_permissions=True)
                        events_sheet = get_sheet(client, EVENTS_MASTER_SHEET_NAME)
                        new_event_data = [
                            str(demo_date), event_name, domain, description, external_url,
                            'No', 'No', whatsapp, new_sheet.url
                        ]
                        events_sheet.append_row(new_event_data)
                        st.success("Event submitted for admin approval!")
                        st.info(f"A new Google Sheet for this event has been created: {new_sheet.url}")
                    except Exception as e:
                        st.error(f"An error occurred: {e}. Ensure the template sheet ID is correct in your secrets.")
        st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.header("Your Created Events")
        events_sheet = get_sheet(client, EVENTS_MASTER_SHEET_NAME)
        if not events_sheet: return
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        # A more robust check for leader's events might be needed if names are not unique
        my_events = events_df
        st.dataframe(my_events, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

def show_student_dashboard():
    st.title(f"🎓 Student Dashboard")
    st.write(f"Welcome, {st.session_state['user_details']['FullName']}!")
    
    client = connect_to_google_sheets()
    if not client: return
    
    events_sheet = get_sheet(client, EVENTS_MASTER_SHEET_NAME)
    if not events_sheet: return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
    
    active_events = events_df[(events_df['Approved_Status'] == 'Yes') & (events_df['Conducted_State'] == 'No')]
    
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
            submission_sheet = event_workbook.worksheet("CurrentState")
            submissions_df = pd.DataFrame(submission_sheet.get_all_records(head=1))
        except Exception as e:
            st.error(f"Could not open the event sheet. Please check the URL and permissions. Error: {e}")
            return
            
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
                    submission_sheet.update(f'A{cell.row}', [submission_data])
                    st.success("Your project details have been updated!")
                else:
                    submission_sheet.append_row(submission_data)
                    st.success("You have successfully enrolled in the event!")
    st.markdown('</div>', unsafe_allow_html=True)

def show_peer_learning_page():
    st.title("🧑‍🎓 Peer Learning Hub")
    st.write("Explore projects from past and present events.")
    
    client = connect_to_google_sheets()
    if not client: return
    
    @st.cache_data(ttl=600)
    def load_all_projects(_client):
        events_sheet = get_sheet(_client, EVENTS_MASTER_SHEET_NAME)
        if not events_sheet: return pd.DataFrame()
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        
        all_projects = []
        for index, event in events_df.iterrows():
            sheet_url = event.get('Project_Demo_Sheet_Link')
            if sheet_url:
                try:
                    workbook = _client.open_by_url(sheet_url)
                    submissions = pd.DataFrame(workbook.worksheet("CurrentState").get_all_records(head=1))
                    if not submissions.empty:
                        submissions['EventName'] = event['ProjectDemo_Event_Name']
                        all_projects.append(submissions)
                except Exception:
                    continue 
        if not all_projects:
            return pd.DataFrame()
        return pd.concat(all_projects, ignore_index=True)

    projects_df = load_all_projects(client)
    if projects_df.empty:
        st.warning("No projects found across any events.")
        return

    project_choice = st.selectbox("Select a project to view", options=projects_df['ProjectTitle'].unique())
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if project_choice:
        project_details = projects_df[projects_df['ProjectTitle'] == project_choice].iloc[0]
        
        st.header(project_details['ProjectTitle'])
        st.caption(f"By {project_details['StudentFullName']} from {project_details['CollegeName']} | Event: {project_details['EventName']}")
        st.write(f"**Description:** {project_details['Description']}")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if project_details['ReportLink']: st.link_button("📄 View Report", project_details['ReportLink'])
        with c2:
            if project_details['PresentationLink']: st.link_button("🖥️ View Presentation", project_details['PresentationLink'])
        with c3:
            if project_details['GitHubLink']: st.link_button("💻 View Code", project_details['GitHubLink'])
        with c4:
             if project_details['Linkedin_Project_Post_Link']: st.link_button("🔗 LinkedIn Post", project_details['Linkedin_Project_Post_Link'])

        if project_details['YouTubeLink']: 
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
                    loader = WebBaseLoader(report_url)
                    docs = loader.load()
                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                    splits = text_splitter.split_documents(docs)
                    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                    vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)
                    llm = ChatGroq(temperature=0, groq_api_key=api_key, model_name="llama3-70b-8192")
                    
                    retriever = vectorstore.as_retriever()
                    qa_chain = RetrievalQA.from_chain_type(
                        llm=llm,
                        chain_type="stuff",
                        retriever=retriever
                    )
                    
                    response = qa_chain.invoke(question)
                    st.success("Answer:")
                    st.write(response["result"])
                except Exception as e:
                    st.error(f"Failed to process the document. Error: {e}")
    st.markdown('</div>', unsafe_allow_html=True)


def show_evaluator_ui():
    st.title("📝 Peer Project Evaluation")
    
    client = connect_to_google_sheets()
    if not client: return
    
    events_sheet = get_sheet(client, EVENTS_MASTER_SHEET_NAME)
    if not events_sheet: return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
    
    active_events = events_df[(events_df['Approved_Status'] == 'Yes') & (events_df['Conducted_State'] == 'No')]
    
    if active_events.empty:
        st.info("No active events available for evaluation.")
        return

    st.markdown('<div class="card">', unsafe_allow_html=True)
    event_choice = st.selectbox("Select Event to Evaluate", options=active_events['ProjectDemo_Event_Name'].tolist())
    if event_choice:
        event_details = active_events[active_events['ProjectDemo_Event_Name'] == event_choice].iloc[0]
        sheet_url = event_details.get('Project_Demo_Sheet_Link')
        if not sheet_url: return
        
        try:
            workbook = client.open_by_url(sheet_url)
            submissions_df = pd.DataFrame(workbook.worksheet("CurrentState").get_all_records(head=1))
        except Exception:
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
            # --- LOGO ---
            # To add your own logo:
            # 1. Convert your 'PragyanAI_Transperent.png' to a base64 string.
            #    You can use an online converter: https://www.base64-image.de/
            # 2. Replace the entire string assigned to 'logo_base64' with your string.
            logo_base64 = "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAARKSURBVHhe7ZxLyBxFFMd/991Md6S7S1AUVFAU9I+gvygIIj6ABfGhCCKCj4LgQxAUxIcYCIqgCAp6CAqiDxAUxMcgCPLjbbJ7d2fu7s62z/Vv9kSS7s7Mzs7s7s7+fZM8ycx8+/nNN9/MvC0A/I8bAP+jBsA/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0A/54GMDMzc/rQ0JA9Pz/XHzx4oIeHh1pqaqrevXvXvXPnTvfs2bPu6OionpycqPT19dUDg4P6/v5+HTs6OkqXLl3qkydP6qWlpdqJEyc0c+bMKScmJuo1NTXqgUFBfZ8+fdq9e/eu3bdv33rBwcF6QkJCHjY1tXv16lVbWlqq3759qw8ODuo7duxQ7+zs1JcvX9ZLS0u1T58+1ejoqL5165Z+7949/fTp05qZmZnuoUOHNG/cuKE7d+5c5/3793V+fn565MiRRllZWb0oLy/XI0eO6JGRkTp//vwxZWdn/yUAvp0GMDMzc4Kenh7d0NBQt2rVqnrb2tr0wcFB/dGjRzV3d3d9w4YN+sKFC1rX1ta6Xbt2rY6NjdW7d+/WnZ2d9eXLl/XWrVt1dna2Pnv2rN6/f193dnbaM2fOaLZt26bZtWtXL4qLi/XIyEh99+5d/eHDh/rFixd1c3OzPnv2rB4dHdUTExP1pqam+qFDh3Tfvn3r/Pr1a/3Tp0/1//z5Q3Nycuri4uL00NBQfXx8XPenpKQ87OxsvXPnztUXL17Ut2/f1mtqalQ7Ozt1dHRU/9u3b/rJkyf12bNn9R8/ftTl5eXqmTNndPv27dO8ePFinZ6e/gMAfEcNYGRkpN6/f18fHh7Wl5aW6ksXL2pVVVX6xYsX9aenp/rSpUv69u1bvejoqD558qRevnxZ7+zs1MvLy/XVq1f15s2b+vbNm7qzs1P/4sUL/eLFC33hwoX6jh079IEDB/To6Kh+9epVfXJyUmfOnDldV1dXR0dH6/nz53Vzc7Pevn1bj46O6t7e3vq2trb6vXv39Hfv3tWDBw9qZmZmuu/evSvMzMzUm5ub9ebNm/Xhw4d63759evPmTX3//n3t6enplzNnzqirq6ujI0eO6PXr13VrayvdsGEDfXh4WF9cXKw3b96sx8fH/g4A/KcNQF5eXl5aWqqtra11cXFx6tixY/revXv63r172tvb2x89elRv3bpVr6+vV+3t7fXmzZu6o6NDR0dHa15eXh0fH69Hjx7VBwcHtbe3t37q1Ck9fvx4/fHjR/348WO9e/eunp6e1t26deunTp3Sffv2rXNra2v9lClTdPfu3XWhUql60dHR+vr1a/3582etqalR7+npej8/P/38+XN9eHiovrOzU/Py8mpvb2999+5dfePGDb1r1y6dPHnyx8vL69ixY/rSpUsaRUVFXqioqNDDwsJ6eHh49lQNAH8PAWBgYKDe2dmpe3p66snJST1+/Lju27dP/8WLF3rDhg06ffr06S5dupQzZ87ovn371vnu3bv69evX2tWrV+vVq1f11KlT+sePH3VjY2MdHh6uf//+XT98+FCvqalRx8fH66NHj+qjR4/qXl5eet68efqqVav0oUOHdLdu3brY1KlTdUJCgq6oqEivra3Vu3fv1g8PD/XW1tZ63759Ojk5uQ4LC/NpM/8f8Xj4E2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHw/7gB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0A/1MD4J/UAOjnAABKAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FMNAH+qAfBPagD8Uw0Af6oB8E9qAPxTDQB/qgHwT2oA/FN/AYzQ8T0eLo//AAAAAElFTkSuQmCC"

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
            if st.session_state.get('role') == 'Admin':
                page = st.sidebar.radio("Navigation", ["Admin Dashboard", "Leader Dashboard"])
            elif st.session_state.get('role') == 'Lead':
                page = st.sidebar.radio("Navigation", ["Leader Dashboard", "Student Dashboard", "Peer Learning", "Evaluate Peer Project"])
            else: # Student
                page = st.sidebar.radio("Navigation", ["Student Dashboard", "Peer Learning", "Evaluate Peer Project"])

            st.sidebar.divider()
            if st.sidebar.button("Logout"):
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

if __name__ == "__main__":
    main()
