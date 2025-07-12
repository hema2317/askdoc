import uuid
import os
import json
import logging
import re
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, redirect, url_for, make_response
from flask_cors import CORS, cross_origin
import openai
import requests
import psycopg2
from psycopg2 import OperationalError
import base64
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY_HERE")
DATABASE_URL = os.getenv("DATABASE_URL", "YOUR_DATABASE_URL_HERE")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "YOUR_GOOGLE_API_KEY_HERE")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "YOUR_GOOGLE_VISION_API_KEY_HERE")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "YOUR_API_AUTH_TOKEN_HERE") 

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://nlfvwbjpeywcessqyqac.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5sZnZ3YmpwZXl3Y2Vzc3F5cWFjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU4NTczNjQsImV4cCI6MjA2MTQzMzM2NH0.zL84P7bK7qHxJt8MtkTPkqNe4U_K512ZgtpPvD9PoRI")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5sZnZ3YmpwZXl3Y2Vzc3F5cWFjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NTg1NzM2NCwiZXhwIjoyMDYxNDMzMzY0fQ.IC28ip8ky-qdHZkhoND-GUh1fY_y2H6qSxIGdD5WqS4")

# Initialize Supabase client
from supabase import create_client, Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Set OpenAI API key
openai.api_key = OPENAI_API_KEY

@app.route("/")
def health_check():
    return "✅ AskDoc backend is running"

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning("Unauthorized access attempt: No Bearer token provided or malformed header.")
            return make_response(jsonify({"error": "Unauthorized: Bearer token missing or malformed"}), 401)

        token = auth_header.split(" ")[1]
        if token != API_AUTH_TOKEN:
            logger.warning(f"Unauthorized access attempt: Invalid API token. Provided: {token[:5]}...")
            return make_response(jsonify({"error": "Unauthorized: Invalid API token"}), 401)
        
        current_user = {"id": "auth_user_id"} 
        return f(current_user=current_user, *args, **kwargs)
    return decorated

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

def build_profile_context(profile_json):
    try:
        profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
    except Exception:
        logger.warning("Could not parse profile_json. Returning empty context.")
        return "No specific health profile provided by the user."

    lines = ["**User's Health Profile Context:**"]
    if name := profile.get("name"):
        lines.append(f"- Name: {name}")
    if age := profile.get("age"):
        lines.append(f"- Age: {age} years")
    if gender := profile.get("gender"):
        lines.append(f"- Gender: {gender}")
    if state := profile.get("state"):
        lines.append(f"- State of Residence: {state}")

    if medical_conditions := profile.get("medical_conditions"):
        if isinstance(medical_conditions, list):
            lines.append("- Known Health Conditions: " + ", ".join(medical_conditions))
        elif isinstance(medical_conditions, str):
            lines.append("- Known Health Conditions: " + medical_conditions)
    if current_medications := profile.get("medications"):
        if isinstance(current_medications, list):
            lines.append("- Current Wellness Products: " + ", ".join(current_medications))
        elif isinstance(current_medications, str):
            lines.append("- Current Wellness Products: " + current_medications)
    if family_history := profile.get("family_history"):
        if isinstance(family_history, list):
            lines.append("- Family Health Background: " + ", ".join(family_history))
        elif isinstance(family_history, str):
            lines.append("- Family Health Background: " + family_history)
    if known_diseases := profile.get("known_diseases"):
        if isinstance(known_diseases, list):
            lines.append("- Other Known Health Considerations: " + ", ".join(known_diseases))
        elif isinstance(known_diseases, str):
            lines.append("- Other Known Health Considerations: " + known_diseases)

    if smoker := profile.get("smoker"):
        lines.append(f"- Smoker: {'Yes' if smoker is True else 'No' if smoker is False else str(smoker)}")
    if drinker := profile.get("drinker"):
        lines.append(f"- Drinker: {'Yes' if drinker is True else 'No' if drinker is False else str(drinker)}")
    if exercise_habits := profile.get("exercise_habits"):
        if isinstance(exercise_habits, list):
            lines.append("- Exercise Habits: " + ", ".join(exercise_habits))
        elif isinstance(exercise_habits, str):
            lines.append("- Exercise Habits: " + exercise_habits)
    if allergies := profile.get("allergies"):
        if isinstance(allergies, list):
            lines.append("- Allergies: " + ", ".join(allergies))
        elif isinstance(allergies, str):
            lines.append("- Allergies: " + allergies)
    
    if len(lines) == 1:
        return "**User's Health Profile Context:** No specific health profile provided by the user."
        
    return "\n".join(lines)

