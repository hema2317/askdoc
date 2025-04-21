import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import openai
import jwt
from functools import wraps
import requests
from geopy.distance import geodesic
import logging
from dotenv import load_dotenv
import uuid
import PyPDF2
import io
from werkzeug.utils import secure_filename
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import dates as mdates
import calendar
import smtplib
from email.mime.text import MIMEText
from authlib.integrations.flask_client import OAuth
from PIL import Image
import pytz
import fitbit  # For wearable integration

load_dotenv()

# Initialize Flask App
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# OAuth Configuration
oauth = OAuth(app)
oauth.register(
    name='fitbit',
    client_id=os.getenv('FITBIT_CLIENT_ID'),
    client_secret=os.getenv('FITBIT_CLIENT_SECRET'),
    access_token_url='https://api.fitbit.com/oauth2/token',
    authorize_url='https://www.fitbit.com/oauth2/authorize',
    api_base_url='https://api.fitbit.com/1/user/-/',
)

# App Configuration
app.config.update({
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'GOOGLE_API_KEY': os.getenv('GOOGLE_API_KEY'),
    'UPLOAD_FOLDER': 'uploads',
    'ALLOWED_EXTENSIONS': {'png', 'jpg', 'jpeg', 'pdf'},
    'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,  # 16MB
})

# Enhanced User Database
users_db = {
    "user1": {
        "password": "pass123",
        "profile": {
            "name": "Sarah Johnson",
            "age": 32,
            "gender": "female",
            "blood_type": "A+",
            "allergies": ["penicillin"],
            "conditions": ["Type 2 Diabetes", "Hypertension"],
            "medications": {
                "Metformin": {
                    "id": str(uuid.uuid4()),
                    "dosage": "500mg",
                    "frequency": "twice daily",
                    "times": ["08:00", "20:00"],
                    "start_date": "2023-01-15",
                    "prescribing_doctor": "Dr. Smith",
                    "purpose": "Blood sugar control",
                    "notes": "Take with meals",
                    "refills": 3,
                    "last_updated": datetime.now().isoformat()
                }
            },
            "emergency_contact": {
                "name": "Michael Johnson",
                "relationship": "Spouse",
                "phone": "555-123-4567"
            },
            "wearable_data": {
                "last_sync": None,
                "heart_rate": [],
                "sleep": [],
                "steps": []
            }
        },
        "conversations": [],
        "appointments": [],
        "symptoms": [],
        "lab_results": []
    }
}

# UI Configuration (Sent to Frontend)
UI_CONFIG = {
    "theme": {
        "primary_color": "#3f51b5",
        "secondary_color": "#ff4081",
        "dark_mode": True
    },
    "features": {
        "medication_reminders": True,
        "symptom_tracking": True,
        "wearable_integration": True,
        "telehealth": True,
        "lab_analysis": True
    },
    "accessibility": {
        "font_size": "medium",
        "voice_controls": True
    }
}

# --------------------------
# HELPER FUNCTIONS
# --------------------------
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generate_medication_schedule(medications):
    """Generate visual medication schedule"""
    fig, ax = plt.subplots(figsize=(10, 4))
    days = list(calendar.day_abbr)
    
    for med_name, details in medications.items():
        times = details.get('times', [])
        for time in times:
            for day in days:
                ax.scatter(day, time, label=f"{med_name} {details['dosage']}")
    
    ax.set_title("Weekly Medication Schedule")
    ax.set_ylabel("Time of Day")
    ax.grid(True)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    buf.seek(0)
    plt.close()
    return buf

def analyze_lab_report(text):
    """Use AI to interpret lab results"""
    prompt = f"""Analyze these lab results for a {users_db['user1']['profile']['age']} year old {users_db['user1']['profile']['gender']}:
    
    Known Conditions: {', '.join(users_db['user1']['profile']['conditions'])}
    Medications: {', '.join(users_db['user1']['profile']['medications'].keys())}
    
    Lab Results:
    {text}
    
    Provide analysis in this JSON format:
    {
        "abnormal_values": [{"test": "", "value": "", "standard_range": "", "implication": ""}],
        "summary": "",
        "recommendations": [],
        "urgency": "routine|urgent|emergency"
    }"""
    
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return json.loads(response.choices[0].message.content)

