import os
import pickle
import streamlit as st
import cv2
import numpy as np
from PIL import Image
import face_recognition
from datetime import datetime
import hashlib

# Simulated fingerprint authentication (in a real app, you'd use a fingerprint scanner SDK)
class FingerprintAuth:
    def __init__(self):
        self.fingerprint_db = {}
        self.load_fingerprints()
    
    def load_fingerprints(self):
        """Load fingerprint templates from disk"""
        if not os.path.exists('fingerprint_db'):
            os.makedirs('fingerprint_db')
        
        for file in os.listdir('fingerprint_db'):
            if file.endswith('.fp'):
                user_id = file[:-3]
                with open(os.path.join('fingerprint_db', file), 'rb') as f:
                    self.fingerprint_db[user_id] = pickle.load(f)
    
    def save_fingerprint(self, user_id, fingerprint_data):
        """Save a fingerprint template"""
        with open(f'fingerprint_db/{user_id}.fp', 'wb') as f:
            pickle.dump(fingerprint_data, f)
        self.fingerprint_db[user_id] = fingerprint_data
    
    def verify_fingerprint(self, user_id, input_data):
        """Verify a fingerprint against stored template"""
        if user_id not in self.fingerprint_db:
            return False
        
        # In a real app, you'd use proper fingerprint matching algorithm
        # Here we just simulate with a simple hash comparison
        stored_hash = hashlib.sha256(pickle.dumps(self.fingerprint_db[user_id])).hexdigest()
        input_hash = hashlib.sha256(pickle.dumps(input_data)).hexdigest()
        
        return stored_hash == input_hash

class FaceAuth:
    def __init__(self):
        self.known_face_encodings = []
        self.known_face_names = []
        self.load_known_faces()
    
    def load_known_faces(self):
        """Load known face encodings from disk"""
        if not os.path.exists('known_faces'):
            os.makedirs('known_faces')
        
        for file in os.listdir('known_faces'):
            if file.endswith('.pkl'):
                user_id = file[:-4]
                with open(os.path.join('known_faces', file), 'rb') as f:
                    encoding = pickle.load(f)
                self.known_face_encodings.append(encoding)
                self.known_face_names.append(user_id)
    
    def save_face_encoding(self, user_id, encoding):
        """Save a face encoding"""
        with open(f'known_faces/{user_id}.pkl', 'wb') as f:
            pickle.dump(encoding, f)
        self.known_face_encodings.append(encoding)
        self.known_face_names.append(user_id)
    
    def recognize_face(self, frame):
        """Recognize faces in a frame"""
        # Convert to RGB (face_recognition uses RGB)
        rgb_frame = frame[:, :, ::-1]
        
        # Find all face locations and encodings
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        
        recognized_users = []
        
        for face_encoding in face_encodings:
            # Compare with known faces
            matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=0.5)
            name = "Unknown"
            
            # Use the known face with the smallest distance to the new face
            face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            best_match_index = np.argmin(face_distances)
            
            if matches[best_match_index]:
                name = self.known_face_names[best_match_index]
                recognized_users.append(name)
        
        return recognized_users, face_locations

# Initialize authentication systems
fingerprint_auth = FingerprintAuth()
face_auth = FaceAuth()

def capture_fingerprint():
    """Simulate fingerprint capture"""
    # In a real app, this would interface with a fingerprint scanner
    st.warning("In a real application, this would capture a fingerprint from a scanner.")
    return np.random.rand(100)  # Simulated fingerprint data

def capture_face():
    """Capture face from webcam"""
    st.write("Please look at the camera for face registration")
    
    cap = cv2.VideoCapture(0)
    img_placeholder = st.empty()
    captured_image = None
    
    while True:
        ret, frame = cap.read()
        if not ret:
            st.error("Failed to capture from camera")
            break
        
        # Display the frame
        img_placeholder.image(frame, channels="BGR", use_column_width=True)
        
        # Check for capture command
        if st.button("Capture Face", key="capture_face"):
            captured_image = frame
            break
    
    cap.release()
    img_placeholder.empty()
    
    if captured_image is not None:
        # Convert to RGB and get face encoding
        rgb_image = captured_image[:, :, ::-1]
        face_encodings = face_recognition.face_encodings(rgb_image)
        
        if len(face_encodings) > 0:
            return face_encodings[0]
        else:
            st.error("No face detected in the captured image")
            return None
    return None

