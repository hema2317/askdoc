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

# Mock DB
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
                    "last_updated": datetime.now().isoformat()
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
        "timestamp": datetime.now().isoformat()
    }
    users_db[user_id]['symptoms'].append(symptom)

    prompt = f"""
Patient Profile:
- Age: {users_db[user_id]['profile']['age']}
- Gender: {users_db[user_id]['profile']['gender']}
- Conditions: {', '.join(users_db[user_id]['profile']['conditions'])}
- Medications: {', '.join(users_db[user_id]['profile']['medications'].keys())}

Symptom: {data['name']}

Give:
1. Cause
2. Remedy
3. Doctor specialty
4. Urgency level (low/medium/high)
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400
        )
        analysis = response.choices[0].message.content
    except Exception as e:
        analysis = "AI analysis failed. Please consult a real doctor."

    return jsonify({"symptom": symptom, "analysis": analysis})

@app.route("/api/ask", methods=["POST"])
@token_required
def ask_doctor(user_id):
    data = request.json
    query = data.get("query")
    prompt = f"""
You are an AI doctor. Respond to the patient's question.

Patient:
- Age: {users_db[user_id]['profile']['age']}
- Conditions: {', '.join(users_db[user_id]['profile']['conditions'])}
- Medications: {', '.join(users_db[user_id]['profile']['medications'].keys())}

Question: {query}

Respond with:
1. Diagnosis / Advice
2. Risk factors
3. Recommended doctor specialty
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400
        )
        result = response.choices[0].message.content
    except:
        result = "Could not get an answer. Please try again."

    conv = {
        "id": str(uuid.uuid4()),
        "query": query,
        "response": result,
        "timestamp": datetime.now().isoformat()
    }

    users_db[user_id]['conversations'].append(conv)
    return jsonify(conv)

@app.route("/api/conversations", methods=["GET"])
@token_required
def get_history(user_id):
    return jsonify({"conversations": users_db[user_id]["conversations"]})

@app.route("/api/medications", methods=["GET", "POST", "PUT", "DELETE"])
@token_required
def meds(user_id):
    meds = users_db[user_id]['profile']['medications']
    if request.method == "GET":
        return jsonify({"medications": meds})
    data = request.json
    name = data['name']
    if request.method == "POST":
        meds[name] = {
            "id": str(uuid.uuid4()),
            "dosage": data['dosage'],
            "frequency": data['frequency'],
            "times": data.get("times", ["08:00"]),
            "purpose": data.get("purpose", ""),
            "last_updated": datetime.now().isoformat()
        }
    elif request.method == "PUT":
        if name in meds:
            meds[name].update(data)
    elif request.method == "DELETE":
        meds.pop(name, None)
    return jsonify({"medications": meds})

@app.route("/api/emergency", methods=["POST"])
@token_required
def emergency(user_id):
    user = users_db[user_id]['profile']
    msg = f"""EMERGENCY ALERT: {user['name']} reported a medical emergency.

Conditions: {', '.join(user['conditions'])}
Medications: {', '.join(user['medications'].keys())}
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

@app.route("/api/medications/schedule")
@token_required
def med_schedule(user_id):
    meds = users_db[user_id]['profile']['medications']
    fig, ax = plt.subplots(figsize=(10, 4))
    for i, (name, med) in enumerate(meds.items()):
        for t in med['times']:
            ax.scatter(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], [int(t.split(":")[0])] * 7, label=name)
    ax.set_title("Weekly Med Schedule")
    ax.legend()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
