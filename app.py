import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import psycopg2
from psycopg2 import sql, OperationalError
import requests
import base64
import re

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")
openai.api_key = OPENAI_API_KEY

# --- Auth Middleware ---
def check_api_token():
    auth = request.headers.get("Authorization")
    if not auth or auth != f"Bearer {API_AUTH_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

# --- Helper Functions ---
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

def generate_openai_response(symptoms, language, profile):
    prompt = f"""
You are a professional medical assistant. Respond in this language: {language}. The user has this profile: {profile}.
Given the following symptoms:
"{symptoms}"

Please analyze the situation in detail by:

1. Identifying the likely medical condition or physiological issue.
2. Explaining *why* this condition is likely happening based on patient profile, medication, dosage, food habits, or known health issues (reasoning required).
3. Suggesting practical remedies or adjustments the user can make at home.
4. Highlighting if the situation requires urgent care or follow-up.
5. Recommending the most relevant type of doctor or specialist to consult.
6. Extracting and listing any medications mentioned.
7. Returning your answer in structured JSON:
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
        reply = response['choices'][0]['message']['content']
        return reply
    except Exception as e:
        logger.error("OpenAI request failed.")
        return None

def parse_openai_json(reply):
    try:
        return json.loads(reply)
    except json.JSONDecodeError:
        return {
            "medical_analysis": reply,
            "root_cause": "Unknown due to parsing error",
            "remedies": [],
            "urgency": None,
            "medicines": [],
            "suggested_doctor": "general",
            "detected_condition": None
        }

# --- Routes ---
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/emergency", methods=["GET"])
def emergency():
    return jsonify({"call": "911"})

@app.route("/analyze", methods=["POST"])
def analyze():
    auth_error = check_api_token()
    if auth_error:
        return auth_error

    data = request.get_json()
    symptoms = data.get("symptoms")
    language = data.get("language", "English")
    profile = data.get("profile", "")

    if not symptoms:
        return jsonify({"error": "Symptoms are required"}), 400

    raw_reply = generate_openai_response(symptoms, language, profile)
    if not raw_reply:
        return jsonify({"error": "AI response failed"}), 500

    parsed = parse_openai_json(raw_reply)
    return jsonify(parsed)

if __name__ == '__main__':
    app.run(debug=True)
