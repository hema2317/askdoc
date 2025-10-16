import os
import re
import json
import uuid
import base64
import logging
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, redirect, make_response
from flask_cors import CORS, cross_origin
from dotenv import load_dotenv
from openai import OpenAI
import requests
import psycopg2
from psycopg2 import OperationalError

# =========================
# Bootstrap
# =========================
load_dotenv()  # local dev only; on Render use Environment tab

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # tighten in prod

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# =========================
# Environment
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")             # sk-...
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")             # e.g., askdoc-token-123

SUPABASE_URL = os.getenv("SUPABASE_URL")                 # https://xxxx.supabase.co
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")       # public anon key
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # service role (server-only)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "")

DATABASE_URL = os.getenv("DATABASE_URL")  # optional, if you ever use psycopg2

# OpenAI client (modern SDK)
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# Helpers
# =========================
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("Unauthorized: Bearer token missing/malformed.")
            return make_response(jsonify({"error": "Unauthorized: Bearer token missing or malformed"}), 401)
        token = auth_header.split(" ", 1)[1]
        if token != API_AUTH_TOKEN:
            logger.warning(f"Unauthorized: Invalid API token. Provided: {token[:8]}...")
            return make_response(jsonify({"error": "Unauthorized: Invalid API token"}), 401)
        return f(current_user={"id": "auth_user_id"}, *args, **kwargs)
    return decorated

def get_db_connection():
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except OperationalError as e:
        logger.error(f"DB connection failed: {e}")
        return None

def build_profile_context(profile_json):
    try:
        profile = json.loads(profile_json) if isinstance(profile_json, str) else (profile_json or {})
    except Exception:
        return "**User's Health Profile Context:** No specific health profile provided by the user."

    lines = ["**User's Health Profile Context:**"]
    def add_line(label, value):
        if isinstance(value, list) and value:
            lines.append(f"- {label}: " + ", ".join(value))
        elif isinstance(value, str) and value:
            lines.append(f"- {label}: " + value)

    if profile.get("name"):   lines.append(f"- Name: {profile.get('name')}")
    if profile.get("age"):    lines.append(f"- Age: {profile.get('age')} years")
    if profile.get("gender"): lines.append(f"- Gender: {profile.get('gender')}")
    if profile.get("state"):  lines.append(f"- State of Residence: {profile.get('state')}")

    add_line("Known Medical Conditions", profile.get("medical_conditions"))
    add_line("Current Medications", profile.get("medications"))
    add_line("Family History of", profile.get("family_history"))
    add_line("Other Known Diseases", profile.get("known_diseases"))
    add_line("Exercise Habits", profile.get("exercise_habits"))
    add_line("Allergies", profile.get("allergies"))

    smoker = profile.get("smoker")
    if smoker is not None:
        lines.append(f"- Smoker: {'Yes' if smoker else 'No'}")

    drinker = profile.get("drinker")
    if drinker is not None:
        lines.append(f"- Drinker: {'Yes' if drinker else 'No'}")

    if len(lines) == 1:
        return "**User's Health Profile Context:** No specific health profile provided by the user."
    return "\n".join(lines)

def parse_openai_json(reply):
    try:
        match = re.search(r"```json\s*(\{.*?\})\s*```", reply, re.DOTALL)
        data = json.loads(match.group(1) if match else reply)

        # normalize lists
        if not isinstance(data.get("remedies"), list):
            data["remedies"] = [data.get("remedies")] if data.get("remedies") else []
        meds = data.get("medicines")
        if not isinstance(meds, list):
            data["medicines"] = [meds] if isinstance(meds, dict) else []
        data["medicines"] = [m for m in data["medicines"] if isinstance(m, dict)]
        cits = data.get("citations")
        if not isinstance(cits, list):
            data["citations"] = [cits] if isinstance(cits, dict) else []
        data["citations"] = [c for c in data["citations"] if isinstance(c, dict)]
        if not isinstance(data.get("history_summary"), list):
            data["history_summary"] = [data.get("history_summary")] if data.get("history_summary") else ["Detail analysis not provided"]

        # defaults
        data.setdefault("detected_condition", "Unsure")
        data.setdefault("medical_analysis", "I could not find anything specific.")
        data.setdefault("why_happening_explanation", "Not provided.")
        data.setdefault("immediate_action", "Consult a healthcare professional.")
        data.setdefault("nurse_tips", "Always seek medical advice from a qualified doctor.")
        data.setdefault("urgency", "Low")
        data.setdefault("suggested_doctor", "General Practitioner")
        data.setdefault("nursing_explanation", "Not provided.")
        data.setdefault("personal_notes", "Not provided.")
        data.setdefault("relevant_information", "Not provided.")
        data.setdefault("hipaa_disclaimer",
            "Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment."
        )
        data.setdefault("medications", [])
        return data
    except Exception:
        logger.exception("parse_openai_json failed")
        return {
            "medical_analysis": "I'm sorry, I couldn't process the request (parse error).",
            "remedies": [], "medicines": [], "citations": [],
            "detected_condition": "unsure", "urgency": "unknown",
            "immediate_action": "Consult a healthcare professional.",
            "nurse_tips": "Provide clear, concise details for better analysis.",
            "nursing_explanation": "Not provided.", "personal_notes": "Not provided.",
            "relevant_information": "Not provided.",
            "history_summary": ["Detail analysis not provided"],
            "hipaa_disclaimer": "Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment."
        }

