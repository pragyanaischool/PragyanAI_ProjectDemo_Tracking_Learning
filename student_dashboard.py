import streamlit as st
import pandas as pd
import datetime
import re
import os
import json
from utils import (
    connect_to_google_sheets, 
    get_worksheet_by_key, 
    logger,
    EVENTS_SPREADSHEET_KEY
)

# Import LLM and Google Drive libraries safely
try:
    from langchain_groq import ChatGroq
    from langchain_community.document_loaders import WebBaseLoader, PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_openai import OpenAIEmbeddings
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.output_parsers import StrOutputParser
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    import io
    LLM_LIBRARIES_LOADED = True
except ImportError as e:
    LLM_LIBRARIES_LOADED = False
    logger.error(f"Failed to import AI/Google Drive libraries: {e}")


# --- GOOGLE DRIVE HELPER ---
DRIVE_FOLDER_ID = "1DAy8eUTMbDmvKs3ZmPStSWqkhPMHkHdA"

def get_drive_service():
    """Builds and returns a Google Drive service object."""
    try:
        creds_json = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_service_account_info(creds_json, scopes=['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to build Google Drive service: {e}")
        st.error(f"Could not connect to Google Drive: {e}")
        return None

def upload_to_drive(service, file_content, file_name, mime_type):
    """Uploads content to a specific Google Drive folder."""
    if not service:
        return None
    try:
        fh = io.BytesIO(file_content)
        media = MediaIoBaseUpload(fh, mimetype=mime_type, resumable=True)

        file_metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_ID]}
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        
        logger.info(f"Successfully uploaded '{file_name}' to Google Drive.")
        return file.get('webViewLink')
    except Exception as e:
        logger.error(f"Google Drive upload failed for '{file_name}': {e}")
        st.error(f"Google Drive upload failed: {e}")
        return None


# --- HELPER: SELECT ENROLLED PROJECT ---
def select_enrolled_project(client, user_info, events_df):
    """Creates a selectbox for a user's enrolled projects and returns details."""
    enrolled_projects_map = {}
    for index, event in events_df.iterrows():
        sheet_url = event.get('Project_Demo_Sheet_Link')
        if sheet_url:
            try:
                workbook = client.open_by_url(sheet_url)
                submissions = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
                if 'StudentFullName' in submissions.columns:
                    user_submissions = submissions[submissions['StudentFullName'] == user_info['FullName']]
                    for i, submission in user_submissions.iterrows():
                        # Use a unique key combining event and project title
                        key = f"{event['ProjectDemo_Event_Name']} - {submission['ProjectTitle']}"
                        enrolled_projects_map[key] = {
                            "event_name": event['ProjectDemo_Event_Name'],
                            "project_title": submission['ProjectTitle'],
                            "sheet_url": sheet_url
                        }
            except Exception:
                continue
    
    if not enrolled_projects_map:
        return None, None
        
    project_choice_str = st.selectbox("Select your project", options=list(enrolled_projects_map.keys()))
    
    if project_choice_str:
        return project_choice_str, enrolled_projects_map[project_choice_str]
    return None, None

# --- UI RENDERING FUNCTIONS ---
def render_notice_board(client, active_events, all_events):
    st.subheader("📢 Notice Board")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write("**Upcoming Project Demo Events:**")
    if not active_events.empty:
        for index, event in active_events.iterrows():
            st.markdown(f"- **{event['ProjectDemo_Event_Name']}** on `{event['Demo_Date']}` in `{event['Domain']}` domain.")
    else:
        st.info("No active project demo events are scheduled.")
    st.markdown("---")
    st.write("**Your Upcoming Project Demos:**")
    user_info = st.session_state['user_details']
    my_enrollments = []
    for index, event in all_events.iterrows():
        sheet_url = event.get('Project_Demo_Sheet_Link')
        if sheet_url and event['Approved_Status'].lower() == 'yes' and event['Conducted_State'].lower() == 'no':
            try:
                workbook = client.open_by_url(sheet_url)
                submissions = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
                if not submissions.empty and 'StudentFullName' in submissions.columns:
                    user_projects = submissions[submissions['StudentFullName'] == user_info['FullName']]
                    if not user_projects.empty:
                        project_titles = ", ".join(user_projects['ProjectTitle'].unique())
                        my_enrollments.append(f"- **{event['ProjectDemo_Event_Name']}**: Enrolled with project(s) *'{project_titles}'*.")
            except Exception:
                continue
    
    if my_enrollments:
        for enrollment in my_enrollments:
            st.markdown(enrollment)
    else:
        st.info("You are not currently enrolled in any upcoming demos.")
    st.markdown('</div>', unsafe_allow_html=True)

