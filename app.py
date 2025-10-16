# app.py
import os
import json
import re
import base64
import logging
import uuid
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, redirect, make_response
from flask_cors import CORS, cross_origin
import requests
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv

# --- Load .env (optional locally; Render uses Environment tab) ---
load_dotenv()

# --- Flask / CORS ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# --- Environment ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "")

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://YOUR-PROJECT.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# --- OpenAI v1 client ---
from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Small sanity checks (log-only) ---
if not API_AUTH_TOKEN:
    logger.warning("API_AUTH_TOKEN missing. Protected routes will reject requests.")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY missing. AI routes will fail.")
if not SUPABASE_ANON_KEY:
    logger.warning("SUPABASE_ANON_KEY missing. History endpoints may fail.")
if not SUPABASE_SERVICE_ROLE_KEY:
    logger.warning("SUPABASE_SERVICE_ROLE_KEY missing. Delete account may fail.")

# --- Health (plain text & JSON) ---
@app.route("/")
def root():
    return "✅ AskDoc backend is running"

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

# --- Auth middleware ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning("Unauthorized: Bearer token missing or malformed.")
            return make_response(jsonify({"error": "Unauthorized: Bearer token missing or malformed"}), 401)
        token = auth_header.split(" ", 1)[1]
        if token != API_AUTH_TOKEN:
            logger.warning("Unauthorized: Invalid API token.")
            return make_response(jsonify({"error": "Unauthorized: Invalid API token"}), 401)
        return f(current_user={"id": "auth_user_id"}, *args, **kwargs)
    return decorated

# --- Optional DB connection (unused but kept for parity) ---
def get_db_connection():
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

# --- Helpers ---
def build_profile_context(profile_json):
    try:
        profile = json.loads(profile_json) if isinstance(profile_json, str) else (profile_json or {})
    except Exception:
        logger.warning("Could not parse profile_json. Using empty context.")
        profile = {}

    lines = ["**User's Health Profile Context:**"]
    def add_line(k, label=None, as_list=False):
        val = profile.get(k)
        if val is None:
            return
        if as_list and isinstance(val, list):
            if val:
                lines.append(f"- {label or k}: " + ", ".join(map(str, val)))
        elif isinstance(val, str):
            lines.append(f"- {label or k}: {val}")
        elif isinstance(val, bool):
            lines.append(f"- {label or k}: {'Yes' if val else 'No'}")
        else:
            lines.append(f"- {label or k}: {val}")

    add_line("name", "Name")
    add_line("age", "Age")
    add_line("gender", "Gender")
    add_line("state", "State of Residence")
    add_line("medical_conditions", "Known Medical Conditions", as_list=True)
    add_line("medications", "Current Medications", as_list=True)
    add_line("family_history", "Family History of", as_list=True)
    add_line("known_diseases", "Other Known Diseases", as_list=True)
    add_line("smoker", "Smoker")
    add_line("drinker", "Drinker")
    add_line("exercise_habits", "Exercise Habits", as_list=True)
    add_line("allergies", "Allergies", as_list=True)

    if len(lines) == 1:
        return "**User's Health Profile Context:** No specific health profile provided by the user."
    return "\n".join(lines)

def generate_openai_response(user_input_text, language, profile_context, prompt_type="symptoms"):
    health_metric_context = """
    Normal Ranges for reference (use only if explicitly mentioned, otherwise ignore):
    - Blood Sugar (Fasting): 70-100 mg/dL (or 3.9-5.6 mmol/L). Below 70 mg/dL is Hypoglycemia (low). Above 125 mg/dL is Hyperglycemia (high).
    - Blood Pressure: Systolic < 120 mmHg, Diastolic < 80 mmHg.
    - Temperature: Oral ~98.6°F (37°C). Fever generally >100.4°F (38°C).
    """

    system_prompt = f"""
You are a highly knowledgeable, empathetic, and responsible virtual health assistant. Your role is to act as a compassionate nurse or health educator.
Always speak simply for a layperson. Start with this disclaimer:

Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment.

{health_metric_context}

--- User's Health Profile ---
{profile_context}

--- Task Instructions ---
Provide a structured analysis tailored to the user's profile. Be explicit when values are low/normal/high.
Return a single JSON object with keys:
1) detected_condition
2) medical_analysis
3) why_happening_explanation
4) immediate_action
5) nurse_tips
6) remedies
7) medications  # array of {{name, dose, time}}
8) urgency
9) suggested_doctor
10) nursing_explanation
11) personal_notes
12) relevant_information
13) hipaa_disclaimer (exact disclaimer above)
14) citations  # array of {{title, url}}
15) history_summary # up to 3 bullets
"""

    if prompt_type == "symptoms":
        user_content = f'Symptoms: "{user_input_text}"'
    elif prompt_type == "photo_analysis":
        user_content = f'Image shows: "{user_input_text}"'
    elif prompt_type == "lab_report":
        user_content = f'Lab Report Text: "{user_input_text}"'
    else:
        user_content = f'Input: "{user_input_text}"'

    full_user_message = system_prompt + f"\n--- User's Input ---\n{user_content}"

    try:
        resp = client.chat.completions.create(
    model="gpt-4o-mini",
            temperature=0.4,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful multilingual health assistant. Adhere strictly to the requested JSON format."
                },
                {"role": "user", "content": full_user_message},
            ],
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI error in generate_openai_response: {e}")
        return None