def call_openai_json(user_input_text, language, profile_context, prompt_type="symptoms"):
    metric_ctx = """
Normal Ranges (for reference only if explicitly mentioned):
- Fasting Blood Sugar: 70–100 mg/dL (3.9–5.6 mmol/L); <70 low, >125 high
- Blood Pressure: <120 / <80 mmHg
- Temperature: ~98.6°F (37°C); fever >100.4°F (38°C)
""".strip()

    system_prompt = f"""
You are a knowledgeable, empathetic virtual health assistant (nurse-like). Keep language simple.
Always include this disclaimer at the top of medical guidance:

"Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment."

{metric_ctx}

--- User Profile ---
{profile_context}

--- Output format (strict JSON) ---
Return a JSON object with keys:
detected_condition, medical_analysis, why_happening_explanation, immediate_action,
nurse_tips, remedies, medications (array of {{name,dose,time}}), urgency, suggested_doctor,
nursing_explanation, personal_notes, relevant_information, hipaa_disclaimer,
citations (array of {{title,url}}), history_summary (array of bullet strings).
""".strip()

    if prompt_type == "symptoms":
        user_content = f'Symptoms: "{user_input_text}"'
    elif prompt_type == "photo_analysis":
        user_content = f'Image description: "{user_input_text}"'
    elif prompt_type == "lab_report":
        user_content = f'Lab Report Text: "{user_input_text}"'
    else:
        user_content = f'Input: "{user_input_text}"'

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful multilingual health assistant. Output strictly valid JSON."},
                {"role": "user", "content": system_prompt + "\n\n--- User Input ---\n" + user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.exception(f"OpenAI error: {e}")
        return None

def get_nearby_doctors(specialty, location):
    if not GOOGLE_API_KEY:
        return []
    try:
        if isinstance(location, dict):
            lat, lng = location.get("lat"), location.get("lng")
            if lat is None or lng is None:
                return []
            loc_str = f"{lat},{lng}"
        elif isinstance(location, str) and "," in location:
            loc_str = location
        else:
            return []

        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "keyword": f"{specialty} doctor",
            "location": loc_str,
            "radius": 10000,
            "type": "doctor",
            "key": GOOGLE_API_KEY,
            "rankby": "prominence",
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        results = r.json().get("results", [])
        filtered = [p for p in results if p.get("rating") is not None]
        filtered.sort(key=lambda x: (x.get("rating", 0), x.get("opening_hours", {}).get("open_now", False)), reverse=True)
        out = []
        for p in filtered[:5]:
            name = p.get("name", "")
            vicinity = p.get("vicinity", "")
            query = requests.utils.quote(f"{name}, {vicinity}")
            maps_link = f"https://www.google.com/maps/search/?api=1&query={query}&query_place_id={p.get('place_id')}"
            out.append({
                "name": name,
                "address": vicinity,
                "rating": p.get("rating"),
                "open_now": p.get("opening_hours", {}).get("open_now", False),
                "phone": p.get("international_phone_number"),
                "maps_link": maps_link,
            })
        return out
    except Exception:
        logger.exception("Google Places error")
        return []

def vision_annotate(features, base64_image):
    if not GOOGLE_VISION_API_KEY:
        return {}
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {"requests": [{"image": {"content": base64_image}, "features": features}]}
        res = requests.post(url, json=body, timeout=60)
        res.raise_for_status()
        return res.json().get("responses", [{}])[0] or {}
    except Exception:
        logger.exception("Vision annotate error")
        return {}

# =========================
# Routes: core health
# =========================
@app.route("/")
def root():
    return "✅ AskDoc backend is running"

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

@app.route("/analyze", methods=["POST"])
@cross_origin()
@token_required
def analyze_symptoms(current_user=None):
    try:
        data = request.get_json() or {}
        symptoms = data.get("symptoms")
        profile = data.get("profile", {})
        location = data.get("location")
        language = data.get("language", "English")

        if not symptoms:
            return jsonify({"error": "Symptoms required"}), 400

        logger.info(f"[ANALYZE] Input: {symptoms}")
        profile_ctx = build_profile_context(profile)
        ai = call_openai_json(symptoms, language, profile_ctx, prompt_type="symptoms")
        if not ai:
            return jsonify({"error": "AI analysis failed to generate response from OpenAI"}), 500

        result = parse_openai_json(ai)
        result["nearby_doctors"] = get_nearby_doctors(result.get("suggested_doctor", "general"), location) if (location and result.get("suggested_doctor")) else []
        return jsonify(result), 200
    except Exception as e:
        logger.exception("/analyze error")
        return jsonify({"error": "Failed to analyze symptoms", "details": str(e)}), 500

@app.route("/photo-analyze", methods=["POST"])
@cross_origin()
@token_required
def analyze_photo(current_user=None):
    data = request.get_json() or {}
    image_base64 = data.get("image_base64")
    profile = data.get("profile", {})
    location = data.get("location")

    if not image_base64:
        return jsonify({"error": "No image provided"}), 400

    labels_resp = vision_annotate([{"type": "LABEL_DETECTION", "maxResults": 10}], image_base64)
    labels = [l["description"] for l in labels_resp.get("labelAnnotations", [])]
    text_resp = vision_annotate([{"type": "TEXT_DETECTION"}], image_base64)
    detected_text = (text_resp.get("fullTextAnnotation") or {}).get("text", "")

    desc = f"Labels: {', '.join(labels)}."
    if detected_text:
        desc += f' OCR: "{detected_text}"'

    profile_ctx = build_profile_context(profile)
    ai = call_openai_json(desc, "English", profile_ctx, prompt_type="photo_analysis")
    if not ai:
        return jsonify({"error": "AI analysis failed to generate response"}), 500

    result = parse_openai_json(ai)
    result["nearby_doctors"] = get_nearby_doctors(result.get("suggested_doctor", "general"), location) if (location and result.get("suggested_doctor")) else []
    result["image_labels"] = labels
    result["image_description"] = desc
    return jsonify(result), 200

@app.route("/analyze-lab-report", methods=["POST"])
@cross_origin()
@token_required
def analyze_lab_report(current_user=None):
    data = request.get_json() or {}
    image_base64 = data.get("image_base64")
    extracted_text = data.get("extracted_text", "")
    location = data.get("location")
    profile = data.get("profile", {})
    language = data.get("language", "English")

    final_text = extracted_text
    if not final_text and image_base64:
        ocr = vision_annotate([{"type": "TEXT_DETECTION"}], image_base64)
        final_text = (ocr.get("fullTextAnnotation") or {}).get("text", "")

    if not final_text:
        return jsonify({"error": "Missing lab report text or image to analyze"}), 400

    profile_ctx = build_profile_context(profile)
    ai = call_openai_json(final_text, language, profile_ctx, prompt_type="lab_report")
    if not ai:
        return jsonify({"error": "AI failed to generate response for lab report"}), 500

    result = parse_openai_json(ai)
    result["nearby_doctors"] = get_nearby_doctors(result.get("suggested_doctor", "general"), location) if (location and result.get("suggested_doctor")) else []
    result["extracted_text"] = final_text
    return jsonify(result), 200

# =========================
# Routes: Q&A, history
# =========================
@app.route("/api/ask", methods=["POST"])
@cross_origin()
@token_required
def ask(current_user=None):
    data = request.get_json() or {}
    q = data.get("question", "").strip()
    if not q:
        return jsonify({"error": "No question provided"}), 400
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": q}],
            temperature=0.5,
        )
        return jsonify({"reply": resp.choices[0].message.content})
    except Exception:
        logger.exception("/api/ask error")
        return jsonify({"error": "OpenAI request failed"}), 500