# --------------------------
# AUTHENTICATION & USER
# --------------------------
@app.route('/api/auth', methods=['POST'])
def authenticate():
    """Enhanced login with UI preferences"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if username not in users_db or users_db[username]['password'] != password:
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = jwt.encode({
        'user_id': username,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, app.config['SECRET_KEY'])
    
    return jsonify({
        "token": token,
        "user_id": username,
        "profile": users_db[username]['profile'],
        "ui_config": UI_CONFIG,
        "quick_actions": [
            {"icon": "pill", "label": "Log Medication", "action": "log_med"},
            {"icon": "heart", "label": "Log Symptoms", "action": "log_symptom"},
            {"icon": "microscope", "label": "Upload Labs", "action": "upload_labs"}
        ]
    })

# --------------------------
# CORE HEALTH FEATURES
# --------------------------
@app.route('/api/medications/schedule', methods=['GET'])
@token_required
def get_medication_schedule(current_user):
    """Generate visual medication schedule"""
    buf = generate_medication_schedule(users_db[current_user]['profile']['medications'])
    return send_file(buf, mimetype='image/png')

@app.route('/api/symptoms', methods=['POST'])
@token_required
def log_symptom(current_user):
    """Track symptoms with severity and context"""
    data = request.json
    symptom = {
        "id": str(uuid.uuid4()),
        "name": data['name'],
        "severity": data.get('severity', 3),  # 1-5 scale
        "duration": data.get('duration', ''),
        "notes": data.get('notes', ''),
        "timestamp": datetime.now().isoformat(),
        "context": {
            "medications_taken": data.get('medications', []),
            "activity": data.get('activity', ''),
            "stress_level": data.get('stress_level', 3)
        }
    }
    
    users_db[current_user]['symptoms'].append(symptom)
    
    # Check for medication interactions
    meds = users_db[current_user]['profile']['medications']
    if any(med in meds for med in symptom['context']['medications_taken']):
        analysis = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{
                "role": "user",
                "content": f"Could {symptom['name']} be related to {symptom['context']['medications_taken']}? Patient also takes {list(meds.keys())}. Respond in one sentence."
            }]
        )
        symptom['ai_analysis'] = analysis.choices[0].message.content
    
    return jsonify(symptom)

# --------------------------
# WEARABLE INTEGRATION
# --------------------------
@app.route('/api/wearable/auth')
@token_required
def wearable_auth(current_user):
    """Initiate Fitbit OAuth flow"""
    redirect_uri = request.base_url + '/callback'
    return oauth.fitbit.authorize_redirect(redirect_uri)

@app.route('/api/wearable/auth/callback')
@token_required
def wearable_auth_callback(current_user):
    """Handle Fitbit OAuth callback"""
    token = oauth.fitbit.authorize_access_token()
    users_db[current_user]['profile']['wearable_data']['access_token'] = token
    return jsonify({"status": "connected"})

@app.route('/api/wearable/data')
@token_required
def get_wearable_data(current_user):
    """Sync wearable data"""
    token = users_db[current_user]['profile']['wearable_data'].get('access_token')
    if not token:
        return jsonify({"error": "Not connected"}), 400
    
    # Get heart rate data
    resp = requests.get(
        'https://api.fitbit.com/1/user/-/activities/heart/date/today/1d.json',
        headers={'Authorization': f'Bearer {token}'}
    )
    
    if resp.status_code == 200:
        users_db[current_user]['profile']['wearable_data']['heart_rate'] = resp.json()
        users_db[current_user]['profile']['wearable_data']['last_sync'] = datetime.now().isoformat()
    
    return jsonify(users_db[current_user]['profile']['wearable_data'])

# --------------------------
# AI POWERED FEATURES
# --------------------------
@app.route('/api/labs/upload', methods=['POST'])
@token_required
def upload_lab_results(current_user):
    """Process lab result PDFs"""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        
        # Read PDF
        pdf = PyPDF2.PdfReader(file)
        text = "\n".join([page.extract_text() for page in pdf.pages])
        
        # Analyze with AI
        analysis = analyze_lab_report(text)
        
        # Store results
        lab_record = {
            "id": str(uuid.uuid4()),
            "date": datetime.now().isoformat(),
            "original_text": text,
            "analysis": analysis,
            "flagged": analysis['urgency'] != "routine"
        }
        
        users_db[current_user]['lab_results'].append(lab_record)
        
        # Send urgent alerts
        if lab_record['flagged']:
            send_alert(current_user, "Urgent lab result", analysis['summary'])
        
        return jsonify(lab_record)
    
    return jsonify({"error": "Invalid file type"}), 400

@app.route('/api/ai/voice', methods=['POST'])
@token_required
def voice_analysis(current_user):
    """Process voice symptom descriptions"""
    audio_file = request.files['audio']
    
    # Transcribe
    transcript = openai.Audio.transcribe("whisper-1", audio_file)
    
    # Analyze
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{
            "role": "system",
            "content": f"Patient profile: {json.dumps(users_db[current_user]['profile'])}"
        }, {
            "role": "user",
            "content": transcript['text']
        }],
        temperature=0.3
    )
    
    return jsonify({
        "transcript": transcript['text'],
        "analysis": response.choices[0].message.content
    })

# --------------------------
# TELEHEALTH & EMERGENCY
# --------------------------
@app.route('/api/telehealth/initiate', methods=['POST'])
@token_required
def initiate_telehealth(current_user):
    """Start a telehealth session"""
    doctor_id = request.json.get('doctor_id')
    
    # Generate unique room ID (in production, use a service like Daily.co)
    room_id = f"telehealth_{current_user}_{doctor_id}_{datetime.now().timestamp()}"
    
    return jsonify({
        "room_url": f"https://telehealth.example.com/{room_id}",
        "access_token": str(uuid.uuid4())
    })

@app.route('/api/emergency/alert', methods=['POST'])
@token_required
def emergency_alert(current_user):
    """Trigger emergency protocols"""
    # Notify emergency contact
    contact = users_db[current_user]['profile']['emergency_contact']
    send_sms(contact['phone'], f"EMERGENCY ALERT for {current_user}")
    
    # Share critical info with EMS
    return jsonify({
        "status": "alert_sent",
        "shared_data": {
            "conditions": users_db[current_user]['profile']['conditions'],
            "medications": list(users_db[current_user]['profile']['medications'].keys()),
            "allergies": users_db[current_user]['profile']['allergies'],
            "last_symptoms": [s['name'] for s in users_db[current_user]['symptoms'][-3:]]
        }
    })

# --------------------------
# RUN APPLICATION
# --------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, ssl_context='adhoc')  # HTTPS for wearable OAuth
