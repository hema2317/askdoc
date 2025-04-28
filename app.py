import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import psycopg2
import base64
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

def parse_lab_results(text):
    lines = text.split('\n')
    labs = {}
    important_markers = ["LDL", "HDL", "Total Cholesterol", "HbA1c", "Glucose", "Creatinine", "Albumin", "Triglycerides", "eGFR"]
    for line in lines:
        for marker in important_markers:
            if marker.lower() in line.lower():
                parts = line.split()
                value = None
                for part in parts:
                    if any(char.isdigit() for char in part):
                        value = part
                        break
                if value:
                    labs[marker] = value
    return labs

def format_lab_prompt(labs):
    formatted = ", ".join([f"{k}: {v}" for k, v in labs.items()])
    prompt = f"""
The following lab results were extracted:
{formatted}

Analyze them and return JSON with:
- Overview of health
- List of abnormal results (if any)
- Suggested actions
- Urgency level (low, moderate, high)
- Personalized advice

Format exactly as JSON.
"""
    return prompt

@app.route("/lab-report", methods=["POST"])
def analyze_lab_report():
    try:
        data = request.json
        image_base64 = data.get("image_base64")

        if not image_base64:
            return jsonify({"error": "Missing image_base64 data"}), 400

        extracted_text = extract_text_from_image(image_base64)
        lab_results = parse_lab_results(extracted_text)

        if not lab_results:
            return jsonify({"error": "No important lab results found."}), 400

        prompt = format_lab_prompt(lab_results)

        ai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional health assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        reply = ai_response['choices'][0]['message']['content']
        start = reply.find('{')
        end = reply.rfind('}')
        interpretation = json.loads(reply[start:end+1])

        result_to_save = {
            "overview": interpretation.get("overview", ""),
            "abnormalities": interpretation.get("abnormal_results", []),
            "suggested_actions": interpretation.get("suggested_actions", []),
            "urgency": interpretation.get("urgency", ""),
            "advice": interpretation.get("personalized_advice", "")
        }

        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO lab_reports (interpretation, created_at)
                    VALUES (%s, %s)
                """, (
                    json.dumps(result_to_save),
                    datetime.utcnow()
                ))
                conn.commit()
                cursor.close()
            except Exception as e:
                logger.error(f"DB insert error for lab report: {e}")
            finally:
                conn.close()

        return jsonify({
            "lab_results": lab_results,
            "interpretation": result_to_save,
            "timestamp": datetime.utcnow().isoformat()
        }), 200

    except Exception as e:
        logger.error(f"Lab report analysis crashed: {str(e)}")
        return jsonify({"error": "Server error during lab report analysis"}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/emergency", methods=["GET"])
def emergency():
    return jsonify({"call": "911"})

if __name__ == '__main__':
    app.run(debug=True)
