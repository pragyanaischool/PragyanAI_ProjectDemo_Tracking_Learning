import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import hashlib
import json
import uuid
import datetime

# --- LLM & RAG Imports ---
# NOTE: You need to install the following packages:
# pip install groq langchain langchain-groq langchain_community faiss-cpu sentence-transformers unstructured
from groq import Groq
from langchain_groq import ChatGroq
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
try:
    from groq import Groq
    from langchain_groq import ChatGroq
    from langchain_community.document_loaders import WebBaseLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain.chains import create_retrieval_chain
    from langchain.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.prompts import ChatPromptTemplate
except ImportError:
    st.error("LLM dependencies are not installed. Please run: pip install groq langchain langchain-groq langchain_community faiss-cpu sentence-transformers unstructured")


# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Project Demo Event Platform V2",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    st.title("🏆 Project Demo Event Platform")
    
    col1, col2 = st.tabs(["Sign In", "Sign Up"])

    with col1:
        st.header("Login")
        with st.form("login_form"):
            login_identifier = st.text_input("Username or Phone Number", key="login_id")
            login_password = st.text_input("Password", type="password", key="login_pass")
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

    with col2:
        st.header("Create Account")
        with st.form("signup_form"):
            st.subheader("Personal Details")
            full_name = st.text_input("Full Name")
            college = st.text_input("College Name")
            branch = st.text_input("Branch")
            roll_no = st.text_input("University Reg. No.")
            pass_year = st.text_input("Year of Passing")
            
            st.subheader("Contact & Login")
            phone_login = st.text_input("Phone (for login)")
            phone_whatsapp = st.text_input("Phone (for WhatsApp)")
            username = st.text_input("Choose a Username")
            password = st.text_input("Choose a Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            
            signup_button = st.form_submit_button("Create Account", use_container_width=True)

            if signup_button:
                if password != confirm_password:
                    st.error("Passwords do not match.")
                # Add more validation here
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

def show_admin_dashboard():
    st.title(f"👑 Admin Dashboard")
    st.write(f"Welcome, {st.session_state['username']}!")

    client = connect_to_google_sheets()
    if not client: return

    tab1, tab2 = st.tabs(["User Management", "Event Management"])

    with tab1:
        st.subheader("User Administration")
        users_sheet = get_sheet(client, USERS_SHEET_NAME)
        if not users_sheet: return
        users_df = pd.DataFrame(users_sheet.get_all_records(head=1))

        st.markdown("---")
        st.subheader("Approve New Users")
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

        st.markdown("---")
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
        
        st.markdown("---")
        st.subheader("Revoke User Access")
        if not approved_users.empty:
            user_to_revoke = st.selectbox("Select user to revoke access", options=approved_users['UserName'].tolist())
            if st.button("Revoke Access", type="primary"):
                cell = users_sheet.find(user_to_revoke)
                users_sheet.update_cell(cell.row, 11, 'Revoked')
                st.warning(f"Access for {user_to_revoke} has been revoked.")
                st.rerun()

    with tab2:
        st.subheader("Event Administration")
        events_sheet = get_sheet(client, EVENTS_MASTER_SHEET_NAME)
        if not events_sheet: return
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))

        st.markdown("---")
        st.subheader("Approve New Project Demo Events")
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

        st.markdown("---")
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
                    # Assuming Project_Demo_Sheet_Link is column I
                    events_sheet.update_cell(cell.row, 9, sheet_link)
                    # Assuming Project_Evaluation_GoogleFormLink is a new column J
                    # This requires the user to add the column to their sheet
                    # events_sheet.update_cell(cell.row, 10, eval_form_link) 
                    st.success("Event updated.")
                    st.rerun()

def show_leader_dashboard():
    st.title(f"🧑‍🏫 Lead Dashboard")
    st.write(f"Welcome, {st.session_state['username']}!")

    client = connect_to_google_sheets()
    if not client: return

    tab1, tab2 = st.tabs(["Create Project Demo", "Manage My Demos"])

    with tab1:
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
                        # Copy the template sheet
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

    with tab2:
        st.header("Your Created Events")
        events_sheet = get_sheet(client, EVENTS_MASTER_SHEET_NAME)
        if not events_sheet: return
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        my_events = events_df[events_df['ProjectDemo_Event_Name'].str.contains(st.session_state['username'], case=False)] # Simple check
        st.dataframe(my_events)


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
                    'No', '', '', '', '', '', '', '' # Presented, Score, and other fields left blank
                ]
                
                if not my_submission.empty:
                    # Find cell and update row - more robust than index
                    cell = submission_sheet.find(user_info['FullName'])
                    submission_sheet.update(f'A{cell.row}', [submission_data])
                    st.success("Your project details have been updated!")
                else:
                    submission_sheet.append_row(submission_data)
                    st.success("You have successfully enrolled in the event!")

def show_peer_learning_page():
    st.title("🧑‍🎓 Peer Learning Hub")
    st.write("Explore projects from past and present events.")
    
    client = connect_to_google_sheets()
    if not client: return
    
    # Load all projects from all events
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
                    continue # Skip sheets that can't be opened
        if not all_projects:
            return pd.DataFrame()
        return pd.concat(all_projects, ignore_index=True)

    projects_df = load_all_projects(client)
    if projects_df.empty:
        st.warning("No projects found across any events.")
        return

    project_choice = st.selectbox("Select a project to view", options=projects_df['ProjectTitle'].unique())
    if project_choice:
        project_details = projects_df[projects_df['ProjectTitle'] == project_choice].iloc[0]
        
        st.header(project_details['ProjectTitle'])
        st.caption(f"By {project_details['StudentFullName']} from {project_details['CollegeName']} | Event: {project_details['EventName']}")
        st.write(f"**Description:** {project_details['Description']}")
        
        # Display links and media
        if st.button('View Report'): st.link_button("Open Report", project_details['ReportLink'])
        if st.button('View Presentation'): st.link_button("Open Presentation", project_details['PresentationLink'])
        if project_details['YouTubeLink']: st.video(project_details['YouTubeLink'])
        
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
                    
                    prompt = ChatPromptTemplate.from_template("""Answer the following question based only on the provided context:
                    <context>
                    {context}
                    </context>
                    Question: {input}""")
                    
                    document_chain = create_stuff_documents_chain(llm, prompt)
                    retriever = vectorstore.as_retriever()
                    retrieval_chain = create_retrieval_chain(retriever, document_chain)
                    
                    response = retrieval_chain.invoke({"input": question})
                    st.success("Answer:")
                    st.write(response["answer"])

                except Exception as e:
                    st.error(f"Failed to process the document. The URL might be inaccessible or in an unsupported format. Error: {e}")

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

# --- MAIN APP LOGIC ---
def main():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        show_login_page()
    else:
        st.sidebar.title(f"Welcome, {st.session_state.get('username', '')}!")
        st.sidebar.caption(f"Role: {st.session_state.get('role', '').capitalize()}")
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