def save_medication_to_supabase(user_id, name, dose, timing, source="manual"):
    if not name or not user_id:
        logger.warning(f"Attempted to save wellness product without name or user_id. Name: {name}, User ID: {user_id}")
        return

    data = {
        "user_id": user_id,
        "name": name,
        "dose": dose,
        "timing": timing,
        "source": source,
        "created_at": datetime.utcnow().isoformat()
    }
    try:
        response = supabase.table("medications").insert(data).execute()
        if response.data:
            logger.info(f"✅ Saved wellness product to Supabase: {name} for user {user_id}")
        else:
            logger.error(f"❌ Failed to save wellness product {name} to Supabase: {response.error}")
    except Exception as e:
        logger.exception(f"Exception while saving wellness product {name} to Supabase for user {user_id}")

def generate_openai_response(user_input_text, language, profile_context, prompt_type="symptoms"):
    health_metric_context = """
    Normal Ranges for reference (use only if explicitly mentioned, otherwise ignore):
    - Blood Sugar (Fasting): 70-100 mg/dL (or 3.9-5.6 mmol/L). Below 70 mg/dL may indicate low blood sugar. Above 125 mg/dL may indicate high blood sugar.
    - Blood Pressure: Systolic < 120 mmHg, Diastolic < 80 mmHg.
    - Temperature: Oral ~98.6°F (37°C). Above 100.4°F (38°C) may indicate fever.
    """

    system_prompt = f"""
    You are an AI health assistant providing general wellness information. Your role is to help users understand potential health insights based on their symptoms and profile.
    
    IMPORTANT DISCLAIMER: 
    - I am not a medical professional and cannot provide diagnoses or treatment plans.
    - My responses are for informational purposes only and should not be considered medical advice.
    - Always consult with a qualified healthcare provider for medical concerns.

    {health_metric_context}

    --- User's Health Profile ---
    {profile_context}

    --- Instructions ---
    Based on the provided information, offer:
    1. Possible interpretations of symptoms (never diagnoses)
    2. General wellness suggestions
    3. When to consider professional consultation
    4. Educational information about health metrics

    Response Format (JSON):
    {{
        "health_insight": "General interpretation of symptoms (never a diagnosis)",
        "possible_conditions": ["Possible conditions that might match these symptoms"],
        "wellness_suggestions": ["General suggestions for self-care"],
        "consider_professional_help": "When to consider consulting a healthcare provider",
        "educational_info": "Helpful information about the symptoms",
        "wellness_products": [{{"name": "Product name", "dose": "", "time": ""}}],
        "urgency_level": "low/moderate/high",
        "specialist_suggestion": "Type of specialist that might be helpful if symptoms persist",
        "nursing_insight": "General nursing perspective on the situation",
        "personal_notes": "Additional considerations",
        "relevant_info": "Other relevant health context",
        "disclaimer": "I am an AI assistant and not a medical professional. This information is educational only and not a substitute for professional medical advice.",
        "sources": [{{"title": "", "url": ""}}],
        "health_summary": ["Key points from this interaction"]
    }}
    """

    if prompt_type == "symptoms":
        user_content = f"User reported: \"{user_input_text}\""
    elif prompt_type == "photo_analysis":
        user_content = f"Image shows: \"{user_input_text}\""
    elif prompt_type == "lab_report":
        user_content = f"Lab Report Text: \"{user_input_text}\""
    else:
        user_content = f"Input: \"{user_input_text}\""

    full_user_message = system_prompt + f"\n--- User's Input ---\n{user_content}"
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an AI health assistant providing general wellness information."},
                {"role": "user", "content": full_user_message}
            ],
            temperature=0.4,
            response_format={"type": "json_object"}
        )
        return response['choices'][0]['message']['content']
    except openai.APIError as e:
        logger.error(f"OpenAI API error: Status {e.status_code}, Response: {e.response}")
        return None
    except Exception as e:
        logger.error(f"Error in generate_openai_response: {e}")
        return None

