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

def clean_extracted_text(text):
    patterns_to_remove = [
        r'\\bCONFIDENTIAL\\b', r'\\bCOPY\\b', r'\\bSAMPLE\\b',
        r'\\bDRAFT\\b', r'\\bWATERMARK\\b', r'©.*?\\n',
        r'\\d{4}-\\d{2}-\\d{2}', r'Page \\d+ of \\d+',
        r'Patient ID.*?\\n', r'Lab ID.*?\\n'
    ]
    cleaned = text
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\\n+', '\\n', cleaned.strip())
    cleaned = re.sub(r'\\s+', ' ', cleaned)
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
                        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]
                    }
                ]
            }
        )
        vision_data = vision_response.json()

        if ("responses" not in vision_data or not vision_data["responses"] or
            "fullTextAnnotation" not in vision_data["responses"][0]):
            logger.error("Vision API error: No fullTextAnnotation")
            return jsonify({"error": "Failed to extract text from image"}), 400

        extracted_text = vision_data["responses"][0]["fullTextAnnotation"].get("text", "No text detected")
        cleaned_text = clean_extracted_text(extracted_text)

        return jsonify({"extracted_text": cleaned_text}), 200

    except Exception as e:
        logger.error(f"Vision OCR error: {e}")
        return jsonify({"error": "Failed to process image"}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/emergency", methods=["GET"])
def emergency():
    return jsonify({"call": "911"})

if __name__ == '__main__':
    app.run(debug=True)
