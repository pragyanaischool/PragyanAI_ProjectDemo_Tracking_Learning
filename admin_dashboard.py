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

def render_statistics(client):
    st.subheader("Platform Statistics")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)

    # Total Students
    users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
    if users_sheet:
        users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
        total_students = len(users_df[users_df['Status(Approved/NotApproved)'] == 'Approved'])
        col1.metric("Total Approved Students", total_students)
    else:
        col1.metric("Total Approved Students", "Error")

    # Total Events
    events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if events_sheet:
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        total_events = len(events_df)
        col2.metric("Total Events Created", total_events)
    else:
        col2.metric("Total Events Created", "Error")
        events_df = pd.DataFrame() # Ensure dataframe exists

    # Total Project Enrollments
    total_projects = 0
    if not events_df.empty:
        for index, row in events_df.iterrows():
            sheet_url = row.get('Project_Demo_Sheet_Link')
            if sheet_url:
                try:
                    workbook = client.open_by_url(sheet_url)
                    project_list_sheet = workbook.worksheet("Project_List")
                    records = project_list_sheet.get_all_records(head=1)
                    total_projects += len(records)
                except Exception as e:
                    logger.error(f"Could not count projects for event '{row.get('ProjectDemo_Event_Name')}': {e}")
                    continue
    col3.metric("Total Project Enrollments", total_projects)
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_user_approval(client):
    st.subheader("Approve New Users")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
    if not users_sheet: 
        st.markdown('</div>', unsafe_allow_html=True)
        return
        
    users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
    pending_users = users_df[users_df['Status(Approved/NotApproved)'] == 'NotApproved']
    if not pending_users.empty:
        users_to_approve = st.multiselect("Select users to approve", options=pending_users['UserName'].tolist())
        if st.button("Approve Selected Users"):
            for user in users_to_approve:
                cell = users_sheet.find(user)
                users_sheet.update_cell(cell.row, 11, 'Approved')
            st.success("Selected users approved.")
            st.rerun()
    else:
        st.info("No users are pending approval.")
    st.markdown('</div>', unsafe_allow_html=True)

def render_leader_management(client):
    st.subheader("Manage & View Leaders")
    users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
    if not users_sheet: return
    users_df = pd.DataFrame(users_sheet.get_all_records(head=1))

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write("Promote a Student to a Leader role.")
    approved_users = users_df[users_df['Status(Approved/NotApproved)'] == 'Approved']
    students = approved_users[approved_users['Role(Student/Lead)'] == 'Student']
    if not students.empty:
        user_to_make_leader = st.selectbox("Select user to promote to Leader", options=students['UserName'].tolist())
        if st.button("Promote to Leader"):
            cell = users_sheet.find(user_to_make_leader)
            users_sheet.update_cell(cell.row, 12, 'Lead')
            st.success(f"{user_to_make_leader} is now a Leader.")
            st.rerun()
    else:
        st.info("No students available to promote.")
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write("List of All Current Leaders")
    leaders_df = users_df[users_df['Role(Student/Lead)'] == 'Lead']
    if not leaders_df.empty:
        st.dataframe(leaders_df[['FullName', 'CollegeName', 'UserName', 'Phone(login)']])
    else:
        st.info("There are currently no leaders.")
    st.markdown('</div>', unsafe_allow_html=True)

def render_all_students(client):
    st.subheader("List of All Enrolled Students")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
    if not users_sheet:
        st.markdown('</div>', unsafe_allow_html=True)
        return
    users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
    students_df = users_df[users_df['Status(Approved/NotApproved)'] == 'Approved']
    st.dataframe(students_df[['FullName', 'CollegeName', 'Branch', 'UserName', 'Phone(login)', 'Role(Student/Lead)']])
    st.markdown('</div>', unsafe_allow_html=True)

def render_enrollments_by_project(client):
    st.subheader("View Enrollments by Project Demo")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if not events_sheet:
        st.markdown('</div>', unsafe_allow_html=True)
        return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
    
    event_choice = st.selectbox("Select an Event", options=events_df['ProjectDemo_Event_Name'].tolist())
    if event_choice:
        sheet_url = events_df[events_df['ProjectDemo_Event_Name'] == event_choice].iloc[0].get('Project_Demo_Sheet_Link')
        if sheet_url:
            try:
                workbook = client.open_by_url(sheet_url)
                project_list = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
                st.write(f"Found {len(project_list)} enrollments for '{event_choice}':")
                st.dataframe(project_list)
            except Exception as e:
                st.error(f"Could not open or read the sheet for this event. Please check the link and permissions. Error: {e}")
        else:
            st.warning("This event does not have a sheet link yet.")
    st.markdown('</div>', unsafe_allow_html=True)

