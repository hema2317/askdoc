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

def parse_lab_results_with_ai(text):
    prompt = f"""
You are a medical lab assistant.

You will be given raw text extracted from a lab report (it could be blood work, urine work, pathology, biopsy, imaging reports like MRI or X-ray, etc.).

Please do the following:

1. Identify all test names and their corresponding values.
2. Organize them into JSON format.
3. Include a field called 'type_of_report' (example: KFT, LFT, MRI, Urinalysis, etc.) based on best guess.
4. If possible, flag any abnormal values (just basic based on text, not detailed interpretation).

The text is:

{text}

Respond ONLY with JSON in this format:

{{
    "type_of_report": "Kidney Function Test (KFT)",
    "tests": [
        {{"name": "Urea", "value": "16.00 mg/dL"}},
        {{"name": "Creatinine", "value": "0.90 mg/dL"}},
        ...
    ],
    "abnormal_tests": [
        {{"name": "Creatinine", "value": "High"}}
    ]
}}
"""
    ai_response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a smart medical AI assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    reply = ai_response['choices'][0]['message']['content']
    start = reply.find('{')
    end = reply.rfind('}')
    parsed_result = json.loads(reply[start:end+1])
    return parsed_result
    
@app.route("/lab-report", methods=["POST"])
def analyze_lab_report():
    try:
        data = request.json
        image_base64 = data.get("image_base64")

        if not image_base64:
            return jsonify({"error": "Missing image_base64 data"}), 400

        extracted_text = extract_text_from_image(image_base64)
        parsed_lab_data = parse_lab_results_with_ai(extracted_text)

        if not parsed_lab_data:
            return jsonify({"error": "Lab report parsing failed."}), 400

        result_to_save = {
            "type_of_report": parsed_lab_data.get("type_of_report", ""),
            "tests": parsed_lab_data.get("tests", []),
            "abnormal_tests": parsed_lab_data.get("abnormal_tests", [])
        }

        # Save into database if available
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
            "parsed_lab_data": result_to_save,
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