def parse_openai_json(reply: str) -> dict:
    try:
        match = re.search(r"```json\s*(\{.*?\})\s*```", reply, re.DOTALL)
        json_str = match.group(1) if match else reply
        data = json.loads(json_str)

        # normalize list fields
        for key in ("remedies",):
            if key in data and not isinstance(data[key], list):
                data[key] = [data[key]] if data[key] else []

        # 'medications' must be a list of dicts
        meds = data.get("medications", [])
        if not isinstance(meds, list):
            meds = [meds] if isinstance(meds, dict) else []
        data["medications"] = [m for m in meds if isinstance(m, dict)]

        cits = data.get("citations", [])
        if not isinstance(cits, list):
            cits = [cits] if isinstance(cits, dict) else []
        data["citations"] = [c for c in cits if isinstance(c, dict)]

        hs = data.get("history_summary", [])
        if not isinstance(hs, list):
            hs = [hs] if isinstance(hs, str) else []
        data["history_summary"] = hs or ["Detail analysis not provided"]

        # defaults
        defaults = {
            "detected_condition": "Unsure",
            "medical_analysis": "Not provided.",
            "why_happening_explanation": "Not provided.",
            "immediate_action": "Consult a healthcare professional.",
            "nurse_tips": "Always seek medical advice from a qualified doctor.",
            "urgency": "Low",
            "suggested_doctor": "General Practitioner",
            "nursing_explanation": "Not provided.",
            "personal_notes": "Not provided.",
            "relevant_information": "Not provided.",
            "hipaa_disclaimer": (
                "Disclaimer: I am a virtual AI assistant and not a medical doctor. "
                "This information is for educational purposes only and is not a substitute for professional medical advice. "
                "Always consult a qualified healthcare provider for diagnosis and treatment."
            ),
        }
        for k, v in defaults.items():
            data.setdefault(k, v)

        return data
    except Exception as e:
        logger.error(f"JSON parsing failed: {e}")
        return {
            "medical_analysis": "I'm sorry, I couldn't fully process the request. (JSON Parse Error)",
            "root_cause": "Parsing error.",
            "remedies": [],
            "medications": [],
            "detected_condition": "unsure",
            "why_happening_explanation": "Insufficient information.",
            "immediate_action": "Consult a healthcare professional.",
            "nurse_tips": "Provide clear info for accuracy.",
            "hipaa_disclaimer": (
                "Disclaimer: I am a virtual AI assistant and not a medical doctor. "
                "This information is for educational purposes only and is not a substitute for professional medical advice. "
                "Always consult a qualified healthcare provider for diagnosis and treatment."
            ),
            "urgency": "unknown",
            "suggested_doctor": "general",
            "nursing_explanation": "Not provided.",
            "personal_notes": "Not provided.",
            "relevant_information": "Not provided.",
            "citations": [],
            "history_summary": ["Detail analysis not provided"],
        }

