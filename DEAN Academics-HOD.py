import streamlit as st
import os
import time
from datetime import datetime
import pandas as pd
from gtts import gTTS
from moviepy.editor import *
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Add these to your imports at the top
VIDEO_DIR = "generated_videos"
os.makedirs(VIDEO_DIR, exist_ok=True)

def generate_audio(text, output_file):
    tts = gTTS(text=text, lang='en')
    tts.save(output_file)

def create_video(question_text, output_file, audio_file):
    # Create a simple image with the question text
    width, height = 800, 600
    img = Image.new('RGB', (width, height), color=(73, 109, 137))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    # Wrap text
    lines = []
    words = question_text.split()
    current_line = []
    max_width = width - 40
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        test_width = draw.textlength(test_line, font=font)
        if test_width <= max_width:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    
    # Draw text
    y_text = 50
    for line in lines:
        draw.text((40, y_text), line, font=font, fill=(255, 255, 255))
        y_text += 30
    
    # Convert to numpy array for moviepy
    img_np = np.array(img)
    
    # Create video clip
    audio_clip = AudioFileClip(audio_file)
    img_clip = ImageClip(img_np).set_duration(audio_clip.duration)
    video_clip = img_clip.set_audio(audio_clip)
    video_clip.write_videofile(output_file, fps=24, codec='libx264')
    
    return output_file

# Modify your Take Quiz section like this:
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
                    
                    # Generate video for this question
                    audio_file = os.path.join(VIDEO_DIR, f"q{idx}_audio.mp3")
                    video_file = os.path.join(VIDEO_DIR, f"q{idx}_video.mp4")
                    
                    # Only generate if not already exists
                    if not os.path.exists(video_file):
                        generate_audio(question_text, audio_file)
                        create_video(question_text, video_file, audio_file)
                    
                    # Display the video question
                    st.markdown(f"**Question {idx+1}**")
                    st.video(video_file)
                    
                    # Display options
                    ans = st.radio("Select your answer:", 
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

                        st.success(f"Quiz submitted successfully! Your score is {score}/{len(QUESTIONS)}.")
                        st.session_state.quiz_submitted = True
                        st.session_state.camera_active = False
                        remove_active_student(username)
