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
                                "type": "DOCUMENT_TEXT_DETECTION"
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
    profile = data.get("profile", {})

    if not image_base64:
        logger.error("Missing image_base64 in request")
        return jsonify({"error": "Missing image_base64 data"}), 400

    try:
        # 1. Enhanced OCR with preprocessing hints
        vision_response = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}",
            json={
                "requests": [
                    {
                        "image": {"content": image_base64},
                        "features": [{
                            "type": "DOCUMENT_TEXT_DETECTION",
                            "model": "builtin/latest"  # Use latest OCR model
                        }],
                        "imageContext": {
                            "textDetectionParams": {
                                "enableTextDetectionConfidenceScore": True,
                                "advancedOcrOptions": ["legacy_layout"]
                            }
                        }
                    }
                ]
            },
            timeout=30  # Increased timeout for complex images
        )
        
        if vision_response.status_code != 200:
            logger.error(f"Vision API error: {vision_response.text}")
            return jsonify({"error": "Vision API failed to process image"}), 500
            
        vision_data = vision_response.json()

        if not vision_data.get("responses"):
            logger.error("Vision API error: No responses field")
            return jsonify({"error": "Failed to process image"}), 400

        # Get full text or fallback to concatenated words
        full_text_annotation = vision_data["responses"][0].get("fullTextAnnotation", {})
        if full_text_annotation:
            extracted_text = full_text_annotation.get("text", "")
            # Calculate average confidence score
            confidences = []
            for page in full_text_annotation.get("pages", []):
                for block in page.get("blocks", []):
                    for paragraph in block.get("paragraphs", []):
                        for word in paragraph.get("words", []):
                            if "confidence" in word:
                                confidences.append(word["confidence"])
            avg_confidence = sum(confidences)/len(confidences) if confidences else 0
        else:
            # Fallback to concatenating detected text
            extracted_text = " ".join([
                annotation.get("description", "")
                for annotation in vision_data["responses"][0].get("textAnnotations", [{}])[1:]  # Skip first element (whole text)
            ])
            avg_confidence = 0.5  # Default confidence for fallback

        # 2. Text cleaning and watermark removal
        cleaned_text = extracted_text
        
        # Remove common watermarks and non-relevant text
        watermark_patterns = [
            r"(?i)\b(?:confidential|sample|draft|copy|watermark|©|©.*?)\b",
            r"\b\d{4}-\d{2}-\d{2}\b",  # Dates that might be part of watermark
            r"Page \d+ of \d+",
            r"Lab ID:.*?\n",
            r"Patient ID:.*?\n"
        ]
        
        for pattern in watermark_patterns:
            cleaned_text = re.sub(pattern, "", cleaned_text)
        
        # Remove excessive whitespace
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text.strip())

        # 3. Parse lab tests with enhanced error handling
        parsing_prompt = f"""You are an expert medical lab analyst. Extract test results from this lab report:

PATIENT PROFILE (for reference):
{json.dumps(profile, indent=2)}

LAB REPORT TEXT:
{cleaned_text}

Instructions:
1. Extract ALL test names and values
2. Standardize test names (e.g., "Hb" → "Hemoglobin")
3. Include units and reference ranges when available
4. Mark abnormal values based on reference ranges
5. Ignore any remaining watermarks or headers

Return ONLY valid JSON format:
{{
  "results": [
    {{
      "test": "Standardized Test Name",
      "value": "measured value",
      "units": "unit of measurement",
      "range": "reference range if available",
      "status": "normal/abnormal/high/low"
    }}
  ],
  "metadata": {{
    "confidence": {avg_confidence},
    "text_length": {len(cleaned_text)},
    "watermark_detected": {"true" if "watermark" in extracted_text.lower() else "false"}
  }}
}}"""

        parsing_response = openai.ChatCompletion.create(
            model="gpt-4",  # Use GPT-4 for better extraction
            messages=[{"role": "user", "content": parsing_prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        try:
            lab_results = json.loads(parsing_response.choices[0].message.content)
            if not lab_results.get("results"):
                raise ValueError("No results extracted")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse lab results: {e}")
            return jsonify({"error": "Failed to extract lab data", "extracted_text": cleaned_text}), 400

        # 4. Enhanced interpretation with medical context
        interpretation_prompt = {
            "role": "system",
            "content": f"""You are a medical specialist analyzing lab results for this patient:
{json.dumps(profile, indent=2)}

Consider their medical history when interpreting results."""
        }

        interpretation_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                interpretation_prompt,
                {
                    "role": "user",
                    "content": f"""Analyze these lab results:
{json.dumps(lab_results['results'], indent=2)}

Provide:
1. Overall health assessment
2. Detailed analysis of abnormal results
3. Clinical recommendations
4. Follow-up suggestions

Return structured JSON with:
{{
  "overview": "...",
  "abnormal_results": [{{"test": "...", "interpretation": "...", "urgency": "low/medium/high", "recommendation": "..."}}],
  "normal_results": ["..."],
  "summary": "...",
  "next_steps": ["..."],
  "clinical_notes": "..."
}}"""
                }
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        interpretation = json.loads(interpretation_response.choices[0].message.content)

        # 5. Compile final response
        response_data = {
            "extracted_text": cleaned_text,
            "lab_results": lab_results["results"],
            "interpretation": interpretation,
            "confidence": avg_confidence,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": lab_results.get("metadata", {})
        }

        # Save to database if needed
        if DATABASE_URL:
            try:
                conn = psycopg2.connect(DATABASE_URL)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO lab_reports 
                    (patient_id, raw_text, analysis, created_at) 
                    VALUES (%s, %s, %s, %s)
                    """, 
                    (profile.get("id"), cleaned_text, json.dumps(response_data), datetime.utcnow())
                conn.commit()
            except Exception as db_error:
                logger.error(f"Database error: {db_error}")
            finally:
                if conn:
                    conn.close()

        return jsonify(response_data), 200

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return jsonify({"error": "Service temporarily unavailable"}), 503
    except Exception as e:
        logger.error(f"Lab analysis error: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Failed to analyze lab report",
            "detail": str(e)
        }), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/emergency", methods=["GET"])
def emergency():
    return jsonify({"call": "911"})

if __name__ == '__main__':
    app.run(debug=True)
