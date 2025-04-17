import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
import json
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoTransformerBase
from streamlit_autorefresh import st_autorefresh
import av
import smtplib
from email.message import EmailMessage
import random
from moviepy.editor import TextClip, CompositeVideoClip, concatenate_videoclips
from moviepy.config import change_settings
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Configure MoviePy to use ImageMagick if available
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})

# Configuration
PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"
RECORDING_DIR = "recordings"
QUESTION_VIDEO_DIR = "question_videos"
os.makedirs(RECORDING_DIR, exist_ok=True)
os.makedirs(QUESTION_VIDEO_DIR, exist_ok=True)

# Email configuration
EMAIL_SENDER = "rajkumar.k0322@gmail.com"
EMAIL_PASSWORD = "kcxf lzrq xnts xlng"  # App Password
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Secret key for professor panel
PROFESSOR_SECRET_KEY = "RRCE@123"

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'role' not in st.session_state:
    st.session_state.role = ""
if 'camera_active' not in st.session_state:
    st.session_state.camera_active = False
if 'prof_verified' not in st.session_state:
    st.session_state.prof_verified = False
if 'quiz_submitted' not in st.session_state:
    st.session_state.quiz_submitted = False
if 'usn' not in st.session_state:
    st.session_state.usn = ""
if 'section' not in st.session_state:
    st.session_state.section = ""
if 'prof_dir' not in st.session_state:
    st.session_state.prof_dir = "professor_data"

