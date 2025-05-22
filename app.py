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

# --- App Setup ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")

openai.api_key = OPENAI_API_KEY

# --- Middleware: Check API token ---
def check_api_token():
    auth = request.headers.get("Authorization")
    if not auth or auth != f"Bearer {API_AUTH_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

# --- Optional DB Connection ---
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

# --- OpenAI Medical Analysis ---
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
7. Any medicines mentioned

Return JSON only:
{{
  "detected_condition": "...",
  "medical_analysis": "...",
  "root_cause": "...",
  "remedies": ["...", "..."],
  "urgency": "low | moderate | high",
  "suggested_doctor": "...",
  "medicines": ["..."]
}}
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful multilingual health assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"OpenAI request failed: {e}")
        return None

# --- Fallback if OpenAI JSON is malformed ---
def parse_openai_json(reply):
    try:
        return json.loads(reply)
    except json.JSONDecodeError:
        return {
            "medical_analysis": reply or "No response from OpenAI.",
            "root_cause": "Unknown due to parsing error",
            "remedies": [],
            "urgency": "unknown",
            "medicines": [],
            "suggested_doctor": "general",
            "detected_condition": "unsure"
        }

# --- Google Maps Nearby Doctor Lookup ---
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
    location = data.get("location", "")  # Format: "lat,lng"

    reply = generate_openai_response(symptoms, language, profile)
    if not reply:
        return jsonify({"error": "OpenAI failed to respond"}), 500

    parsed = parse_openai_json(reply)

    # Optional: fetch real doctor options
    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)

    return jsonify(parsed)

# --- Main entrypoint (for local testing only) ---
if __name__ == '__main__':
    app.run(debug=True)
