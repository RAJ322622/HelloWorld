import streamlit as st
import hashlib
import time
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime
from pytz import timezone
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoTransformerBase
from streamlit_autorefresh import st_autorefresh
import av
import smtplib
from email.message import EmailMessage
import random
from gtts import gTTS
import cv2
import moviepy.editor as mp
import tempfile
import firebase_admin
from firebase_admin import credentials, firestore, storage as fb_storage
from google.cloud import storage as gcp_storage

# Initialize Firebase (for Streamlit Cloud)
if not firebase_admin._apps:
    firebase_config = json.loads(st.secrets["firebase"]["config"])
    cred = credentials.Certificate(firebase_config)
    firebase_admin.initialize_app(cred, {
        'storageBucket': st.secrets["firebase"]["storage_bucket"]
    })

db = firestore.client()
bucket = fb_storage.bucket()

# Configuration
PROF_CSV_FILE = "prof_quiz_results.csv"
STUDENT_CSV_FILE = "student_quiz_results.csv"
ACTIVE_FILE = "active_students.json"

# Create temporary directories for recordings
RECORDING_DIR = tempfile.mkdtemp()
VIDEO_DIR = tempfile.mkdtemp()
os.makedirs(RECORDING_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# Email configuration
EMAIL_SENDER = st.secrets["email"]["sender"]
EMAIL_PASSWORD = st.secrets["email"]["password"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Secret key for professor panel
PROFESSOR_SECRET_KEY = st.secrets["app"]["professor_secret_key"]

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

# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Firebase Database Operations
def register_user(username, password, role, email):
    user_data = {
        "username": username,
        "password": hash_password(password),
        "role": role,
        "email": email,
        "created_at": datetime.now(timezone('UTC')),
        "password_changes": 0,
        "quiz_attempts": 0
    }
    db.collection("users").document(username).set(user_data)

def authenticate_user(username, password):
    user_ref = db.collection("users").document(username)
    user = user_ref.get()
    if user.exists:
        return user.to_dict()["password"] == hash_password(password)
    return False

def get_user_role(username):
    user_ref = db.collection("users").document(username)
    user = user_ref.get()
    return user.to_dict()["role"] if user.exists else "student"

def get_user_email(username):
    user_ref = db.collection("users").document(username)
    user = user_ref.get()
    return user.to_dict().get("email") if user.exists else None

def update_password(username, new_password):
    user_ref = db.collection("users").document(username)
    user_ref.update({
        "password": hash_password(new_password),
        "password_changes": firestore.Increment(1)
    })

def get_password_change_count(username):
    user_ref = db.collection("users").document(username)
    user = user_ref.get()
    return user.to_dict().get("password_changes", 0) if user.exists else 0

def increment_quiz_attempt(username):
    user_ref = db.collection("users").document(username)
    user_ref.update({
        "quiz_attempts": firestore.Increment(1)
    })

def get_quiz_attempt_count(username):
    user_ref = db.collection("users").document(username)
    user = user_ref.get()
    return user.to_dict().get("quiz_attempts", 0) if user.exists else 0

# Active student tracking (using Firestore)
def add_active_student(username):
    active_ref = db.collection("active_students").document(username)
    active_ref.set({
        "timestamp": datetime.now(timezone('UTC'))
    })

def remove_active_student(username):
    db.collection("active_students").document(username).delete()

def get_live_students():
    active_students = db.collection("active_students").stream()
    return [student.id for student in active_students]

# Cloud Storage Operations
def save_results_to_cloud(filename, data):
    blob = bucket.blob(filename)
    if isinstance(data, pd.DataFrame):
        blob.upload_from_string(data.to_csv(index=False), content_type='text/csv')
    else:
        blob.upload_from_string(data)
    return blob.public_url

def get_results_from_cloud(filename):
    blob = bucket.blob(filename)
    if not blob.exists():
        return None
    content = blob.download_as_string()
    return pd.read_csv(io.StringIO(content.decode('utf-8')))

# Email functions
def send_email_otp(to_email, otp):
    try:
        msg = EmailMessage()
        msg.set_content(f"Your OTP for Secure Quiz App is: {otp}")
        msg['Subject'] = "Email Verification OTP - Secure Quiz App"
        msg['From'] = EMAIL_SENDER
        msg['To'] = to_email

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send OTP: {e}")
        return False

# Quiz Questions
QUESTIONS = [
    {"question": "🔤 Which data type is used to store a single character in C? 🎯", "options": ["char", "int", "float", "double"], "answer": "char"},
    {"question": "🔢 What is the output of 5 / 2 in C if both operands are integers? ⚡", "options": ["2.5", "2", "3", "Error"], "answer": "2"},
    {"question": "🔁 Which loop is used when the number of iterations is known? 🔄", "options": ["while", "do-while", "for", "if"], "answer": "for"},
    {"question": "📌 What is the format specifier for printing an integer in C? 🖨️", "options": ["%c", "%d", "%f", "%s"], "answer": "%d"},
    {"question": "🚀 Which operator is used for incrementing a variable by 1 in C? ➕", "options": ["+", "++", "--", "="], "answer": "++"},
]

# Video Processing
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

def generate_audio(question_text, filename):
    try:
        tts = gTTS(text=question_text, lang='en')
        tts.save(filename)
        return True
    except Exception as e:
        st.error(f"Error generating audio: {e}")
        return False

def create_video(question_text, filename, audio_file):
    width, height = 640, 480
    img = np.full((height, width, 3), (255, 223, 186), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, 10, (width, height))
    
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
        video_clip = mp.VideoFileClip(filename)
        audio_clip = mp.AudioFileClip(audio_file)
        final_video = video_clip.set_audio(audio_clip)
        final_path = filename.replace('.mp4', '_final.mp4')
        final_video.write_videofile(final_path, codec='libx264', fps=10, audio_codec='aac')
        return final_path
    except Exception as e:
        st.error(f"Error creating video: {e}")
        return filename  # Return video without audio if there's an error

# UI Starts
st.title("🎓 Secure Quiz App with Webcam 📹")
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
                st.session_state['reg_otp'] = otp
                st.session_state['reg_data'] = (username, password, role, email)
                st.success("OTP sent to your email!")
    
    otp_entered = st.text_input("Enter OTP")
    if st.button("Verify and Register"):
        if otp_entered == st.session_state.get('reg_otp'):
            username, password, role, email = st.session_state['reg_data']
            register_user(username, password, role, email)
            del st.session_state['reg_otp']
            del st.session_state['reg_data']
            st.success("Registration successful! Please login.")
        else:
            st.error("Incorrect OTP!")

elif choice == "Login":
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = get_user_role(username)
            st.success("Login successful!")
        else:
            st.error("Invalid username or password.")

    # Password reset
    st.markdown("---")
    st.subheader("Forgot Password?")
    reset_email = st.text_input("Enter your registered email")
    
    if st.button("Send Reset OTP"):
        user_ref = db.collection("users").where("email", "==", reset_email).limit(1).get()
        if user_ref:
            otp = str(random.randint(100000, 999999))
            if send_email_otp(reset_email, otp):
                st.session_state['reset_otp'] = otp
                st.session_state['reset_email'] = reset_email
                st.session_state['reset_user'] = user_ref[0].id
                st.success("OTP sent to your email!")
        else:
            st.error("Email not found!")

    if 'reset_otp' in st.session_state:
        st.markdown("---")
        st.subheader("Reset Password")
        entered_otp = st.text_input("Enter OTP")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        
        if st.button("Reset Password"):
            if entered_otp == st.session_state['reset_otp']:
                if new_password == confirm_password:
                    update_password(st.session_state['reset_user'], new_password)
                    st.success("Password updated successfully!")
                    for key in ['reset_otp', 'reset_email', 'reset_user']:
                        if key in st.session_state:
                            del st.session_state[key]
                else:
                    st.error("Passwords don't match!")
            else:
                st.error("Invalid OTP!")

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
            attempt_count = get_quiz_attempt_count(username)
            
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
                    st.markdown("<span style='color:red;'>📹 Webcam is ON</span>", unsafe_allow_html=True)
                    webrtc_streamer(
                        key="camera",
                        mode=WebRtcMode.SENDRECV,
                        media_stream_constraints={"video": True, "audio": False},
                        video_processor_factory=VideoProcessor,
                    )

                for idx, question in enumerate(QUESTIONS):
                    question_text = question["question"]
                    audio_filename = os.path.join(VIDEO_DIR, f"question_{idx}.mp3")
                    video_filename = os.path.join(VIDEO_DIR, f"question_{idx}.mp4")
                    
                    if generate_audio(question_text, audio_filename):
                        final_video_path = create_video(question_text, video_filename, audio_filename)
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

                        # Save results to Firestore
                        result_data = {
                            "username": username,
                            "usn": st.session_state.usn,
                            "section": st.session_state.section,
                            "score": score,
                            "time_taken": time_taken,
                            "timestamp": datetime.now(timezone('UTC'))
                        }
                        db.collection("quiz_results").add(result_data)
                        
                        # Also save to CSV in cloud storage
                        new_row = pd.DataFrame([[
                            username, 
                            hash_password(username), 
                            st.session_state.usn, 
                            st.session_state.section, 
                            score, 
                            time_taken, 
                            datetime.now(timezone('UTC'))
                        ]], columns=["Username", "Hashed_Password", "USN", "Section", "Score", "Time_Taken", "Timestamp"])
                        
                        save_results_to_cloud(PROF_CSV_FILE, new_row)
                        save_results_to_cloud(f"{st.session_state.section}_results.csv", new_row)

                        # Update attempts
                        increment_quiz_attempt(username)

                        # Send results via email
                        student_email = get_user_email(username)
                        if student_email:
                            try:
                                msg = EmailMessage()
                                msg.set_content(f"""Dear {username},
                                
You have successfully submitted your quiz.
Score: {score}/{len(QUESTIONS)}
Time Taken: {time_taken} seconds

Thank you for participating.""")
                                msg['Subject'] = "Quiz Submission Confirmation"
                                msg['From'] = EMAIL_SENDER
                                msg['To'] = student_email

                                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                                server.starttls()
                                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
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
        confirm_pass = st.text_input("Confirm New Password", type="password")
        
        if st.button("Change Password"):
            if not authenticate_user(username, old_pass):
                st.error("Old password is incorrect!")
            elif new_pass != confirm_pass:
                st.error("New passwords don't match!")
            elif get_password_change_count(username) >= 2:
                st.error("Password can only be changed twice.")
            else:
                update_password(username, new_pass)
                st.success("Password updated successfully!")

elif choice == "Professor Panel":
    st.subheader("👨‍🏫 Professor Access Panel")
    
    if 'prof_secret_verified' not in st.session_state:
        secret_key = st.text_input("Enter Professor Secret Key to continue", type="password")
        
        if st.button("Verify Key"):
            if secret_key == PROFESSOR_SECRET_KEY:
                st.session_state.prof_secret_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        tab1, tab2 = st.tabs(["Professor Login", "Professor Registration"])
        
        with tab1:
            if not st.session_state.get('prof_logged_in', False):
                prof_id = st.text_input("Professor ID")
                prof_pass = st.text_input("Professor Password", type="password")
                
                if st.button("Login as Professor"):
                    user_ref = db.collection("users").document(prof_id)
                    user = user_ref.get()
                    if user.exists and user.to_dict()["role"] == "professor":
                        if user.to_dict()["password"] == hash_password(prof_pass):
                            st.session_state.prof_logged_in = True
                            st.session_state.username = prof_id
                            st.session_state.role = "professor"
                            st.success(f"Welcome Professor {prof_id}!")
                            st.rerun()
                        else:
                            st.error("Invalid password!")
                    else:
                        st.error("Professor not found!")
            else:
                st.success(f"Welcome Professor {st.session_state.username}!")
                st.subheader("Student Results Management")
                
                # View all results
                results_ref = db.collection("quiz_results")
                results = [doc.to_dict() for doc in results_ref.stream()]
                
                if results:
                    df = pd.DataFrame(results)
                    
                    # Display statistics
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Students", len(df))
                    with col2:
                        avg_score = df['score'].mean()
                        st.metric("Average Score", f"{avg_score:.1f}/{len(QUESTIONS)}")
                    with col3:
                        pass_rate = (len(df[df['score'] >= len(QUESTIONS)/2]) / len(df)) * 100
                        st.metric("Pass Rate", f"{pass_rate:.1f}%")

                    # Filter and sort options
                    st.subheader("Filter Results")
                    section_filter = st.selectbox("Filter by Section", ["All"] + list(df['section'].unique()))
                    if section_filter != "All":
                        df = df[df['section'] == section_filter]
                    
                    sort_by = st.selectbox("Sort by", ["score", "time_taken", "timestamp", "section"])
                    ascending = st.checkbox("Ascending order", True)
                    df = df.sort_values(by=sort_by, ascending=ascending)
                    
                    st.dataframe(df)
                    
                    # Download option
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download Results",
                        data=csv,
                        file_name=f"quiz_results_{section_filter if section_filter != 'All' else 'all'}.csv",
                        mime="text/csv"
                    )
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
            institutional_email = st.text_input("Institutional Email")
            
            if st.button("Request Account"):
                if full_name and designation and department and institutional_email:
                    prof_id = f"PROF-{random.randint(10000, 99999)}"
                    temp_password = str(random.randint(100000, 999999))
                    
                    register_user(prof_id, temp_password, "professor", institutional_email)
                    
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
        st.header("📊 Live Monitoring Dashboard")
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
            results_ref = db.collection("quiz_results").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(5)
            recent_results = [doc.to_dict() for doc in results_ref.stream()]
            
            if recent_results:
                st.table(pd.DataFrame(recent_results))
            else:
                st.warning("No quiz submissions yet.")

elif choice == "View Recorded Video":
    st.subheader("Recorded Sessions")
    # Note: In Streamlit Cloud, recordings would need to be saved to cloud storage
    st.warning("Recording playback is not fully supported in this cloud version. For full functionality, run locally.")
