import os
import json
import logging
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import requests
import psycopg2
from psycopg2 import OperationalError

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
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer ") or auth.split(" ")[1] != API_AUTH_TOKEN:
        logger.warning(f"Unauthorized access attempt. Auth header: {auth}")
        return jsonify({"error": "Unauthorized"}), 401
    return None

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

def generate_openai_response(prompt_content, language, profile_data):
    profile_str = json.dumps(profile_data) if isinstance(profile_data, dict) else str(profile_data)

    system_message = {
        "role": "system",
        "content": f"You are a professional medical assistant. Respond ONLY in {language}. Return valid JSON inside triple backticks."
    }

    user_message = {
        "role": "user",
        "content": f"Patient profile:\n{profile_str}\n\nQuery/Symptoms/Report:\n{prompt_content}"
    }

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[system_message, user_message],
            temperature=0.4
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"OpenAI request failed: {e}")
        return None

def parse_openai_json(reply):
    try:
        match = re.search(r'json\s*(\{.*?\})\s*', reply, re.DOTALL)
        json_str = match.group(1) if match else reply
        parsed = json.loads(json_str)

        default_keys = {
            "detected_condition": "Unspecified",
            "medical_analysis": reply or "No analysis provided.",
            "root_cause": "Not identified",
            "remedies": [],
            "urgency": "low",
            "medicines": [],
            "suggested_doctor": "General Practitioner",
            "good_results": [],
            "bad_results": [],
            "actionable_advice": [],
            "image_description": ""
        }

        for key, default_value in default_keys.items():
            if key not in parsed:
                parsed[key] = default_value
            if isinstance(default_value, list) and not isinstance(parsed[key], list):
                parsed[key] = [str(parsed[key])] if parsed[key] else []

        return parsed
    except Exception as e:
        logger.error(f"Parsing error: {e}")
        return default_keys

def get_nearby_doctors(specialty, location):
    try:
        if not re.fullmatch(r"^-?\d+.?\d*,-?\d+.?\d*$", str(location)):
            logger.warning(f"Invalid location format: '{location}'")
            return []

        lat, lng = location.split(",")
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "keyword": f"{specialty} doctor",
            "location": f"{lat},{lng}",
            "radius": 10000,
            "type": "doctor",
            "key": GOOGLE_API_KEY,
            "rankby": "prominence"
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json().get("results", [])

        sorted_results = sorted(results, key=lambda x: x.get("rating", 0) if isinstance(x.get("rating"), (int, float)) else 0, reverse=True)
        
        doctors = []
        for place in sorted_results[:5]:
            maps_link = f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(place.get('name', '') + ' ' + place.get('vicinity', ''))}&query_place_id={place.get('place_id', '')}"
            
            doctors.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "open_now": place.get("opening_hours", {}).get("open_now", "N/A"),
                "maps_link": maps_link
            })
        return doctors
    except Exception as e:
        logger.error(f"Google Maps API error: {e}")
        return []

def get_image_text_and_labels(base64_image):
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [{
                "image": {"content": base64_image},
                "features": [
                    {"type": "TEXT_DETECTION"},
                    {"type": "LABEL_DETECTION", "maxResults": 10}
                ]
            }]
        }
        res = requests.post(url, json=body)
        res.raise_for_status()
        response_data = res.json()["responses"][0]

        full_text = response_data.get("fullTextAnnotation", {}).get("text", "")
        labels = [label['description'] for label in response_data.get("labelAnnotations", [])]

        return full_text, labels
    except Exception as e:
        logger.error(f"Vision API error: {e}")
        return "", []

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/analyze", methods=["POST"])
def analyze():
    auth_response = check_api_token()
    if auth_response:
        return auth_response

    data = request.json
    symptoms = data.get("symptoms", "")
    language = data.get("language", "English")
    profile_data = data.get("profile", {})
    location = data.get("location", "")

    reply = generate_openai_response(symptoms, language, profile_data)
    if not reply:
        return jsonify({"error": "OpenAI failed"}), 500

    parsed = parse_openai_json(reply)
    parsed["type"] = "symptom_analysis"

    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)

    return jsonify(parsed)

@app.route("/photo-analyze", methods=["POST"])
def analyze_photo():
    auth_response = check_api_token()
    if auth_response:
        return auth_response

    data = request.get_json()
    image_base64 = data.get("image_base64")
    profile_data = data.get("profile", {})
    location = data.get("location", "")

    if not image_base64:
        return jsonify({"error": "Missing image"}), 400

    image_text, labels = get_image_text_and_labels(image_base64)
    symptoms_prompt = f"Analyze this image. "
    if labels:
        symptoms_prompt += f"Image likely shows: {', '.join(labels)}. "
    if image_text:
        symptoms_prompt += f"Detected text in image: {image_text}. "

    reply = generate_openai_response(symptoms_prompt, "English", profile_data)
    if not reply:
        return jsonify({"error": "OpenAI failed"}), 500

    parsed = parse_openai_json(reply)
    parsed["image_labels"] = labels
    parsed["image_text_detected"] = image_text
    parsed["type"] = "photo_analysis"

    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)

    return jsonify(parsed)

@app.route("/analyze-lab-report", methods=["POST"])
def analyze_lab_report():
    auth_response = check_api_token()
    if auth_response:
        return auth_response

    data = request.get_json()
    image_base64 = data.get("image_base64")
    profile_data = data.get("profile", {})
    location = data.get("location", "")

    if not image_base64:
        return jsonify({"error": "Missing lab report image"}), 400

    full_text, labels = get_image_text_and_labels(image_base64)
    if not full_text:
        return jsonify({"error": "Could not extract text from image"}), 400

    prompt = f"Analyze this lab report:\nPatient profile: {json.dumps(profile_data)}\nReport Text:\n{full_text}"
    reply = generate_openai_response(prompt, "English", profile_data)
    if not reply:
        return jsonify({"error": "OpenAI failed"}), 500

    parsed = parse_openai_json(reply)
    parsed["type"] = "lab_report"

    if "detected_condition" not in parsed:
        parsed["detected_condition"] = parsed.get("medical_analysis", "Lab Report Analysis").split('.')[0]

    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)

    return jsonify(parsed)

if __name__ == '__main__':
    app.run(debug=True)