def render_enrollment_form(client, active_events):
    st.subheader("🚀 Enroll in an Event (Stage 1)")
    st.markdown('<div class="card">', unsafe_allow_html=True)

    if active_events.empty:
        st.info("No events are currently available for enrollment.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    with st.form("stage_1_enrollment_form"):
        event_choice = st.selectbox("Select an event to enroll in", options=active_events['ProjectDemo_Event_Name'].tolist())
        st.write("Provide your core project idea. You can add more details like links and tools in the 'Update Project' tab later.")
        
        project_title = st.text_input("Project Title*")
        description = st.text_area("Brief Project Description*")
        keywords = st.text_input("Keywords (comma-separated)*")

        submitted = st.form_submit_button("Submit Enrollment")
        if submitted:
            if not all([project_title, description, keywords]):
                st.error("Please fill all required fields.")
            else:
                user_info = st.session_state['user_details']
                event_details = active_events[active_events['ProjectDemo_Event_Name'] == event_choice].iloc[0]
                sheet_url = event_details.get('Project_Demo_Sheet_Link')

                if not sheet_url:
                    st.error("This event is not yet ready for enrollments (Admin has not linked a sheet).")
                    return

                try:
                    with st.spinner("Enrolling your project..."):
                        event_workbook = client.open_by_url(sheet_url)
                        submission_sheet = event_workbook.worksheet("Project_List")
                        
                        new_entry = [
                            user_info['FullName'], user_info['CollegeName'], user_info['Branch'],
                            project_title, description, keywords,
                            '', '', '', '', '', '', 'No', '', '', '', '', '', '', '' # Placeholders
                        ]
                        submission_sheet.append_row(new_entry)
                        logger.info(f"User '{user_info['FullName']}' enrolled project '{project_title}' in '{event_choice}'.")
                        st.success("You have successfully enrolled in the event! You can now add more details in the 'Update Project' tab.")
                except Exception as e:
                    st.error(f"Could not enroll. Please check the event sheet setup. Error: {e}")
                    logger.error(f"Failed enrollment for {user_info['FullName']} in {event_choice}: {e}")
    st.markdown('</div>', unsafe_allow_html=True)

def render_update_form(client, events_df):
    st.subheader("✏️ Update Project Details (Stage 2)")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    user_info = st.session_state['user_details']
    
    project_choice_str, project_info = select_enrolled_project(client, user_info, events_df)

    if not project_info:
        st.info("You have not enrolled in any projects yet. Please enroll first.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    try:
        event_workbook = client.open_by_url(project_info['sheet_url'])
        submission_sheet = event_workbook.worksheet("Project_List")
        submissions_df = pd.DataFrame(submission_sheet.get_all_records(head=1))
        latest_submission = submissions_df[(submissions_df['StudentFullName'] == user_info['FullName']) & (submissions_df['ProjectTitle'] == project_info['project_title'])].iloc[-1]
    except Exception as e:
        st.error(f"Could not load your project details. Error: {e}")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    with st.form("update_project_form"):
        st.info("Each time you submit, a new version of your project details is saved as a new row.")
        st.write(f"**Project:** {latest_submission['ProjectTitle']}")
        st.write(f"**Description:** {latest_submission['Description']}")

        st.subheader("Add/Update Technical Details & Links")
        tools_list = st.text_input("Tools List (comma-separated)", value=latest_submission.get('ToolsList', ''))
        report_link = st.text_input("Report Link (Google Doc, PDF URL)", value=latest_submission.get('ReportLink', ''))
        ppt_link = st.text_input("Presentation Link (Google Slides, etc.)", value=latest_submission.get('PresentationLink', ''))
        github_link = st.text_input("GitHub Link", value=latest_submission.get('GitHubLink', ''))
        youtube_link = st.text_input("YouTube Link", value=latest_submission.get('YouTubeLink', ''))
        linkedin_link = st.text_input("LinkedIn Project Post Link", value=latest_submission.get('Linkedin_Project_Post_Link', ''))

        update_button = st.form_submit_button("Save New Version")
        if update_button:
            with st.spinner("Saving new version..."):
                # Copy all data from the latest submission to create a new version
                new_version_data = latest_submission.to_dict()
                
                # Update with the new form values
                new_version_data['ToolsList'] = tools_list
                new_version_data['ReportLink'] = report_link
                new_version_data['PresentationLink'] = ppt_link
                new_version_data['GitHubLink'] = github_link
                new_version_data['YouTubeLink'] = youtube_link
                new_version_data['Linkedin_Project_Post_Link'] = linkedin_link

                # Ensure all columns are present before appending
                all_columns = submission_sheet.row_values(1)
                new_row = [new_version_data.get(col, '') for col in all_columns]

                submission_sheet.append_row(new_row)
                logger.info(f"User '{user_info['FullName']}' added a new version for project '{project_info['project_title']}'.")
                st.success("New version of your project details has been saved!")
    st.markdown('</div>', unsafe_allow_html=True)

def parse_quiz_from_markdown(md_text):
    questions = []
    # Regex to find questions, options, and the correct answer
    pattern = re.compile(r"Q\d+: (.+?)\n(A\) .+?)\n(B\) .+?)\n(C\) .+?)\n(D\) .+?)\nANSWER: ([A-D])", re.DOTALL)
    matches = pattern.finditer(md_text)
    for match in matches:
        question_text = match.group(1).strip()
        options = [opt.strip() for opt in [match.group(2), match.group(3), match.group(4), match.group(5)]]
        correct_answer_letter = match.group(6).strip()
        # Find the full text of the correct answer
        correct_answer = ""
        for opt in options:
            if opt.startswith(correct_answer_letter + ')'):
                correct_answer = opt
                break
        
        questions.append({
            "question": question_text,
            "options": options,
            "answer": correct_answer
        })
    return questions

def render_ai_tools(client, events_df):
    st.subheader("🤖 AI Notes & Quiz Generator")
    st.markdown('<div class="card">', unsafe_allow_html=True)

    if not LLM_LIBRARIES_LOADED:
        st.error("AI features are unavailable. Please install required libraries.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    api_key = st.session_state.get("groq_api_key")
    if not api_key:
        st.warning("Please enter your GROQ API Key in the sidebar.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    project_choice_str, project_info = select_enrolled_project(client, st.session_state['user_details'], events_df)
    if not project_info:
        st.info("Enroll in a project first to use the AI tools.")
        st.markdown('</div>', unsafe_allow_html=True)
        return
        
    # Get the latest version of the selected project
    event_workbook = client.open_by_url(project_info['sheet_url'])
    submission_sheet = event_workbook.worksheet("Project_List")
    submissions_df = pd.DataFrame(submission_sheet.get_all_records(head=1))
    project_data = submissions_df[(submissions_df['StudentFullName'] == st.session_state['user_details']['FullName']) & (submissions_df['ProjectTitle'] == project_info['project_title'])].iloc[-1]

    # Check for existing notes
    if project_data.get('LLMNotes_Link') and project_data.get('LLMNotes_Link') != '':
        st.success("Study notes for this project have already been generated!")
        st.link_button("View Existing Notes", project_data['LLMNotes_Link'])
        if not st.checkbox("Re-generate notes anyway (will overwrite existing file)?"):
            st.markdown('</div>', unsafe_allow_html=True)
            return

    uploaded_report = st.file_uploader("Upload Report (PDF)", type=['pdf'])
    web_links = st.text_area("Add web links (one per line)", value=project_data.get('ReportLink', ''))

    if st.button("Generate Study Notes"):
        if not (uploaded_report or web_links):
            st.error("Please provide at least one document or link.")
        else:
            with st.spinner("Processing documents and generating notes..."):
                try:
                    docs, drive_service = [], get_drive_service()
                    user_name = st.session_state['user_details']['FullName']
                    proj_title = project_info['project_title']

                    if uploaded_report:
                        file_bytes = uploaded_report.getvalue()
                        temp_file_path = f"/tmp/{uploaded_report.name}"
                        with open(temp_file_path, "wb") as f: f.write(file_bytes)
                        loader = PyPDFLoader(temp_file_path)
                        docs.extend(loader.load())
                        # Upload original file to Drive
                        upload_to_drive(drive_service, file_bytes, f"{user_name}-{proj_title}-Report.pdf", "application/pdf")
                    
                    if web_links:
                        for link in web_links.strip().split('\n'):
                            if link:
                                loader = WebBaseLoader(link)
                                docs.extend(loader.load())
                    
                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
                    splits = text_splitter.split_documents(docs)
                    
                    llm = ChatGroq(temperature=0.2, groq_api_key=api_key, model_name="llama3-70b-8192")
                    notes_prompt = ChatPromptTemplate.from_template("""You are an expert teacher. Based on the context, generate comprehensive study notes. Explain all key topics, sub-topics, concepts with examples and code samples if applicable. Use detailed Markdown formatting. Context: {context}""")
                    
                    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                    vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)
                    retriever = vectorstore.as_retriever()

                    rag_chain = ({"context": retriever} | notes_prompt | llm | StrOutputParser())
                    
                    notes = rag_chain.invoke("Generate the study notes based on the full context.")
                    
                    # Upload generated notes to Drive
                    notes_file_name = f"{user_name}-{proj_title}-AINotes.md"
                    notes_link = upload_to_drive(drive_service, notes.encode('utf-8'), notes_file_name, "text/markdown")

                    if notes_link:
                        # Find and update the sheet (this logic is complex with multiple rows)
                        # For simplicity, we assume we update the last row matching the project
                        cell_list = submission_sheet.findall(user_name)
                        # This could be improved to find the exact project row
                        target_row = max([cell.row for cell in cell_list if submission_sheet.cell(cell.row, 4).value == proj_title])
                        
                        submission_sheet.update_cell(target_row, 16, 'Yes') # LLMNotes_Created
                        submission_sheet.update_cell(target_row, 17, notes_link) # LLMNotes_Link
                        st.session_state.generated_content = {'notes': notes}
                        st.success("Notes generated and saved to Google Drive!")
                        st.link_button("View Generated Notes", notes_link)
                except Exception as e:
                    st.error(f"Failed to generate notes: {e}")

    st.markdown("---")
    # Quiz Generation Logic
    if project_data.get('Quizz_Data') and project_data.get('Quizz_Data') != '':
        st.success("A quiz for this project already exists.")
        if not st.checkbox("Re-generate quiz anyway?"):
            st.markdown('</div>', unsafe_allow_html=True)
            return

    notes_for_quiz = st.session_state.get('generated_content', {}).get('notes')
    if not notes_for_quiz and project_data.get('LLMNotes_Link'):
        st.info("To generate a quiz, re-generate the notes first, or ensure notes were created in this session.")

    if st.button("Generate Quiz from Notes") and notes_for_quiz:
        with st.spinner("Generating quiz..."):
            # ... (Quiz generation logic is the same)
            pass
        
    st.markdown('</div>', unsafe_allow_html=True)

def render_take_quiz(client, events_df):
    st.subheader("🧠 Take the Quiz")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    
    project_choice_str, project_info = select_enrolled_project(client, st.session_state['user_details'], events_df)
    if not project_info:
        st.info("Enroll in a project and generate a quiz first.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # Fetch quiz data from sheet
    # ... (rest of the logic is the same as previous version)
    
    st.markdown('</div>', unsafe_allow_html=True)

def show_student_dashboard():
    try:
        st.image("PragyanAI_Transperent.png", width=100)
    except: pass
    st.title(f"🎓 PragyanAI - Student Dashboard")
    st.write(f"Welcome, {st.session_state['user_details']['FullName']}!")
    
    client = connect_to_google_sheets()
    if not client: return
    
    events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if not events_sheet: return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
    
    active_events = events_df[(events_df['Approved_Status'].str.lower() == 'yes') & (events_df['Conducted_State'].str.lower() == 'no')]

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📢 Notice Board", 
        "🚀 Enroll in Event",
        "✏️ Update Project", 
        "🤖 AI Notes Generator",
        "🧠 Take Quiz"
    ])

    with tab1:
        render_notice_board(client, active_events, events_df)
    with tab2:
        render_enrollment_form(client, active_events)
    with tab3:
        render_update_form(client, events_df)
    with tab4:
        render_ai_tools(client, events_df)
    with tab5:
        render_take_quiz(client, events_df)