# --- Google helpers ---
def get_nearby_doctors(specialty, location):
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY not set.")
        return []
    try:
        if isinstance(location, dict):
            lat, lng = location.get("lat"), location.get("lng")
            if lat is None or lng is None:
                return []
            location_str = f"{lat},{lng}"
        elif isinstance(location, str) and "," in location:
            location_str = location
        else:
            return []

        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "keyword": f"{specialty} doctor",
            "location": location_str,
            "radius": 10000,
            "type": "doctor",
            "key": GOOGLE_API_KEY,
            "rankby": "prominence",
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        results = r.json().get("results", [])
        filtered = [p for p in results if p.get("rating") is not None]
        sorted_results = sorted(
            filtered,
            key=lambda x: (
                x.get("rating", 0),
                x.get("opening_hours", {}).get("open_now", False) if isinstance(x.get("opening_hours"), dict) else False,
            ),
            reverse=True,
        )
        out = []
        for place in sorted_results[:5]:
            name = place.get("name", "")
            vicinity = place.get("vicinity", "")
            q = requests.utils.quote(f"{name}, {vicinity}")
            maps_link = f"https://www.google.com/maps/search/?api=1&query={q}&query_place_id={place.get('place_id')}"
            out.append(
                {
                    "name": name,
                    "address": vicinity,
                    "rating": place.get("rating"),
                    "open_now": place.get("opening_hours", {}).get("open_now", False),
                    "phone": place.get("international_phone_number"),  # often not present in Nearby Search
                    "maps_link": maps_link,
                }
            )
        return out
    except Exception as e:
        logger.error(f"Places API error: {e}")
        return []

def get_image_labels(base64_image):
    if not GOOGLE_VISION_API_KEY:
        logger.error("GOOGLE_VISION_API_KEY not set.")
        return []
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [
                {"image": {"content": base64_image}, "features": [{"type": "LABEL_DETECTION", "maxResults": 10}]}
            ]
        }
        res = requests.post(url, json=body, timeout=30)
        res.raise_for_status()
        labels = [
            l["description"]
            for l in res.json().get("responses", [{}])[0].get("labelAnnotations", [])  # type: ignore[index]
        ]
        return labels
    except Exception as e:
        logger.error(f"Vision label error: {e}")
        return []

def get_image_text(base64_image):
    if not GOOGLE_VISION_API_KEY:
        logger.error("GOOGLE_VISION_API_KEY not set.")
        return ""
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [
                {"image": {"content": base64_image}, "features": [{"type": "TEXT_DETECTION"}]}
            ]
        }
        res = requests.post(url, json=body, timeout=60)
        res.raise_for_status()
        annotations = res.json().get("responses", [{}])[0]
        return annotations.get("fullTextAnnotation", {}).get("text", "")
    except Exception as e:
        logger.error(f"Vision OCR error: {e}")
        return ""

# --- Core routes ---
@app.route("/analyze", methods=["POST"])
@cross_origin()
@token_required
def analyze_symptoms(current_user=None):
    try:
        data = request.get_json() or {}
        symptoms = data.get("symptoms")
        profile_data = data.get("profile", {})
        location = data.get("location")
        language = data.get("language", "English")

        if not symptoms:
            return jsonify({"error": "Symptoms required"}), 400

        logger.info(f"[ANALYZE] Input: {symptoms}, User ID: {profile_data.get('user_id')}")
        profile_context = build_profile_context(profile_data)

        ai = generate_openai_response(symptoms, language, profile_context, prompt_type="symptoms")
        if not ai:
            return jsonify({"error": "AI analysis failed to generate response from OpenAI"}), 500

        result = parse_openai_json(ai)
        result["nearby_doctors"] = get_nearby_doctors(result.get("suggested_doctor", "general"), location) if location else []

        return jsonify(result), 200
    except Exception as e:
        logger.exception("Error in /analyze")
        return jsonify({"error": "Failed to analyze symptoms", "details": str(e)}), 500

@app.route("/debug/openai", methods=["GET"])
def debug_openai():
    try:
        from openai import __version__ as openai_version
    except Exception:
        openai_version = "unknown"

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=2,
        )
        return jsonify({
            "ok": True,
            "openai_version": openai_version,
            "reply": r.choices[0].message.content
        }), 200
    except Exception as e:
        return jsonify({
            "ok": False,
            "openai_version": openai_version,
            "error_type": type(e).__name__,
            "error": str(e)
        }), 500

