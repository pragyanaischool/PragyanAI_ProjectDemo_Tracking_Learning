import streamlit as st
import pandas as pd
import datetime
import re
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


def render_notice_board(client, active_events, all_events):
    st.subheader("📢 Notice Board")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    
    # --- Upcoming Events ---
    st.write("**Upcoming Project Demo Events:**")
    if not active_events.empty:
        for index, event in active_events.iterrows():
            st.markdown(f"- **{event['ProjectDemo_Event_Name']}** on `{event['Demo_Date']}` in the domain of `{event['Domain']}`.")
    else:
        st.info("There are no active project demo events scheduled.")
    
    st.markdown("---")
    
    # --- Your Enrolled Events ---
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
    
    enrolled_projects = []
    for index, event in events_df.iterrows():
        sheet_url = event.get('Project_Demo_Sheet_Link')
        if sheet_url:
            try:
                workbook = client.open_by_url(sheet_url)
                submissions = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
                if 'StudentFullName' in submissions.columns:
                    user_submissions = submissions[submissions['StudentFullName'] == user_info['FullName']]
                    if not user_submissions.empty:
                        for i, submission in user_submissions.iterrows():
                            # Create a unique identifier for each submission to handle multiple projects in one event
                            enrolled_projects.append(f"{event['ProjectDemo_Event_Name']} - {submission['ProjectTitle']}")
            except Exception:
                continue
    
    # Get unique project identifiers
    unique_enrolled_projects = sorted(list(set(enrolled_projects)))

    if not unique_enrolled_projects:
        st.info("You have not enrolled in any projects yet. Please enroll first.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    project_choice_str = st.selectbox("Select your project to update", options=unique_enrolled_projects)
    
    if project_choice_str:
        event_name, project_title = project_choice_str.split(' - ', 1)
        
        event_details = events_df[events_df['ProjectDemo_Event_Name'] == event_name].iloc[0]
        sheet_url = event_details.get('Project_Demo_Sheet_Link')

        try:
            event_workbook = client.open_by_url(sheet_url)
            submission_sheet = event_workbook.worksheet("Project_List")
            submissions_df = pd.DataFrame(submission_sheet.get_all_records(head=1))
            latest_submission = submissions_df[(submissions_df['StudentFullName'] == user_info['FullName']) & (submissions_df['ProjectTitle'] == project_title)].iloc[-1]
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
    web_links = st.text_area("Add web material links (one URL per line)")

    if "generated_content" not in st.session_state:
        st.session_state.generated_content = {}

    generate_notes_button = st.button("Generate Study Notes")

    if generate_notes_button:
        if not (report_file or web_links):
            st.error("Please provide at least one document or link.")
        else:
            with st.spinner("Reading documents and generating notes..."):
                try:
                    docs = []
                    if report_file:
                        with open(report_file.name, "wb") as f: f.write(report_file.getbuffer())
                        loader = PyPDFLoader(report_file.name)
                        docs.extend(loader.load())
                    if web_links:
                        for link in web_links.strip().split('\n'):
                            loader = WebBaseLoader(link)
                            docs.extend(loader.load())
                    
                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
                    splits = text_splitter.split_documents(docs)
                    
                    llm = ChatGroq(temperature=0.2, groq_api_key=api_key, model_name="llama3-70b-8192")
                    notes_prompt = ChatPromptTemplate.from_template("""You are an expert teacher. Based on the context, generate comprehensive study notes. Explain all key topics, sub-topics, concepts with examples and code samples if applicable. Use detailed Markdown formatting. Context: {context}""")
                    
                    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                    vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)
                    retriever = vectorstore.as_retriever()

                    rag_chain = ({"context": retriever, "question": RunnablePassthrough()} | notes_prompt | llm | StrOutputParser())
                    
                    notes = rag_chain.invoke("Generate the study notes based on the full context.")
                    st.session_state.generated_content['notes'] = notes
                    st.session_state.generated_content['quiz'] = None # Reset quiz
                    logger.info("AI Notes generated successfully.")
                    st.success("Study notes generated!")
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    logger.error(f"AI Notes generation failed: {e}")

    if st.session_state.generated_content.get('notes'):
        st.markdown("---")
        st.subheader("Generated Notes")
        st.markdown(st.session_state.generated_content['notes'])
        st.download_button("Download Notes", st.session_state.generated_content['notes'], "study_notes.md", "text/markdown")

        if st.button("Generate Quiz from Notes"):
            with st.spinner("Generating quiz..."):
                try:
                    llm = ChatGroq(temperature=0.3, groq_api_key=api_key, model_name="llama3-70b-8192")
                    quiz_prompt = ChatPromptTemplate.from_template("""Based on the following notes, create a multiple-choice quiz with 5 questions. For each question, provide 4 options (A, B, C, D) and specify the correct answer on a new line.
                    Format each question exactly like this example:
                    Q1: What is the main topic?
                    A) Option 1
                    B) Option 2
                    C) Option 3
                    D) Option 4
                    ANSWER: B

                    Notes:
                    {notes}""")
                    quiz_chain = quiz_prompt | llm | StrOutputParser()
                    quiz_md = quiz_chain.invoke({"notes": st.session_state.generated_content['notes']})
                    
                    parsed_quiz = parse_quiz_from_markdown(quiz_md)
                    if not parsed_quiz:
                        st.error("The AI failed to generate a quiz in the correct format. Please try again.")
                        logger.error(f"Failed to parse quiz from markdown: {quiz_md}")
                    else:
                        st.session_state.generated_content['quiz'] = parsed_quiz
                        st.session_state.generated_content['quiz_md'] = quiz_md
                        logger.info("AI Quiz generated successfully.")
                        st.success("Quiz generated! Go to the 'Take Quiz' tab to start.")
                except Exception as e:
                    st.error(f"An error occurred during quiz generation: {e}")
                    logger.error(f"AI Quiz generation failed: {e}")
    
    st.markdown('</div>', unsafe_allow_html=True)


