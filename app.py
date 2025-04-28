import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import psycopg2
from psycopg2 import OperationalError
import requests
import re

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
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

def clean_extracted_text(text):
    patterns_to_remove = [
        r'\bCONFIDENTIAL\b', r'\bCOPY\b', r'\bSAMPLE\b',
        r'\bDRAFT\b', r'\bWATERMARK\b', r'©.*?\n',
        r'\d{4}-\d{2}-\d{2}', r'Page \d+ of \d+',
        r'Patient ID.*?\n', r'Lab ID.*?\n'
    ]
    cleaned = text
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Additional watermark cleaning
    cleaned = re.sub(r'Drlogy.*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'Pathology Laboratory.*', '', cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r'\n+', '\n', cleaned.strip())
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned

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

1. Identify likely medical condition.
2. Explain why it may occur.
3. Recommend remedies.
4. Urgency level.
5. Suggested specialist.
6. Extract medicines.

Return JSON:
{{
  "detected_condition": "...",
  "medical_analysis": "...",
  "root_cause": "...",
  "remedies": ["...", "..."],
  "urgency": "low|moderate|high",
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
        parsed = json.loads(reply)
        parsed["query"] = symptoms
    except Exception as e:
        logger.error(f"OpenAI error or JSON parse error: {e}")
        return jsonify({"error": "AI analysis failed"}), 500

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
                        "image": {"content": image_base64},
                        "features": [{"type": "TEXT_DETECTION"}]
                    }
                ]
            }
        )
        vision_data = vision_response.json()

        if ("responses" not in vision_data or not vision_data["responses"] or
            "fullTextAnnotation" not in vision_data["responses"][0]):
            logger.error(f"Vision API error: {vision_response.text}")
            return jsonify({"error": "Failed to extract text from image"}), 400

        extracted_text = vision_data["responses"][0]["fullTextAnnotation"].get("text", "No text detected")
        cleaned_text = clean_extracted_text(extracted_text)

        return jsonify({"extracted_text": cleaned_text}), 200

    except Exception as e:
        logger.error(f"Vision OCR error: {e}")
        return jsonify({"error": "Failed to process image"}), 500

@app.route("/lab-report", methods=["POST"])
def analyze_lab_report():
    try:
        data = request.json
        image_base64 = data.get("image_base64")

        if not image_base64:
            return jsonify({"error": "Missing image_base64 data"}), 400

        vision_response = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}",
            json={
                "requests": [
                    {
                        "image": {"content": image_base64},
                        "features": [{"type": "TEXT_DETECTION"}]
                    }
                ]
            }
        )

        vision_data = vision_response.json()

        if ("responses" not in vision_data or not vision_data["responses"] or
            "fullTextAnnotation" not in vision_data["responses"][0]):
            logger.error(f"Vision API failed: {vision_response.text}")
            return jsonify({"error": "Failed to extract text from image"}), 500

        extracted_text = vision_data["responses"][0]["fullTextAnnotation"].get("text", "No text detected")
        cleaned_text = clean_extracted_text(extracted_text)

        if not cleaned_text.strip() or cleaned_text == "No text detected":
            return jsonify({"error": "No meaningful text extracted"}), 400

        parsing_prompt = f"""
Extract lab test names and values from the text below:
{cleaned_text}

Return JSON array only:
[
  {{"test": "Glucose", "value": "110 mg/dL"}},
  {{"test": "Creatinine", "value": "1.2 mg/dL"}}
]
"""

        parsing_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": parsing_prompt}],
            temperature=0.1
        )

        parsing_reply = parsing_response['choices'][0]['message']['content']
        start = parsing_reply.find('[')
        end = parsing_reply.rfind(']')
        lab_results_json = parsing_reply[start:end+1]
        lab_results = json.loads(lab_results_json)

        interpretation_prompt = f"""
Analyze these lab results:

{json.dumps(lab_results, indent=2)}

Give:
- Overview
- Abnormal results
- Normal results
- Health summary

Return JSON structured.
"""

        interpretation_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": interpretation_prompt}],
            temperature=0.2
        )

        interpretation_reply = interpretation_response['choices'][0]['message']['content']
        start = interpretation_reply.find('{')
        end = interpretation_reply.rfind('}')
        interpretation_json = interpretation_reply[start:end+1]
        interpretation = json.loads(interpretation_json)

        response_data = {
            "extracted_text": cleaned_text,
            "lab_results": lab_results,
            "interpretation": interpretation,
            "timestamp": datetime.utcnow().isoformat()
        }

        return jsonify(response_data), 200

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
