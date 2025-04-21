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
from twilio.rest import Client
import random

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
app.config.update({
    'SECRET_KEY': os.getenv('SECRET_KEY', 'your-secret-key-here'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'TWILIO_ACCOUNT_SID': os.getenv('TWILIO_SID'),
    'TWILIO_AUTH_TOKEN': os.getenv('TWILIO_TOKEN'),
    'TWILIO_PHONE': os.getenv('TWILIO_PHONE'),
    'TEST_PHONE': os.getenv('TEST_PHONE')
})

# Initialize OpenAI
openai.api_key = app.config['OPENAI_API_KEY']

# Mock Database
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
                "phone": app.config['TEST_PHONE']
            }
        },
        "conversations": [],
        "symptoms": [],
        "appointments": []
    }
}

# Mock doctor database
doctors_db = [
    {
        "id": "doc1",
        "name": "Dr. Sarah Miller",
        "specialty": "Cardiology",
        "distance": "2.5 miles",
        "phone": "(555) 123-4567",
        "address": "123 Medical Center Dr",
        "rating": 4.8
    },
    {
        "id": "doc2",
        "name": "Dr. James Wilson",
        "specialty": "General Practice",
        "distance": "1.2 miles",
        "phone": "(555) 987-6543",
        "address": "456 Health Plaza",
        "rating": 4.5
    },
    {
        "id": "doc3",
        "name": "Dr. Emily Chen",
        "specialty": "Endocrinology",
        "distance": "3.1 miles",
        "phone": "(555) 456-7890",
        "address": "789 Wellness Blvd",
        "rating": 4.9
    }
]

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
        except Exception as e:
            return jsonify({"error": "Invalid token"}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

def generate_medication_schedule(medications):
    """Generate visual medication schedule as PNG"""
    plt.style.use('default')
    fig, ax = plt.subplots(figsize=(10, 4))
    days = list(calendar.day_abbr)
    
    colors = plt.cm.tab10.colors  # Use a color map
    
    for i, (med_name, details) in enumerate(medications.items()):
        times = details.get('times', [])
        for time in times:
            for day in days:
                hour, minute = map(int, time.split(':'))
                time_num = hour + minute/60
                ax.scatter(
                    day, 
                    time_num, 
                    color=colors[i % len(colors)],
                    s=200,
                    label=f"{med_name} {details['dosage']}"
                )
    
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

def send_sms(to, body):
    """Send SMS using Twilio"""
    if not all([app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN'], app.config['TWILIO_PHONE']]):
        print(f"SMS would be sent to {to}: {body}")
        return True
        
    try:
        client = Client(app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN'])
        message = client.messages.create(
            body=body,
            from_=app.config['TWILIO_PHONE'],
            to=to
        )
        return True
    except Exception as e:
        print(f"Failed to send SMS: {str(e)}")
        return False

# API Endpoints
@app.route('/api/auth', methods=['POST'])
def authenticate():
    """User login endpoint"""
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
    """Full CRUD for medications"""
    if request.method == 'GET':
        return jsonify({
            "medications": users_db[current_user]['profile']['medications']
        })
    
    elif request.method == 'POST':
        data = request.json
        med_name = data.get('name')
        if not med_name:
            return jsonify({"error": "Medication name is required"}), 400
        
        med_id = str(uuid.uuid4())
        users_db[current_user]['profile']['medications'][med_name] = {
            "id": med_id,
            "dosage": data.get('dosage', ''),
            "frequency": data.get('frequency', ''),
            "times": data.get('times', ["08:00"]),
            "purpose": data.get('purpose', ''),
            "last_updated": datetime.now().isoformat()
        }
        
        return jsonify({
            "message": "Medication added successfully",
            "medications": users_db[current_user]['profile']['medications']
        })
    
    elif request.method == 'PUT':
        data = request.json
        med_name = data.get('name')
        if not med_name or med_name not in users_db[current_user]['profile']['medications']:
            return jsonify({"error": "Medication not found"}), 404
        
        # Update only provided fields
        med_data = users_db[current_user]['profile']['medications'][med_name]
        if 'dosage' in data: med_data['dosage'] = data['dosage']
        if 'frequency' in data: med_data['frequency'] = data['frequency']
        if 'times' in data: med_data['times'] = data['times']
        if 'purpose' in data: med_data['purpose'] = data['purpose']
        med_data['last_updated'] = datetime.now().isoformat()
        
        return jsonify({
            "message": "Medication updated successfully",
            "medication": med_data
        })
    
    elif request.method == 'DELETE':
        med_name = request.json.get('name')
        if not med_name or med_name not in users_db[current_user]['profile']['medications']:
            return jsonify({"error": "Medication not found"}), 404
        
        deleted_med = users_db[current_user]['profile']['medications'].pop(med_name)
        return jsonify({
            "message": "Medication deleted successfully",
            "deleted_medication": deleted_med
        })

@app.route('/api/medications/schedule', methods=['GET'])
@token_required
def get_medication_schedule(current_user):
    """Generate visual medication schedule"""
    medications = users_db[current_user]['profile']['medications']
    buf = generate_medication_schedule(medications)
    return send_file(buf, mimetype='image/png')

@app.route('/api/symptoms', methods=['POST'])
@token_required
def log_symptom(current_user):
    """Log a new symptom with AI analysis"""
    data = request.json
    if not data.get('name'):
        return jsonify({"error": "Symptom name is required"}), 400
    
    symptom = {
        "id": str(uuid.uuid4()),
        "name": data['name'],
        "severity": data.get('severity', 3),
        "notes": data.get('notes', ''),
        "timestamp": datetime.now().isoformat()
    }
    
    users_db[current_user]['symptoms'].append(symptom)
    
    # Generate AI analysis
    prompt = f"""Patient Profile:
- Age: {users_db[current_user]['profile']['age']}
- Gender: {users_db[current_user]['profile']['gender']}
- Conditions: {users_db[current_user]['profile']['conditions']}
- Medications: {list(users_db[current_user]['profile']['medications'].keys())}

Reported Symptom:
- Name: {data['name']}
- Severity: {data.get('severity', 3)}/5
- Notes: {data.get('notes', 'N/A')}

Provide a medical analysis in this format:
1. Possible Causes: [bullet points]
2. Recommended Actions: [bullet points]
3. Medication Interactions: [bullet points]
4. When to Seek Help: [description]"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400
        )
        analysis = response.choices[0].message.content
    except Exception as e:
        analysis = "Could not generate analysis. Please consult your doctor."
    
    return jsonify({
        "symptom": symptom,
        "analysis": analysis
    })

@app.route('/api/doctors', methods=['GET'])
@token_required
def get_doctors(current_user):
    """Get list of doctors with optional filtering"""
    specialty = request.args.get('specialty', '').lower()
    
    if specialty:
        filtered_doctors = [doc for doc in doctors_db if specialty in doc['specialty'].lower()]
    else:
        filtered_doctors = doctors_db
    
    return jsonify({
        "doctors": filtered_doctors
    })

@app.route('/api/ask', methods=['POST'])
@token_required
def ask_doctor(current_user):
    """Ask a medical question to AI doctor"""
    data = request.json
    query = data.get('query')
    if not query:
        return jsonify({"error": "Question is required"}), 400
    
    # Store conversation
    conversation = {
        "id": str(uuid.uuid4()),
        "query": query,
        "timestamp": datetime.now().isoformat()
    }
    
    # Generate AI response
    prompt = f"""You are a medical professional answering a patient's question.

Patient Profile:
- Name: {users_db[current_user]['profile']['name']}
- Age: {users_db[current_user]['profile']['age']}
- Gender: {users_db[current_user]['profile']['gender']}
- Conditions: {users_db[current_user]['profile']['conditions']}
- Medications: {list(users_db[current_user]['profile']['medications'].keys())}
- Allergies: {users_db[current_user]['profile']['allergies']}

Question: {query}

Provide a thorough response with:
1. Professional medical advice
2. Possible medication interactions
3. Warning signs to watch for
4. Recommended follow-up actions"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        answer = response.choices[0].message.content
    except Exception as e:
        answer = "I couldn't process your question. Please try again or consult your doctor."
    
    conversation["response"] = answer
    users_db[current_user]['conversations'].append(conversation)
    
    return jsonify({
        "answer": answer,
        "conversation_id": conversation["id"]
    })

@app.route('/api/conversations', methods=['GET'])
@token_required
def get_conversations(current_user):
    """Get conversation history"""
    return jsonify({
        "conversations": users_db[current_user]['conversations']
    })

@app.route('/api/emergency', methods=['POST'])
@token_required
def emergency_alert(current_user):
    """Trigger emergency protocols"""
    contact = users_db[current_user]['profile']['emergency_contact']
    user = users_db[current_user]['profile']
    
    # Prepare emergency message
    message = f"""EMERGENCY ALERT for {user['name']}

Current Medications:
{", ".join(user['medications'].keys()) or "None"}

Medical Conditions:
{", ".join(user['conditions']) or "None"}

Allergies:
{", ".join(user['allergies']) or "None"}

Blood Type: {user['blood_type']}

LAST KNOWN LOCATION: {request.json.get('location', 'Unknown')}"""
    
    # Send SMS
    sms_sent = send_sms(contact['phone'], message)
    
    return jsonify({
        "status": "alert_sent" if sms_sent else "alert_failed",
        "contact": contact['name'],
        "phone": contact['phone'],
        "message": message
    })

@app.route('/api/user/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    """Get user profile"""
    return jsonify(users_db[current_user]['profile'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