def parse_openai_json(reply):
    try:
        match = re.search(r'```json\s*(\{.*?\})\s*```', reply, re.DOTALL)
        if match:
            json_str = match.group(1)
            logger.info(f"Found JSON in markdown block: {json_str[:100]}...")
        else:
            json_str = reply
            logger.info(f"Attempting to parse full reply as JSON: {json_str[:100]}...")
            
        parsed_data = json.loads(json_str)

        wellness_suggestions = parsed_data.get('wellness_suggestions')
        if not isinstance(wellness_suggestions, list):
            parsed_data['wellness_suggestions'] = [wellness_suggestions] if wellness_suggestions else []
            
        wellness_products = parsed_data.get('wellness_products')
        if not isinstance(wellness_products, list):
            parsed_data['wellness_products'] = [wellness_products] if isinstance(wellness_products, dict) else []
        parsed_data['wellness_products'] = [m for m in parsed_data['wellness_products'] if isinstance(m, dict)]

        sources = parsed_data.get('sources')
        if not isinstance(sources, list):
            parsed_data['sources'] = [sources] if isinstance(sources, dict) else []
        parsed_data['sources'] = [c for c in parsed_data['sources'] if isinstance(c, dict)]

        health_summary = parsed_data.get('health_summary')
        if not isinstance(health_summary, list):
            parsed_data['health_summary'] = [health_summary] if isinstance(health_summary, str) else ["General health information not provided"]
        
        parsed_data.setdefault('health_insight', 'General health information')
        parsed_data.setdefault('possible_conditions', ['Various possible conditions'])
        parsed_data.setdefault('wellness_suggestions', [])
        parsed_data.setdefault('consider_professional_help', 'Consult a healthcare provider if symptoms persist or worsen')
        parsed_data.setdefault('educational_info', 'General health information')
        parsed_data.setdefault('urgency_level', 'low')
        parsed_data.setdefault('specialist_suggestion', 'General Practitioner')
        parsed_data.setdefault('nursing_insight', 'General health perspective')
        parsed_data.setdefault('personal_notes', 'Additional considerations may apply')
        parsed_data.setdefault('relevant_info', 'General health context')
        parsed_data.setdefault('disclaimer', "I am an AI assistant and not a medical professional. This information is educational only and not a substitute for professional medical advice.")
        parsed_data.setdefault('sources', [])
        parsed_data.setdefault('wellness_products', [])
        parsed_data.setdefault('health_summary', ["General health information not provided"])
        
        return parsed_data
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {e}. Raw reply: {reply}")
        return {
            "health_insight": "I couldn't fully process the request. Please try again or rephrase your symptoms.",
            "possible_conditions": ["Various possible conditions"],
            "wellness_suggestions": [],
            "consider_professional_help": "Consult a healthcare provider if needed",
            "disclaimer": "I am an AI assistant and not a medical professional. This information is educational only and not a substitute for professional medical advice.",
            "urgency_level": "unknown",
            "specialist_suggestion": "general",
            "sources": [],
            "health_summary": ["General health information not provided"]
        }
    except Exception as e:
        logger.error(f"Unexpected error in JSON parsing: {e}")
        return {
            "health_insight": "An unexpected error occurred during analysis. Please try again.",
            "possible_conditions": ["Various possible conditions"],
            "wellness_suggestions": [],
            "consider_professional_help": "Consult a healthcare provider if needed",
            "disclaimer": "I am an AI assistant and not a medical professional. This information is educational only and not a substitute for professional medical advice.",
            "urgency_level": "unknown",
            "specialist_suggestion": "general",
            "sources": [],
            "health_summary": ["General health information not provided"]
        }

@app.route("/api/doctors", methods=["POST"])
@cross_origin()
@token_required
def api_get_doctors(current_user=None):
    data = request.get_json()
    specialty = data.get("specialty")
    location = data.get("location")

    if not specialty or not location:
        return jsonify({"error": "Specialty and location are required"}), 400

    if isinstance(location, str) and ',' in location:
        try:
            lat_str, lng_str = location.split(',')
            location = {'lat': float(lat_str), 'lng': float(lng_str)}
        except ValueError:
            return jsonify({"error": "Invalid location format"}), 400
    elif not isinstance(location, dict) or 'lat' not in location or 'lng' not in location:
        return jsonify({"error": "Invalid location object"}), 400

    doctors = get_nearby_doctors(specialty, location)
    return jsonify({"doctors": doctors}), 200

