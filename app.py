
import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask\_cors import CORS
import openai
import psycopg2
from psycopg2 import sql, OperationalError
import requests
import base64
import re  # <- (You were using re.match without importing re)

app = Flask(**name**)

# 🚨 Fixed CORS setup

CORS(app, resources={r"/*": {"origins": "*"}})

# Logging setup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(**name**)

# Environment Variables

OPENAI\_API\_KEY = os.getenv("OPENAI\_API\_KEY")
DATABASE\_URL = os.getenv("DATABASE\_URL")
GOOGLE\_API\_KEY = os.getenv("GOOGLE\_API\_KEY")
GOOGLE\_VISION\_API\_KEY = os.getenv("GOOGLE\_VISION\_API\_KEY")
openai.api\_key = OPENAI\_API\_KEY

# --- Helper Functions ---

def get\_db\_connection():
try:
conn = psycopg2.connect(DATABASE\_URL, sslmode='require')
return conn
except OperationalError as e:
logger.error(f"Database connection failed: {e}")
return None

def generate\_openai\_response(symptoms, language, profile):
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
   "detected\_condition": "...",
   "medical\_analysis": "...",
   "root\_cause": "...",
   "remedies": \["...", "..."],
   "urgency": "low | moderate | high",
   "suggested\_doctor": "...",
   "medicines": \["..."]
   }}
   """
   try:
   response = openai.ChatCompletion.create(
   model="gpt-3.5-turbo",
   messages=\[
   {"role": "system", "content": "You are a helpful multilingual health assistant."},
   {"role": "user", "content": prompt}
   ],
   temperature=0.4
   )
   reply = response\['choices']\[0]\['message']\['content']
   return reply
   except Exception as e:
   logger.error("OpenAI request failed.")
   return None

def parse\_openai\_json(reply):
try:
return json.loads(reply)
except json.JSONDecodeError:
return {
"medical\_analysis": reply,
"root\_cause": "Unknown due to parsing error",
"remedies": \[],
"urgency": None,
"medicines": \[],
"suggested\_doctor": "general",
"detected\_condition": None
}

# --- API Routes ---

@app.route("/analyze", methods=\["POST"])
def analyze():
data = request.json
symptoms = data.get("symptoms", "")
location = data.get("location", {})
language = data.get("language", "English")
profile = data.get("profile", "")

```
if not symptoms:
    return jsonify({"error": "Symptoms required"}), 400

prompt = f"""
```

You are a professional medical assistant. Respond in this language: {language}. The user has this profile: {profile}.
Given the following symptoms:
"{symptoms}"

1. Identify the likely medical condition.
2. Explain why this condition may be occurring in this specific patient (consider age, profile, habits, chronic diseases, etc.).
3. Recommend simple remedies or next steps.
4. Highlight if the situation requires urgent care.
5. Suggest a relevant medical specialist.
6. If any medicine is mentioned, extract it.
7. Return structured JSON with: detected\_condition, medical\_analysis, root\_cause, remedies (array), urgency, suggested\_doctor, medicines (array)
   """

   try:
   response = openai.ChatCompletion.create(
   model="gpt-3.5-turbo",
   messages=\[
   {"role": "system", "content": "You are a helpful multilingual health assistant."},
   {"role": "user", "content": prompt}
   ],
   temperature=0.4
   )
   reply = response\['choices']\[0]\['message']\['content']
   parsed = json.loads(reply)
   parsed\["query"] = symptoms
   except Exception as e:
   logger.error(f"OpenAI error or JSON parse error: {e}")
   return jsonify({"error": "AI analysis failed"}), 500

   # Save to database

   conn = get\_db\_connection()
   if conn:
   try:
   cursor = conn.cursor()
   cursor.execute("""
   INSERT INTO medical\_analyses (query, analysis, detected\_condition, medicines, created\_at)
   VALUES (%s, %s, %s, %s, %s)
   """, (
   symptoms,
   parsed.get("medical\_analysis"),
   parsed.get("detected\_condition"),
   json.dumps(parsed.get("medicines", \[])),
   datetime.utcnow()
   ))
   conn.commit()
   cursor.close()
   except Exception as e:
   logger.error(f"DB insert error: {e}")
   finally:
   conn.close()

   # Fetch nearby doctors

   if location and parsed.get("suggested\_doctor"):
   try:
   doc\_response = requests.get(
   "[https://maps.googleapis.com/maps/api/place/nearbysearch/json](https://maps.googleapis.com/maps/api/place/nearbysearch/json)",
   params={
   "location": f"{location.get('lat')},{location.get('lng')}",
   "radius": 5000,
   "keyword": f"{parsed.get('suggested\_doctor')} doctor",
   "key": GOOGLE\_API\_KEY
   }
   )
   parsed\["doctors"] = doc\_response.json().get("results", \[])\[:5]
   except Exception as e:
   logger.error(f"Google API error: {e}")
   parsed\["doctors"] = \[]

   return jsonify(parsed), 200
   @app.route("/vision", methods=\["POST"])
   def vision\_ocr():
   data = request.json
   image\_base64 = data.get("image\_base64")

   if not image\_base64:
   return jsonify({"error": "Missing image\_base64 data"}), 400

   try:
   vision\_response = requests.post(
   f"[https://vision.googleapis.com/v1/images\:annotate?key={GOOGLE\_VISION\_API\_KEY}](https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY})",
   json={
   "requests": \[
   {
   "image": {
   "content": image\_base64
   },
   "features": \[
   {
   "type": "DOCUMENT\_TEXT\_DETECTION"
   }
   ]
   }
   ]
   }
   )
   vision\_data = vision\_response.json()
   extracted\_text = vision\_data\["responses"]\[0].get("fullTextAnnotation", {}).get("text", "No text detected")
   return jsonify({"extracted\_text": extracted\_text}), 200

   except Exception as e:
   logger.error(f"Google Vision API error: {e}")
   return jsonify({"error": "Failed to process image with Vision API"}), 500

@app.route("/api/doctors", methods=\["GET"])
def get\_doctors():
lat = request.args.get("lat")
lng = request.args.get("lng")
specialty = request.args.get("specialty", "general")

```
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
```

@app.route("/appointments", methods=\["POST"])
def book\_appointment():
data = request.json
name = data.get("name")
doctor = data.get("doctor")
date = data.get("date")

```
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
```

@app.route("/lab-report", methods=\["POST"])
def analyze\_lab\_report():
data = request.json
image\_base64 = data.get("image\_base64")
profile = data.get("profile", {})

```
if not image_base64:
    return jsonify({"error": "Missing image_base64 data"}), 400

