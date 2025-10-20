import streamlit as st
import pandas as pd
from utils import (
    connect_to_google_sheets, 
    get_worksheet_by_key, 
    logger,
    EVENTS_SPREADSHEET_KEY
)

def show_student_dashboard():
    st.title(f"🎓 PragyanAI - Student Dashboard")
    st.write(f"Welcome, {st.session_state['user_details']['FullName']}!")
    
    client = connect_to_google_sheets()
    if not client: return
    
    events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if not events_sheet: return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
    logger.info(f"Debug (Student Dashboard): Columns from 'Project_Demos_List': {events_df.columns.tolist()}")
    
    approved_col, conducted_col = 'Approved_Status', 'Conducted_State'
    if approved_col not in events_df.columns or conducted_col not in events_df.columns:
        st.error("Critical Error: 'Project_Demos_List' sheet is missing required columns.")
        return
    
    active_events = events_df[(events_df[approved_col].str.lower() == 'yes') & (events_df[conducted_col].str.lower() == 'no')]
    
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
            st.error("Event sheet link not found for this event. Please contact an admin.")
            return

        try:
            event_workbook = client.open_by_url(sheet_url)
            submission_sheet = event_workbook.worksheet("Project_List") 
            submissions_df = pd.DataFrame(submission_sheet.get_all_records(head=1))
        except Exception as e:
            st.error(f"Could not open the event sheet. Please check the URL and permissions. Error: {e}")
            return
            
        my_submission = pd.DataFrame()
        if 'StudentFullName' in submissions_df.columns:
            my_submission = submissions_df[submissions_df['StudentFullName'] == st.session_state['user_details']['FullName']]
        
        with st.form("enrollment_form"):
            # Form fields for student enrollment...
            st.header(f"Your Submission for: '{event_choice}'")
            project_title = st.text_input("Project Title", value=my_submission['ProjectTitle'].iloc[0] if not my_submission.empty else "")
            description = st.text_area("Description", value=my_submission['Description'].iloc[0] if not my_submission.empty else "")
            # ... other fields
            submitted = st.form_submit_button("Submit / Update Enrollment")
            if submitted:
                user_info = st.session_state['user_details']
                submission_data = [ user_info['FullName'], user_info['CollegeName'], user_info['Branch'], project_title, description, '', '', '', '', '', '', '', 'No', '', '', '', '', '', '', '' ]
                
                if not my_submission.empty:
                    cell = submission_sheet.find(user_info['FullName'])
                    submission_sheet.update(f'A{cell.row}:T{cell.row}', [submission_data])
                    st.success("Your project details have been updated!")
                else:
                    submission_sheet.append_row(submission_data)
                    st.success("You have successfully enrolled!")
    st.markdown('</div>', unsafe_allow_html=True)

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
