import streamlit as st
import pandas as pd
import datetime
from utils import (
    connect_to_google_sheets, 
    get_worksheet_by_key, 
    hash_password, 
    check_password, 
    logger,
    USERS_ADMIN_SPREADSHEET_KEY
)

def create_user(details):
    client = connect_to_google_sheets()
    if not client: return False, "Database connection failed."
    users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
    if not users_sheet: return False, "Users sheet not accessible."

    users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
    logger.info(f"Debug (Create User): Columns read from 'User' sheet: {users_df.columns.tolist()}")
    if not users_df.empty and (details['UserName'] in users_df['UserName'].values or str(details['Phone(login)']) in users_df['Phone(login)'].astype(str).values):
        logger.warning(f"Attempt to create existing user: {details['UserName']}")
        return False, "Username or Login Phone already exists."

    new_user_data = [
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        details['FullName'], details['CollegeName'], details['Branch'],
        details['RollNO(UniversityRegNo)'], details['YearofPassing_Passed'],
        str(details['Phone(login)']), str(details['Phone(Whatsapp)']), details['UserName'],
        hash_password(details['Password']), 'NotApproved', 'Student'
    ]
    users_sheet.append_row(new_user_data)
    logger.info(f"New user created: {details['UserName']}. Pending approval.")
    return True, "Account created! Please wait for admin approval."

def authenticate_user(login_identifier, password):
    client = connect_to_google_sheets()
    if not client: return None
    users_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "User")
    if not users_sheet: return None
    
    users_df = pd.DataFrame(users_sheet.get_all_records(head=1))
    logger.info(f"Debug (Auth User): Columns read from 'User' sheet: {users_df.columns.tolist()}")
    if users_df.empty: 
        logger.warning("Auth attempt on empty 'User' sheet.")
        return "not_found"

    required_cols = ['UserName', 'Phone(login)', 'Password', 'Status(Approved/NotApproved)']
    if not all(col in users_df.columns for col in required_cols):
        st.error("The 'User' sheet is missing required columns. Check headers.")
        logger.error(f"Missing required columns in 'User' sheet. Required: {required_cols}")
        return None

    user_record_df = users_df[(users_df['UserName'] == login_identifier) | (users_df['Phone(login)'].astype(str) == str(login_identifier))]
    
    if user_record_df.empty:
        logger.warning(f"Login failed: User '{login_identifier}' not found.")
        return "not_found"
    
    user_data = user_record_df.iloc[0]
    
    if check_password(user_data['Password'], password):
        if str(user_data['Status(Approved/NotApproved)']).strip().lower() == 'approved':
            logger.info(f"Successful login for user: '{login_identifier}'.")
            return user_data
        else:
            logger.warning(f"Login failed for '{login_identifier}': Account not approved.")
            st.warning("Your account is not approved or is pending approval.")
            return "pending"
    else:
        logger.warning(f"Login failed for '{login_identifier}': Invalid password.")
        return "invalid_password"

def authenticate_admin(username, password):
    client = connect_to_google_sheets()
    if not client: return None
    admin_sheet = get_worksheet_by_key(client, USERS_ADMIN_SPREADSHEET_KEY, "Admin")
    if not admin_sheet: return None
    
    admins_df = pd.DataFrame(admin_sheet.get_all_records(head=1))
    logger.info(f"Debug (Auth Admin): Columns read from 'Admin' sheet: {admins_df.columns.tolist()}")
    if admins_df.empty: 
        logger.error("Admin auth attempt on empty 'Admin' sheet.")
        return None

    if 'UserName' not in admins_df.columns or 'Password' not in admins_df.columns:
        st.error("The 'Admin' sheet is missing required columns ('UserName', 'Password').")
        logger.error("Missing columns in 'Admin' sheet.")
        return None

    admin_record = admins_df[admins_df['UserName'] == username]
    if not admin_record.empty and admin_record.iloc[0]['Password'] == password:
        logger.info(f"Successful admin login for: '{username}'.")
        return admin_record.iloc[0]
    
    logger.warning(f"Failed admin login attempt for user: '{username}'.")
    return None

def show_login_page():
    st.title("🏆 PragyanAI Project Demo Tracking Platform")
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        user_tab, signup_tab, admin_tab = st.tabs(["**Student/Lead Sign In**", "**Sign Up**", "**Admin Sign In**"])

        with user_tab:
            with st.form("login_form"):
                st.subheader("Login to your Account")
                login_identifier = st.text_input("Username or Phone Number", key="login_id")
                login_password = st.text_input("Password", type="password", key="login_pass")
                st.markdown("<br>", unsafe_allow_html=True)
                login_button = st.form_submit_button("Login", use_container_width=True)

                if login_button:
                    user_data = authenticate_user(login_identifier, login_password)
                    if isinstance(user_data, pd.Series):
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = user_data['UserName']
                        st.session_state['role'] = user_data['Role(Student/Lead)']
                        st.session_state['is_admin'] = False
                        st.session_state['user_details'] = user_data.to_dict()
                        st.rerun()
                    elif user_data == "not_found":
                        st.error("User does not exist. Please check your username/phone or sign up.")
                    elif user_data == "invalid_password":
                        st.error("Invalid credentials. Please check your password.")
        
        with signup_tab:
            with st.form("signup_form"):
                st.subheader("Create a New Account")
                # Input fields...
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
                    if not all([full_name, college, branch, roll_no, pass_year, phone_login, username, password]):
                        st.error("Please fill all the fields.")
                    elif password != confirm_password:
                        st.error("Passwords do not match.")
                    else:
                        details = { "FullName": full_name, "CollegeName": college, "Branch": branch, "RollNO(UniversityRegNo)": roll_no, "YearofPassing_Passed": pass_year, "Phone(login)": phone_login, "Phone(Whatsapp)": phone_whatsapp, "UserName": username, "Password": password }
                        success, message = create_user(details)
                        if success: st.success(message)
                        else: st.error(message)

        with admin_tab:
            with st.form("admin_login_form"):
                st.subheader("Admin Login")
                admin_user = st.text_input("Admin Username", key="admin_user")
                admin_pass = st.text_input("Admin Password", type="password", key="admin_pass")
                st.markdown("<br>", unsafe_allow_html=True)
                admin_login_button = st.form_submit_button("Admin Login", use_container_width=True)
                if admin_login_button:
                    admin_data = authenticate_admin(admin_user, admin_pass)
                    if admin_data is not None:
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = admin_data['UserName']
                        st.session_state['role'] = 'Admin'
                        st.session_state['is_admin'] = True
                        st.session_state['user_details'] = admin_data.to_dict()
                        st.rerun()
                    else:
                        st.error("Invalid Admin credentials.")

        st.markdown('</div>', unsafe_allow_html=True)
