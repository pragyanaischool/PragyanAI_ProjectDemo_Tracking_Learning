import streamlit as st
import pandas as pd
import datetime
from utils import (
    connect_to_google_sheets, 
    get_worksheet_by_key, 
    logger,
    EVENTS_SPREADSHEET_KEY
)

# Import LLM libraries safely
try:
    from langchain_groq import ChatGroq
    from langchain_community.document_loaders import WebBaseLoader, PyPDFLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.output_parsers import StrOutputParser
    LLM_LIBRARIES_LOADED = True
except ImportError:
    LLM_LIBRARIES_LOADED = False


def render_notice_board(active_events):
    st.subheader("📢 Notice Board")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if not active_events.empty:
        st.write("**Upcoming Project Demo Events:**")
        for index, event in active_events.iterrows():
            st.markdown(f"- **{event['ProjectDemo_Event_Name']}** on `{event['Demo_Date']}` in the domain of `{event['Domain']}`.")
    else:
        st.info("There are no active project demo events scheduled.")
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
    
    # Find events the user has enrolled in
    enrolled_projects = []
    for index, event in events_df.iterrows():
        sheet_url = event.get('Project_Demo_Sheet_Link')
        if sheet_url:
            try:
                workbook = client.open_by_url(sheet_url)
                submissions = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
                user_submissions = submissions[submissions['StudentFullName'] == user_info['FullName']]
                if not user_submissions.empty:
                    for i, submission in user_submissions.iterrows():
                        enrolled_projects.append(f"{event['ProjectDemo_Event_Name']} - {submission['ProjectTitle']}")
            except Exception:
                continue
    
    if not enrolled_projects:
        st.info("You have not enrolled in any projects yet. Please enroll in the 'Notice Board & Enroll' tab first.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    project_choice_str = st.selectbox("Select your project to update", options=enrolled_projects)
    
    if project_choice_str:
        event_name, project_title = project_choice_str.split(' - ', 1)
        
        event_details = events_df[events_df['ProjectDemo_Event_Name'] == event_name].iloc[0]
        sheet_url = event_details.get('Project_Demo_Sheet_Link')

        try:
            event_workbook = client.open_by_url(sheet_url)
            submission_sheet = event_workbook.worksheet("Project_List")
            submissions_df = pd.DataFrame(submission_sheet.get_all_records(head=1))
            # Get the latest submission for this project
            latest_submission = submissions_df[(submissions_df['StudentFullName'] == user_info['FullName']) & (submissions_df['ProjectTitle'] == project_title)].iloc[-1]
        except Exception as e:
            st.error(f"Could not load your project details. Error: {e}")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        with st.form("update_project_form"):
            st.info("Each time you submit, a new version of your project details is saved.")
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
                    # Create a new row by copying old data and updating with new
                    new_version_data = latest_submission.values.tolist()
                    new_version_data[6] = tools_list
                    new_version_data[7] = report_link
                    new_version_data[8] = ppt_link
                    new_version_data[9] = github_link
                    new_version_data[10] = youtube_link
                    new_version_data[11] = linkedin_link

                    submission_sheet.append_row(new_version_data)
                    logger.info(f"User '{user_info['FullName']}' added a new version for project '{project_title}'.")
                    st.success("New version of your project details has been saved!")
    
    st.markdown('</div>', unsafe_allow_html=True)


def render_ai_tools():
    st.subheader("🤖 AI Notes & Quiz Generator")
    st.markdown('<div class="card">', unsafe_allow_html=True)

    if not LLM_LIBRARIES_LOADED:
        st.error("AI features are unavailable because required libraries are not installed.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.info("This tool uses AI to generate study notes and quizzes based on your project materials.")
    api_key = st.session_state.get("groq_api_key")
    if not api_key:
        st.warning("Please enter your GROQ API Key in the sidebar to use AI features.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    report_file = st.file_uploader("Upload Report (PDF)", type=['pdf'])
    ppt_file = st.file_uploader("Upload Presentation (PDF)", type=['pdf'])
    web_links = st.text_area("Add web material links (one URL per line)")

    if st.button("Generate Study Notes"):
        if not (report_file or ppt_file or web_links):
            st.error("Please provide at least one document or link.")
        else:
            with st.spinner("Reading documents and generating notes... This may take a moment."):
                try:
                    # Document Loading and Processing
                    docs = []
                    if report_file:
                        with open(report_file.name, "wb") as f: f.write(report_file.getbuffer())
                        loader = PyPDFLoader(report_file.name)
                        docs.extend(loader.load())
                    if ppt_file:
                        with open(ppt_file.name, "wb") as f: f.write(ppt_file.getbuffer())
                        loader = PyPDFLoader(ppt_file.name)
                        docs.extend(loader.load())
                    if web_links:
                        for link in web_links.strip().split('\n'):
                            loader = WebBaseLoader(link)
                            docs.extend(loader.load())
                    
                    # Text Splitting
                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
                    splits = text_splitter.split_documents(docs)
                    
                    # LLM and Prompt
                    llm = ChatGroq(temperature=0.2, groq_api_key=api_key, model_name="llama3-70b-8192")
                    notes_prompt = ChatPromptTemplate.from_template(
                        """You are an expert teacher and content creator. Based on the provided context, generate a comprehensive set of study notes.
                        Your notes must be well-structured, clear, and detailed.
                        - Start with a high-level summary of the main topic.
                        - Identify and explain all key topics, sub-topics, and core concepts.
                        - For each concept, provide a clear definition and examples.
                        - If code is mentioned, provide sample code snippets with explanations.
                        - Use Markdown for formatting (headings, bold text, lists).

                        Context:
                        {context}
                        """
                    )
                    
                    # Create RAG Chain for Notes
                    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                    vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)
                    retriever = vectorstore.as_retriever()

                    rag_chain = (
                        {"context": retriever, "question": RunnablePassthrough()}
                        | notes_prompt
                        | llm
                        | StrOutputParser()
                    )
                    
                    # Invoke and store in session state
                    notes = rag_chain.invoke("Generate the study notes based on the full context.")
                    st.session_state.generated_notes = notes
                    logger.info("AI Notes generated successfully.")
                    st.success("Study notes generated!")

                except Exception as e:
                    st.error(f"An error occurred during note generation: {e}")
                    logger.error(f"AI Notes generation failed: {e}")

    if 'generated_notes' in st.session_state:
        st.subheader("Generated Notes")
        st.markdown(st.session_state.generated_notes)
        st.download_button("Download Notes", st.session_state.generated_notes, "study_notes.md", "text/markdown")

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

    tab1, tab2, tab3 = st.tabs(["📢 Notice Board & Enroll", "✏️ Update Project Details", "🤖 AI Notes & Quiz"])

    with tab1:
        render_notice_board(active_events)
        render_enrollment_form(client, active_events)

    with tab2:
        render_update_form(client, events_df)
    
    with tab3:
        render_ai_tools()

def show_evaluator_ui():
    st.title("📝 PragyanAI - Peer Project Evaluation")
    
    client = connect_to_google_sheets()
    if not client: return
    
    events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if not events_sheet: return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
    
    active_events = events_df[(events_df['Approved_Status'].str.lower() == 'yes') & (events_df['Conducted_State'].str.lower() == 'no')]
    
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
            submissions_df = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
        except Exception: return
        
        candidate = st.selectbox("Select Candidate to Evaluate", options=submissions_df['StudentFullName'].tolist())
        
        if candidate:
            with st.form("evaluation_form"):
                st.header(f"Evaluating: {candidate}")
                score1 = st.slider("Presentation", 0, 100, 50)
                score2 = st.slider("Technical Knowledge", 0, 100, 50)
                score3 = st.slider("Demo & Code", 0, 100, 50)
                score4 = st.slider("Q & A", 0, 100, 50)
                
                submitted = st.form_submit_button("Submit Evaluation")
                if submitted:
                    avg_score = (score1 + score2 + score3 + score4) / 4
                    eval_sheet = workbook.worksheet("ProjectEvaluation")
                    eval_data = [candidate, submissions_df[submissions_df['StudentFullName'] == candidate]['ProjectTitle'].iloc[0], avg_score, st.session_state['username']]
                    eval_sheet.append_row(eval_data)
                    st.success(f"Evaluation for {candidate} submitted!")
    st.markdown('</div>', unsafe_allow_html=True)
