import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file, send_from_directory
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
import numpy as np
from io import BytesIO
import base64

# Load environment variables
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
    'TWILIO_ACCOUNT_SID': os.getenv('TWILIO_SID'),
    'TWILIO_AUTH_TOKEN': os.getenv('TWILIO_TOKEN'),
    'TWILIO_PHONE': os.getenv('TWILIO_PHONE')
})

# Database Simulation (In production, use PostgreSQL/MongoDB)
class HealthDatabase:
    def __init__(self):
        self.users = {
            "user1": {
                "password": "pass123",
                "profile": self._create_sample_profile(),
                "conversations": [],
                "appointments": [],
                "symptoms": [],
                "lab_results": [],
                "notifications": []
            }
        }
        self.doctor_cache = {}
        self.medication_history = []
        self.conversation_logs = []

    def _create_sample_profile(self):
        return {
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
                "phone": os.getenv('TEST_PHONE')
            },
            "wearable_data": {
                "last_sync": None,
                "heart_rate": [],
                "sleep": [],
                "steps": []
            },
            "settings": {
                "dark_mode": True,
                "medication_reminders": True,
                "emergency_alerts": True
            }
        }

db = HealthDatabase()

# --------------------------
# HELPER FUNCTIONS
# --------------------------
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generate_token(user_id):
    return jwt.encode(
        {'user_id': user_id, 'exp': datetime.utcnow() + timedelta(hours=24)},
        app.config['SECRET_KEY'],
        algorithm='HS256'
    )

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            data = jwt.decode(token.split()[1], app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['user_id']
        except Exception as e:
            logging.error(f"Token error: {str(e)}")
            return jsonify({"error": "Invalid token"}), 401

        return f(current_user, *args, **kwargs)
    return decorated

def generate_medication_schedule(medications):
    """Generate visual medication schedule as PNG"""
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6))
    days = list(calendar.day_abbr)
    colors = plt.cm.viridis(np.linspace(0, 1, len(medications)))
    
    for (med_name, details), color in zip(medications.items(), colors):
        times = details.get('times', [])
        for time in times:
            for day in days:
                hour, minute = map(int, time.split(':'))
                time_num = hour + minute/60
                ax.scatter(day, time_num, color=color, s=200, label=f"{med_name} {details['dosage']}")
    
    ax.set_title("Weekly Medication Schedule", pad=20)
    ax.set_ylabel("Time of Day", labelpad=15)
    ax.yaxis.set_major_formatter(lambda x, pos: f"{int(x)}:{int((x%1)*60):02d}")
    ax.grid(True, alpha=0.3)
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def analyze_lab_report(text):
    """Use AI to interpret lab results"""
    prompt = f"""Analyze these lab results for a {db.users['user1']['profile']['age']} year old {db.users['user1']['profile']['gender']}:
    
    Known Conditions: {', '.join(db.users['user1']['profile']['conditions'])}
    Medications: {', '.join(db.users['user1']['profile']['medications'].keys())}
    
    Lab Results:
    {text}
    
    Provide analysis in this JSON format:
    {
        "abnormal_values": [{"test": "", "value": "", "standard_range": "", "implication": ""}],
        "summary": "",
        "recommendations": [],
        "urgency": "routine|urgent|emergency",
        "related_conditions": []
    }"""
    
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return json.loads(response.choices[0].message.content)