def get_db_connection():
    conn = sqlite3.connect('quiz_app.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    role TEXT DEFAULT 'student',
                    email TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS password_changes (
                    username TEXT PRIMARY KEY,
                    change_count INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
                    username TEXT PRIMARY KEY,
                    attempt_count INTEGER DEFAULT 0)''')
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, role, email):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                     (username, hash_password(password), role, email))
        conn.commit()
        st.success("Registration successful! Please login.")
    except sqlite3.IntegrityError:
        st.error("Username already exists!")
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user and user[0] == hash_password(password)

def get_user_role(username):
    conn = get_db_connection()
    cursor = conn.execute("SELECT role FROM users WHERE username = ?", (username,))
    role = cursor.fetchone()
    conn.close()
    return role[0] if role else "student"

def add_active_student(username):
    try:
        with open(ACTIVE_FILE, "r") as f:
            data = json.load(f)
    except:
        data = []
    if username not in data:
        data.append(username)
        with open(ACTIVE_FILE, "w") as f:
            json.dump(data, f)

def remove_active_student(username):
    try:
        with open(ACTIVE_FILE, "r") as f:
            data = json.load(f)
        data = [u for u in data if u != username]
        with open(ACTIVE_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass

def get_live_students():
    try:
        with open(ACTIVE_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def send_email_otp(to_email, otp):
    try:
        msg = EmailMessage()
        msg.set_content(f"Your OTP for Secure Quiz App is: {otp}")
        msg['Subject'] = "Email Verification OTP - Secure Quiz App"
        msg['From'] = "rajkumar.k0322@gmail.com"
        msg['To'] = to_email

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send OTP: {e}")
        return False

def create_question_video(question_data, idx):
    """Create a video for a single question with options"""
    video_path = os.path.join(QUESTION_VIDEO_DIR, f"q{idx}.mp4")
    
    # If video already exists, return the path
    if os.path.exists(video_path):
        return video_path
    
    # Create question text
    question = question_data["question"]
    options = question_data["options"]
    
    # Create a background image
    img = Image.new('RGB', (800, 600), color=(73, 109, 137))
    d = ImageDraw.Draw(img)
    
    # Use a larger font
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except:
        font = ImageFont.load_default()
    
    # Draw question text
    d.text((50, 50), f"Question {idx+1}: {question}", fill=(255, 255, 255), font=font)
    
    # Draw options
    y_offset = 150
    for i, option in enumerate(options):
        d.text((100, y_offset), f"{chr(65+i)}. {option}", fill=(255, 255, 255), font=font)
        y_offset += 50
    
    # Convert to numpy array
    img_np = np.array(img)
    
    # Create video clip (5 seconds duration)
    question_clip = TextClip(txt=f"Question {idx+1}", fontsize=50, color='white', size=(800, 600), bg_color='navy').set_duration(1)
    question_clip = question_clip.set_position('center')
    
    # Create options clip
    options_text = "\n".join([f"{chr(65+i)}. {opt}" for i, opt in enumerate(options)])
    options_clip = TextClip(txt=options_text, fontsize=30, color='white', size=(800, 400), bg_color='navy').set_duration(4)
    options_clip = options_clip.set_position(('center', 150))
    
    # Combine clips
    final_clip = CompositeVideoClip([question_clip, options_clip], size=(800, 600))
    final_clip = final_clip.set_duration(5)  # 5 seconds total
    
    # Write to file
    final_clip.write_videofile(video_path, fps=24, codec='libx264')
    
    return video_path

def generate_all_question_videos(questions):
    """Generate videos for all questions"""
    video_paths = []
    for idx, question in enumerate(questions):
        video_path = create_question_video(question, idx)
        video_paths.append(video_path)
    return video_paths

# Dummy question bank
QUESTIONS = [
    {"question": "What is the format specifier for an integer in C?", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "Which loop is used when the number of iterations is known?", "options": ["while", "do-while", "for", "if"], "answer": "for"},
]

# Generate question videos at startup
question_videos = generate_all_question_videos(QUESTIONS)

class VideoProcessor(VideoTransformerBase):
    def recv(self, frame):
        return frame

# UI Starts
st.title("\U0001F393 Secure Quiz App with Video Questions \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "View Recorded Video"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["student"])

    if st.button("Send OTP"):
        if username and email and password:
            otp = str(random.randint(100000, 999999))
            if send_email_otp(email, otp):
                st.session_state['reg_otp'] = otp
                st.session_state['reg_data'] = (username, password, role, email)
                st.success("OTP sent to your email.")
    
    otp_entered = st.text_input("Enter OTP")
    if st.button("Verify and Register"):
        if otp_entered == st.session_state.get('reg_otp'):
            username, password, role, email = st.session_state['reg_data']
            register_user(username, password, role, email)
            del st.session_state['reg_otp']
            del st.session_state['reg_data']
        else:
            st.error("Incorrect OTP!")

elif choice == "Login":
    st.subheader("Login")
    if 'login_username' not in st.session_state:
        st.session_state.login_username = ""
    if 'login_password' not in st.session_state:
        st.session_state.login_password = ""

    username = st.text_input("Username", value=st.session_state.login_username, key="login_username_widget")
    password = st.text_input("Password", type="password", value=st.session_state.login_password, key="login_password_widget")
    
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = get_user_role(username)
            st.success("Login successful!")
        else:
            st.error("Invalid username or password.")

    st.markdown("### Forgot Password?")
    forgot_email = st.text_input("Enter registered email", key="forgot_email_input")
    
    if st.button("Send Reset OTP"):
        conn = get_db_connection()
        user = conn.execute("SELECT username FROM users WHERE email = ?", (forgot_email,)).fetchone()
        conn.close()

        if user:
            otp = str(random.randint(100000, 999999))
            st.session_state['reset_email'] = forgot_email
            st.session_state['reset_otp'] = otp
            st.session_state['reset_user'] = user[0]
            if send_email_otp(forgot_email, otp):
                st.success("OTP sent to your email.")
        else:
            st.error("Email not registered.")

    if 'reset_otp' in st.session_state and 'reset_email' in st.session_state:
        st.markdown("### Reset Your Password")
        entered_otp = st.text_input("Enter OTP to reset password", key="reset_otp_input")
        new_password = st.text_input("New Password", type="password", key="reset_new_password")
        confirm_password = st.text_input("Confirm New Password", type="password", key="reset_confirm_password")

        if st.button("Reset Password"):
            if entered_otp == st.session_state.get('reset_otp'):
                if new_password == confirm_password:
                    conn = get_db_connection()
                    try:
                        conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                  (hash_password(new_password), st.session_state['reset_user']))
                        cursor = conn.execute("SELECT password FROM users WHERE username = ?",
                                             (st.session_state['reset_user'],))
                        updated_password = cursor.fetchone()[0]
                        
                        if updated_password == hash_password(new_password):
                            cursor = conn.execute("SELECT change_count FROM password_changes WHERE username = ?",
                                                (st.session_state['reset_user'],))
                            record = cursor.fetchone()
                            
                            if record:
                                conn.execute("UPDATE password_changes SET change_count = change_count + 1 WHERE username = ?",
                                           (st.session_state['reset_user'],))
                            else:
                                conn.execute("INSERT INTO password_changes (username, change_count) VALUES (?, 1)",
                                           (st.session_state['reset_user'],))
                            
                            conn.commit()
                            st.session_state.login_username = st.session_state['reset_user']
                            st.session_state.login_password = new_password
                            st.success("Password reset successfully! Your credentials have been filled below. Click Login to continue.")
                            for key in ['reset_otp', 'reset_email', 'reset_user']:
                                if key in st.session_state:
                                    del st.session_state[key]
                            st.rerun()
                        else:
                            st.error("Password update failed. Please try again.")
                    except Exception as e:
                        st.error(f"Error updating password: {str(e)}")
                    finally:
                        conn.close()
                else:
                    st.error("Passwords do not match. Please try again.")
            else:
                st.error("Incorrect OTP. Please try again.")

elif choice == "Take Quiz":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        usn = st.text_input("Enter your USN")
        section = st.text_input("Enter your Section")
        st.session_state.usn = usn.strip().upper()
        st.session_state.section = section.strip().upper()

        if usn and section:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT attempt_count FROM quiz_attempts WHERE username = ?", (username,))
            record = cur.fetchone()
            attempt_count = record[0] if record else 0

            if attempt_count >= 2:
                st.error("You have already taken the quiz 2 times. No more attempts allowed.")
            else:
                score = 0
                if "quiz_start_time" not in st.session_state:
                    st.session_state.quiz_start_time = time.time()

                time_elapsed = int(time.time() - st.session_state.quiz_start_time)
                time_limit = 25 * 60  # 25 minutes
                time_left = time_limit - time_elapsed

                if time_left <= 0:
                    st.warning("⏰ Time is up! Auto-submitting your quiz.")
                    st.session_state.auto_submit = True
                else:
                    mins, secs = divmod(time_left, 60)
                    st.info(f"⏳ Time left: {mins:02d}:{secs:02d}")

                answers = {}

                if not st.session_state.quiz_submitted and not st.session_state.camera_active:
                    add_active_student(username)
                    st.session_state.camera_active = True

                if st.session_state.camera_active and not st.session_state.quiz_submitted:
                    st.markdown("<span style='color:red;'>\U0001F7E2 Webcam is ON</span>", unsafe_allow_html=True)
                    webrtc_streamer(
                        key="camera",
                        mode=WebRtcMode.SENDRECV,
                        media_stream_constraints={"video": True, "audio": False},
                        video_processor_factory=VideoProcessor,
                    )

                # Display video questions
                for idx, question in enumerate(QUESTIONS):
                    video_file = question_videos[idx]
                    st.video(video_file)
                    ans = st.radio(f"Select your answer for Q{idx+1}:", 
                                 question['options'], 
                                 key=f"q{idx}", 
                                 index=None)
                    answers[question['question']] = ans

                submit_btn = st.button("Submit Quiz")
                auto_submit_triggered = st.session_state.get("auto_submit", False)

                if (submit_btn or auto_submit_triggered) and not st.session_state.quiz_submitted:
                    if None in answers.values():
                        st.error("Please answer all questions before submitting the quiz.")
                    else:
                        for q in QUESTIONS:
                            if answers.get(q["question"]) == q["answer"]:
                                score += 1
                        time_taken = round(time.time() - st.session_state.quiz_start_time, 2)

                        new_row = pd.DataFrame([[username, hash_password(username), st.session_state.usn, st.session_state.section, score, time_taken, datetime.now()]],
                                           columns=["Username", "Hashed_Password", "USN", "Section", "Score", "Time_Taken", "Timestamp"])

                        if os.path.exists(PROF_CSV_FILE):
                            prof_df = pd.read_csv(PROF_CSV_FILE)
                            prof_df = pd.concat([prof_df, new_row], ignore_index=True)
                        else:
                            prof_df = new_row
                        prof_df.to_csv(PROF_CSV_FILE, index=False)

                        section_file = f"{st.session_state.section}_results.csv"
                        if os.path.exists(section_file):
                            sec_df = pd.read_csv(section_file)
                            sec_df = pd.concat([sec_df, new_row], ignore_index=True)
                        else:
                            sec_df = new_row
                        sec_df.to_csv(section_file, index=False)

                        if record:
                            cur.execute("UPDATE quiz_attempts SET attempt_count = attempt_count + 1 WHERE username = ?", (username,))
                        else:
                            cur.execute("INSERT INTO quiz_attempts (username, attempt_count) VALUES (?, ?)", (username, 1))
                        conn.commit()
                        conn.close()

                        conn = get_db_connection()
                        email_result = conn.execute("SELECT email FROM users WHERE username = ?", (username,)).fetchone()
                        conn.close()
                        if email_result:
                            student_email = email_result[0]
                            try:
                                msg = EmailMessage()
                                msg.set_content(f"Dear {username},\n\nYou have successfully submitted your quiz.\nScore: {score}/{len(QUESTIONS)}\nTime Taken: {time_taken} seconds\n\nThank you for participating.")
                                msg['Subject'] = "Quiz Submission Confirmation"
                                msg['From'] = "rajkumar.k0322@gmail.com"
                                msg['To'] = student_email

                                server = smtplib.SMTP('smtp.gmail.com', 587)
                                server.starttls()
                                server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")
                                server.send_message(msg)
                                server.quit()
                            except Exception as e:
                                st.error(f"Result email failed: {e}")

                        st.success(f"Quiz submitted successfully! Your score is {score}/{len(QUESTIONS)}.")
                        st.session_state.quiz_submitted = True
                        st.session_state.camera_active = False
                        remove_active_student(username)



elif choice == "Professor Panel":
    st.subheader("\U0001F9D1‍\U0001F3EB Professor Access Panel")
    
    if not st.session_state.prof_secret_verified:
        secret_key = st.text_input("Enter Professor Secret Key", type="password")
        
        if st.button("Verify Key"):
            if secret_key == PROFESSOR_SECRET_KEY:
                st.session_state.prof_secret_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        tab1, tab2 = st.tabs(["Professor Login", "Professor Registration"])
        
        with tab1:
            if not st.session_state.prof_logged_in:
                prof_id = st.text_input("Professor ID")
                prof_pass = st.text_input("Professor Password", type="password")
                
                if st.button("Login as Professor"):
                    conn = get_db_connection()
                    cursor = conn.execute("SELECT password, role FROM users WHERE username = ? AND role = 'professor'", 
                                        (prof_id,))
                    prof_data = cursor.fetchone()
                    conn.close()
                    
                    if prof_data and prof_data[0] == hash_password(prof_pass):
                        st.session_state.prof_logged_in = True
                        st.session_state.username = prof_id
                        st.session_state.role = "professor"
                        st.success(f"Welcome Professor {prof_id}!")
                        st.rerun()
                    else:
                        st.error("Invalid Professor credentials")
            else:
                st.success(f"Welcome Professor {st.session_state.username}!")
                st.subheader("Student Results Management")
                
                # View results
                result_files = [PROF_CSV_FILE] if os.path.exists(PROF_CSV_FILE) else []
                result_files.extend(f for f in os.listdir() if f.endswith("_results.csv"))
                
                if result_files:
                    selected_file = st.selectbox("Select results file", result_files)
                    try:
                        df = pd.read_csv(selected_file)
                        
                        # Display stats
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Total Students", len(df))
                        col2.metric("Average Score", f"{df['Score'].mean():.1f}/{len(QUESTIONS)}")
                        col3.metric("Pass Rate", f"{(len(df[df['Score'] >= len(QUESTIONS)/2]) / len(df)) * 100:.1f}%")
                        
                        # Sort options
                        sort_by = st.selectbox("Sort by", ["Score", "Time_Taken", "Timestamp", "Section"])
                        ascending = st.checkbox("Ascending order", True)
                        sorted_df = df.sort_values(by=sort_by, ascending=ascending)
                        
                        st.dataframe(sorted_df)
                        st.download_button(
                            "Download Results",
                            sorted_df.to_csv(index=False),
                            f"sorted_{selected_file}",
                            "text/csv"
                        )
                    except Exception as e:
                        st.error(f"Error loading results: {e}")
                else:
                    st.warning("No results available yet.")
                
                if st.button("Logout"):
                    st.session_state.prof_logged_in = False
                    st.session_state.username = ""
                    st.session_state.role = ""
                    st.rerun()
        
        with tab2:
            st.subheader("Professor Registration")
            st.warning("Professor accounts require verification.")
            
            full_name = st.text_input("Full Name")
            designation = st.text_input("Designation")
            department = st.selectbox("Department", ["CSE", "ISE", "ECE", "EEE", "MECH", "CIVIL"])
            email = st.text_input("Institutional Email")
            
            if st.button("Request Account"):
                if all([full_name, designation, department, email]):
                    prof_id = f"PROF-{random.randint(10000, 99999)}"
                    temp_pass = str(random.randint(100000, 999999))
                    
                    conn = get_db_connection()
                    try:
                        conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                                    (prof_id, hash_password(temp_pass), "professor", email))
                        conn.commit()
                        
                        # Send credentials
                        try:
                            msg = EmailMessage()
                            msg.set_content(f"""Dear {full_name},

Your professor account has been created:

Username: {prof_id}
Password: {temp_pass}

Please login and change your password immediately.

Regards,
Quiz App Team""")
                            msg['Subject'] = "Professor Account Credentials"
                            msg['From'] = EMAIL_SENDER
                            msg['To'] = email

                            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                                server.starttls()
                                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                                server.send_message(msg)
                            
                            st.success("Account created! Credentials sent to your email.")
                        except Exception as e:
                            st.error(f"Account created but email failed: {e}")
                    except sqlite3.IntegrityError:
                        st.error("Professor with this email already exists!")
                    finally:
                        conn.close()
                else:
                    st.error("Please fill all fields!")

elif choice == "Professor Monitoring Panel":
    if not st.session_state.prof_verified:
        secret_key = st.text_input("Enter Professor Secret Key", type="password")
        
        if st.button("Verify Key"):
            if secret_key == PROFESSOR_SECRET_KEY:
                st.session_state.prof_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        st_autorefresh(interval=10000, key="monitor_refresh")
        st.header("\U0001F4E1 Live Monitoring Dashboard")
        
        live_students = get_live_students()
        if live_students:
            st.write(f"Active students ({len(live_students)}):")
            for student in live_students:
                st.write(f"- {student}")
        else:
            st.write("No active students at the moment.")
        
        st.markdown("---")
        st.subheader("Recent Quiz Submissions")
        if os.path.exists(PROF_CSV_FILE):
            df = pd.read_csv(PROF_CSV_FILE)
            st.dataframe(df.sort_values("Timestamp", ascending=False).head(5))
        else:
            st.warning("No quiz submissions yet.")

elif choice == "View Recorded Video":
    st.subheader("Recorded Sessions")
    video_files = [f for f in os.listdir(RECORDING_DIR) if f.endswith(".mp4")]
    
    if video_files:
        selected_video = st.selectbox("Select recording", video_files)
        video_path = os.path.join(RECORDING_DIR, selected_video)
        st.video(video_path)
    else:
        st.warning("No recordings available.")