@app.route("/api/history", methods=["POST"])
@cross_origin()
@token_required
def save_history(current_user=None):
    try:
        data = request.get_json() or {}
        user_id = data.get("user_id")
        query = data.get("query")
        response_obj = data.get("response")
        if not user_id or not query or not response_obj:
            return jsonify({"error": "Missing user_id, query, or response"}), 400

        parsed = response_obj if isinstance(response_obj, dict) else json.loads(response_obj)
        meds = parsed.get("medicines")
        rems = parsed.get("remedies")
        cits = parsed.get("citations")
        if not isinstance(meds, list): meds = [meds] if isinstance(meds, dict) else []
        if not isinstance(rems, list): rems = [rems] if rems else []
        if not isinstance(cits, list): cits = [cits] if isinstance(cits, dict) else []
        meds = [m for m in meds if isinstance(m, dict)]
        cits = [c for c in cits if isinstance(c, dict)]

        payload = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "query": query,
            "detected_condition": parsed.get("detected_condition"),
            "medical_analysis": parsed.get("medical_analysis"),
            "remedies": rems,
            "urgency": parsed.get("urgency"),
            "medicines": meds,
            "suggested_doctor": parsed.get("suggested_doctor"),
            "raw_text": json.dumps(parsed),
            "timestamp": datetime.utcnow().isoformat(),
            "nursing_explanation": parsed.get("nursing_explanation"),
            "personal_notes": parsed.get("personal_notes"),
            "relevant_information": parsed.get("relevant_information"),
            "why_happening_explanation": parsed.get("why_happening_explanation"),
            "immediate_action": parsed.get("immediate_action"),
            "nurse_tips": parsed.get("nurse_tips"),
            "citations": cits,
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
        logger.exception("save_history error")
        return jsonify({"error": str(e)}), 500