@app.route('/api/doctors', methods=['GET'])
@cross_origin()
@token_required
def doctors_api(current_user=None):
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    specialty = request.args.get('specialty', 'general')

    if not lat or not lng:
        return jsonify({'error': 'Missing lat/lng'}), 400

    try:
        location = {'lat': float(lat), 'lng': float(lng)}
    except ValueError:
        return jsonify({'error': 'Invalid lat/lng format'}), 400

    doctors = get_nearby_doctors(specialty, location)
    return jsonify({'results': doctors}), 200

def get_nearby_doctors(specialty, location):
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY is not set for Places API.")
        return []
        
    try:
        if isinstance(location, dict):
            lat = location.get("lat")
            lng = location.get("lng")
            if lat is None or lng is None:
                logger.error("Location dictionary missing 'lat' or 'lng' keys.")
                return []
            location_str = f"{lat},{lng}"
        elif isinstance(location, str) and "," in location:
            location_str = location
        else:
            logger.error(f"Invalid location format received: {location}. Expected dict or 'lat,lng' string.")
            return []

        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "keyword": f"{specialty} doctor",
            "location": location_str,
            "radius": 10000,
            "type": "doctor",
            "key": GOOGLE_API_KEY,
            "rankby": "prominence"
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        results = response.json().get("results", [])
        
        filtered_results = [p for p in results if p.get("rating") is not None]
        sorted_results = sorted(
            filtered_results, 
            key=lambda x: (x.get("rating", 0), x.get("opening_hours", {}).get("open_now", False) if isinstance(x.get("opening_hours"), dict) else False), 
            reverse=True
        )

        doctors = []
        for place in sorted_results[:5]:
            open_now = place.get("opening_hours", {}).get("open_now", False)
            
            place_name = place.get('name', '')
            place_vicinity = place.get('vicinity', '')
            query_string = requests.utils.quote(f"{place_name}, {place_vicinity}")
            
            maps_link = f"https://www.google.com/maps/search/?api=1&query={query_string}&query_place_id={place.get('place_id')}"

            doctors.append({
                "name": place_name,
                "address": place_vicinity,
                "rating": place.get("rating"),
                "open_now": open_now,
                "phone": place.get("international_phone_number"),
                "maps_link": maps_link
            })
        return doctors
    except requests.exceptions.RequestException as e:
        logger.error(f"Google Maps API request failed: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching nearby doctors: {e}")
        return []

def get_image_labels(base64_image):
    if not GOOGLE_VISION_API_KEY:
        logger.error("GOOGLE_VISION_API_KEY is not set for Vision API.")
        return []
        
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [{
                "image": {"content": base64_image},
                "features": [{"type": "LABEL_DETECTION", "maxResults": 10}]
            }]
        }
        res = requests.post(url, json=body)
        res.raise_for_status()
        labels = [label['description'] for label in res.json().get("responses", [{}])[0].get("labelAnnotations", [])]
        return labels
    except requests.exceptions.RequestException as e:
        logger.error(f"Google Vision API request failed: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting image labels: {e}")
        return []

