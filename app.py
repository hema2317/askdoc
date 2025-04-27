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
import re  # <- (You were using re.match without importing re)

app = Flask(__name__)

# 🚨 Fixed CORS setup
CORS(app, resources={r"/*": {"origins": "*"}})

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
openai.api_key = OPENAI_API_KEY

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
        logger.error(f"OpenAI error: {e}")
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

# --- API Routes ---

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    symptoms = data.get("symptoms", "")
    location = data.get("location", {})
    language = data.get("language", "English")
    profile = data.get("profile", "")

    if not symptoms:
        return jsonify({"error": "Symptoms required"}), 400

    prompt = f"""
You are a professional medical assistant. Respond in this language: {language}. The user has this profile: {profile}.
Given the following symptoms:
"{symptoms}"

1. Identify the likely medical condition.
2. Explain why this condition may be occurring in this specific patient (consider age, profile, habits, chronic diseases, etc.).
3. Recommend simple remedies or next steps.
4. Highlight if the situation requires urgent care.
5. Suggest a relevant medical specialist.
6. If any medicine is mentioned, extract it.
7. Return structured JSON with: detected_condition, medical_analysis, root_cause, remedies (array), urgency, suggested_doctor, medicines (array)
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
        parsed = json.loads(reply)
        parsed["query"] = symptoms
    except Exception as e:
        logger.error(f"OpenAI error or JSON parse error: {e}")
        return jsonify({"error": "AI analysis failed"}), 500

    # Save to database
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

    # Fetch nearby doctors
    if location and parsed.get("suggested_doctor"):
        try:
            doc_response = requests.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={
                    "location": f"{location.get('lat')},{location.get('lng')}",
                    "radius": 5000,
                    "keyword": f"{parsed.get('suggested_doctor')} doctor",
                    "key": GOOGLE_API_KEY
                }
            )
            parsed["doctors"] = doc_response.json().get("results", [])[:5]
        except Exception as e:
            logger.error(f"Google API error: {e}")
            parsed["doctors"] = []

    return jsonify(parsed), 200
@app.route("/vision", methods=["POST"])
def vision_ocr():
    data = request.json
    image_base64 = data.get("image_base64")

    if not image_base64:
        return jsonify({"error": "Missing image_base64 data"}), 400

    try:
        vision_response = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}",
            json={
                "requests": [
                    {
                        "image": {
                            "content": image_base64
                        },
                        "features": [
                            {
                                "type": "TEXT_DETECTION"
                            }
                        ]
                    }
                ]
            }
        )
        vision_data = vision_response.json()
        extracted_text = vision_data["responses"][0].get("fullTextAnnotation", {}).get("text", "No text detected")
        return jsonify({"extracted_text": extracted_text}), 200

    except Exception as e:
        logger.error(f"Google Vision API error: {e}")
        return jsonify({"error": "Failed to process image with Vision API"}), 500

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

@app.route("/appointments", methods=["POST"])
def book_appointment():
    data = request.json
    name = data.get("name")
    doctor = data.get("doctor")
    date = data.get("date")

    if not all([name, doctor, date]):
        return jsonify({"error": "Missing name, doctor or date"}), 400

    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO appointments (patient_name, doctor_name, appointment_date, created_at)
                VALUES (%s, %s, %s, %s)
            """, (name, doctor, date, datetime.utcnow()))
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"DB insert error: {e}")
            return jsonify({"error": "Failed to book appointment"}), 500
        finally:
            conn.close()

    return jsonify({"status": "Appointment booked"})

@app.route("/lab-report", methods=["POST"])
def analyze_lab_report():
    data = request.json
    image_base64 = data.get("image_base64")

    if not image_base64:
        return jsonify({"error": "Missing image_base64 data"}), 400

    try:
        # OCR Step
        vision_response = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}",
            json={
                "requests": [
                    {
                        "image": {
                            "content": image_base64
                        },
                        "features": [
                            {
                                "type": "TEXT_DETECTION"
                            }
                        ]
                    }
                ]
            }
        )
        vision_data = vision_response.json()
        extracted_text = vision_data["responses"][0].get("fullTextAnnotation", {}).get("text", "No text detected")
        
        if not extracted_text.strip() or extracted_text == "No text detected":
            return jsonify({"error": "No text detected from lab report."}), 400
        
        # 💬 Ask OpenAI to parse the extracted text
        prompt = f"""
You are a professional medical assistant.

Given the following extracted lab report text:

{extracted_text}

Extract the important test names and values into structured JSON like this:

[
  {{"test": "Glucose", "value": "120 mg/dL"}},
  {{"test": "Creatinine", "value": "1.2 mg/dL"}},
  ...
]

Only include real lab test results. Ignore headers or random notes.
"""

        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful health assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
        )

        lab_results_text = openai_response['choices'][0]['message']['content']
        lab_results = json.loads(lab_results_text)

        response_data = {
            "extracted_text": extracted_text,
            "lab_results": lab_results,
            "timestamp": datetime.utcnow().isoformat()
        }

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"Lab report analysis error: {e}")
        return jsonify({"error": "Failed to analyze lab report."}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/emergency", methods=["GET"])
def emergency():
    return jsonify({"call": "911"})

if __name__ == '__main__':
    app.run(debug=True)
