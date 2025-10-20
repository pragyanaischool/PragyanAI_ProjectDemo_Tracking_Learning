import streamlit as st
import pandas as pd
from utils import connect_to_google_sheets, load_all_projects, logger

def show_student_profile():
    st.title(f"👤 My Profile & Projects")

    user_details = st.session_state.get('user_details', {})
    if not user_details:
        st.error("Could not load user details. Please log in again.")
        return

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.header(user_details.get('FullName', 'No Name'))
    
    col1, col2 = st.columns(2)
    col1.write(f"**College:** {user_details.get('CollegeName', 'N/A')}")
    col2.write(f"**Branch:** {user_details.get('Branch', 'N/A')}")
    col1.write(f"**Username:** {user_details.get('UserName', 'N/A')}")
    col2.write(f"**Login Phone:** {user_details.get('Phone(login)', 'N/A')}")
    
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("My Project Enrollments")
    
    client = connect_to_google_sheets()
    if not client:
        st.error("Failed to connect to the database.")
        return

    all_projects_df = load_all_projects(client)
    
    if all_projects_df.empty:
        st.info("You have not enrolled in any projects yet.")
    else:
        my_projects_df = all_projects_df[all_projects_df['StudentFullName'] == user_details['FullName']]
        if my_projects_df.empty:
            st.info("You have not enrolled in any projects yet.")
        else:
            # Display relevant columns
            display_cols = ['EventName', 'ProjectTitle', 'Description']
            st.dataframe(my_projects_df[display_cols], use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)
