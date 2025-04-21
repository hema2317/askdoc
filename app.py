import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import jwt
from functools import wraps
import requests
from geopy.distance import geodesic
import logging
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config.update({
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY', 'your-secret-key-123'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'GOOGLE_API_KEY': os.getenv('GOOGLE_API_KEY')
})

openai.api_key = app.config['OPENAI_API_KEY']

users_db = {
    "user1": {
        "password": "pass123",
        "profile": {
            "age": 32,
            "gender": "female",
            "medical_history": "diabetes",
            "medications": ["Metformin"]
        },
        "conversations": []
    }
}

doctor_cache = {}

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
        except:
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
    return jsonify({"token": token, "user_id": username, "profile": users_db[username]['profile']})

@app.route('/api/medications', methods=['GET'])
@token_required
def get_medications(current_user):
    return jsonify({"medications": users_db[current_user]['profile'].get('medications', [])})

@app.route('/api/ask', methods=['POST'])
@token_required
def ask_question(current_user):
    data = request.json
    query = data.get('query', '').strip()
    new_meds = data.get('new_medications', [])

    if not query:
        return jsonify({"error": "Please describe your symptoms"}), 400

    # Update user medication history
    if new_meds:
        existing = users_db[current_user]['profile'].get('medications', [])
        users_db[current_user]['profile']['medications'] = list(set(existing + new_meds))

    try:
        prompt = f"""As a senior medical professional, analyze these symptoms with caution:

Patient Profile:
- Age: {users_db[current_user]['profile'].get('age', 'Not specified')}
- Gender: {users_db[current_user]['profile'].get('gender', 'Not specified')}
- Medical History: {users_db[current_user]['profile'].get('medical_history', 'None')}
- Medications: {', '.join(users_db[current_user]['profile'].get('medications', []))}

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

        users_db[current_user]['conversations'].append({
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "response": answer,
            "raw_response": raw_answer,
            "medications": users_db[current_user]['profile']['medications']
        })

        return jsonify(answer)
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "AI processing failed"}), 500

@app.route('/api/find-doctors', methods=['POST'])
@token_required
def find_doctors(current_user):
    data = request.json
    location = data.get('location', {"lat": 40.7608, "lng": -111.8910})
    specialty = data.get('specialty', '')

    try:
        params = {
            'key': app.config['GOOGLE_API_KEY'],
            'location': f"{location['lat']},{location['lng']}",
            'radius': 10000,
            'type': 'doctor',
            'keyword': specialty + ' doctor' if specialty else 'doctor'
        }

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

            place_id = place['place_id']
            phone = None
            try:
                detail_res = requests.get(
                    'https://maps.googleapis.com/maps/api/place/details/json',
                    params={
                        'key': app.config['GOOGLE_API_KEY'],
                        'place_id': place_id,
                        'fields': 'formatted_phone_number'
                    }
                )
                phone_data = detail_res.json()
                phone = phone_data.get('result', {}).get('formatted_phone_number')
            except:
                pass

            doctors.append({
                "id": place_id,
                "name": place.get('name'),
                "address": place.get('vicinity'),
                "distance": round(distance, 1),
                "rating": place.get('rating'),
                "location": place['geometry']['location'],
                "specialties": [specialty] if specialty else [],
                "phone": phone
            })

        return jsonify({"doctors": doctors})

    except Exception as e:
        logging.error(f"Doctor search error: {str(e)}")
        return jsonify({"error": "Service unavailable"}), 503

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