try:
    # 1. OCR Step
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

    if "responses" not in vision_data or not vision_data["responses"]:
        logger.error("Vision API error: No responses field")
        return jsonify({"error": "Failed to process image, no response from Vision API"}), 400

    extracted_text = vision_data["responses"][0].get("fullTextAnnotation", {}).get("text", "No text detected")

    if not extracted_text.strip() or extracted_text == "No text detected":
        return jsonify({"error": "No text detected from lab report."}), 400

    # 2. Parse lab tests from extracted text
    parsing_prompt = f"""
```

Extract test names and values from the following lab report text.

Text:
{extracted\_text}

Return only a JSON array like:
\[
{{"test": "Glucose", "value": "110 mg/dL"}},
{{"test": "Creatinine", "value": "1.2 mg/dL"}}
]
"""
parsing\_response = openai.ChatCompletion.create(
model="gpt-3.5-turbo",
messages=\[{"role": "user", "content": parsing\_prompt}],
temperature=0.1,
)

```
    parsing_reply = parsing_response['choices'][0]['message']['content']
    start = parsing_reply.find('[')
    end = parsing_reply.rfind(']')
    lab_results_json = parsing_reply[start:end+1]
    lab_results = json.loads(lab_results_json)

    # 3. Interpret lab results with enhanced prompt
    interpretation_prompt = f"""
```

You are a professional health assistant. The user has the following profile: {json.dumps(profile, indent=2)}.

Here are the lab results:
{json.dumps(lab\_results, indent=2)}

Provide a detailed analysis in a conversational tone, considering the user's profile (age, conditions, medications, lifestyle, etc.). Include:

1. **Overview**: A brief summary of the overall health status based on the lab results.
2. **Good Results**: List tests with normal values, explaining why they are positive for the user's health.
3. **Bad Results**: List tests with abnormal values, explaining potential causes (linked to profile if possible) and implications.
4. **Actionable Advice**: Suggest specific actions (e.g., dietary changes, follow-up tests, lifestyle adjustments).
5. **Urgency**: Indicate if immediate medical attention is needed ("low", "moderate", "high").
6. **Specialist**: Recommend a relevant specialist if needed.

Return structured JSON like:
{{
"overview": "...",
"good\_results": \[{{"test": "...", "value": "...", "explanation": "..."}}],
"bad\_results": \[{{"test": "...", "value": "...", "explanation": "...", "potential\_cause": "..."}}],
"actionable\_advice": \["...", "..."],
"urgency": "low | moderate | high",
"suggested\_specialist": "...",
"summary": "A conversational summary suitable for a chat interface, e.g., 'Your glucose is a bit high, which might be due to...'"
}}
"""
interpretation\_response = openai.ChatCompletion.create(
model="gpt-3.5-turbo",
messages=\[{"role": "user", "content": interpretation\_prompt}],
temperature=0.2,
)

```
    interpretation_reply = interpretation_response['choices'][0]['message']['content']
    start = interpretation_reply.find('{')
    end = interpretation_reply.rfind('}')
    interpretation_json = interpretation_reply[start:end+1]
    interpretation = json.loads(interpretation_json)

    # 4. Return result
    response_data = {
        "extracted_text": extracted_text,
        "lab_results": lab_results,
        "interpretation": interpretation,
        "timestamp": datetime.utcnow().isoformat()
    }

    return jsonify(response_data), 200

except Exception as e:
    logger.error(f"Lab report analysis error: {e}")
    return jsonify({"error": "Failed to analyze lab report."}), 500
    
```

@app.route("/health", methods=\["GET"])
def health():
return jsonify({"status": "ok"})

@app.route("/emergency", methods=\["GET"])
def emergency():
return jsonify({"call": "911"})

if **name** == '**main**':
app.run(debug=True)