def get_image_text(base64_image):
    if not GOOGLE_VISION_API_KEY:
        logger.error("GOOGLE_VISION_API_KEY is not set for Vision API.")
        return ""

    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [{
                "image": {"content": base64_image},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }
        res = requests.post(url, json=body)
        res.raise_for_status()
        annotations = res.json().get("responses", [{}])[0]
        extracted_text = annotations.get("fullTextAnnotation", {}).get("text", "")
        return extracted_text
    except requests.exceptions.RequestException as e:
        logger.error(f"Google Vision OCR request failed: {e}")
        return ""
    except Exception as e:
        logger.error(f"Error extracting image text: {e}")
        return ""

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route("/analyze", methods=["POST"])
@cross_origin()
@token_required
def analyze_symptoms(current_user=None):
    try:
        data = request.get_json()
        symptoms = data.get('symptoms')
        profile_data = data.get('profile', {})
        location = data.get('location')
        user_id = profile_data.get('user_id')
        language = data.get("language", "English")

        if not symptoms:
            return jsonify({'error': 'Symptoms required'}), 400
        if not user_id:
            logger.warning("Analyze request received without user_id. History and wellness products cannot be saved.")

        logger.info(f"[ANALYZE] Input: {symptoms}, User ID: {user_id}")
        profile_context = build_profile_context(profile_data)
        
        ai_response_content = generate_openai_response(symptoms, language, profile_context, prompt_type="symptoms")
        if not ai_response_content:
            return jsonify({"error": "AI analysis failed to generate response from OpenAI"}), 500
            
        result_json = parse_openai_json(ai_response_content) 

        if user_id and result_json.get("wellness_products"):
            for med in result_json["wellness_products"]:
                if isinstance(med, dict):
                    save_medication_to_supabase(
                        user_id=user_id, 
                        name=med.get("name"), 
                        dose=med.get("dose"), 
                        timing=med.get("time"),
                        source="chat"
                    )

        if location and result_json.get("specialist_suggestion"):
            result_json["nearby_doctors"] = get_nearby_doctors(result_json["specialist_suggestion"], location)
        else:
            result_json["nearby_doctors"] = []

        if user_id:
            try:
                health_summary_data = result_json.get("health_summary", ["General health information not provided"])
                if not isinstance(health_summary_data, list):
                    health_summary_data = [health_summary_data]

                save_payload = {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "query": symptoms,
                    "response": result_json,
                    "summary": health_summary_data,
                    "detected_condition": result_json.get("possible_conditions", ["Various possible conditions"])[0],
                    "medical_analysis": result_json.get("health_insight"),
                    "urgency": result_json.get("urgency_level"),
                    "suggested_doctor": result_json.get("specialist_suggestion"),
                    "timestamp": datetime.utcnow().isoformat(),
                    "raw_text": json.dumps(result_json)
                }
                
                supabase_response = supabase.table("history").insert(save_payload).execute()
                if supabase_response.data:
                    logger.info(f"✅ Saved analysis to history for user {user_id}")
                else:
                    logger.error(f"❌ Failed to save history for user {user_id}: {supabase_response.error}")
            except Exception as e:
                logger.exception(f"Exception while saving history for user {user_id}:")
        
        return jsonify(result_json), 200

    except Exception as e:
        logger.exception("Error in /analyze route")
        return jsonify({'error': 'Failed to analyze symptoms', "details": str(e)}), 500

@app.route('/analyze-trends', methods=['POST'])
@cross_origin()
@token_required
def analyze_trends(current_user=None):
    try:
        data = request.get_json()

        symptoms = data.get("symptoms", [])
        profile_context = data.get("profile_context", "")
        user_id = data.get('user_id')

        if not symptoms or not isinstance(symptoms, list):
            logger.error("Missing or invalid symptom data for trend analysis.")
            return jsonify({"error": "Missing or invalid symptom data"}), 400
            
        trend_input = "User's Symptom Timeline:\n"
        for entry in symptoms:
            date = entry.get("date", "N/A")
            issue = entry.get("issue", "N/A")
            symptom = entry.get("symptom", "N/A")
            severity = entry.get("severity", "N/A")
            status = entry.get("status", "N/A")
            trend_input += f"- Date: {date}, Issue: {issue}, Symptom: {symptom}, Severity: {severity}/10, Status: {status}\n"

        prompt = f"""
You are an AI health assistant analyzing symptom patterns. Provide general insights only, not medical advice.

{profile_context}

The user has logged these symptoms over time:

{trend_input}

Generate a wellness-focused summary with:
- Observed symptom patterns
- General wellness suggestions
- When to consider professional consultation
- Educational information

Include this disclaimer:
"Note: I am not a medical professional. This is general wellness information only. Always consult a healthcare provider for medical concerns."

Example format:
- Pattern: ...
- Wellness suggestions: ...
- Consider professional help if: ...
- Educational notes: ...
"""

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an AI health assistant providing general wellness insights."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=600
        )

        summary_text = response['choices'][0]['message']['content'].strip()

        return jsonify({ 
            "summary": summary_text,
            "sources": [{
                "title": "General Health Information",
                "url": "https://www.cdc.gov/healthcommunication/toolstemplates/entertainmented/tips/GeneralHealth.html"
            }]
        })

    except openai.APIError as e:
        logger.error(f"OpenAI API error in /analyze-trends: {e.status_code} - {e.response}")
        return jsonify({"error": "AI trend analysis failed due to API error", "details": str(e.response)}), 500
    except Exception as e:
        logger.exception("AI trend summary error:")
        return jsonify({"error": "Trend analysis failed", "details": str(e)}), 500