def render_take_quiz():
    st.subheader("🧠 Take the Quiz")
    st.markdown('<div class="card">', unsafe_allow_html=True)

    if 'generated_content' not in st.session_state or not st.session_state.generated_content.get('quiz'):
        st.info("Please generate notes and then a quiz in the 'AI Notes & Quiz' tab first.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    quiz = st.session_state.generated_content['quiz']
    
    if 'quiz_score' not in st.session_state:
        st.session_state.quiz_score = 0
        st.session_state.current_question_index = 0

    index = st.session_state.current_question_index

    if index < len(quiz):
        question_item = quiz[index]
        st.write(f"**Question {index + 1}/{len(quiz)}:** {question_item['question']}")
        
        # The options need to be stripped of their 'A) ' prefix for the radio button labels
        option_labels = [opt[3:] for opt in question_item['options']]
        user_answer = st.radio("Choose your answer:", option_labels, key=f"q_{index}")

        if st.button("Submit Answer"):
            # Find the full option text that matches the selected label
            selected_option_full = ""
            for opt in question_item['options']:
                if opt.endswith(user_answer):
                    selected_option_full = opt
                    break
            
            if selected_option_full == question_item['answer']:
                st.success("Correct!")
                st.session_state.quiz_score += 1
            else:
                st.error(f"Incorrect. The correct answer was: {question_item['answer']}")
            
            st.session_state.current_question_index += 1
            st.rerun()

    else:
        st.success(f"**Quiz Complete!** Your final score: {st.session_state.quiz_score}/{len(quiz)}")
        st.balloons()
        if st.button("Restart Quiz"):
            # Reset quiz state
            del st.session_state.quiz_score
            del st.session_state.current_question_index
            st.rerun()

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
        render_ai_tools()
    with tab5:
        render_take_quiz()

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
