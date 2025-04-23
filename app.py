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

app = Flask(__name__)
CORS(app)

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
openai.api_key = OPENAI_API_KEY

# --- Helper Functions ---
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

def generate_openai_response(symptoms):
    prompt = f"""
You are a professional medical assistant. Given the following symptoms:

"{symptoms}"

1. Identify the likely medical condition or issue.
2. Recommend simple remedies if applicable.
3. Highlight if the situation requires urgent care.
4. Suggest a relevant medical specialist.
5. If any medicine is mentioned, extract it.
6. Return everything in a structured JSON with fields: detected_condition, medical_analysis, remedies (array), urgency, suggested_doctor, medicines (array)
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful health assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )
        reply = response['choices'][0]['message']['content']
        return reply
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return None

def parse_openai_json(reply):
    try:
        return json.loads(reply)
    except json.JSONDecodeError:
        return {
            "medical_analysis": reply,
            "remedies": [],
            "urgency": None,
            "medicines": [],
            "suggested_doctor": "general",
            "detected_condition": None
        }

# --- API Routes ---
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    symptoms = data.get("symptoms", "")
    location = data.get("location", {})
    if not symptoms:
        return jsonify({"error": "Symptoms required"}), 400

    ai_raw_reply = generate_openai_response(symptoms)
    if not ai_raw_reply:
        return jsonify({"error": "Failed to fetch AI analysis"}), 500

    parsed = parse_openai_json(ai_raw_reply)
    parsed["query"] = symptoms

    # Save history in DB
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO medical_analyses (query, analysis, detected_condition, medicines, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                symptoms,
                parsed.get("medical_analysis"),
                parsed.get("detected_condition"),
                json.dumps(parsed.get("medicines", [])),
                datetime.utcnow()
            ))
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"DB insert error: {e}")
        finally:
            conn.close()

    return jsonify(parsed), 200

@app.route("/api/doctors", methods=["GET"])
def get_doctors():
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    specialty = request.args.get("specialty", "general")

    if not lat or not lng or not GOOGLE_API_KEY:
        return jsonify({"error": "Missing required parameters or API key"}), 400

    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params={
                "location": f"{lat},{lng}",
                "radius": 5000,
                "keyword": f"{specialty} doctor",
                "key": GOOGLE_API_KEY
            }
        )
        results = response.json().get("results", [])
        doctors = [
            {
                "name": r.get("name"),
                "phone": r.get("formatted_phone_number", "N/A"),
                "rating": r.get("rating"),
                "address": r.get("vicinity")
            } for r in results[:10]
        ]
        return jsonify({"doctors": doctors})
    except Exception as e:
        logger.error(f"Google Places API error: {e}")
        return jsonify({"doctors": []}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/emergency", methods=["GET"])
def emergency():
    return jsonify({"call": "911"})

if __name__ == '__main__':
    app.run(debug=True)
