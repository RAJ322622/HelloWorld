import streamlit as st
import sqlite3
import hashlib
import time
import pandas as pd
import os
import tempfile 
import cv2
import numpy as np
import moviepy.editor as mp
from gtts import gTTS
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
import av
from datetime import datetime
import smtplib
from email.message import EmailMessage
import random
import json
from streamlit_autorefresh import st_autorefresh

# Constants
EMAIL_SENDER = "rajkumar.k0322@gmail.com"
EMAIL_PASSWORD = "kcxf lzrq xnts xlng"  # App Password
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
PROFESSOR_SECRET_KEY = "RRCE@123"
ACTIVE_FILE = "active_students.json"
PROF_CSV_FILE = "professor_results.csv"

# Use tempfile for all directories
VIDEO_DIR = os.path.join(tempfile.gettempdir(), "videos")
RECORDING_DIR = os.path.join(tempfile.gettempdir(), "recordings")
CSV_FILE = os.path.join(tempfile.gettempdir(), "quiz_results.csv")

# Create directories safely
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

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
    try:
        conn = sqlite3.connect('quiz_app.db', check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency handling
        return conn
    except sqlite3.Error as e:
        st.error(f"Database connection error: {e}")
        raise

def migrate_database():
    conn = None
    try:
        conn = get_db_connection()
        
        # Add email column if it doesn't exist
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        
        # Add role column if it doesn't exist
        try:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student'")
        except sqlite3.OperationalError:
            pass  # Column already exists
            
        conn.commit()
        st.success("Database migration completed successfully!")
    except sqlite3.Error as e:
        pass
    finally:
        if conn:
            conn.close()

# Call this function once (you can remove it after)
migrate_database()

# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, role, email):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if username already exists
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            st.error("Username already exists!")
            return False
            
        # Insert new user
        cursor.execute(
            "INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)", 
            (username, hash_password(password), role, email)
        )

        conn.commit()
        st.success("Registration successful! Please login.")
        return True
        
    except sqlite3.Error as e:
        st.error(f"Database error during registration: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

# Authenticate user with improved error handling
def authenticate_user(username, password):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        return user[0] == hash_password(password) if user else False
    except sqlite3.Error as e:
        st.error(f"Authentication error: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

# Get user role with improved error handling
def get_user_role(username):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT role FROM users WHERE username = ?", (username,))
        role = cursor.fetchone()
        return role[0] if role else "student"
    except sqlite3.Error as e:
        st.error(f"Error getting user role: {str(e)}")
        return "student"
    finally:
        if conn:
            conn.close()

# Email functions with improved error handling
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

# Active student tracking with improved error handling
def add_active_student(username):
    try:
        data = []
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE, "r") as f:
                data = json.load(f)
        if username not in data:
            data.append(username)
            with open(ACTIVE_FILE, "w") as f:
                json.dump(data, f)
    except Exception as e:
        st.error(f"Error adding active student: {str(e)}")

def remove_active_student(username):
    try:
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE, "r") as f:
                data = json.load(f)
            data = [u for u in data if u != username]
            with open(ACTIVE_FILE, "w") as f:
                json.dump(data, f)
    except Exception as e:
        st.error(f"Error removing active student: {str(e)}")

def get_live_students():
    try:
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE, "r") as f:
                return json.load(f)
        return []
    except Exception as e:
        st.error(f"Error getting live students: {str(e)}")
        return []

