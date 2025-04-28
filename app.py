import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import psycopg2
import requests

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
openai.api_key = OPENAI_API_KEY

# --- Helper Functions ---

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

def extract_text_from_image(base64_image):
    try:
        vision_url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [
                {
                    "image": {"content": base64_image},
                    "features": [{"type": "TEXT_DETECTION"}]
                }
            ]
        }
        response = requests.post(vision_url, json=body)
        response.raise_for_status()
        text = response.json()['responses'][0]['fullTextAnnotation']['text']
        return text
    except Exception as e:
        logger.error(f"Google Vision OCR failed: {e}")
        raise

def parse_lab_results_with_ai(text):
    prompt = f"""
You are a medical lab assistant with expertise in interpreting laboratory reports.

Analyze the following extracted text from a lab report:

{text}

Respond ONLY in JSON format:
- type_of_report
- tests (name, value, unit, normal range, status: normal/high/low)
- abnormal_tests (name, reason)
- clinical_interpretation (summary, potential_conditions, recommendations)
- red_flags
"""
    try:
        ai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a highly skilled medical lab report interpreter."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000
        )
        reply = ai_response['choices'][0]['message']['content']
        start = reply.find('{')
        end = reply.rfind('}')
        parsed_result = json.loads(reply[start:end+1])
        return parsed_result
    except Exception as e:
        logger.error(f"AI interpretation failed: {e}")
        raise

# --- Routes ---

@app.route("/lab-report", methods=["POST"])
def analyze_lab_report():
    try:
        data = request.json
        image_base64 = data.get("image_base64")

        if not image_base64:
            return jsonify({"error": "Missing image_base64 data"}), 400

        extracted_text = extract_text_from_image(image_base64)
        parsed_lab_data = parse_lab_results_with_ai(extracted_text)

        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO lab_reports (interpretation, created_at) VALUES (%s, %s)",
                    (json.dumps(parsed_lab_data), datetime.utcnow())
                )
                conn.commit()
                cursor.close()
            except Exception as e:
                logger.error(f"DB insert error for lab report: {e}")
            finally:
                conn.close()

        return jsonify({
            "parsed_lab_data": parsed_lab_data,
            "timestamp": datetime.utcnow().isoformat()
        }), 200

    except Exception as e:
        logger.error(f"Lab report analysis crashed: {str(e)}")
        return jsonify({"error": "Server error during lab report analysis"}), 500

@app.route("/analyze", methods=["POST"])
def analyze_symptoms():
    try:
        data = request.json
        symptoms = data.get("symptoms", "")
        profile = data.get("profile", {})

        if not symptoms:
            return jsonify({"error": "Symptoms missing"}), 400

        prompt = f"""
You are a professional medical AI with expertise in internal medicine. User profile:
{json.dumps(profile, indent=2)}

Analyze these symptoms:
"{symptoms}"

Respond ONLY in JSON format:
- possible_causes
- suggested_remedies
- urgency_level (normal / moderate / emergency)
- suggested_doctor_type
"""

        ai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a skilled medical AI assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        reply = ai_response['choices'][0]['message']['content']
        start = reply.find('{')
        end = reply.rfind('}')
        parsed_response = json.loads(reply[start:end+1])

        return jsonify(parsed_response), 200

    except Exception as e:
        logger.error(f"Symptom analysis failed: {e}")
        return jsonify({"error": "Server error during symptom analysis"}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/emergency", methods=["GET"])
def emergency():
    return jsonify({"call": "911"})

# --- Main Entry Point ---

if __name__ == '__main__':
    app.run(debug=True)
