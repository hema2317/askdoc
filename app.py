from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import jwt
from functools import wraps
from datetime import datetime, timedelta
import uuid
import openai
import os
from dotenv import load_dotenv
import io
import matplotlib.pyplot as plt
import calendar
import smtplib
from email.mime.text import MIMEText
import requests

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
app.config.update({
    'SECRET_KEY': os.getenv('SECRET_KEY'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'GOOGLE_API_KEY': os.getenv('GOOGLE_API_KEY'),
    'TWILIO_SID': os.getenv('TWILIO_SID'),
    'TWILIO_TOKEN': os.getenv('TWILIO_TOKEN')
})

# Database
users_db = {
    "user1": {
        "password": "pass123",
        "profile": {
            "name": "Alex Johnson",
            "age": 35,
            "gender": "male",
            "blood_type": "A+",
            "allergies": ["penicillin"],
            "conditions": ["Hypertension"],
            "medications": {
                "Lisinopril": {
                    "id": str(uuid.uuid4()),
                    "dosage": "10mg",
                    "frequency": "daily",
                    "times": ["08:00"],
                    "purpose": "Blood pressure control",
                    "last_updated": datetime.now().isoformat()
                }
            },
            "emergency_contact": {
                "name": "Sarah Johnson",
                "relationship": "Spouse",
                "phone": os.getenv('TEST_PHONE')
            }
        },
        "conversations": [],
        "symptoms": [],
        "appointments": []
    }
}

# Helper Functions
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
            return jsonify({"error": "Token missing"}), 401
        
        try:
            data = jwt.decode(token.split()[1], app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['user_id']
        except Exception as e:
            return jsonify({"error": "Invalid token"}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

def generate_medication_schedule(medications):
    """Generate visual medication schedule"""
    plt.style.use('default')
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

def find_nearby_doctors(location, specialty=""):
    """Use Google Places API to find doctors"""
    # Mock data for demonstration
    return [
        {
            "id": "doc1",
            "name": "Dr. Sarah Miller",
            "specialty": "Cardiology" if not specialty else specialty,
            "distance": "2.5 miles",
            "phone": "(555) 123-4567",
            "address": "123 Medical Center Dr"
        }
    ]

# API Endpoints
@app.route('/api/auth', methods=['POST'])
def authenticate():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if username not in users_db or users_db[username]['password'] != password:
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = generate_token(username)
    return jsonify({
        "token": token,
        "user_id": username,
        "profile": users_db[username]['profile']
    })

@app.route('/api/medications', methods=['GET', 'POST', 'PUT', 'DELETE'])
@token_required
def manage_medications(current_user):
    if request.method == 'GET':
        return jsonify({
            "medications": users_db[current_user]['profile']['medications']
        })
    
    elif request.method == 'POST':
        data = request.json
        med_name = data.get('name')
        
        users_db[current_user]['profile']['medications'][med_name] = {
            "id": str(uuid.uuid4()),
            "dosage": data.get('dosage'),
            "frequency": data.get('frequency'),
            "times": data.get('times', []),
            "purpose": data.get('purpose', ''),
            "last_updated": datetime.now().isoformat()
        }
        return jsonify({
            "message": "Medication added",
            "medications": users_db[current_user]['profile']['medications']
        })
    
    elif request.method == 'PUT':
        data = request.json
        med_name = data.get('name')
        
        if med_name in users_db[current_user]['profile']['medications']:
            users_db[current_user]['profile']['medications'][med_name].update({
                "dosage": data.get('dosage'),
                "frequency": data.get('frequency'),
                "times": data.get('times'),
                "last_updated": datetime.now().isoformat()
            })
            return jsonify({
                "message": "Medication updated",
                "medications": users_db[current_user]['profile']['medications']
            })
        return jsonify({"error": "Medication not found"}), 404
    
    elif request.method == 'DELETE':
        med_name = request.json.get('name')
        if med_name in users_db[current_user]['profile']['medications']:
            del users_db[current_user]['profile']['medications'][med_name]
            return jsonify({
                "message": "Medication deleted",
                "medications": users_db[current_user]['profile']['medications']
            })
        return jsonify({"error": "Medication not found"}), 404

@app.route('/api/medications/schedule', methods=['GET'])
@token_required
def medication_schedule(current_user):
    buf = generate_medication_schedule(users_db[current_user]['profile']['medications'])
    return send_file(buf, mimetype='image/png')

@app.route('/api/symptoms', methods=['POST'])
@token_required
def log_symptom(current_user):
    data = request.json
    symptom = {
        "id": str(uuid.uuid4()),
        "name": data.get('name'),
        "severity": data.get('severity', 3),
        "timestamp": datetime.now().isoformat(),
        "notes": data.get('notes', '')
    }
    
    users_db[current_user]['symptoms'].append(symptom)
    
    # AI Analysis
    prompt = f"""Patient with {users_db[current_user]['profile']['conditions']} taking {list(users_db[current_user]['profile']['medications'].keys())} reports:
    
    Symptom: {data.get('name')}
    Severity: {data.get('severity', 3)}
    Notes: {data.get('notes', '')}
    
    Provide:
    1. Possible causes
    2. Recommended actions
    3. Medication interactions to check"""
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    
    return jsonify({
        "symptom": symptom,
        "analysis": response.choices[0].message.content
    })

@app.route('/api/doctors', methods=['GET'])
@token_required
def find_doctors(current_user):
    location = request.args.get('location', '')
    specialty = request.args.get('specialty', '')
    
    doctors = find_nearby_doctors(location, specialty)
    return jsonify({"doctors": doctors})

@app.route('/api/ask', methods=['POST'])
@token_required
def ask_doctor(current_user):
    data = request.json
    query = data.get('query')
    
    if not query:
        return jsonify({"error": "Query required"}), 400
    
    # Store conversation
    conversation = {
        "id": str(uuid.uuid4()),
        "query": query,
        "timestamp": datetime.now().isoformat()
    }
    
    # Generate AI response
    prompt = f"""As a doctor, respond to this patient:

Patient Profile:
- Name: {users_db[current_user]['profile']['name']}
- Age: {users_db[current_user]['profile']['age']}
- Conditions: {users_db[current_user]['profile']['conditions']}
- Medications: {list(users_db[current_user]['profile']['medications'].keys())}

Question: {query}

Provide:
1. Professional medical advice
2. Possible medication interactions
3. When to seek immediate care"""
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400
    )
    
    conversation["response"] = response.choices[0].message.content
    users_db[current_user]['conversations'].append(conversation)
    
    return jsonify({
        "answer": conversation["response"],
        "conversation_id": conversation["id"]
    })

@app.route('/api/conversations', methods=['GET'])
@token_required
def get_conversations(current_user):
    return jsonify({
        "conversations": users_db[current_user]['conversations']
    })

@app.route('/api/emergency', methods=['POST'])
@token_required
def emergency_alert(current_user):
    contact = users_db[current_user]['profile']['emergency_contact']
    
    # In production, use Twilio to send SMS
    print(f"ALERT SENT TO {contact['phone']}: Emergency for {users_db[current_user]['profile']['name']}")
    
    return jsonify({
        "status": "alert_sent",
        "contact": contact['name'],
        "phone": contact['phone']
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
