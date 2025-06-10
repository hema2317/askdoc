import os
import json
import logging
import re
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import requests
import psycopg2
from psycopg2 import OperationalError
import base64

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

# --- Auth Check ---
def check_api_token():
    auth = request.headers.get("Authorization")
    if not auth or auth != f"Bearer {API_AUTH_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

# --- DB Connection ---
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

# --- OpenAI Response ---
def generate_openai_response(symptoms, language, profile):
    prompt = f"""
You are a professional medical assistant. Respond ONLY in this language: {language}.
You MUST return valid JSON inside triple backticks.

Patient profile:
{profile}

Symptoms:
"{symptoms}"

Return JSON only in this format (inside ```json):

```json
{{
  "detected_condition": "string",
  "medical_analysis": "string",
  "root_cause": "string",
  "remedies": ["string", "string"],
  "urgency": "low | moderate | high",
  "suggested_doctor": "string",
  "medicines": ["string"]
}}
```
If unsure, return your best guess.
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

# --- JSON Parsing ---
def parse_openai_json(reply):
    try:
        match = re.search(r'```json\s*(\{.*?\})\s*```', reply, re.DOTALL)
        json_str = match.group(1) if match else reply
        return json.loads(json_str)
    except Exception as e:
        logger.error(f"JSON parsing failed: {e}")
        return {
            "medical_analysis": reply or "No response from OpenAI.",
            "root_cause": "Unknown",
            "remedies": [],
            "urgency": "unknown",
            "medicines": [],
            "suggested_doctor": "general",
            "detected_condition": "unsure"
        }

# --- Nearby Doctor Lookup ---
def get_nearby_doctors(specialty, location):
    try:
        lat, lng = location.split(",")
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "keyword": specialty,
            "location": f"{lat},{lng}",
            "radius": 5000,
            "type": "doctor",
            "key": GOOGLE_API_KEY,
            "rankby": "prominence"
        }
        response = requests.get(url, params=params)
        sorted_results = sorted(response.json().get("results", []), key=lambda x: x.get("rating", 0), reverse=True)
        doctors = []
        for place in sorted_results[:5]:
            doctors.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "open_now": place.get("opening_hours", {}).get("open_now", "N/A"),
                "maps_link": f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place.get('place_id')}"
            })
        return doctors
    except Exception as e:
        logger.error(f"Google Maps API failed: {e}")
        return []

# --- OCR Text Extraction ---
def extract_text_from_image(base64_image):
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [{
                "image": {"content": base64_image},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }
        res = requests.post(url, json=body)
        return res.json()["responses"][0].get("fullTextAnnotation", {}).get("text", "")
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return ""

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

@app.route("/labreport-analyze", methods=["POST"])
def analyze_labreport():
    auth = check_api_token()
    if auth:
        return auth

    data = request.get_json()
    image_base64 = data.get("image_base64")
    language = data.get("language", "English")
    profile = data.get("profile", "")
    location = data.get("location", "")

    if not image_base64:
        return jsonify({"error": "Missing lab report image"}), 400

    text = extract_text_from_image(image_base64)
    if not text.strip():
        return jsonify({"error": "No text extracted from lab report"}), 400

    reply = generate_openai_response(text, language, profile)
    parsed = parse_openai_json(reply)
    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)

    parsed["extracted_text"] = text
    return jsonify(parsed)

# --- Entrypoint ---
if __name__ == '__main__':
    app.run(debug=True)