@app.route("/api/ask", methods=["POST"])
@cross_origin()
@token_required
def ask(current_user=None):
    data = request.get_json()
    question = data.get("question", "")
    if not question:
        return jsonify({"error": "No question provided"}), 400

    logger.info(f"[ASK] Question: {question}")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{ "role": "user", "content": question }],
            temperature=0.5
        )
        reply = response["choices"][0]["message"]["content"]
        return jsonify({ "reply": reply })
    except openai.APIError as e:
        logger.error(f"OpenAI API error in /ask: {e.status_code} - {e.response}")
        return jsonify({ "error": "OpenAI request failed" }), 500
    except Exception as e:
        logger.error(f"Error in /ask: {e}")
        return jsonify({ "error": "An unexpected error occurred" }), 500

@app.route("/photo-analyze", methods=["POST"])
@cross_origin()
@token_required
def analyze_photo(current_user=None):
    data = request.get_json()
    image_base64 = data.get("image_base64")
    profile_data = data.get("profile", {})
    location_data = data.get("location", "")
    
    if not image_base64:
        return jsonify({"error": "No image provided"}), 400

    logger.info("📸 /photo-analyze: Analyzing image for labels and text")

    labels = get_image_labels(image_base64)
    detected_text = get_image_text(image_base64)

    image_description_for_llm = f"The image provides visual cues: {', '.join(labels)}."
    if detected_text:
        image_description_for_llm += f" Additionally, text detected in the image: \"{detected_text}\""
    
    profile_context = build_profile_context(profile_data)

    llm_reply_content = generate_openai_response(image_description_for_llm, "English", profile_context, prompt_type="photo_analysis")

    if not llm_reply_content:
        return jsonify({"error": "AI analysis failed to generate response."}), 500

    parsed_analysis = parse_openai_json(llm_reply_content)

    if location_data and parsed_analysis.get("specialist_suggestion"):
        parsed_analysis["nearby_doctors"] = get_nearby_doctors(parsed_analysis["specialist_suggestion"], location_data)
    else:
        parsed_analysis["nearby_doctors"] = []
    
    parsed_analysis["image_labels"] = labels
    parsed_analysis["image_description"] = image_description_for_llm

    return jsonify(parsed_analysis)

@app.route("/analyze-lab-report", methods=["POST"])
@cross_origin()
@token_required
def analyze_lab_report(current_user=None):
    data = request.get_json()
    image_base64 = data.get("image_base64")
    extracted_text_from_frontend = data.get("extracted_text", "")
    location = data.get("location", "")
    profile_data = data.get("profile", {})
    language = data.get("language", "English")

    final_text_for_ai = ""

    if extracted_text_from_frontend and extracted_text_from_frontend != "PDF document uploaded. Extracting text on backend...":
        final_text_for_ai = extracted_text_from_frontend
        logger.info("🧪 Using frontend extracted text for lab report analysis.")
    elif image_base64:
        logger.info("🧪 Performing OCR on backend for lab report image...")
        extracted_text_from_backend = get_image_text(image_base64)
        if not extracted_text_from_backend:
            return jsonify({"error": "OCR failed to extract text from backend for image"}), 500
        final_text_for_ai = extracted_text_from_backend

    if not final_text_for_ai:
        return jsonify({"error": "Missing lab report text or image to analyze"}), 400

    profile_context = build_profile_context(profile_data)
    reply_content = generate_openai_response(final_text_for_ai, language, profile_context, prompt_type="lab_report")

    if not reply_content:
        return jsonify({"error": "AI failed to generate response for lab report"}), 500

    parsed_response = parse_openai_json(reply_content)

    if location and parsed_response.get("specialist_suggestion"):
        parsed_response["nearby_doctors"] = get_nearby_doctors(parsed_response["specialist_suggestion"], location)
    else:
        parsed_response["nearby_doctors"] = []

    parsed_response["extracted_text"] = final_text_for_ai
    return jsonify(parsed_response)
    
