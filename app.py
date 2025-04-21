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
import io
import matplotlib.pyplot as plt
import calendar
import numpy as np

# Load environment variables
load_dotenv()

# Initialize Flask App
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Configuration
app.config.update({
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'GOOGLE_API_KEY': os.getenv('GOOGLE_API_KEY'),
})

# Mock Database
class HealthDatabase:
    def __init__(self):
        self.users = {
            "user1": {
                "password": "pass123",
                "profile": self._create_sample_profile(),
                "conversations": [],
                "appointments": [],
                "symptoms": [],
                "lab_results": []
            }
        }
    
    def _create_sample_profile(self):
        return {
            "name": "Alex Johnson",
            "age": 32,
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
                "phone": "+1234567890"
            }
        }

db = HealthDatabase()

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
            return jsonify({"error": "Token is missing"}), 401
        
        try:
            data = jwt.decode(token.split()[1], app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['user_id']
        except:
            return jsonify({"error": "Invalid token"}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

def generate_medication_schedule(medications):
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

# API Routes
@app.route('/api/auth', methods=['POST'])
def authenticate():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if username not in db.users or db.users[username]['password'] != password:
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = generate_token(username)
    return jsonify({
        "token": token,
        "user_id": username,
        "profile": db.users[username]['profile']
    })

@app.route('/api/medications', methods=['GET', 'POST'])
@token_required
def manage_medications(current_user):
    if request.method == 'GET':
        return jsonify({
            "medications": db.users[current_user]['profile']['medications']
        })
    
    elif request.method == 'POST':
        data = request.json
        med_name = data.get('name')
        if not med_name:
            return jsonify({"error": "Medication name is required"}), 400
        
        db.users[current_user]['profile']['medications'][med_name] = {
            "id": str(uuid.uuid4()),
            "dosage": data.get('dosage', ''),
            "frequency": data.get('frequency', ''),
            "times": data.get('times', []),
            "purpose": data.get('purpose', ''),
            "last_updated": datetime.now().isoformat()
        }
        
        return jsonify({
            "message": "Medication added successfully",
            "medications": db.users[current_user]['profile']['medications']
        })

@app.route('/api/medications/schedule', methods=['GET'])
@token_required
def get_medication_schedule(current_user):
    medications = db.users[current_user]['profile']['medications']
    buf = generate_medication_schedule(medications)
    return send_file(buf, mimetype='image/png')

@app.route('/api/symptoms', methods=['POST'])
@token_required
def log_symptom(current_user):
    data = request.json
    symptom = {
        "id": str(uuid.uuid4()),
        "name": data['name'],
        "severity": data.get('severity', 3),
        "timestamp": datetime.now().isoformat()
    }
    
    db.users[current_user]['symptoms'].append(symptom)
    
    # Generate AI suggestion
    prompt = f"Patient with {db.users[current_user]['profile']['conditions']} reports {data['name']}. What could this indicate?"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100
    )
    
    return jsonify({
        "symptom": symptom,
        "suggestion": response.choices[0].message.content
    })

@app.route('/api/doctors', methods=['GET'])
@token_required
def find_doctors(current_user):
    # Mock doctor data - in production use Google Places API
    doctors = [
        {
            "id": "doc1",
            "name": "Dr. Sarah Miller",
            "specialty": "Cardiology",
            "distance": "2.5 miles",
            "phone": "(555) 123-4567"
        },
        {
            "id": "doc2",
            "name": "Dr. James Wilson",
            "specialty": "General Practice",
            "distance": "1.2 miles",
            "phone": "(555) 987-6543"
        }
    ]
    return jsonify({"doctors": doctors})

@app.route('/api/ask', methods=['POST'])
@token_required
def ask_question(current_user):
    data = request.json
    query = data.get('query', '')
    
    prompt = f"""Patient Profile:
- Age: {db.users[current_user]['profile']['age']}
- Gender: {db.users[current_user]['profile']['gender']}
- Conditions: {db.users[current_user]['profile']['conditions']}
- Medications: {list(db.users[current_user]['profile']['medications'].keys())}

Question: {query}

Provide a concise medical opinion:"""
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200
    )
    
    answer = response.choices[0].message.content
    
    # Store conversation
    db.users[current_user]['conversations'].append({
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "response": answer
    })
    
    return jsonify({"answer": answer})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
