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

def check_api_token():
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {API_AUTH_TOKEN}":
        logger.warning(f"Unauthorized access attempt: Header={auth_header}, Expected={API_AUTH_TOKEN}")
        return jsonify({"error": "Unauthorized"}), 401
    return None

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

def get_nearby_doctors(specialty, location):
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY is not set for Places API.")
        return []

    try:
        lat, lng = location.split(",")
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "keyword": f"{specialty} doctor",
            "location": f"{lat},{lng}",
            "radius": 10000,
            "type": "doctor",
            "key": GOOGLE_API_KEY
        }
        response = requests.get(url, params=params)
        response.raise_for_status()

        results = response.json().get("results", [])
        filtered_results = [p for p in results if p.get("rating") is not None]
        sorted_results = sorted(
            filtered_results,
            key=lambda x: (x.get("rating", 0), x.get("user_ratings_total", 0)),
            reverse=True
        )

        doctors = []
        for place in sorted_results[:5]:
            doctors.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "user_ratings_total": place.get("user_ratings_total"),
                "open_now": place.get("opening_hours", {}).get("open_now", False),
                "maps_link": f"https://www.google.com/maps/search/?api=1&query={place.get('name')},{place.get('vicinity')}&query_place_id={place.get('place_id')}"
            })
        return doctors
    except requests.exceptions.RequestException as e:
        logger.error(f"Google Maps API request failed: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching nearby doctors: {e}")
        return []
@app.route("/analyze", methods=["POST"])
def analyze_symptoms():
    token_error = check_api_token()
    if token_error:
        return token_error

    try:
        data = request.json
        symptoms = data.get("symptoms", "").strip()
        profile = data.get("profile", {})
        location = data.get("location", {})
        language = data.get("language", "English")

        if not symptoms:
            return jsonify({"error": "Missing symptoms"}), 400

        # Construct profile context
        profile_context = build_profile_context(profile)
        prompt = f"""You are a medical assistant. The patient's context is:\n{profile_context}\n\nThey reported the following symptoms:\n{symptoms}\n\nAnalyze this and respond with:\n- Possible medical condition\n- Suggested remedy\n- Urgency level\n- Doctor to see\nBe brief and medically sound."""

        logger.info("[ANALYZE] Sending prompt to OpenAI...")

        openai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful medical assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=400
        )

        reply = openai_response.choices[0].message.content.strip()
        logger.info(f"[ANALYZE] AI replied:\n{reply}")

        # Extract summary
        detected_condition = extract_condition(reply)
        suggested_doctor = extract_doctor(reply)
        remedy = extract_remedy(reply)
        urgency = extract_urgency(reply)

        nearby_doctors = []
        if location and "lat" in location and "lng" in location:
            lat = location["lat"]
            lng = location["lng"]
            doctor_type = suggested_doctor or "general"
            logger.info(f"[ANALYZE] Fetching doctors for: {doctor_type} near {lat}, {lng}")
            nearby_doctors = get_nearby_doctors(doctor_type, f"{lat},{lng}")
        else:
            logger.warning("[ANALYZE] Missing location data")

        return jsonify({
            "detected_condition": detected_condition,
            "suggested_doctor": suggested_doctor,
            "remedy": remedy,
            "urgency": urgency,
            "medical_analysis": reply,
            "nearby_doctors": nearby_doctors
        })

    except Exception as e:
        logger.exception("[ANALYZE] Failed to process")
        return jsonify({"error": str(e)}), 500

@app.route('/api/doctors')
def doctors_endpoint():
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    specialty = request.args.get('specialty', 'general')

    if not lat or not lng:
        return jsonify({"error": "Missing lat/lng"}), 400

    location = f"{lat},{lng}"
    results = get_nearby_doctors(specialty, location)
    return jsonify(results)

# ... all existing functions and routes remain unchanged after this

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  
    app.run(host='0.0.0.0', port=port)