def render_all_demos(client):
    st.subheader("List of All Project Demos")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if not events_sheet:
        st.markdown('</div>', unsafe_allow_html=True)
        return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
    st.dataframe(events_df)
    st.markdown('</div>', unsafe_allow_html=True)

def render_system_logs():
    st.subheader("Application Log")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    log_file = 'app_log.txt'
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            log_content = f.read()
        st.code(log_content, language='log')
        st.download_button("Download Log File", log_content, "pragyanai_app_log.txt", "text/plain")
    else:
        st.info("Log file not found. It will be created as the application runs.")
    st.markdown('</div>', unsafe_allow_html=True)


def show_admin_dashboard():
    st.title(f"👑 PragyanAI - Admin Dashboard")
    
    client = connect_to_google_sheets()
    if not client: return

    # Using a selectbox in the main area as a sub-menu
    st.markdown("---")
    sub_menu = st.selectbox(
        "Admin Menu",
        [
            "Statistics",
            "Approve New Users", 
            "Manage Leaders",
            "List all Students",
            "Enrollments by Project Demo",
            "List all Project Demos",
            "Manage & Approve Events",
            "System Logs"
        ]
    )
    st.markdown("---")

    if sub_menu == "Statistics":
        render_statistics(client)
    elif sub_menu == "Approve New Users":
        render_user_approval(client)
    elif sub_menu == "Manage Leaders":
        render_leader_management(client)
    elif sub_menu == "List all Students":
        render_all_students(client)
    elif sub_menu == "Enrollments by Project Demo":
        render_enrollments_by_project(client)
    elif sub_menu == "List all Project Demos":
        render_all_demos(client)
    elif sub_menu == "Manage & Approve Events":
        # The original event management UI
        st.subheader("Manage & Approve Project Demo Events")
        st.markdown('<div class="card">', unsafe_allow_html=True)
        events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
        if not events_sheet: return
        events_df = pd.DataFrame(events_sheet.get_all_records(head=1))
        
        event_to_manage = st.selectbox("Select an event to manage", options=events_df['ProjectDemo_Event_Name'].tolist(), key="admin_manage_event")
        if event_to_manage:
            event_details = events_df[events_df['ProjectDemo_Event_Name'] == event_to_manage].iloc[0]
            with st.form("admin_manage_event_form"):
                st.write(f"**Status:** {event_details.get('Approved_Status', 'N/A')}")
                st.subheader("Stage 2: Add Links & Finalize")
                
                if st.form_submit_button("Create New Google Sheet for this Event"):
                    with st.spinner("Creating..."):
                        try:
                            new_sheet = client.copy(EVENT_TEMPLATE_SPREADSHEET_KEY, title=f"Event - {event_to_manage}", copy_permissions=True)
                            st.session_state.new_sheet_link = new_sheet.url
                            st.success(f"New sheet created! Link auto-filled below.")
                        except Exception as e:
                            st.error(f"Failed to create sheet. Error: {e}")
                
                sheet_link = st.text_input("Project Demo Sheet Link*", value=st.session_state.get('new_sheet_link', event_details.get('Project_Demo_Sheet_Link', '')))
                whatsapp_link = st.text_input("WhatsApp Group Link", value=event_details.get('WhatsappLink', ''))
                
                if st.form_submit_button("Save and Approve Event"):
                    if not sheet_link:
                        st.error("Sheet Link is required before approving.")
                    else:
                        cell = events_sheet.find(event_to_manage)
                        events_sheet.update_cell(cell.row, 6, 'Yes') # Approved_Status
                        events_sheet.update_cell(cell.row, 8, whatsapp_link)
                        events_sheet.update_cell(cell.row, 9, sheet_link)
                        st.success(f"Event '{event_to_manage}' approved!")
                        if 'new_sheet_link' in st.session_state: del st.session_state['new_sheet_link']
                        st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    elif sub_menu == "System Logs":
        render_system_logs()
        