def register_user():
    """Register a new user with fingerprint and face"""
    st.header("User Registration")
    
    user_id = st.text_input("Enter User ID")
    if not user_id:
        return
    
    if user_id in fingerprint_auth.fingerprint_db:
        st.error("User ID already exists")
        return
    
    # Capture fingerprint
    st.subheader("Step 1: Fingerprint Registration")
    if st.button("Capture Fingerprint"):
        fingerprint_data = capture_fingerprint()
        fingerprint_auth.save_fingerprint(user_id, fingerprint_data)
        st.success("Fingerprint registered successfully!")
    
    # Capture face
    st.subheader("Step 2: Face Registration")
    if st.button("Capture Face"):
        face_encoding = capture_face()
        if face_encoding is not None:
            face_auth.save_face_encoding(user_id, face_encoding)
            st.success("Face registered successfully!")

def authenticate_user():
    """Authenticate user with fingerprint and face"""
    st.header("User Authentication")
    
    # Fingerprint authentication
    st.subheader("Step 1: Fingerprint Authentication")
    user_id = st.text_input("Enter your User ID for authentication")
    
    if not user_id:
        return
    
    if user_id not in fingerprint_auth.fingerprint_db:
        st.error("User ID not found")
        return
    
    if st.button("Scan Fingerprint"):
        input_fingerprint = capture_fingerprint()
        if fingerprint_auth.verify_fingerprint(user_id, input_fingerprint):
            st.success("Fingerprint verified!")
            
            # Face authentication
            st.subheader("Step 2: Face Authentication")
            st.write("Please look at the camera for face verification")
            
            cap = cv2.VideoCapture(0)
            img_placeholder = st.empty()
            authenticated = False
            
            for _ in range(30):  # Check for 30 frames
                ret, frame = cap.read()
                if not ret:
                    continue
                
                # Display the frame
                img_placeholder.image(frame, channels="BGR", use_column_width=True)
                
                # Recognize faces
                recognized_users, face_locations = face_auth.recognize_face(frame)
                
                if user_id in recognized_users:
                    authenticated = True
                    break
            
            cap.release()
            img_placeholder.empty()
            
            if authenticated:
                st.success(f"Face verified! Welcome, {user_id}")
                log_authentication(user_id, True)
            else:
                st.error("Face verification failed")
                log_authentication(user_id, False)
        else:
            st.error("Fingerprint verification failed")
            log_authentication(user_id, False)

def log_authentication(user_id, success):
    """Log authentication attempts"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    
    with open("auth_log.txt", "a") as f:
        f.write(f"{timestamp} - {user_id} - {status}\n")

def view_logs():
    """View authentication logs"""
    st.header("Authentication Logs")
    
    if os.path.exists("auth_log.txt"):
        with open("auth_log.txt", "r") as f:
            logs = f.readlines()
        
        if logs:
            st.text_area("Logs", "\n".join(logs), height=300)
        else:
            st.info("No logs available")
    else:
        st.info("No logs available")

def main():
    st.title("Biometric Authentication System")
    st.write("Combine fingerprint and face recognition for secure authentication")
    
    menu = ["Home", "Register User", "Authenticate User", "View Logs"]
    choice = st.sidebar.selectbox("Menu", menu)
    
    if choice == "Home":
        st.subheader("Home")
        st.write("""
        This system provides two-factor authentication using:
        - Fingerprint recognition
        - Facial recognition
        
        Please use the menu to navigate to registration or authentication.
        """)
        
        # Display registered users
        if fingerprint_auth.fingerprint_db:
            st.subheader("Registered Users")
            st.write(list(fingerprint_auth.fingerprint_db.keys()))
    
    elif choice == "Register User":
        register_user()
    
    elif choice == "Authenticate User":
        authenticate_user()
    
    elif choice == "View Logs":
        view_logs()

if __name__ == "__main__":
    main()