# Quiz questions
QUESTIONS = [
    {"question": "🔤 Which data type is used to store a single character in C? 🎯", "options": ["char", "int", "float", "double"], "answer": "char"},
    {"question": "🔢 What is the output of 5 / 2 in C if both operands are integers? ⚡", "options": ["2.5", "2", "3", "Error"], "answer": "2"},
    {"question": "🔁 Which loop is used when the number of iterations is known? 🔄", "options": ["while", "do-while", "for", "if"], "answer": "for"},
    {"question": "📌 What is the format specifier for printing an integer in C? 🖨️", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"}]

# Generate audio for questions with error handling
def generate_audio(question_text, filename):
    try:
        if not os.path.exists(filename):
            tts = gTTS(text=question_text, lang='en')
            tts.save(filename)
    except Exception as e:
        st.error(f"Error generating audio: {str(e)}")

# Create video for questions with error handling
def create_video(question_text, filename, audio_file):
    try:
        video_path = os.path.join(VIDEO_DIR, filename)
        if os.path.exists(video_path):
            return video_path

        width, height = 640, 480
        img = np.full((height, width, 3), (255, 223, 186), dtype=np.uint8)
        font = cv2.FONT_HERSHEY_SIMPLEX

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(video_path, fourcc, 10, (width, height))

        for _ in range(50):
            img_copy = img.copy()
            text_size = cv2.getTextSize(question_text, font, 1, 2)[0]
            text_x = (width - text_size[0]) // 2
            text_y = (height + text_size[1]) // 2
            cv2.putText(img_copy, question_text, (text_x, text_y), font, 1, (0, 0, 255), 2, cv2.LINE_AA)
            out.write(img_copy)

        out.release()

        video_clip = mp.VideoFileClip(video_path)
        audio_clip = mp.AudioFileClip(audio_file)
        final_video = video_clip.set_audio(audio_clip)
        final_video.write_videofile(video_path, codec='libx264', fps=10, audio_codec='aac')

        return video_path
    except Exception as e:
        st.error(f"Error creating video: {str(e)}")
        return None

# Video Processor for Streamlit WebRTC with improved error handling
# Video Processor for Streamlit WebRTC
class VideoProcessor(VideoProcessorBase):
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

# Streamlit UI
st.title("🎥 Interactive Video Quiz 🎬")

# UI Starts
st.title("\U0001F393 Secure Quiz App with Webcam \U0001F4F5")
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "View Recorded Video"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    st.subheader("Register")
    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    
    if st.button("Send OTP"):
        if username and email and password:
            otp = str(random.randint(100000, 999999))
            if send_email_otp(email, otp):
                st.session_state['reg_otp'] = otp
                st.session_state['reg_data'] = (username, password, email)
                st.success("OTP sent to your email.")
            else:
                st.error("Failed to send OTP. Please try again.")
    
    otp_entered = st.text_input("Enter OTP")
    if st.button("Verify and Register"):
        if 'reg_otp' in st.session_state and otp_entered == st.session_state['reg_otp']:
            username, password, email = st.session_state['reg_data']
            if register_user(username, password, "student", email):  # Explicitly setting role to "student"
                # Clear registration data
                del st.session_state['reg_otp']
                del st.session_state['reg_data']
                st.success("Registration successful! Please login.")
        else:
            st.error("Incorrect OTP or OTP not requested!")

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
            conn = None
            try:
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
    # Status indicator with better visual hierarchy
    with st.container():
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown("<div style='background-color: #ff4444; padding: 10px; border-radius: 5px;'>"
                       "<span style='color: white; font-weight: bold;'>🔴 LIVE</span></div>", 
                       unsafe_allow_html=True)
        with col2:
            st.markdown("<p style='font-size: 16px; color: #333;'>"
                        "You're being actively monitored through your webcam. "
                        "Please maintain proper exam conduct.</p>", 
                        unsafe_allow_html=True)
    
    # Camera section with optimized performance
    try:
        # Performance optimization - only initialize when needed
        if 'camera_init' not in st.session_state:
            with st.spinner("Initializing secure monitoring..."):
                webrtc_ctx = webrtc_streamer(
                    key="secure_quiz_monitoring",
                    mode=WebRtcMode.SENDRECV,
                    media_stream_constraints={
                        "video": {
                            "width": {"ideal": 640},
                            "height": {"ideal": 480},
                            "frameRate": {"ideal": 15}
                        },
                        "audio": False
                    },
                    video_processor_factory=VideoProcessor,
                    async_processing=True,
                    rtc_configuration={
                        "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
                    },
                    sendback_audio=False
                )
                st.session_state.camera_init = True
                
                # Show monitoring status
                if webrtc_ctx.state.playing:
                    st.success("Monitoring active - Your exam session is being recorded")
                else:
                    st.warning("Waiting for camera connection...")
        else:
            # If already initialized, show status
            st.info("Monitoring system is active - Continue with your quiz")

    except Exception as e:
        # Enhanced fallback with multiple options
        st.warning("Webcam access limited - Alternative monitoring enabled")
        
        with st.expander("⚠️ Webcam Options"):
            st.write("""
            Your system is being monitored through alternative methods.
            You may:
            - Try refreshing the page to enable camera
            - Use a different browser (Chrome recommended)
            - Upload a recording if required
            """)
            
            # Recording upload fallback
            uploaded_file = st.file_uploader(
                "Or upload your exam recording (MP4 format)",
                type=["mp4"],
                accept_multiple_files=False
            )
            
            if uploaded_file:
                try:
                    with st.spinner("Securely uploading your recording..."):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"backup_recording_{st.session_state.username}_{timestamp}.mp4"
                        save_path = os.path.join(RECORDING_DIR, filename)
                        
                        with open(save_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        
                        st.success("Recording successfully submitted!")
                        st.session_state.recording_uploaded = True
                except Exception as upload_error:
                    st.error(f"Upload failed: {str(upload_error)}")    
                                               
                            

                    # VIDEO QUESTIONS SECTION
                    for idx, question in enumerate(QUESTIONS):
                        question_text = question["question"]
                        
                        # Generate audio and video files
                        audio_file = os.path.join(VIDEO_DIR, f"question_{idx}.mp3")
                        video_file = os.path.join(VIDEO_DIR, f"question_{idx}.mp4")
                        
                        # Generate audio if it doesn't exist
                        if not os.path.exists(audio_file):
                            tts = gTTS(text=question_text, lang='en')
                            tts.save(audio_file)
                        
                        # Create video if it doesn't exist
                        if not os.path.exists(video_file):
                            width, height = 640, 480
                            img = np.full((height, width, 3), (255, 223, 186), dtype=np.uint8)
                            font = cv2.FONT_HERSHEY_SIMPLEX
                            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                            out = cv2.VideoWriter(video_file, fourcc, 10, (width, height))
                            
                            for _ in range(50):  # 5 seconds of video at 10fps
                                img_copy = img.copy()
                                text_size = cv2.getTextSize(question_text, font, 1, 2)[0]
                                text_x = (width - text_size[0]) // 2
                                text_y = (height + text_size[1]) // 2
                                cv2.putText(img_copy, question_text, (text_x, text_y), font, 1, (0, 0, 255), 2, cv2.LINE_AA)
                                out.write(img_copy)
                            out.release()
                        
                        # Combine with audio
                        try:
                            video_clip = mp.VideoFileClip(video_file)
                            audio_clip = mp.AudioFileClip(audio_file)
                            final_video = video_clip.set_audio(audio_clip)
                            final_video_path = video_file.replace('.mp4', '_final.mp4')
                            final_video.write_videofile(final_video_path, codec='libx264', fps=10, audio_codec='aac')
                            
                            # Display the video question
                            st.video(final_video_path)
                        except Exception as e:
                            st.error(f"Error creating video for question {idx+1}: {str(e)}")
                            # Fallback to text display if video fails
                            st.markdown(f"**Q{idx+1}:** {question['question']}")
                        
                        # Display answer options
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
                            try:
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

                                # Send results via email
                                email_result = conn.execute("SELECT email FROM users WHERE username = ?", (username,)).fetchone()
                                if email_result:
                                    student_email = email_result[0]
                                    try:
                                        msg = EmailMessage()
                                        msg.set_content(f"Dear {username},\n\nYou have successfully submitted your quiz.\nScore: {score}/{len(QUESTIONS)}\nTime Taken: {time_taken} seconds\n\nThank you for participating.")
                                        msg['Subject'] = "Quiz Submission Confirmation"
                                        msg['From'] = EMAIL_SENDER
                                        msg['To'] = student_email

                                        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                                            server.starttls()
                                            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                                            server.send_message(msg)
                                    except Exception as e:
                                        st.error(f"Result email failed: {e}")

                                st.success(f"Quiz submitted successfully! Your score is {score}/{len(QUESTIONS)}.")
                                st.session_state.quiz_submitted = True
                                st.session_state.camera_active = False
                                remove_active_student(username)
                            except Exception as e:
                                st.error(f"Error saving results: {str(e)}")
            except sqlite3.Error as e:
                st.error(f"Database error: {str(e)}")
            finally:
                if conn:
                    conn.close()


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