@app.route("/photo-analyze", methods=["POST"])
@cross_origin()
@token_required
def analyze_photo(current_user=None):
    try:
        data = request.get_json() or {}
        image_base64 = data.get("image_base64")
        profile_data = data.get("profile", {})
        location = data.get("location")

        if not image_base64:
            return jsonify({"error": "No image provided"}), 400

        labels = get_image_labels(image_base64)
        text = get_image_text(image_base64)

        desc = f"The image provides visual cues: {', '.join(labels)}." if labels else "The image provides limited visual cues."
        if text:
            desc += f' Additionally, text detected in the image: "{text}"'

        profile_context = build_profile_context(profile_data)
        ai = generate_openai_response(desc, "English", profile_context, prompt_type="photo_analysis")
        if not ai:
            return jsonify({"error": "AI analysis failed to generate response from OpenAI"}), 500

        parsed = parse_openai_json(ai)
        parsed["nearby_doctors"] = get_nearby_doctors(parsed.get("suggested_doctor", "general"), location) if location else []
        parsed["image_labels"] = labels
        parsed["image_description"] = desc
        return jsonify(parsed), 200
    except Exception as e:
        logger.exception("Error in /photo-analyze")
        return jsonify({"error": "Failed to analyze image", "details": str(e)}), 500

@app.route("/analyze-lab-report", methods=["POST"])
@cross_origin()
@token_required
def analyze_lab_report(current_user=None):
    try:
        data = request.get_json() or {}
        image_base64 = data.get("image_base64")
        extracted_text_frontend = data.get("extracted_text", "")
        location = data.get("location")
        profile_data = data.get("profile", {})
        language = data.get("language", "English")

        final_text = ""
        if extracted_text_frontend and extracted_text_frontend != "PDF document uploaded. Extracting text on backend...":
            final_text = extracted_text_frontend
        elif image_base64:
            final_text = get_image_text(image_base64)

        if not final_text:
            return jsonify({"error": "Missing lab report text or image to analyze"}), 400

        profile_context = build_profile_context(profile_data)
        ai = generate_openai_response(final_text, language, profile_context, prompt_type="lab_report")
        if not ai:
            return jsonify({"error": "AI failed to generate response for lab report"}), 500

        parsed = parse_openai_json(ai)
        parsed["nearby_doctors"] = get_nearby_doctors(parsed.get("suggested_doctor", "general"), location) if location else []
        parsed["extracted_text"] = final_text
        return jsonify(parsed), 200
    except Exception as e:
        logger.exception("Error in /analyze-lab-report")
        return jsonify({"error": "Failed to analyze lab report", "details": str(e)}), 500

@app.route("/api/ask", methods=["POST"])
@cross_origin()
@token_required
def ask(current_user=None):
    try:
        data = request.get_json() or {}
        question = data.get("question", "").strip()
        if not question:
            return jsonify({"error": "No question provided"}), 400

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": question}],
            temperature=0.5,
        )
        reply = resp.choices[0].message.content
        return jsonify({"reply": reply}), 200
    except Exception as e:
        logger.error(f"OpenAI error in /api/ask: {e}")
        return jsonify({"error": "OpenAI request failed"}), 500

# --- History (Supabase REST) ---
@app.route("/api/history", methods=["POST"])
@cross_origin()
@token_required
def save_history(current_user=None):
    try:
        data = request.get_json() or {}
        user_id = data.get("user_id")
        query = data.get("query")
        response = data.get("response")
        if not user_id or not query or not response:
            return jsonify({"error": "Missing user_id, query, or response"}), 400

        parsed = response if isinstance(response, dict) else json.loads(response)

        # normalize
        medicines = parsed.get("medicines")
        remedies = parsed.get("remedies")
        citations = parsed.get("citations")

        if not isinstance(medicines, list):
            medicines = [medicines] if isinstance(medicines, dict) else []
        if not isinstance(remedies, list):
            remedies = [remedies] if remedies else []
        if not isinstance(citations, list):
            citations = [citations] if isinstance(citations, dict) else []

        payload = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "query": query,
            "detected_condition": parsed.get("detected_condition"),
            "medical_analysis": parsed.get("medical_analysis"),
            "remedies": remedies,
            "urgency": parsed.get("urgency"),
            "medicines": medicines,
            "suggested_doctor": parsed.get("suggested_doctor"),
            "raw_text": json.dumps(parsed),
            "timestamp": datetime.utcnow().isoformat(),
            "nursing_explanation": parsed.get("nursing_explanation"),
            "personal_notes": parsed.get("personal_notes"),
            "relevant_information": parsed.get("relevant_information"),
            "why_happening_explanation": parsed.get("why_happening_explanation"),
            "immediate_action": parsed.get("immediate_action"),
            "nurse_tips": parsed.get("nurse_tips"),
            "citations": citations,
        }

        url = f"{SUPABASE_URL}/rest/v1/history"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
        if r.status_code != 201:
            logger.error(f"Supabase insert error: {r.text}")
            return jsonify({"error": "Failed to save history", "details": r.text}), 500
        return jsonify({"success": True, "data": r.json()}), 200
    except Exception as e:
        logger.exception("Exception while saving history")
        return jsonify({"error": str(e)}), 500

