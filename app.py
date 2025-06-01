import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import requests
import psycopg2
from psycopg2 import OperationalError

# --- Setup ---
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")

openai.api_key = OPENAI_API_KEY

# --- Middleware ---
def check_api_token():
    auth = request.headers.get("Authorization")
    if not auth or auth != f"Bearer {API_AUTH_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

# --- DB connection (optional) ---
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

# --- Google Maps: Get nearby doctors ---
def get_nearby_doctors(specialty, location):
    try:
        lat, lng = location.split(",")
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "keyword": specialty,
            "location": f"{lat},{lng}",
            "radius": 5000,
            "type": "doctor",
            "key": GOOGLE_API_KEY
        }
        response = requests.get(url, params=params)
        data = response.json()
        doctors = []
        for place in data.get("results", [])[:5]:
            doctors.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "open_now": place.get("opening_hours", {}).get("open_now", "N/A")
            })
        return doctors
    except Exception as e:
        logger.error(f"Google Places API failed: {e}")
        return []

# --- OpenAI prompt ---
def generate_openai_response(symptoms, language, profile):
    prompt = f"""
You are a professional medical assistant. Respond in this language: {language}.
The user has this profile: {profile}

Symptoms:
"{symptoms}"

Please analyze this case and return a structured medical explanation:

1. Detected condition
2. Root cause
3. Medical explanation
4. Home remedies
5. Urgency level (low, moderate, high)
6. Suggested doctor type
7. Extract and list all medications mentioned

Return JSON:
{{
  "detected_condition": "...",
  "medical_analysis": "...",
  "root_cause": "...",
  "remedies": ["..."],
  "urgency": "low | moderate | high",
  "suggested_doctor": "...",
  "medicines": ["..."]
}}
"""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful multilingual health assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        return res['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return None

def parse_openai_json(reply):
    try:
        return json.loads(reply)
    except Exception as e:
        logger.error(f"Parsing OpenAI response failed: {e}")
        return {
            "medical_analysis": reply or "No response",
            "root_cause": "Unknown",
            "remedies": [],
            "urgency": "unknown",
            "medicines": [],
            "suggested_doctor": "general",
            "detected_condition": "unsure"
        }

# --- Google Vision API ---
def analyze_image_with_vision(base64_image):
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        payload = {
            "requests": [
                {
                    "image": {"content": base64_image},
                    "features": [{"type": "LABEL_DETECTION", "maxResults": 10}]
                }
            ]
        }
        headers = {'Content-Type': 'application/json'}
        res = requests.post(url, headers=headers, json=payload)
        labels = res.json()['responses'][0].get('labelAnnotations', [])
        return [label['description'] for label in labels]
    except Exception as e:
        logger.error(f"Google Vision error: {e}")
        return []

# --- Routes ---
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/analyze", methods=["POST"])
def analyze():
    auth = check_api_token()
    if auth:
        return auth

    data = request.json
    symptoms = data.get("symptoms", "")
    language = data.get("language", "English")
    profile = data.get("profile", "")
    location = data.get("location", "")

    reply = generate_openai_response(symptoms, language, profile)
    if not reply:
        return jsonify({"error": "OpenAI failed"}), 500

    parsed = parse_openai_json(reply)

    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)

    return jsonify(parsed)

@app.route("/photo-analyze", methods=["POST"])
def photo_analyze():
    auth = check_api_token()
    if auth:
        return auth

    try:
        data = request.json
        image_base64 = data.get("image")
        profile = data.get("profile", "")
        language = data.get("language", "English")

        if not image_base64:
            return jsonify({"error": "Image data missing"}), 400

        # Step 1: Use Google Vision API to detect labels from image
        vision_url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        vision_payload = {
            "requests": [
                {
                    "image": {"content": image_base64},
                    "features": [{"type": "LABEL_DETECTION", "maxResults": 5}]
                }
            ]
        }
        vision_response = requests.post(vision_url, json=vision_payload)
        labels = vision_response.json().get("responses", [{}])[0].get("labelAnnotations", [])

        keywords = ", ".join([label["description"] for label in labels]) if labels else "unknown skin condition"

        # Step 2: Pass result to OpenAI for medical suggestion
        prompt = f"""
The user uploaded a photo and Google Vision detected these labels: {keywords}

Patient Profile:
{profile}

Please diagnose the possible condition, explain medically, list remedies, urgency, and doctor type.

Return JSON:
{{
  "detected_condition": "...",
  "medical_analysis": "...",
  "root_cause": "...",
  "remedies": ["..."],
  "urgency": "...",
  "suggested_doctor": "...",
  "medicines": ["..."]
}}
"""
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful dermatologist assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        reply = openai_response['choices'][0]['message']['content']
        parsed = parse_openai_json(reply)

        return jsonify(parsed)

    except Exception as e:
        logger.error(f"Photo analysis failed: {e}")
        return jsonify({"error": "Photo analysis failed"}), 500


# --- Main ---
if __name__ == "__main__":
    app.run(debug=True)
