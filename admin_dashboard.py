import streamlit as st
import pandas as pd
import os
from utils import (
    connect_to_google_sheets, 
    get_worksheet_by_key, 
    logger,
    USERS_ADMIN_SPREADSHEET_KEY,
    EVENTS_SPREADSHEET_KEY,
    EVENT_TEMPLATE_SPREADSHEET_KEY
)

def show_admin_dashboard():
    st.title(f"👑 PragyanAI - Admin Dashboard")
    
    client = connect_to_google_sheets()
    if not client: return

    tab1, tab2, tab3 = st.tabs(["👤 User Management", "🗓️ Event Management", "⚙️ System Logs"])

    with tab1:
        # User Management UI...
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Approve New Users")
        users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
        if not users_sheet: return
        users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
        logger.info(f"Debug (Admin User Mgt): Columns read from 'User' sheet: {users_df.columns.tolist()}")

        status_col, role_col = 'Status(Approved/NotApproved)', 'Role(Student/Lead)'
        if status_col not in users_df.columns or role_col not in users_df.columns:
            st.error(f"Critical Error: 'User' sheet missing required columns '{status_col}' or '{role_col}'.")
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

        # Other user management sections...
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Manage Leaders")
        approved_users = users_df[users_df[status_col] == 'Approved']
        students = approved_users[approved_users[role_col] == 'Student']
        if not students.empty:
            user_to_make_leader = st.selectbox("Select user to promote to Leader", options=students['UserName'].tolist())
            if st.button("Promote to Leader"):
                cell = users_sheet.find(user_to_make_leader)
                users_sheet.update_cell(cell.row, 12, 'Lead')
                logger.info(f"Admin promoted '{user_to_make_leader}' to Leader.")
                st.success(f"{user_to_make_leader} is now a Leader.")
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        # Event Management UI...
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Manage & Approve Project Demo Events")
        events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
        if not events_sheet: return
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        logger.info(f"Debug (Admin Event Mgt): Columns read from 'Project_Demos_List': {events_df.columns.tolist()}")
        
        required_cols = ['ProjectDemo_Event_Name', 'Approved_Status']
        if not all(col in events_df.columns for col in required_cols):
            st.error("Critical Error: 'Project_Demos_List' sheet is missing required columns.")
            return
            
        event_to_manage = st.selectbox("Select an event to manage", options=events_df['ProjectDemo_Event_Name'].tolist())
        
        if event_to_manage:
            event_details = events_df[events_df['ProjectDemo_Event_Name'] == event_to_manage].iloc[0]
            with st.form("admin_manage_event_form"):
                st.write(f"**Status:** {event_details.get('Approved_Status', 'N/A')}")
                st.subheader("Stage 2: Add Links & Finalize")
                
                if st.form_submit_button("Create New Google Sheet for this Event"):
                    with st.spinner("Creating new event sheet..."):
                        try:
                            new_sheet = client.copy(EVENT_TEMPLATE_SPREADSHEET_KEY, title=f"Event - {event_to_manage}", copy_permissions=True)
                            st.session_state.new_sheet_link = new_sheet.url
                            st.success(f"New sheet created! Link auto-filled below.")
                        except Exception as e:
                            st.error(f"Failed to create new sheet. Error: {e}")
                
                sheet_link = st.text_input("Project Demo Sheet Link*", value=st.session_state.get('new_sheet_link', event_details.get('Project_Demo_Sheet_Link', '')))
                whatsapp_link = st.text_input("WhatsApp Group Link", value=event_details.get('WhatsappLink', ''))
                
                approve_button = st.form_submit_button("Save and Approve Event")
                if approve_button:
                    if not sheet_link:
                        st.error("You must provide or create a 'Project Demo Sheet Link' before approving.")
                    else:
                        cell = events_sheet.find(event_to_manage)
                        events_sheet.update_cell(cell.row, 6, 'Yes') # Approved_Status
                        events_sheet.update_cell(cell.row, 8, whatsapp_link)
                        events_sheet.update_cell(cell.row, 9, sheet_link)
                        logger.info(f"Admin approved event '{event_to_manage}'.")
                        st.success(f"Event '{event_to_manage}' has been approved and details updated!")
                        if 'new_sheet_link' in st.session_state: del st.session_state['new_sheet_link']
                        st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with tab3:
        # Log Viewer UI...
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Application Log")
        log_file = 'app_log.txt'
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                log_content = f.read()
            st.code(log_content, language='log')
            st.download_button("Download Log File", log_content, "pragyanai_app_log.txt", "text/plain")
        else:
            st.info("Log file not found.")
        st.markdown('</div>', unsafe_allow_html=True)