def send_sms(to, body):
    """Send SMS using Twilio"""
    if not app.config['TWILIO_ACCOUNT_SID']:
        logging.warning("Twilio not configured - simulated SMS sent")
        return True
        
    from twilio.rest import Client
    client = Client(app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN'])
    
    try:
        message = client.messages.create(
            body=body,
            from_=app.config['TWILIO_PHONE'],
            to=to
        )
        return True
    except Exception as e:
        logging.error(f"SMS send failed: {str(e)}")
        return False

# --------------------------
# API ROUTES
# --------------------------
@app.route('/api/auth', methods=['POST'])
def authenticate():
    """Enhanced login with UI preferences"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if username not in db.users or db.users[username]['password'] != password:
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = generate_token(username)
    
    return jsonify({
        "token": token,
        "user_id": username,
        "profile": db.users[username]['profile'],
        "ui_config": {
            "theme": {
                "primary_color": "#3f51b5",
                "secondary_color": "#ff4081",
                "dark_mode": db.users[username]['profile']['settings']['dark_mode']
            },
            "quick_actions": [
                {"icon": "pill", "label": "Log Medication", "action": "log_med"},
                {"icon": "heart", "label": "Log Symptoms", "action": "log_symptom"},
                {"icon": "microscope", "label": "Upload Labs", "action": "upload_labs"}
            ]
        }
    })

@app.route('/api/medications', methods=['GET', 'POST', 'PUT', 'DELETE'])
@token_required
def manage_medications(current_user):
    if request.method == 'GET':
        return jsonify({
            "medications": db.users[current_user]['profile']['medications'],
            "schedule_image_url": f"/api/medications/schedule?token={request.headers.get('Authorization').split()[1]}"
        })
    
    elif request.method == 'POST':
        data = request.json
        med_name = data.get('name')
        if not med_name:
            return jsonify({"error": "Medication name is required"}), 400
        
        med_id = str(uuid.uuid4())
        medications = db.users[current_user]['profile']['medications']
        medications[med_name] = {
            "id": med_id,
            "dosage": data.get('dosage', ''),
            "frequency": data.get('frequency', ''),
            "times": data.get('times', []),
            "start_date": data.get('start_date', ''),
            "prescribing_doctor": data.get('prescribing_doctor', ''),
            "purpose": data.get('purpose', ''),
            "notes": data.get('notes', ''),
            "refills": data.get('refills', 0),
            "last_updated": datetime.now().isoformat()
        }
        
        db.medication_history.append({
            "user_id": current_user,
            "action": "ADD",
            "medication": medications[med_name],
            "timestamp": datetime.now().isoformat()
        })
        
        return jsonify({
            "message": "Medication added successfully",
            "medications": medications
        })
    
    elif request.method == 'PUT':
        data = request.json
        med_name = data.get('name')
        if not med_name:
            return jsonify({"error": "Medication name is required"}), 400
        
        medications = db.users[current_user]['profile']['medications']
        if med_name not in medications:
            return jsonify({"error": "Medication not found"}), 404
        
        # Update medication details
        for key, value in data.items():
            if key != 'name' and key in medications[med_name]:
                medications[med_name][key] = value
        
        medications[med_name]['last_updated'] = datetime.now().isoformat()
        
        db.medication_history.append({
            "user_id": current_user,
            "action": "UPDATE",
            "medication": medications[med_name],
            "timestamp": datetime.now().isoformat()
        })
        
        return jsonify({
            "message": "Medication updated successfully",
            "medications": medications
        })
    
    elif request.method == 'DELETE':
        data = request.json
        med_name = data.get('name')
        if not med_name:
            return jsonify({"error": "Medication name is required"}), 400
        
        medications = db.users[current_user]['profile']['medications']
        if med_name in medications:
            deleted_med = medications[med_name]
            del medications[med_name]
            
            db.medication_history.append({
                "user_id": current_user,
                "action": "DELETE",
                "medication": deleted_med,
                "timestamp": datetime.now().isoformat()
            })
            
            return jsonify({
                "message": "Medication removed successfully",
                "medications": medications
            })
        else:
            return jsonify({"error": "Medication not found"}), 404

@app.route('/api/medications/schedule', methods=['GET'])
@token_required
def get_medication_schedule(current_user):
    """Generate visual medication schedule"""
    medications = db.users[current_user]['profile']['medications']
    buf = generate_medication_schedule(medications)
    return send_file(buf, mimetype='image/png')

@app.route('/api/symptoms', methods=['GET', 'POST'])
@token_required
def manage_symptoms(current_user):
    if request.method == 'GET':
        return jsonify({
            "symptoms": db.users[current_user]['symptoms']
        })
    
    elif request.method == 'POST':
        data = request.json
        symptom = {
            "id": str(uuid.uuid4()),
            "name": data['name'],
            "severity": data.get('severity', 3),
            "duration": data.get('duration', ''),
            "notes": data.get('notes', ''),
            "timestamp": datetime.now().isoformat(),
            "context": {
                "medications_taken": data.get('medications', []),
                "activity": data.get('activity', ''),
                "stress_level": data.get('stress_level', 3)
            }
        }
        
        # Check for medication interactions
        meds = db.users[current_user]['profile']['medications']
        if any(med in meds for med in symptom['context']['medications_taken']):
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{
                    "role": "user",
                    "content": f"Could {symptom['name']} be related to {symptom['context']['medications_taken']}? Patient also takes {list(meds.keys())}. Respond in one sentence."
                }],
                temperature=0.3
            )
            symptom['ai_analysis'] = response.choices[0].message.content
        
        db.users[current_user]['symptoms'].append(symptom)
        
        # Check for emergency symptoms
        emergency_keywords = ['chest pain', 'difficulty breathing', 'severe bleeding']
        if any(keyword in symptom['name'].lower() for keyword in emergency_keywords):
            send_sms(
                db.users[current_user]['profile']['emergency_contact']['phone'],
                f"EMERGENCY: {current_user} reported {symptom['name']} at {datetime.now().strftime('%H:%M')}"
            )
        
        return jsonify(symptom)

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
        
        db.users[current_user]['lab_results'].append(lab_record)
        
        # Send urgent alerts
        if lab_record['flagged']:
            send_sms(
                db.users[current_user]['profile']['emergency_contact']['phone'],
                f"Urgent lab result: {analysis['summary'][:160]}"
            )
        
        return jsonify(lab_record)
    
    return jsonify({"error": "Invalid file type"}), 400

@app.route('/api/ai/voice', methods=['POST'])
@token_required
def voice_analysis(current_user):
    """Process voice symptom descriptions"""
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file"}), 400
    
    audio_file = request.files['audio']
    
    # In production, save to temporary storage
    audio_bytes = audio_file.read()
    
    # Transcribe with Whisper (simulated here)
    transcript = "Simulated transcription of audio symptom description"
    
    # Analyze with AI
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{
            "role": "system",
            "content": f"Patient profile: {json.dumps(db.users[current_user]['profile'])}"
        }, {
            "role": "user",
            "content": transcript
        }],
        temperature=0.3
    )
    
    return jsonify({
        "transcript": transcript,
        "analysis": response.choices[0].message.content
    })

@app.route('/api/emergency/alert', methods=['POST'])
@token_required
def emergency_alert(current_user):
    """Trigger emergency protocols"""
    contact = db.users[current_user]['profile']['emergency_contact']
    send_sms(contact['phone'], f"EMERGENCY ALERT for {current_user}")
    
    return jsonify({
        "status": "alert_sent",
        "shared_data": {
            "conditions": db.users[current_user]['profile']['conditions'],
            "medications": list(db.users[current_user]['profile']['medications'].keys()),
            "allergies": db.users[current_user]['profile']['allergies'],
            "last_symptoms": [s['name'] for s in db.users[current_user]['symptoms'][-3:]],
            "location": request.json.get('location', 'Unknown')
        }
    })

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
    db.users[current_user]['profile']['wearable_data']['access_token'] = token
    return jsonify({"status": "connected"})

@app.route('/api/wearable/data')
@token_required
def get_wearable_data(current_user):
    """Sync wearable data"""
    token = db.users[current_user]['profile']['wearable_data'].get('access_token')
    if not token:
        return jsonify({"error": "Not connected"}), 400
    
    # Simulated data - in production use Fitbit API
    now = datetime.now()
    db.users[current_user]['profile']['wearable_data'] = {
        "last_sync": now.isoformat(),
        "heart_rate": [
            {"time": (now - timedelta(minutes=i)).strftime("%H:%M"), "bpm": 72 + i%10}
            for i in range(60)
        ],
        "sleep": {
            "last_night": {
                "duration": "7h 32m",
                "stages": {
                    "deep": "1h 45m",
                    "light": "4h 12m",
                    "rem": "1h 35m"
                },
                "score": 82
            }
        },
        "steps": [
            {"date": (now - timedelta(days=i)).strftime("%Y-%m-%d"), "count": 7543 - i*500}
            for i in range(7)
        ]
    }
    
    return jsonify(db.users[current_user]['profile']['wearable_data'])

# --------------------------
# RUN APPLICATION
# --------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, ssl_context='adhoc')