@app.route("/api/history", methods=["GET"])
@cross_origin()
@token_required
def get_history(current_user=None):
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400

        url = f"{SUPABASE_URL}/rest/v1/history?user_id=eq.{user_id}&order=timestamp.desc"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            logger.error(f"Supabase fetch error: {r.text}")
            return jsonify({"error": "Failed to fetch history", "details": r.text}), 500

        history = r.json()
        # best-effort: inflate 'response' from raw_text
        for entry in history:
            raw = entry.get("raw_text")
            if isinstance(raw, str) and raw:
                try:
                    entry["response"] = json.loads(raw)
                except Exception:
                    entry["response"] = {}
        return jsonify(history), 200
    except Exception as e:
        logger.exception("Exception while fetching history")
        return jsonify({"error": str(e)}), 500

# --- Password reset (Supabase Auth) ---
@app.route("/request-password-reset", methods=["POST"])
@cross_origin()
@token_required
def request_password_reset(current_user=None):
    try:
        data = request.get_json() or {}
        email = data.get("email")
        redirect_to = data.get("redirect_to")
        if not email:
            return jsonify({"error": "Email is required"}), 400
        if not redirect_to:
            return jsonify({"error": "Redirect URL for password reset is required"}), 400

        url = f"{SUPABASE_URL}/auth/v1/recover"
        headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
        payload = {"email": email, "redirect_to": redirect_to}
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return jsonify({"message": "Password reset email sent."}), 200
    except requests.exceptions.RequestException as e:
        logger.error(f"Supabase recover error: {e}")
        return jsonify({"error": "Failed to send password reset email."}), 500
    except Exception as e:
        logger.error(f"Unexpected error in /request-password-reset: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500

@app.route("/verify-password-reset", methods=["GET"])
@cross_origin()
def verify_password_reset():
    access_token = request.args.get("access_token")
    refresh_token = request.args.get("refresh_token")
    if access_token and refresh_token:
        frontend_reset_url = "https://askdocapp-92cc3.web.app/reset-password.html"
        full_redirect = f"{frontend_reset_url}#access_token={access_token}&refresh_token={refresh_token}"
        logger.info(f"Redirecting to frontend reset page: {full_redirect}")
        return redirect(full_redirect)
    logger.warning("Missing access_token or refresh_token in /verify-password-reset.")
    return redirect("https://askdocapp-92cc3.web.app/reset-password.html?error=invalid_link")

# --- Delete account & data ---
@app.route("/api/delete-account", methods=["POST"])
@cross_origin()
@token_required
def delete_account(current_user=None):
    try:
        data = request.get_json() or {}
        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"result": {"success": False, "error": "Missing user_id"}}), 400

        svc_headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

        # delete rows from your tables
        base = f"{SUPABASE_URL}/rest/v1"
        endpoints = [
            f"{base}/profiles?user_id=eq.{user_id}",
            f"{base}/history?user_id=eq.{user_id}",
            f"{base}/medications?user_id=eq.{user_id}",
        ]
        for ep in endpoints:
            dr = requests.delete(ep, headers=svc_headers, timeout=20)
            if dr.status_code not in (200, 204):
                logger.error(f"Failed table delete {ep}: {dr.status_code} {dr.text}")
                return jsonify({"result": {"success": False, "error": "Failed to delete user data", "details": dr.text}}), 500

        # delete from Supabase Auth
        auth_url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
        ar = requests.delete(auth_url, headers=svc_headers, timeout=20)
        if ar.status_code != 204:
            logger.error(f"Failed auth delete: {ar.status_code} {ar.text}")
            return jsonify({"result": {"success": False, "error": "Failed to delete user from Supabase Auth", "details": ar.text}}), 500

        return jsonify({"result": {"success": True, "message": "Account and associated data deleted successfully."}}), 200
    except Exception as e:
        logger.exception("Account deletion failed")
        return jsonify({"result": {"success": False, "error": "Internal server error", "details": str(e)}}), 500

# --- Simple test route for logs ---
@app.route("/api/test-delete-log", methods=["GET"])
def test_log_route():
    print("[TEST LOG] This route was hit!")
    return jsonify({"message": "Logging works!"})

# --- Entrypoint ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
