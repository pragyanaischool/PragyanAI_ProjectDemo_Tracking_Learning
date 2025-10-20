import streamlit as st
import pandas as pd
import datetime
from utils import (
    connect_to_google_sheets, 
    get_worksheet_by_key, 
    logger,
    EVENTS_SPREADSHEET_KEY,
    EVENT_TEMPLATE_SPREADSHEET_KEY
)

def show_leader_dashboard():
    st.title(f"🧑‍🏫 PragyanAI - Lead Dashboard")

    client = connect_to_google_sheets()
    if not client: return

    tab1, tab2, tab3, tab4 = st.tabs(["🚀 Create Project Demo", "✏️ Modify Event", "📊 Check Enrollments", "📋 All My Demos"])

    with tab1:
        # Create Project Demo UI
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.header("Create New Project Demo Event (Stage 1)")
        with st.form("leader_create_event"):
            st.write("Provide initial details. An Admin will add the Google Sheet link and approve it.")
            event_name = st.text_input("Project Event Name*")
            demo_date = st.date_input("Demo Date*")
            domain = st.text_input("Domain (e.g., AI/ML, Web Development)*")
            description = st.text_area("Brief Description*")

            submitted = st.form_submit_button("Submit for Admin Review")
            if submitted:
                if not all([event_name, demo_date, domain, description]):
                    st.error("Please fill all required fields marked with *.")
                else:
                    with st.spinner("Submitting event request..."):
                        try:
                            events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
                            new_event_data = [str(demo_date), event_name, domain, description, '', 'No', 'No', '', '', '', '', '', '', '', '', '', '', '']
                            events_sheet.append_row(new_event_data)
                            logger.info(f"Leader '{st.session_state['username']}' created new event '{event_name}' for approval.")
                            st.success("Event submitted for admin review!")
                        except Exception as e:
                            st.error(f"An unexpected error occurred: {e}")
                            logger.error(f"Failed to create new event request for '{event_name}': {e}")
        st.markdown('</div>', unsafe_allow_html=True)

    events_sheet = get_worksheet_by_key(client, EVENTS_SPREADSHEET_KEY, "Project_Demos_List")
    if not events_sheet:
        st.error("Could not load events list.")
        return
    events_df = pd.DataFrame(events_sheet.get_all_records(head=1))

    with tab2:
        # Modify Event UI
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.header("Modify Event Details")
        event_to_modify = st.selectbox("Select an event to modify", options=events_df['ProjectDemo_Event_Name'].tolist(), key="lead_modify_select")
        if event_to_modify:
            event_details = events_df[events_df['ProjectDemo_Event_Name'] == event_to_modify].iloc[0]
            with st.form("lead_modify_form"):
                st.info("You can update the descriptive details. Links and status are managed by Admins.")
                domain = st.text_input("Domain", value=event_details.get('Domain', ''))
                description = st.text_area("Brief Description", value=event_details.get('BriefDescription', ''))
                # Add sample fields here for modification if needed
                
                update_button = st.form_submit_button("Save Changes")
                if update_button:
                    cell = events_sheet.find(event_to_modify)
                    events_sheet.update_cell(cell.row, 3, domain)
                    events_sheet.update_cell(cell.row, 4, description)
                    logger.info(f"Leader '{st.session_state['username']}' updated event '{event_to_modify}'.")
                    st.success("Event details updated!")
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with tab3:
        # Check Enrollments UI
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.header("Check Student Enrollments")
        approved_events_df = events_df[events_df['Approved_Status'].str.lower() == 'yes']
        if not approved_events_df.empty:
            event_to_check = st.selectbox("Select an approved event", options=approved_events_df['ProjectDemo_Event_Name'].tolist(), key="lead_check_enrollments")
            if event_to_check:
                sheet_url = approved_events_df[approved_events_df['ProjectDemo_Event_Name'] == event_to_check].iloc[0]['Project_Demo_Sheet_Link']
                if sheet_url:
                    try:
                        workbook = client.open_by_url(sheet_url)
                        submissions_df = pd.DataFrame(workbook.worksheet("Project_List").get_all_records(head=1))
                        st.write(f"Displaying {len(submissions_df)} enrollments for '{event_to_check}':")
                        st.dataframe(submissions_df)
                    except Exception as e:
                        st.error(f"Could not load enrollments. Check the sheet link and permissions. Error: {e}")
                else:
                    st.warning("This event does not have a Google Sheet linked by the Admin yet.")
        else:
            st.info("No approved events found to check enrollments.")
        st.markdown('</div>', unsafe_allow_html=True)

    with tab4:
        # All My Demos UI
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.header("All Created Events")
        st.dataframe(events_df, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
