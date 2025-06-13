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
    auth = request.headers.get("Authorization")
    if not auth or auth != f"Bearer {API_AUTH_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None
def build_profile_context(profile_json):
    try:
        profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
    except Exception:
        return "No additional profile context available."

    lines = []
    if name := profile.get("name"):
        lines.append(f"Name: {name}")
    if dob := profile.get("dob"):
        age = calculate_age(dob)
        lines.append(f"Age: {age}")
    if gender := profile.get("gender"):
        lines.append(f"Gender: {gender}")
    if blood := profile.get("blood_type"):
        lines.append(f"Blood Type: {blood}")
    if state := profile.get("state"):
        lines.append(f"State: {state}")
    if known := profile.get("known_diseases"):
        lines.append("Known Diseases: " + ", ".join(known))
    if family := profile.get("family_history"):
        lines.append("Family History: " + ", ".join(family))
    if smoking := profile.get("smoking"):
        lines.append("Smoking Habits: " + ", ".join(smoking))
    if exercise := profile.get("exercise"):
        lines.append("Exercise Habits: " + ", ".join(exercise))

    return "\n".join(lines)

def calculate_age(dob_str):
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d")
        today = datetime.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return "Unknown"

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
    profile_context = build_profile_context(profile)
    reply = generate_openai_response(symptoms, language, profile_context)

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

@app.route("/photo-analyze", methods=["POST"])
def analyze_photo():
    auth = check_api_token()
    if auth:
        return auth

    data = request.get_json()
    logger.info(f"📸 /photo-analyze request: {data.keys()}")

    image_base64 = data.get("image_base64")
    if not image_base64:
        return jsonify({"error": "Missing image"}), 400

    labels = get_image_labels(image_base64)
    logger.info(f"🧠 Labels from Vision API: {labels}")

    prompt = f"This image likely shows: {', '.join(labels)}. Provide diagnosis as a medical assistant."
    reply = generate_openai_response(prompt, "English", build_profile_context("Photo-based analysis"))
    parsed = parse_openai_json(reply)
    parsed["image_labels"] = labels
    return jsonify(parsed)

@app.route("/analyze-lab-report", methods=["POST"])
def analyze_lab_report():
    auth = check_api_token()
    if auth:
        return auth

    data = request.get_json()
    image_base64 = data.get("image_base64")
    extracted_text = data.get("extracted_text", "")
    location = data.get("location", "")
    profile = data.get("profile", "")
    language = data.get("language", "English")

    if not extracted_text and not image_base64:
        return jsonify({"error": "Missing lab report text or image"}), 400

    # If text not provided, extract from image
    if not extracted_text and image_base64:
        try:
            url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
            body = {
                "requests": [{
                    "image": {"content": image_base64},
                    "features": [{"type": "TEXT_DETECTION"}]
                }]
            }
            res = requests.post(url, json=body)
            annotations = res.json()["responses"][0]
            extracted_text = annotations.get("fullTextAnnotation", {}).get("text", "")
            if not extracted_text:
                return jsonify({"error": "OCR failed to extract text"}), 500
        except Exception as e:
            logger.error(f"Vision OCR error: {e}")
            return jsonify({"error": "OCR processing failed"}), 500

    logger.info("🧪 /analyze-lab-report analyzing extracted lab report text")
    profile_context = build_profile_context(profile)
    reply = generate_openai_response(extracted_text, language, profile_context)

    if not reply:
        return jsonify({"error": "OpenAI failed"}), 500

    parsed = parse_openai_json(reply)

    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)

    parsed["extracted_text"] = extracted_text
    return jsonify(parsed)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000)) 
    app.run(host='0.0.0.0', port=port)

