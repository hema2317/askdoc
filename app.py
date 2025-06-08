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
You are a professional medical assistant. Respond in this language: {language}.
The user has this profile: {profile}

Symptoms:
"{symptoms}"

Analyze and return JSON only:
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

def parse_openai_json(reply):
    try:
        return json.loads(reply)
    except json.JSONDecodeError:
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
            "key": GOOGLE_API_KEY
        }
        response = requests.get(url, params=params)
        doctors = []
        for place in response.json().get("results", [])[:5]:
            doctors.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "open_now": place.get("opening_hours", {}).get("open_now", "N/A")
            })
        return doctors
    except Exception as e:
        logger.error(f"Google Maps API failed: {e}")
        return []

# --- Google Vision Labeling ---
def get_image_labels(base64_image):
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [{
                "image": {"content": base64_image},
                "features": [{"type": "LABEL_DETECTION", "maxResults": 5}]
            }]
        }
        res = requests.post(url, json=body)
        labels = [label['description'] for label in res.json()["responses"][0]["labelAnnotations"]]
        return labels
    except Exception as e:
        logger.error(f"Vision API error: {e}")
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

    logger.info(f"[ANALYZE] Input: {symptoms}")
    reply = generate_openai_response(symptoms, language, profile)
    if not reply:
        return jsonify({"error": "OpenAI failed"}), 500

    parsed = parse_openai_json(reply)

    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)

    return jsonify(parsed)

@app.route("/api/ask", methods=["POST"])
def ask():
    auth = check_api_token()
    if auth:
        return auth

    data = request.get_json()
    question = data.get("question", "")
    if not question:
        return jsonify({"error": "No question provided"}), 400

    logger.info(f"[ASK] Question: {question}")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{ "role": "user", "content": question }],
            temperature=0.5
        )
        reply = response["choices"][0]["message"]["content"]
        return jsonify({ "reply": reply })
    except Exception as e:
        logger.error(f"OpenAI Error in /ask: {e}")
        return jsonify({ "error": "OpenAI request failed" }), 500
