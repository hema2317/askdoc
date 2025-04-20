import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS
import openai
import jwt
from functools import wraps
import requests
from geopy.distance import geodesic
import logging
from werkzeug.utils import secure_filename
from fpdf import FPDF
import tempfile
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configuration
app.config.update({
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY', 'your-secret-key-123'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'GOOGLE_API_KEY': os.getenv('GOOGLE_API_KEY'),
    'UPLOAD_FOLDER': 'uploads/',
    'ALLOWED_EXTENSIONS': {'png', 'jpg', 'jpeg', 'gif'},
    'MAX_CONTENT_LENGTH': 16 * 1024 * 1024
})

# Initialize OpenAI
openai.api_key = app.config['OPENAI_API_KEY']

users_db = {
    "user1": {
        "password": "pass123",
        "profile": {
            "age": 32,
            "gender": "female",
            "medical_history": "diabetes",
            "medications": "Metformin"
        },
        "conversations": []
    }
}

doctor_cache = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generate_token(user_id):
    return jwt.encode({'user_id': user_id, 'exp': datetime.utcnow() + timedelta(hours=24)}, app.config['SECRET_KEY'], algorithm='HS256')

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

@app.route('/api/auth', methods=['POST'])
def authenticate():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Missing credentials"}), 400

    if username not in users_db or users_db[username]['password'] != password:
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_token(username)
    return jsonify({
        "token": token,
        "user_id": username,
        "profile": users_db[username]['profile']
    })

@app.route('/api/ask', methods=['POST'])
@token_required
def ask_question(current_user):
    data = request.json
    query = data.get('query', '').strip()

    if not query:
        return jsonify({"error": "Please describe your symptoms"}), 400
    if len(query) > 1000:
        return jsonify({"error": "Query too long (max 1000 characters)"}), 400

    try:
        prompt = f"""As a senior medical professional, analyze these symptoms with caution:

Patient Profile:
- Age: {users_db[current_user]['profile'].get('age', 'Not specified')}
- Gender: {users_db[current_user]['profile'].get('gender', 'Not specified')}
- Medical History: {users_db[current_user]['profile'].get('medical_history', 'None')}
- Medications: {users_db[current_user]['profile'].get('medications', 'None')}

Symptoms: \"{query}\"

Provide a structured response in valid JSON format ONLY:
{{
  "conditions": ["list possible conditions by likelihood"],
  "actions": ["list recommended actions"],
  "warnings": ["list warning signs"],
  "emergency": "when to seek immediate care",
  "specialist": "recommended specialist type",
  "summary": "2-line doctor briefing"
}}"""

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )

        raw_answer = response.choices[0].message.content.strip()

        try:
            answer = json.loads(raw_answer)
        except json.JSONDecodeError:
            answer = {
                "conditions": ["Consultation recommended"],
                "actions": ["Schedule a doctor's appointment"],
                "warnings": ["Watch for worsening symptoms"],
                "emergency": "Seek help if severe pain or difficulty breathing",
                "specialist": "General Practitioner",
                "summary": "Patient requires professional medical evaluation"
            }

        conversation = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "response": answer,
            "raw_response": raw_answer
        }
        users_db[current_user]['conversations'].append(conversation)

        return jsonify(answer)

    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "AI processing failed"}), 500

@app.route('/api/history', methods=['GET'])
@token_required
def get_history(current_user):
    return jsonify(users_db[current_user]['conversations'])

@app.route('/api/doctors', methods=['POST'])
@token_required
def find_doctors(current_user):
    data = request.json
    location = data.get('location')
    specialty = data.get('specialty', '')

    if not location or 'lat' not in location or 'lng' not in location:
        return jsonify({"error": "Invalid location"}), 400

    try:
        cache_key = f"{location['lat']},{location['lng']},{specialty}"
        if cache_key in doctor_cache:
            cached_data = doctor_cache[cache_key]
            if (datetime.now() - cached_data['timestamp']).seconds < 3600:
                return jsonify(cached_data['data'])

        params = {
            'key': app.config['GOOGLE_API_KEY'],
            'location': f"{location['lat']},{location['lng']}",
            'radius': 10000,
            'type': 'doctor',
            'rankby': 'distance'
        }

        if specialty:
            params['keyword'] = specialty + ' doctor'

        response = requests.get(
            'https://maps.googleapis.com/maps/api/place/nearbysearch/json',
            params=params
        )
        places_data = response.json()

        if places_data.get('status') != 'OK':
            return jsonify({"error": "Doctor search failed"}), 500

        doctors = []
        for place in places_data.get('results', [])[:5]:
            distance = geodesic(
                (location['lat'], location['lng']),
                (place['geometry']['location']['lat'], place['geometry']['location']['lng'])
            ).miles

            doctors.append({
                "id": place['place_id'],
                "name": place.get('name'),
                "address": place.get('vicinity'),
                "distance": round(distance, 1),
                "rating": place.get('rating'),
                "location": place['geometry']['location'],
                "specialties": [specialty] if specialty else []
            })

        doctor_cache[cache_key] = {
            'data': {"doctors": doctors},
            'timestamp': datetime.now()
        }

        return jsonify({"doctors": doctors})

    except Exception as e:
        logging.error(f"Doctor search error: {str(e)}")
        return jsonify({"error": "Service unavailable"}), 503

@app.route('/api/upload', methods=['POST'])
@token_required
def upload_file(current_user):
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(f"{current_user}_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        return jsonify({"message": "File uploaded successfully", "path": filepath})

    return jsonify({"error": "Invalid file type"}), 400

@app.route('/api/generate-report', methods=['POST'])
@token_required
def generate_report(current_user):
    conversations = users_db[current_user]['conversations']
    if not conversations:
        return jsonify({"error": "No history available"}), 404

    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt="AskDoc Medical Report", ln=1, align='C')
        pdf.cell(200, 10, txt=f"Patient: {current_user}", ln=2, align='C')
        pdf.cell(200, 10, txt=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=3, align='C')
        pdf.ln(15)

        for i, conv in enumerate(conversations, 1):
            pdf.set_font("Arial", 'B', 12)
            pdf.multi_cell(0, 10, txt=f"Consultation {i} - {conv['timestamp'][:10]}", align='L')
            pdf.set_font("Arial", size=10)
            pdf.multi_cell(0, 8, txt=f"Question: {conv['query']}", align='L')
            try:
                response = conv['response'] if isinstance(conv['response'], dict) else json.loads(conv['response'])
                pdf.multi_cell(0, 8, txt=f"Conditions: {', '.join(response.get('conditions', []))}", align='L')
                pdf.multi_cell(0, 8, txt=f"Actions:\n- " + '\n- '.join(response.get('actions', [])), align='L')
                pdf.multi_cell(0, 8, txt=f"Summary: {response.get('summary', '')}", align='L')
            except:
                pdf.multi_cell(0, 8, txt=f"Response: {conv['response']}", align='L')
            pdf.ln(10)

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        pdf.output(temp_file.name)

        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name=f"AskDoc_Report_{current_user}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        logging.error(f"Report generation error: {str(e)}")
        return jsonify({"error": "Failed to generate report"}), 500

@app.route('/')
def home():
    return "AskDoc API is running 🚀"

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
