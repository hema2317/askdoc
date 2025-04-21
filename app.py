from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv
import openai, jwt, os, uuid, io, matplotlib.pyplot as plt, calendar
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
    'TEST_PHONE': os.getenv('TEST_PHONE')
})

openai.api_key = app.config['OPENAI_API_KEY']

# Enhanced Mock DB with medication history
users_db = {
    "user1": {
        "password": "pass123",
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
                    "history": []  # Track medication intake
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

# Medical Analysis Helper
def get_medical_response(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """You are a medical assistant that provides:
1. Possible causes for symptoms
2. Home remedies and self-care tips
3. When to see a doctor
4. Relevant precautions

Always include disclaimers that this is not medical advice."""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # More conservative responses
            max_tokens=500
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
- Current Medications: {', '.join(users_db[user_id]['profile']['medications'].keys())}

Reported Symptom: {data['name']}
Severity: {data.get('severity', 3)}/10
Additional Notes: {data.get('notes', 'None')}

Provide:
1. Possible explanations (common causes)
2. Self-care recommendations
3. Warning signs that warrant immediate medical attention
4. Suggested specialist if condition persists
"""

    analysis = get_medical_response(prompt)
    if not analysis:
        analysis = "Could not generate analysis. Please try again or consult your doctor."

    return jsonify({
        "symptom": symptom,
        "analysis": analysis,
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/ask", methods=["POST"])
@token_required
def ask_doctor(user_id):
    data = request.json
    query = data.get("query")
    
    prompt = f"""
Patient Background:
- Name: {users_db[user_id]['profile']['name']}
- Age: {users_db[user_id]['profile']['age']}
- Gender: {users_db[user_id]['profile']['gender']}
- Medical Conditions: {', '.join(users_db[user_id]['profile']['conditions'])}
- Allergies: {', '.join(users_db[user_id]['profile']['allergies'])}
- Current Medications: {', '.join(users_db[user_id]['profile']['medications'].keys())}

Patient Question: {query}

Provide a helpful response that:
1. Acknowledges the concern
2. Provides general information (not diagnosis)
3. Suggests when to seek medical attention
4. Mentions any relevant precautions
5. Always includes disclaimer
"""
    result = get_medical_response(prompt)
    if not result:
        result = "Could not process your question. Please try again or consult your doctor."

    conv = {
        "id": str(uuid.uuid4()),
        "query": query,
        "response": result,
        "timestamp": datetime.now().isoformat(),
        "type": "general_question"
    }

    users_db[user_id]['conversations'].append(conv)
    return jsonify(conv)

@app.route("/api/conversations", methods=["GET"])
@token_required
def get_history(user_id):
    return jsonify({
        "conversations": users_db[user_id]["conversations"],
        "symptoms": users_db[user_id]["symptoms"]
    })

@app.route("/api/medications", methods=["GET", "POST", "PUT", "DELETE"])
@token_required
def meds(user_id):
    meds = users_db[user_id]['profile']['medications']
    if request.method == "GET":
        return jsonify({"medications": meds})
    
    data = request.json
    if not data or 'name' not in data:
        return jsonify({"error": "Medication name required"}), 400
        
    name = data['name']
    
    if request.method == "POST":
        meds[name] = {
            "id": str(uuid.uuid4()),
            "dosage": data['dosage'],
            "frequency": data['frequency'],
            "times": data.get("times", ["08:00"]),
            "purpose": data.get("purpose", ""),
            "last_updated": datetime.now().isoformat(),
            "history": []
        }
    elif request.method == "PUT":
        if name in meds:
            meds[name].update(data)
    elif request.method == "DELETE":
        meds.pop(name, None)
    return jsonify({"medications": meds})

@app.route("/api/medications/log", methods=["POST"])
@token_required
def log_medication(user_id):
    data = request.json
    med_name = data['name']
    taken_at = data.get('timestamp', datetime.now().isoformat())
    notes = data.get('notes', '')
    
    if med_name not in users_db[user_id]['profile']['medications']:
        return jsonify({"error": "Medication not found"}), 404
    
    log_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": taken_at,
        "notes": notes,
        "logged_via": data.get('source', 'manual')  # 'manual' or 'chat'
    }
    
    users_db[user_id]['profile']['medications'][med_name]['history'].append(log_entry)
    
    return jsonify({
        "status": "logged",
        "medication": med_name,
        "log_entry": log_entry
    })

@app.route("/api/emergency", methods=["POST"])
@token_required
def emergency(user_id):
    user = users_db[user_id]['profile']
    msg = f"""EMERGENCY ALERT: {user['name']} reported a medical emergency.

Conditions: {', '.join(user['conditions'])}
Medications: {', '.join(user['medications'].keys())}
Allergies: {', '.join(user['allergies'])}
"""
    try:
        client = Client(app.config['TWILIO_SID'], app.config['TWILIO_TOKEN'])
        client.messages.create(
            body=msg,
            from_=app.config['TWILIO_PHONE'],
            to=user['emergency_contact']['phone']
        )
    except Exception as e:
        print("Twilio failed:", str(e))
    return jsonify({"status": "alert_sent", "message": msg})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
