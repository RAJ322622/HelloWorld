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
from gtts import gTTS
import cv2
import numpy as np
import moviepy.editor as mp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"
RECORDING_DIR = "recordings"
VIDEO_DIR = "question_videos"
os.makedirs(RECORDING_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# Email configuration from environment variables
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

# Secret key for professor panel from environment variable
PROFESSOR_SECRET_KEY = os.getenv("PROFESSOR_SECRET_KEY")

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
if 'prof_secret_verified' not in st.session_state:
    st.session_state.prof_secret_verified = False
if 'prof_logged_in' not in st.session_state:
    st.session_state.prof_logged_in = False

def get_db_connection():
    conn = sqlite3.connect('quiz_app.db', check_same_thread=False)
    
    # Create tables if they don't exist
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

def send_email_otp(to_email, otp):
    try:
        msg = EmailMessage()
        msg.set_content(f"Your OTP for Secure Quiz App is: {otp}")
        msg['Subject'] = "Email Verification OTP - Secure Quiz App"
        msg['From'] = EMAIL_SENDER
        msg['To'] = to_email

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Failed to send OTP: {e}")
        return False

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
    except (FileNotFoundError, json.JSONDecodeError):
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
    except (FileNotFoundError, json.JSONDecodeError):
        pass

def get_live_students():
    try:
        with open(ACTIVE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

QUESTIONS = [
    {"question": "🔤 Which data type is used to store a single character in C? 🎯", 
     "options": ["char", "int", "float", "double"], 
     "answer": "char"},
    # ... (keep your existing questions)
]

class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.recording = True
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_file = os.path.join(RECORDING_DIR, f"quiz_recording_{timestamp}.mp4")
        self.container = av.open(self.output_file, mode="w")
        self.stream = self.container.add_stream("h264", rate=30)
        self.stream.width = 640
        self.stream.height = 480
        self.stream.pix_fmt = "yuv420p"

    def recv(self, frame):
        if self.recording:
            img = frame.to_ndarray(format="bgr24")
            frame = av.VideoFrame.from_ndarray(img, format="bgr24")
            packet = self.stream.encode(frame)
            if packet:
                self.container.mux(packet)
        return frame

    def close(self):
        if self.recording:
            self.recording = False
            # Flush stream
            for packet in self.stream.encode():
                self.container.mux(packet)
            self.container.close()

def generate_audio(question_text, filename):
    if not os.path.exists(filename):
        tts = gTTS(text=question_text, lang='en')
        tts.save(filename)

def create_video(question_text, filename, audio_file):
    video_path = os.path.join(VIDEO_DIR, filename)
    if os.path.exists(video_path):
        return video_path

    width, height = 640, 480
    img = np.full((height, width, 3), (255, 223, 186), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, 10, (width, height))

    for _ in range(50):  # 5 seconds at 10 fps
        img_copy = img.copy()
        text_size = cv2.getTextSize(question_text, font, 0.8, 2)[0]
        text_x = (width - text_size[0]) // 2
        text_y = (height + text_size[1]) // 2
        cv2.putText(img_copy, question_text, (text_x, text_y), font, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
        out.write(img_copy)

    out.release()

    video_clip = mp.VideoFileClip(video_path)
    audio_clip = mp.AudioFileClip(audio_file)
    final_video = video_clip.set_audio(audio_clip)
    final_video.write_videofile(video_path, codec='libx264', fps=10, audio_codec='aac')

    return video_path

# Main UI
st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "View Recorded Video"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    st.subheader("Register")
    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["student"])

    if st.button("Send OTP"):
        if username and email and password:
            otp = str(random.randint(100000, 999999))
            if send_email_otp(email, otp):
                st.session_state.reg_otp = otp
                st.session_state.reg_data = (username, password, role, email)
                st.success("OTP sent to your email.")
    
    otp_entered = st.text_input("Enter OTP")
    if st.button("Verify and Register"):
        if otp_entered == st.session_state.get('reg_otp', ''):
            username, password, role, email = st.session_state.reg_data
            register_user(username, password, role, email)
            del st.session_state.reg_otp
            del st.session_state.reg_data
        else:
            st.error("Incorrect OTP!")

elif choice == "Login":
    st.subheader("Login")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = get_user_role(username)
            st.success("Login successful!")
        else:
            st.error("Invalid username or password.")

    # Forgot password section
    st.markdown("### Forgot Password?")
    forgot_email = st.text_input("Enter registered email", key="forgot_email")
    
    if st.button("Send Reset OTP"):
        conn = get_db_connection()
        user = conn.execute("SELECT username FROM users WHERE email = ?", (forgot_email,)).fetchone()
        conn.close()

        if user:
            otp = str(random.randint(100000, 999999))
            st.session_state.reset_otp = otp
            st.session_state.reset_email = forgot_email
            st.session_state.reset_user = user[0]
            if send_email_otp(forgot_email, otp):
                st.success("OTP sent to your email.")
        else:
            st.error("Email not registered.")

    if 'reset_otp' in st.session_state:
        st.markdown("### Reset Your Password")
        entered_otp = st.text_input("Enter OTP", key="reset_otp_input")
        new_password = st.text_input("New Password", type="password", key="new_password")
        confirm_password = st.text_input("Confirm New Password", type="password", key="confirm_password")
        
        if st.button("Reset Password"):
            if entered_otp == st.session_state.reset_otp:
                if new_password == confirm_password:
                    conn = get_db_connection()
                    try:
                        conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                   (hash_password(new_password), st.session_state.reset_user))
                        
                        # Update password change count
                        cursor = conn.execute("SELECT change_count FROM password_changes WHERE username = ?",
                                            (st.session_state.reset_user,))
                        record = cursor.fetchone()
                        
                        if record:
                            conn.execute("UPDATE password_changes SET change_count = change_count + 1 WHERE username = ?",
                                       (st.session_state.reset_user,))
                        else:
                            conn.execute("INSERT INTO password_changes (username, change_count) VALUES (?, 1)",
                                       (st.session_state.reset_user,))
                        
                        conn.commit()
                        st.success("Password reset successfully! Please login with your new password.")
                        
                        # Clear reset state
                        del st.session_state.reset_otp
                        del st.session_state.reset_email
                        del st.session_state.reset_user
                    except Exception as e:
                        st.error(f"Error updating password: {str(e)}")
                    finally:
                        conn.close()
                else:
                    st.error("Passwords do not match.")
            else:
                st.error("Incorrect OTP.")

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
                # Initialize quiz timer
                if "quiz_start_time" not in st.session_state:
                    st.session_state.quiz_start_time = time.time()
                    st.session_state.answers = {}

                time_elapsed = int(time.time() - st.session_state.quiz_start_time)
                time_limit = 25 * 60  # 25 minutes
                time_left = max(0, time_limit - time_elapsed)
                mins, secs = divmod(time_left, 60)
                st.info(f"⏳ Time left: {mins:02d}:{secs:02d}")

                if time_left <= 0:
                    st.warning("⏰ Time is up! Auto-submitting your quiz.")
                    st.session_state.auto_submit = True

                # Start camera monitoring
                if not st.session_state.quiz_submitted and not st.session_state.camera_active:
                    add_active_student(username)
                    st.session_state.camera_active = True

                if st.session_state.camera_active and not st.session_state.quiz_submitted:
                    st.markdown("<span style='color:red;'>\U0001F7E2 Webcam is ON</span>", unsafe_allow_html=True)
                    webrtc_ctx = webrtc_streamer(
                        key="quiz_camera",
                        mode=WebRtcMode.SENDRECV,
                        media_stream_constraints={"video": True, "audio": False},
                        video_processor_factory=VideoProcessor,
                        async_processing=True
                    )

                # Display questions
                for idx, question in enumerate(QUESTIONS):
                    question_text = question["question"]
                    audio_file = os.path.join(VIDEO_DIR, f"q{idx}_audio.mp3")
                    video_file = os.path.join(VIDEO_DIR, f"q{idx}_video.mp4")

                    generate_audio(question_text, audio_file)
                    video_path = create_video(question_text, video_file, audio_file)

                    st.video(video_path)
                    ans = st.radio(f"Select your answer for Question {idx+1}:", 
                                   question['options'], 
                                   key=f"q{idx}", 
                                   index=None)
                    st.session_state.answers[question['question']] = ans

                submit_btn = st.button("Submit Quiz")
                auto_submit_triggered = st.session_state.get("auto_submit", False)

                if (submit_btn or auto_submit_triggered) and not st.session_state.quiz_submitted:
                    if None in st.session_state.answers.values():
                        st.error("Please answer all questions before submitting.")
                    else:
                        # Calculate score
                        score = sum(1 for q in QUESTIONS 
                                  if st.session_state.answers.get(q["question"]) == q["answer"])
                        time_taken = round(time.time() - st.session_state.quiz_start_time, 2)

                        # Save results
                        new_row = pd.DataFrame([[
                            username, 
                            hash_password(username), 
                            st.session_state.usn, 
                            st.session_state.section, 
                            score, 
                            time_taken, 
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ]], columns=["Username", "Hashed_Password", "USN", "Section", "Score", "Time_Taken", "Timestamp"])

                        # Save to professor's file
                        if os.path.exists(PROF_CSV_FILE):
                            prof_df = pd.read_csv(PROF_CSV_FILE)
                            prof_df = pd.concat([prof_df, new_row], ignore_index=True)
                        else:
                            prof_df = new_row
                        prof_df.to_csv(PROF_CSV_FILE, index=False)

                        # Save to section file
                        section_file = f"{st.session_state.section}_results.csv"
                        if os.path.exists(section_file):
                            sec_df = pd.read_csv(section_file)
                            sec_df = pd.concat([sec_df, new_row], ignore_index=True)
                        else:
                            sec_df = new_row
                        sec_df.to_csv(section_file, index=False)

                        # Update attempt count
                        if record:
                            cur.execute("UPDATE quiz_attempts SET attempt_count = attempt_count + 1 WHERE username = ?", 
                                       (username,))
                        else:
                            cur.execute("INSERT INTO quiz_attempts (username, attempt_count) VALUES (?, 1)", 
                                       (username,))
                        conn.commit()
                        conn.close()

                        # Send email confirmation
                        conn = get_db_connection()
                        email_result = conn.execute("SELECT email FROM users WHERE username = ?", (username,)).fetchone()
                        conn.close()

                        if email_result and email_result[0]:
                            try:
                                msg = EmailMessage()
                                msg.set_content(f"""Dear {username},

You have successfully submitted your quiz.
Score: {score}/{len(QUESTIONS)}
Time Taken: {time_taken} seconds

Thank you for participating.""")
                                msg['Subject'] = "Quiz Submission Confirmation"
                                msg['From'] = EMAIL_SENDER
                                msg['To'] = email_result[0]

                                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                                    server.starttls()
                                    server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                                    server.send_message(msg)
                                
                                st.success("Quiz result has been emailed to you.")
                            except Exception as e:
                                st.warning(f"Result email failed: {e}")

                        # Cleanup
                        st.session_state.quiz_submitted = True
                        st.session_state.camera_active = False
                        remove_active_student(username)
                        st.success(f"✅ Quiz submitted! Your score: {score}/{len(QUESTIONS)}")

elif choice == "Change Password":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        st.subheader("Change Password")
        username = st.session_state.username
        old_pass = st.text_input("Old Password", type="password")
        new_pass = st.text_input("New Password", type="password")
        confirm_pass = st.text_input("Confirm New Password", type="password")
        
        if st.button("Change Password"):
            if not authenticate_user(username, old_pass):
                st.error("Old password is incorrect!")
            elif new_pass != confirm_pass:
                st.error("New passwords don't match!")
            else:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT change_count FROM password_changes WHERE username = ?", (username,))
                    record = cursor.fetchone()
                    
                    if record and record[0] >= 2:
                        st.error("Password can only be changed twice.")
                    else:
                        # Update password
                        conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                     (hash_password(new_pass), username))
                        
                        # Update change count
                        if record:
                            conn.execute("UPDATE password_changes SET change_count = change_count + 1 WHERE username = ?",
                                       (username,))
                        else:
                            conn.execute("INSERT INTO password_changes (username, change_count) VALUES (?, 1)",
                                       (username,))
                        
                        conn.commit()
                        st.success("Password updated successfully!")
                except Exception as e:
                    st.error(f"Error changing password: {str(e)}")
                finally:
                    conn.close()

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
