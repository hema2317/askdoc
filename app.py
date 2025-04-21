from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv
import openai, jwt, os, uuid, io, re
from twilio.rest import Client

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

app.config.update({
    'SECRET_KEY': os.getenv('SECRET_KEY', 'askdoc-key'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'TWILIO_SID': os.getenv('TWILIO_SID'),
    'TWILIO_TOKEN': os.getenv('TWILIO_TOKEN'),
    'TWILIO_PHONE': os.getenv('TWILIO_PHONE'),
    'TEST_PHONE': os.getenv('TEST_PHONE'),
    'MAX_DAILY_DIAGNOSIS': int(os.getenv('MAX_DAILY_DIAGNOSIS', 5))
})

openai.api_key = app.config['OPENAI_API_KEY']

# Enhanced Mock DB with Usage Tracking
users_db = {
    "user1": {
        "password": "pass123",
        "usage": {
            "last_diagnosis_date": None,
            "diagnosis_count": 0
        },
        "profile": {
            "name": "Alex",
            "age": 40,
            "gender": "male",
            "conditions": ["Diabetes", "Hypertension"],
            "allergies": ["penicillin"],
            "blood_type": "O+",
            "medications": {
                "Metformin": {
                    "id": str(uuid.uuid4()),
                    "dosage": "500mg",
                    "frequency": "daily",
                    "times": ["08:00"],
                    "purpose": "Lower blood sugar",
                    "last_updated": datetime.now().isoformat(),
                    "history": []
                }
            },
            "emergency_contact": {
                "name": "Sarah",
                "phone": app.config['TEST_PHONE']
            }
        },
        "conversations": [],
        "symptoms": []
    }
}

# Authentication
def token_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        token = request.headers.get('Authorization', '').split(" ")[-1]
        try:
            decoded = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            return f(decoded['user_id'], *args, **kwargs)
        except Exception:
            return jsonify({"error": "Invalid token"}), 401
    return wrap

def generate_token(user_id):
    return jwt.encode({'user_id': user_id, 'exp': datetime.utcnow() + timedelta(days=1)}, app.config['SECRET_KEY'], algorithm='HS256')

# Medical Response Generator
def get_medical_response(prompt, mode="general"):
    system_messages = {
        "general": "You are a medical assistant providing general health information. Never diagnose.",
        "diagnosis": """You are a medical assistant suggesting POSSIBLE conditions. Always:
1. Rank possibilities by likelihood
2. Specify needed tests for confirmation
3. State urgency level
4. Include disclaimers"""
    }
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4" if mode == "diagnosis" else "gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_messages[mode]},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3 if mode == "diagnosis" else 0.7,
            max_tokens=600
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI Error: {str(e)}")
        return None

# Routes
@app.route("/api/auth", methods=["POST"])
def auth():
    data = request.json
    if data['username'] in users_db and users_db[data['username']]['password'] == data['password']:
        token = generate_token(data['username'])
        return jsonify({"token": token, "profile": users_db[data['username']]['profile']})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/symptoms", methods=["POST"])
@token_required
def log_symptom(user_id):
    data = request.json
    symptom = {
        "id": str(uuid.uuid4()),
        "name": data['name'],
        "severity": data.get("severity", 3),
        "duration": data.get("duration", ""),
        "timestamp": datetime.now().isoformat(),
        "notes": data.get("notes", "")
    }
    users_db[user_id]['symptoms'].append(symptom)

    prompt = f"""
Patient Profile:
- Age: {users_db[user_id]['profile']['age']}
- Gender: {users_db[user_id]['profile']['gender']}
- Conditions: {', '.join(users_db[user_id]['profile']['conditions'])}
- Allergies: {', '.join(users_db[user_id]['profile']['allergies'])}

Symptom: {data['name']}
Severity: {data.get('severity', 3)}/10
Duration: {data.get('duration', 'unknown')}

Provide:
1. Possible explanations (non-diagnostic)
2. Self-care recommendations
3. When to see a doctor
"""
    analysis = get_medical_response(prompt)
    if not analysis:
        analysis = "Could not generate analysis. Please consult your doctor."

    return jsonify({"symptom": symptom, "analysis": analysis})

@app.route("/api/analyze", methods=["POST"])
@token_required
def medical_analysis(user_id):
    # Rate limiting
    today = datetime.now().date()
    last_date = users_db[user_id]['usage']['last_diagnosis_date']
    if last_date and last_date == today and users_db[user_id]['usage']['diagnosis_count'] >= app.config['MAX_DAILY_DIAGNOSIS']:
        return jsonify({"error": "Daily diagnosis limit reached"}), 429

    data = request.json
    symptoms = data.get("symptoms", "")
    
    if not symptoms:
        return jsonify({"error": "Symptoms required"}), 400

    # Verify user consent
    if not data.get("consent_given", False):
        return jsonify({"error": "Diagnosis requires explicit consent"}), 403

    disclaimer = """
    ⚠️ IMPORTANT: This is NOT a medical diagnosis. Possible conditions are suggested based on the information provided. 
    Always consult a qualified healthcare provider for accurate assessment. Never delay seeking medical advice because of AI suggestions.
    """

    prompt = f"""
Patient Background:
- Age: {users_db[user_id]['profile']['age']}
- Gender: {users_db[user_id]['profile']['gender']}
- Known Conditions: {', '.join(users_db[user_id]['profile']['conditions'])}
- Allergies: {', '.join(users_db[user_id]['profile']['allergies'])}

Reported Symptoms:
{symptoms}

Duration: {data.get('duration', 'unknown')}
Severity: {data.get('severity', 'unknown')}

Format your response with:
1. Top 3 possible conditions (with likelihood)
2. Recommended diagnostic tests
3. Urgency level (1-5 scale)
4. Next steps
"""
    analysis = get_medical_response(prompt, mode="diagnosis")
    if not analysis:
        return jsonify({"error": "Analysis failed"}), 500

    full_response = disclaimer + "\n\n" + analysis

    # Update usage
    users_db[user_id]['usage']['diagnosis_count'] += 1
    users_db[user_id]['usage']['last_diagnosis_date'] = today

    # Log conversation
    users_db[user_id]['conversations'].append({
        "id": str(uuid.uuid4()),
        "type": "diagnostic_analysis",
        "content": symptoms,
        "response": full_response,
        "timestamp": datetime.now().isoformat()
    })

    return jsonify({"analysis": full_response})

@app.route("/api/medications/log", methods=["POST"])
@token_required
def log_medication(user_id):
    data = request.json
    if not data or 'name' not in data:
        return jsonify({"error": "Medication name required"}), 400

    med_name = data['name']
    if med_name not in users_db[user_id]['profile']['medications']:
        return jsonify({"error": "Medication not found"}), 404

    log_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": data.get('timestamp', datetime.now().isoformat()),
        "notes": data.get('notes', ''),
        "source": data.get('source', 'manual')
    }

    users_db[user_id]['profile']['medications'][med_name]['history'].append(log_entry)
    return jsonify({"status": "logged", "entry": log_entry})

# ... [Keep all other existing endpoints from previous versions] ...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
