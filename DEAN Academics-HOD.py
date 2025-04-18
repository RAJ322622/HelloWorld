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

# Ensure directories exist
VIDEO_DIR = os.path.join(tempfile.gettempdir(), "videos")
RECORDING_DIR = tempfile.mkdtemp()
CSV_FILE = os.path.join(tempfile.gettempdir(), "quiz_results.csv")

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if "username" not in st.session_state:
    st.session_state["username"] = ""


# Database connection
def get_db_connection():
    conn = sqlite3.connect('quiz_app.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT)''')
    return conn

# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# User registration
def register_user(username, password):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
        st.success("Registration successful! Please login.")
    except sqlite3.IntegrityError:
        st.error("Username already exists!")
    conn.close()

# User authentication
def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.execute("SELECT password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user and user[0] == hash_password(password)

# Quiz questions
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
    {"question": "📦 What is the keyword used to dynamically allocate memory in C? 🏗️", "options": ["malloc", "new", "alloc", "create"], "answer": "malloc"},
    {"question": "🛑 Which statement is used to terminate a loop in C? 🔚", "options": ["break", "continue", "stop", "exit"], "answer": "break"},
    {"question": "🧮 What will be the value of x after x = 10 % 3; ? ⚙️", "options": ["1", "2", "3", "0"], "answer": "1"},
    {"question": "⚙️ Which operator is used to access the value stored at a memory address in C? 🎯", "options": ["&", "*", "->", "."], "answer": "*"},
    {"question": "🔍 What does the 'sizeof' operator return in C? 📏", "options": ["The size of a variable", "The value of a variable", "The address of a variable", "The type of a variable"], "answer": "The size of a variable"},
]

# Generate audio for questions
def generate_audio(question_text, filename):
    if not os.path.exists(filename):
        tts = gTTS(text=question_text, lang='en')
        tts.save(filename)

# Create video for questions
def create_video(question_text, filename, audio_file):
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

menu = ["Register", "Login", "Take Quiz", "View Recorded Video"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Register"):
        register_user(username, password)

elif choice == "Login":
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.success("Login successful!")
        else:
            st.error("Invalid credentials!")

elif choice == "Take Quiz":
    if not st.session_state["logged_in"]:
        st.warning("Please login first!")
    else:
        username = st.session_state["username"]
        score = 0
        start_time = time.time()
        answers = {}

        # Start camera monitoring
        st.subheader("📷 Live Camera Monitoring Enabled")
        try:
            webrtc_streamer(
                key="camera",
                mode=WebRtcMode.SENDRECV,
                media_stream_constraints={"video": True, "audio": False},
                video_processor_factory=VideoProcessor,
            )
        except Exception as e:
            st.warning("Live camera unavailable in this environment")
            st.info("Please use the file upload option below")
        
        video_file = st.file_uploader("Upload recording instead", type=["mp4", "mov"])
        
        for idx, question in enumerate(QUESTIONS):
            question_text = question["question"]
            audio_file = os.path.join(VIDEO_DIR, f"question_{idx}.mp3")
            video_file = os.path.join(VIDEO_DIR, f"question_{idx}.mp4")

            generate_audio(question_text, audio_file)
            video_file = create_video(question_text, video_file, audio_file)

            st.video(video_file)
            selected_option = st.radio(f"Select your answer for Question {idx+1}", question["options"], key=f"q{idx}")
            answers[question_text] = selected_option

        if st.button("Submit Quiz"):
            for question in QUESTIONS:
                if answers.get(question["question"]) == question["answer"]:
                    score += 1

            time_taken = round(time.time() - start_time, 2)
            st.write(f"Your Score: {score}")
            st.write(f"Time Taken: {time_taken} seconds")

            # Save results to CSV
            df = pd.DataFrame([[username, hash_password(username), score, time_taken, datetime.now()]], 
                              columns=["Username", "Hashed_Password", "Score", "Time_Taken", "Timestamp"])
            try:
                existing_df = pd.read_csv(CSV_FILE)
                updated_df = pd.concat([existing_df, df], ignore_index=True)
            except FileNotFoundError:
                updated_df = df
            updated_df.to_csv(CSV_FILE, index=False)

            st.success("Quiz completed and saved!")
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
    st.subheader("📷 Upload Recording Instead")
    video_file = st.file_uploader("Upload your quiz recording", type=["mp4", "mov"])

    if video_file:
        # Save the uploaded file
        with open(os.path.join(RECORDING_DIR, "uploaded_recording.mp4"), "wb") as f:
            f.write(video_file.getbuffer())
        st.success("Recording saved!")