@app.route('/api/history', methods=['POST'])
@cross_origin()
@token_required
def save_history(current_user=None):
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        query = data.get('query')
        response = data.get('response')

        if not user_id or not query or not response:
            return jsonify({"error": "Missing user_id, query, or response"}), 400

        parsed_response = response if isinstance(response, dict) else json.loads(response)

        wellness_products = parsed_response.get('wellness_products')
        wellness_suggestions = parsed_response.get('wellness_suggestions')
        sources = parsed_response.get('sources')
        health_summary_data = parsed_response.get('health_summary', ["General health information not provided"])

        if not isinstance(wellness_products, list):
            wellness_products = [wellness_products] if isinstance(wellness_products, dict) else [] 
        if not isinstance(wellness_suggestions, list):
            wellness_suggestions = [wellness_suggestions] if wellness_suggestions else []
        if not isinstance(sources, list):
            sources = [sources] if isinstance(sources, dict) else []
        if not isinstance(health_summary_data, list):
            health_summary_data = [health_summary_data]
        
        wellness_products = [m for m in wellness_products if isinstance(m, dict)]
        sources = [c for c in sources if isinstance(c, dict)]

        payload = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "query": query,
            "detected_condition": parsed_response.get("possible_conditions", ["Various possible conditions"])[0],
            "medical_analysis": parsed_response.get("health_insight"),
            "remedies": wellness_suggestions,
            "urgency": parsed_response.get("urgency_level"),
            "medicines": wellness_products, 
            "suggested_doctor": parsed_response.get("specialist_suggestion"),
            "raw_text": json.dumps(parsed_response),
            "timestamp": datetime.utcnow().isoformat(),
            "nursing_explanation": parsed_response.get("nursing_insight"),
            "personal_notes": parsed_response.get("personal_notes"),
            "relevant_information": parsed_response.get("relevant_info"),
            "why_happening_explanation": parsed_response.get("educational_info"),
            "immediate_action": parsed_response.get("consider_professional_help"),
            "nurse_tips": parsed_response.get("wellness_suggestions"),
            "citations": sources,
            "summary": health_summary_data
        }

        logger.info(f"Saving history for user_id: {user_id}")

        supabase_url = f"{SUPABASE_URL}/rest/v1/history"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        r = requests.post(supabase_url, headers=headers, data=json.dumps(payload))
        if r.status_code != 201:
            logger.error(f"Supabase Insert Error: {r.text}")
            return jsonify({"error": "Failed to save history", "details": r.text}), 500

        return jsonify({"success": True, "data": r.json()}), 200

    except Exception as e:
        logger.exception("Exception while saving history")
        return jsonify({"error": str(e)}), 500