@app.route("/api/history", methods=["GET"])
@cross_origin()
@token_required
def get_history(current_user=None):
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400
    try:
        url = f"{SUPABASE_URL}/rest/v1/history?user_id=eq.{user_id}&order=timestamp.desc"
        headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}", "Content-Type": "application/json"}
        res = requests.get(url, headers=headers, timeout=30)
        if res.status_code != 200:
            logger.error(f"Supabase fetch error: {res.text}")
            return jsonify({"error": "Failed to fetch history", "details": res.text}), 500

        history = res.json()
        for e in history:
            if isinstance(e.get("raw_text"), str):
                try:
                    e["response"] = json.loads(e["raw_text"])
                    if "citations" in e["response"] and not isinstance(e["response"]["citations"], list):
                        e["response"]["citations"] = [e["response"]["citations"]]
                    if "medications" in e["response"] and not isinstance(e["response"]["medications"], list):
                        e["response"]["medications"] = [e["response"]["medications"]]
                except json.JSONDecodeError:
                    e["response"] = {}
            else:
                e["response"] = e.get("response", {})
            for k in ["citations", "medicines"]:
                if k in e and not isinstance(e[k], list):
                    e[k] = [e[k]]
        return jsonify(history), 200
    except Exception:
        logger.exception("get_history error")
        return jsonify({"error": "Internal error while fetching history"}), 500

# =========================
# Routes: Google Places
# =========================
@app.route("/api/doctors", methods=["POST"])
@cross_origin()
@token_required
def doctors_post(current_user=None):
    data = request.get_json() or {}
    specialty = data.get("specialty")
    location = data.get("location")
    if not specialty or not location:
        return jsonify({"error": "Specialty and location are required"}), 400
    return jsonify({"doctors": get_nearby_doctors(specialty, location)}), 200

@app.route("/api/doctors", methods=["GET"])
@cross_origin()
@token_required
def doctors_get(current_user=None):
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    specialty = request.args.get("specialty", "general")
    if not lat or not lng:
        return jsonify({"error": "Missing lat/lng"}), 400
    try:
        location = {"lat": float(lat), "lng": float(lng)}
    except ValueError:
        return jsonify({"error": "Invalid lat/lng format"}), 400
    return jsonify({"results": get_nearby_doctors(specialty, location)}), 200

# =========================
# Password reset & account deletion
# =========================
@app.route("/request-password-reset", methods=["POST"])
@cross_origin()
@token_required
def request_password_reset(current_user=None):
    data = request.get_json() or {}
    email = data.get("email")
    redirect_to = data.get("redirect_to")
    if not email:
        return jsonify({"error": "Email is required"}), 400
    if not redirect_to:
        return jsonify({"error": "Redirect URL for password reset is required"}), 400
    try:
        url = f"{SUPABASE_URL}/auth/v1/recover"
        headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json={"email": email, "redirect_to": redirect_to}, timeout=30)
        r.raise_for_status()
        return jsonify({"message": "Password reset email sent."}), 200
    except Exception:
        logger.exception("Supabase recover error")
        return jsonify({"error": "Failed to send password reset email"}), 500

