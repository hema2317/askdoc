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

@app.route("/lab-report", methods=["POST"])
def analyze_lab_report():
    try:
        data = request.json
        image_base64 = data.get("image_base64")

        if not image_base64:
            return jsonify({"error": "Missing image_base64 data"}), 400

        # Enhanced AI prompt for lab report interpretation
        parsing_prompt = """
The patient has submitted a lab report.
Analyze these results carefully and provide:
- Overall health overview
- Normal and abnormal lab test results
- What abnormal results may indicate
- Personalized advice (e.g., dietary changes, physical activity, hydration)
- Whether to immediately see a doctor or monitor at home
- Short, clear guidance for doctors to act quickly
Return response in JSON format.
"""

        parsing_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": parsing_prompt}],
            temperature=0.2
        )

        interpretation_reply = parsing_response['choices'][0]['message']['content']
        start = interpretation_reply.find('{')
        end = interpretation_reply.rfind('}')
        interpretation_json = interpretation_reply[start:end+1]
        interpretation = json.loads(interpretation_json)

        response_data = {
            "interpretation": interpretation,
            "timestamp": datetime.utcnow().isoformat()
        }

        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO lab_reports (interpretation, created_at)
                    VALUES (%s, %s)
                """, (
                    json.dumps(interpretation),
                    datetime.utcnow()
                ))
                conn.commit()
                cursor.close()
            except Exception as e:
                logger.error(f"DB insert error for lab report: {e}")
            finally:
                conn.close()

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
