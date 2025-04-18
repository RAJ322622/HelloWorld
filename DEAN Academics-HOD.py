# Corrected imports
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import sqlite3
import hashlib
import time
import pandas as pd
import numpy as np
import os
import tempfile
import json
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoTransformerBase
import av
import smtplib
from email.message import EmailMessage
import random
from gtts import gTTS
import cv2
import moviepy.editor as mp

def send_email_otp(to_email, otp):
    try:
        msg = EmailMessage()
        msg.set_content(f"Your OTP for Secure Quiz App is: {otp}")
        msg['Subject'] = "Email Verification OTP - Secure Quiz App"
        msg['From'] = "rajkumar.k0322@gmail.com"
        msg['To'] = to_email

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login("rajkumar.k0322@gmail.com", "kcxf lzrq xnts xlng")  # App Password
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send OTP: {e}")
        return False

# Configuration
# Ensure directories exist
VIDEO_DIR = os.path.join(tempfile.gettempdir(), "videos")
RECORDING_DIR = tempfile.mkdtemp()
CSV_FILE = os.path.join(tempfile.gettempdir(), "quiz_results.cs")
ACTIVE_FILE = "active_students.json"
# Create directories if they don't exist
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

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

    # Create 'users' table if it doesn't exist
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT,
                        role TEXT DEFAULT 'student',
                        email TEXT)''')

    # Create other tables
    conn.execute('''CREATE TABLE IF NOT EXISTS password_changes (
                        username TEXT PRIMARY KEY,
                        change_count INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
                        username TEXT PRIMARY KEY,
                        attempt_count INTEGER DEFAULT 0)''')

    return conn

# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Register user
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

# Authenticate user
def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return user[0] == hash_password(password)
    return False

# Get user role
def get_user_role(username):
    conn = get_db_connection()
    cursor = conn.execute("SELECT role FROM users WHERE username = ?", (username,))
    role = cursor.fetchone()
    conn.close()
    return role[0] if role else "student"

# Active student tracking
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

# Replace your existing QUESTIONS list with this new one
QUESTIONS = [
    {"question": "🔤 Which data type is used to store a single character in C? 🎯", "options": ["char", "int", "float", "double"], "answer": "char"},
    {"question": "🔢 What is the output of 5 / 2 in C if both operands are integers? ⚡", "options": ["2.5", "2", "3", "Error"], "answer": "2"},
    {"question": "🔁 Which loop is used when the number of iterations is known? 🔄", "options": ["while", "do-while", "for", "if"], "answer": "for"},
    {"question": "📌 What is the format specifier for printing an integer in C? 🖨️", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "🚀 Which operator is used for incrementing a variable by 1 in C? ➕", "options": ["+", "++", "--", "="], "answer": "++"},
    {"question": "📂 Which header file is required for input and output operations in C? 🖥️", "options": ["stdlib.h", "stdio.h", "string.h", "math.h"], "answer": "stdio.h"},
    {"question": "🔄 What is the default return type of a function in C if not specified? 📌", "options": ["void", "int", "float", "char"], "answer": "int"},
    {"question": "🎭 What is the output of printf(\"%d\", sizeof(int)); on a 32-bit system? 📏", "options": ["2", "4", "8", "16"], "answer": "4"},
    {"question": "💡 What is the correct syntax for defining a pointer in C? 🎯", "options": ["int ptr;", "int* ptr;", "pointer int ptr;", "ptr int;"], "answer": "int* ptr;"},
    {"question": "🔠 Which function is used to copy strings in C? 📋", "options": ["strcpy", "strcat", "strcmp", "strlen"], "answer": "strcpy"},
    {"question": "📦 What is the keyword used to dynamically allocate memory in C? �️", "options": ["malloc", "new", "alloc", "create"], "answer": "malloc"},
    {"question": "🛑 Which statement is used to terminate a loop in C? 🔚", "options": ["break", "continue", "stop", "exit"], "answer": "break"},
    {"question": "🧮 What will be the value of x after x = 10 % 3; ? ⚙️", "options": ["1", "2", "3", "0"], "answer": "1"},
    {"question": "⚙️ Which operator is used to access the value stored at a memory address in C? 🎯", "options": ["&", "*", "->", "."], "answer": "*"},
    {"question": "🔍 What does the 'sizeof' operator return in C? 📏", "options": ["The size of a variable", "The value of a variable", "The address of a variable", "The type of a variable"], "answer": "The size of a variable"},
]

# Add these functions with your other utility functions
def generate_audio(question_text, filename):
    """Generate audio file and save to the correct path"""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Generate and save audio
        tts = gTTS(text=question_text, lang='en')
        tts.save(filename)
        return True
    except Exception as e:
        st.error(f"Error generating audio: {e}")
        return False

def create_video(question_text, filename, audio_file):
    # Ensure the VIDEO_DIR exists
    os.makedirs(VIDEO_DIR, exist_ok=True)
    
    # Create full paths
    video_path = os.path.join(VIDEO_DIR, filename)
    audio_path = os.path.join(VIDEO_DIR, audio_file)
    
    # Generate audio if it doesn't exist
    if not os.path.exists(audio_path):
        tts = gTTS(text=question_text, lang='en')
        tts.save(audio_path)
    
    # Create video with OpenCV if it doesn't exist
    if not os.path.exists(video_path):
        width, height = 640, 480
        img = np.full((height, width, 3), (255, 223, 186), dtype=np.uint8)
        font = cv2.FONT_HERSHEY_SIMPLEX
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(video_path, fourcc, 10, (width, height))
        
        for _ in range(50):  # 5 seconds of video at 10fps
            img_copy = img.copy()
            text_size = cv2.getTextSize(question_text, font, 1, 2)[0]
            text_x = (width - text_size[0]) // 2
            text_y = (height + text_size[1]) // 2
            cv2.putText(img_copy, question_text, (text_x, text_y), font, 1, (0, 0, 255), 2, cv2.LINE_AA)
            out.write(img_copy)
        out.release()
    
    # Combine with audio using moviepy
    try:
        video_clip = mp.VideoFileClip(video_path)
        audio_clip = mp.AudioFileClip(audio_path)
        final_video = video_clip.set_audio(audio_clip)
        final_path = video_path.replace('.mp4', '_final.mp4')
        final_video.write_videofile(final_path, codec='libx264', fps=10, audio_codec='aac')
        return final_path
    except Exception as e:
        st.error(f"Error creating video: {e}")
        return video_path  # Return video without audio if there's an error

# Replace your existing VideoProcessor class with this one
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.recording = True
        self.container = av.open(os.path.join(RECORDING_DIR, "quiz_recording.mp4"), mode="w")
        self.stream = self.container.add_stream("h264")

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        if self.recording:
            packet = self.stream.encode(frame)
            if packet:
                self.container.mux(packet)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def close(self):
        self.container.close()

# UI Starts
st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
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
            # Clear registration data
            del st.session_state['reg_otp']
            del st.session_state['reg_data']
        else:
            st.error("Incorrect OTP!")

elif choice == "Login":
    st.subheader("Login")

    # Initialize login form fields in session state if they don't exist
    if 'login_username' not in st.session_state:
        st.session_state.login_username = ""
    if 'login_password' not in st.session_state:
        st.session_state.login_password = ""

    # ---------- Login Form ----------
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

    # ---------- Forgot Password ----------
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

    # ---------- Reset Password ----------
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
                        # Update password in users table
                        conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                  (hash_password(new_password), st.session_state['reset_user']))
                        
                        # Verify the password was updated
                        cursor = conn.execute("SELECT password FROM users WHERE username = ?",
                                             (st.session_state['reset_user'],))
                        updated_password = cursor.fetchone()[0]
                        
                        if updated_password == hash_password(new_password):
                            # Update password change count
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
                            
                            # Store credentials for auto-fill (without modifying widget state directly)
                            st.session_state.login_username = st.session_state['reset_user']
                            st.session_state.login_password = new_password
                            
                            st.success("Password reset successfully! Your credentials have been filled below. Click Login to continue.")
                            
                            # Clear reset-related session state
                            for key in ['reset_otp', 'reset_email', 'reset_user']:
                                if key in st.session_state:
                                    del st.session_state[key]
                            
                            # Rerun to update the UI with filled credentials
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

                for idx, question in enumerate(QUESTIONS):
                  question_text = question["question"]
                  
                  # Create filenames with proper paths
                  audio_filename = os.path.join(VIDEO_DIR, f"question_{idx}.mp3")
                  video_filename = os.path.join(VIDEO_DIR, f"question_{idx}.mp4")
                  
                  # Generate content
                  if not generate_audio(question_text, audio_filename):
                      continue  # Skip if audio generation fails
                      
                  final_video_path = create_video(question_text, video_filename, audio_filename)
                  
                  if not os.path.exists(final_video_path):
                      st.error(f"Failed to create video for question {idx+1}")
                      continue
                  
                  # Display question
                  st.video(final_video_path)
                  st.markdown(f"**Q{idx+1}:** {question['question']}")
                  ans = st.radio("Select your answer:", question['options'], key=f"q{idx}", index=None)
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

                        # Append to professor's CSV
                        if os.path.exists(PROF_CSV_FILE):
                            prof_df = pd.read_csv(PROF_CSV_FILE)
                            prof_df = pd.concat([prof_df, new_row], ignore_index=True)
                        else:
                            prof_df = new_row
                        prof_df.to_csv(PROF_CSV_FILE, index=False)

                        # Save to student section-wise CSV
                        section_file = f"{st.session_state.section}_results.csv"
                        if os.path.exists(section_file):
                            sec_df = pd.read_csv(section_file)
                            sec_df = pd.concat([sec_df, new_row], ignore_index=True)
                        else:
                            sec_df = new_row
                        sec_df.to_csv(section_file, index=False)

                        # Update attempts
                        if record:
                            cur.execute("UPDATE quiz_attempts SET attempt_count = attempt_count + 1 WHERE username = ?", (username,))
                        else:
                            cur.execute("INSERT INTO quiz_attempts (username, attempt_count) VALUES (?, ?)", (username, 1))
                        conn.commit()
                        conn.close()

                        # Send results via email
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


elif choice == "Change Password":
    if not st.session_state.logged_in:
        st.warning("Please login first!")
    else:
        username = st.session_state.username
        old_pass = st.text_input("Old Password", type="password")
        new_pass = st.text_input("New Password", type="password")
        if st.button("Change Password"):
            if not authenticate_user(username, old_pass):
                st.error("Old password is incorrect!")
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT change_count FROM password_changes WHERE username = ?", (username,))
                record = cursor.fetchone()
                if record and record[0] >= 2:
                    st.error("Password can only be changed twice.")
                else:
                    conn.execute("UPDATE users SET password = ? WHERE username = ?",
                                 (hash_password(new_pass), username))
                    if record:
                        conn.execute("UPDATE password_changes SET change_count = change_count + 1 WHERE username = ?",
                                     (username,))
                    else:
                        conn.execute("INSERT INTO password_changes (username, change_count) VALUES (?, 1)",
                                     (username,))
                    conn.commit()
                    st.success("Password updated successfully.")
                conn.close()


elif choice == "Professor Panel":
    st.subheader("\U0001F9D1‍\U0001F3EB Professor Access Panel")
    
    # First check for secret key
    if 'prof_secret_verified' not in st.session_state:
        secret_key = st.text_input("Enter Professor Secret Key to continue", type="password")
        
        if st.button("Verify Key"):
            if secret_key == PROFESSOR_SECRET_KEY:
                st.session_state.prof_secret_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        # After secret key verification, show login/registration tabs
        tab1, tab2 = st.tabs(["Professor Login", "Professor Registration"])
        
        with tab1:  # Login tab
            if not st.session_state.get('prof_logged_in', False):
                prof_id = st.text_input("Professor ID")
                prof_pass = st.text_input("Professor Password", type="password")
                
                if st.button("Login as Professor"):
                    conn = get_db_connection()
                    cursor = conn.execute("SELECT password, role, email FROM users WHERE username = ? AND role = 'professor'", 
                                        (prof_id,))
                    prof_data = cursor.fetchone()
                    conn.close()
                    
                    if prof_data and prof_data[0] == hash_password(prof_pass):
                        st.session_state.prof_logged_in = True
                        st.session_state.username = prof_id
                        st.session_state.role = "professor"
                        st.success(f"Welcome Professor {prof_id}!")
                        os.makedirs(st.session_state.prof_dir, exist_ok=True)
                        st.rerun()
                    else:
                        st.error("Invalid Professor credentials")
            else:
                # Show professor dashboard after successful login
                st.success(f"Welcome Professor {st.session_state.username}!")
                st.subheader("Student Results Management")
                
                # View results section
                result_files = []
                if os.path.exists(PROF_CSV_FILE):
                    result_files.append(PROF_CSV_FILE)
                
                # Check for section-wise files
                section_files = [f for f in os.listdir() if f.endswith("_results.csv")]
                result_files.extend(section_files)
                
                if result_files:
                    selected_file = st.selectbox("Select results file", result_files)
                    try:
                        df = pd.read_csv(selected_file)
                        
                        # Display statistics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Students", len(df))
                        with col2:
                            avg_score = df['Score'].mean()
                            st.metric("Average Score", f"{avg_score:.1f}/{len(QUESTIONS)}")
                        with col3:
                            pass_rate = (len(df[df['Score'] >= len(QUESTIONS)/2]) / len(df)) * 100
                            st.metric("Pass Rate", f"{pass_rate:.1f}%")

                        # Show full results
                        st.markdown("### Detailed Results")
                        sort_by = st.selectbox("Sort by", ["Score", "Time_Taken", "Timestamp", "Section"])
                        ascending = st.checkbox("Ascending order", True)
                        sorted_df = df.sort_values(by=sort_by, ascending=ascending)
                        st.dataframe(sorted_df)
                        
                        # Download option
                        st.download_button(
                            label="Download Results",
                            data=sorted_df.to_csv(index=False),
                            file_name=f"sorted_{selected_file}",
                            mime="text/csv"
                        )
                        
                    except Exception as e:
                        st.error(f"Error loading results: {e}")
                else:
                    st.warning("No results available yet.")
                
                # Logout button
                if st.button("Logout"):
                    st.session_state.prof_logged_in = False
                    st.session_state.username = ""
                    st.session_state.role = ""
                    st.rerun()
        
        with tab2:  # Registration tab
            st.subheader("Professor Registration")
            st.warning("Professor accounts require verification.")
            
            # Registration form
            full_name = st.text_input("Full Name")
            designation = st.text_input("Designation")
            department = st.selectbox("Department", ["CSE", "ISE", "ECE", "EEE", "MECH", "CIVIL"])
            institutional_email = st.text_input("Institutional Email")
            
            if st.button("Request Account"):
                if full_name and designation and department and institutional_email:
                    # Generate credentials
                    prof_id = f"PROF-{random.randint(10000, 99999)}"
                    temp_password = str(random.randint(100000, 999999))
                    
                    # Register professor
                    conn = get_db_connection()
                    try:
                        conn.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",
                                    (prof_id, hash_password(temp_password), "professor", institutional_email))
                        conn.commit()
                        
                        # Create directory
                        os.makedirs(f"professor_data/{prof_id}", exist_ok=True)
                        
                        # Send credentials
                        try:
                            msg = EmailMessage()
                            msg.set_content(f"""Dear {full_name},

Your professor account has been created:

Username: {prof_id}
Password: {temp_password}

Please login and change your password immediately.

Regards,
Quiz App Team""")
                            msg['Subject'] = "Professor Account Credentials"
                            msg['From'] = EMAIL_SENDER
                            msg['To'] = institutional_email

                            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                            server.starttls()
                            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                            server.send_message(msg)
                            server.quit()
                            
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
    if not st.session_state.get('prof_verified', False):
        secret_key = st.text_input("Enter Professor Secret Key to continue", type="password")
        
        if st.button("Verify Key"):
            if secret_key == PROFESSOR_SECRET_KEY:
                st.session_state.prof_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        st_autorefresh(interval=10000, key="monitor_refresh")
        st.header("\U0001F4E1 Live Monitoring Dashboard")
        st.info("Monitoring students currently taking the quiz")
        
        live_students = get_live_students()
        if not live_students:
            st.write("No active students at the moment.")
        else:
            st.write(f"Active students ({len(live_students)}):")
            for student in live_students:
                st.write(f"- {student}")
                
            st.markdown("---")
            st.markdown("### Recent Quiz Submissions")
            if os.path.exists(PROF_CSV_FILE):
                df = pd.read_csv(PROF_CSV_FILE)
                recent_submissions = df.sort_values("Timestamp", ascending=False).head(5)
                st.dataframe(recent_submissions)
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