@app.route("/verify-password-reset", methods=["GET"])
@cross_origin()
def verify_password_reset():
    access_token = request.args.get("access_token")
    refresh_token = request.args.get("refresh_token")
    if access_token and refresh_token:
        frontend_reset_url = "https://askdocapp-92cc3.web.app/reset-password.html"
        full_redirect = f"{frontend_reset_url}#access_token={access_token}&refresh_token={refresh_token}"
        return redirect(full_redirect)
    return redirect("https://askdocapp-92cc3.web.app/reset-password.html?error=invalid_link")

@app.route("/api/delete-account", methods=["POST"])
@cross_origin()
@token_required
def delete_account(current_user=None):
    try:
        data = request.get_json() or {}
        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"result": {"success": False, "error": "Missing user_id"}}), 400

        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Prefer": "return=representation",
            "Content-Type": "application/json",
        }
        # delete from public tables
        for table in ["profiles", "history", "medications"]:
            url = f"{SUPABASE_URL}/rest/v1/{table}?user_id=eq.{user_id}"
            res = requests.delete(url, headers=headers, timeout=30)
            logger.info(f"[DELETE {table}] status={res.status_code}")

        # delete from auth
        auth_url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
        auth_res = requests.delete(auth_url, headers=headers, timeout=30)
        if auth_res.status_code != 204:
            return jsonify({"result": {"success": False, "error": "Failed to delete user from Supabase Auth", "details": auth_res.text}}), 500

        return jsonify({"result": {"success": True, "message": "Account and data deleted."}}), 200
    except Exception as e:
        logger.exception("delete_account error")
        return jsonify({"result": {"success": False, "error": "Internal server error", "details": str(e)}}), 500

# =========================
# Trends (LLM summary)
# =========================
@app.route("/analyze-trends", methods=["POST"])
@cross_origin()
@token_required
def analyze_trends(current_user=None):
    try:
        data = request.get_json() or {}
        timeline = data.get("symptoms", [])
        profile_ctx = data.get("profile_context", "")
        if not timeline or not isinstance(timeline, list):
            return jsonify({"error": "Missing or invalid symptom data"}), 400

        trend_input = "User's Symptom Timeline:\n" + "\n".join(
            f"- Date: {e.get('date','N/A')}, Issue: {e.get('issue','N/A')}, Symptom: {e.get('symptom','N/A')}, Severity: {e.get('severity','N/A')}/10, Status: {e.get('status','N/A')}"
            for e in timeline
        )

        prompt = f"""
You are a medical AI assistant analyzing a user's symptom timeline.
{profile_ctx}

{trend_input}

Create a concise 4–6 bullet summary:
- Patterns/recurrences
- Improving/worsening/stable
- When to seek care
- Practical tips
Append a line starting with: Citations: [Title](URL), [Title](URL) or "No specific citations for trends."
""".strip()

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You summarize health trends from timelines."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=600,
        )
        text = resp.choices[0].message.content.strip()

        m = re.search(r"Citations:\s*(.*)", text, re.IGNORECASE)
        citations = []
        if m:
            cit_str = m.group(1).strip()
            text = text.replace(m.group(0), "").strip()
            if cit_str.lower() != "no specific citations for trends.":
                for mm in re.finditer(r"\[(.*?)\]\((.*?)\)", cit_str):
                    citations.append({"title": mm.group(1), "url": mm.group(2)})
        if not citations:
            citations.append({"title": "General Health Trends & Wellness", "url": "https://www.who.int/health-topics/health-and-wellness"})

        return jsonify({"summary": text, "citations": citations}), 200
    except Exception as e:
        logger.exception("analyze_trends error")
        return jsonify({"error": "Trend analysis failed", "details": str(e)}), 500

# =========================
# Debug endpoints (safe)
# =========================
@app.route("/debug/openai", methods=["GET"])
def debug_openai():
    import sys
    try:
        from openai import __version__ as openai_version
    except Exception:
        openai_version = "unknown"
    return jsonify({
        "has_key": bool(OPENAI_API_KEY),
        "key_prefix": (OPENAI_API_KEY[:8] + "...") if OPENAI_API_KEY else None,
        "openai_pkg_version": openai_version,
        "python": sys.version,
    })

@app.route("/debug/openai-test", methods=["GET"])
def debug_openai_test():
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'pong' only."}],
            temperature=0.0,
        )
        return jsonify({"ok": True, "content": resp.choices[0].message.content}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# =========================
# Entrypoint
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