@app.route('/api/history', methods=['GET'])
@cross_origin()
@token_required
def get_history(current_user=None):
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    try:
        supabase_url = f"{SUPABASE_URL}/rest/v1/history?user_id=eq.{user_id}&order=timestamp.desc"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.get(supabase_url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Supabase fetch error: {response.text}")
            return jsonify({"error": "Failed to fetch history", "details": response.text}), 500

        history_data = response.json()
        for entry in history_data:
            if 'raw_text' in entry and isinstance(entry['raw_text'], str):
                try:
                    entry['response'] = json.loads(entry['raw_text'])
                    for key in ['citations', 'wellness_products', 'health_summary']:
                        if key in entry['response'] and not isinstance(entry['response'][key], list):
                            entry['response'][key] = [entry['response'][key]] if entry['response'][key] else []
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse raw_text for history entry {entry.get('id')}. Setting response to empty dict.")
                    entry['response'] = {}
            else:
                entry['response'] = entry.get('response', {})

            for key in ['citations', 'medicines', 'summary']:
                if key in entry and not isinstance(entry[key], list):
                    entry[key] = [entry[key]] if entry[key] else []

        return jsonify(history_data), 200

    except Exception as e:
        logger.exception("Exception while fetching history")
        return jsonify({"error": str(e)}), 500

@app.route("/request-password-reset", methods=["POST"])
@cross_origin()
@token_required
def request_password_reset(current_user=None):
    data = request.get_json()
    email = data.get("email")
    frontend_redirect_url = data.get("redirect_to")

    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    if not frontend_redirect_url:
        return jsonify({"error": "Redirect URL for password reset is required"}), 400

    logger.info(f"Received password reset request for email: {email}")

    supabase_reset_url = f"{SUPABASE_URL}/auth/v1/recover"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "email": email,
        "redirect_to": frontend_redirect_url
    }

    try:
        response = requests.post(supabase_reset_url, headers=headers, json=payload)
        response.raise_for_status()

        logger.info(f"Supabase password reset request sent for {email}. Status: {response.status_code}")
        return jsonify({"message": "Password reset email sent. Please check your inbox (and spam folder!)."}), 200
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending password reset request to Supabase: {e}")
        return jsonify({"error": "Failed to send password reset email. Please try again later."}), 500
    except Exception as e:
        logger.error(f"Unexpected error in /request-password-reset: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500

@app.route("/api/test-delete-log", methods=["GET"])
def test_log_route():
    print("[TEST LOG] This route was hit!")
    return jsonify({"message": "Logging works!"})
    
@app.route("/api/delete-account", methods=["POST"])
@cross_origin()
@token_required
def delete_account(current_user=None):
    try:
        data = request.get_json()
        user_id = data.get("user_id")

        print(f"[DELETE] Request received for user_id: {user_id}")

        if not user_id:
            print("[DELETE] ❌ Missing user_id in request")
            return jsonify({
                "result": {
                    "success": False,
                    "error": "Missing user_id"
                }
            }), 400

        service_role_headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Prefer": "return=representation"
        }

        profile_url = f"{SUPABASE_URL}/rest/v1/profiles?user_id=eq.{user_id}"
        history_url = f"{SUPABASE_URL}/rest/v1/history?user_id=eq.{user_id}"
        medications_url = f"{SUPABASE_URL}/rest/v1/medications?user_id=eq.{user_id}"

        profile_response = requests.delete(profile_url, headers=service_role_headers)
        history_response = requests.delete(history_url, headers=service_role_headers)
        medications_response = requests.delete(medications_url, headers=service_role_headers)

        print(f"[DELETE] 🔄 Profile deleted: {profile_response.status_code}")
        print(f"[DELETE] 🔄 History deleted: {history_response.status_code}")
        print(f"[DELETE] 🔄 Medications deleted: {medications_response.status_code}")

        if not (profile_response.status_code in [200, 204] and 
                history_response.status_code in [200, 204] and
                medications_response.status_code in [200, 204]):
            
            if profile_response.status_code not in [200, 204]:
                logger.error(f"Failed to delete profile: {profile_response.status_code} - {profile_response.text}")
            if history_response.status_code not in [200, 204]:
                logger.error(f"Failed to delete history: {history_response.status_code} - {history_response.text}")
            if medications_response.status_code not in [200, 204]:
                logger.error(f"Failed to delete medications: {medications_response.status_code} - {medications_response.text}")

            return jsonify({
                "result": {
                    "success": False,
                    "error": "Failed to delete user data (profile, history, or medications)",
                    "details": {
                        "profile_status": profile_response.status_code,
                        "history_status": history_response.status_code,
                        "medications_status": medications_response.status_code,
                        "profile_error": profile_response.text,
                        "history_error": history_response.text,
                        "medications_error": medications_response.text
                    }
                }
            }), 500

        service_headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json"
        }

        delete_auth_url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
        auth_response = requests.delete(delete_auth_url, headers=service_headers)

        print(f"[AUTH DELETE] 🔐 Status: {auth_response.status_code}")
        print(f"[AUTH DELETE] 🔐 Response: {auth_response.text}")

        if auth_response.status_code != 204:
            logger.error(f"Failed to delete user from Supabase Auth: {auth_response.status_code} - {auth_response.text}")
            return jsonify({
                "result": {
                    "success": False,
                    "error": "Failed to delete user from Supabase Auth",
                    "details": auth_response.text
                }
            }), 500

        print(f"[✅ DELETE] Successfully removed all data for user {user_id}")
        return jsonify({
            "result": {
                "success": True,
                "message": "Account and associated data deleted successfully."
            }
        }), 200

    except Exception as e:
        logger.exception("[ERROR] ❌ Account deletion failed unexpectedly:")
        return jsonify({
            "result": {
                "success": False,
                "error": "Internal server error during account deletion",
                "details": str(e)
            }
        }), 500

@app.route("/verify-password-reset", methods=["GET"])
@cross_origin()
def verify_password_reset():
    access_token = request.args.get("access_token")
    refresh_token = request.args.get("refresh_token")

    if access_token and refresh_token:
        frontend_reset_url = "https://askdocapp-92cc3.web.app/reset-password.html"
        full_redirect_url = f"{frontend_reset_url}#access_token={access_token}&refresh_token={refresh_token}"
        logger.info(f"Redirecting to frontend reset page: {full_redirect_url}")
        return redirect(full_redirect_url)
    else:
        logger.warning("Missing access_token or refresh_token in /verify-password-reset. Redirecting to error.")
        return redirect("https://askdocapp-92cc3.web.app/reset-password.html?error=invalid_link")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  
    app.run(host='0.0.0.0', port=port)
