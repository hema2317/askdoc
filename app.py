import uuid
import os
import json
import logging
import re
from datetime import datetime
from functools import wraps # Import functools for decorators

from flask import Flask, request, jsonify, redirect, url_for, make_response # Import make_response for decorator
from flask_cors import CORS, cross_origin # Ensure cross_origin is imported
import openai
import requests
import psycopg2
from psycopg2 import OperationalError
import base64
from dotenv import load_dotenv

load_dotenv() # ✅ Load environment variables

app = Flask(__name__) # ✅ Define app only once
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN") # The secret token expected from frontend

# Supabase Project URL and Anon Key (from your frontend code)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://nlfvwbjpeywcessqyqac.supabase.co")
# IMPORTANT: Double-check this SUPABASE_ANON_KEY. The one in your traceback looks different from a valid anon key format.
# It should be a long string starting with 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
# Your previous snippet had: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5sZnZ3YmpwZXl3Y2Vzc3F5cWFjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU4NTczNjQsImV4cCI6MjA2MTQzMzM2NH0.zL84P7bK7qHxJt8MtkTPkqNe4U_K512ZgtpPvD9PoRI"
# Which looked more correct.
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5sZnZ3YmpwZXl3Y2Vzc3F5cWFjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU4NTczNjQsImV4cCI6MjA2MTQzMzM2NH0.zL84P7bK7qHxJt8MtkTPkqNe4U_K512ZgtpPvD9PoRI")


openai.api_key = OPENAI_API_KEY

# --- Authentication Middleware (Updated for decorator pattern) ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"Unauthorized access attempt: No Bearer token provided or malformed header.")
            return make_response(jsonify({"error": "Unauthorized: Bearer token missing or malformed"}), 401) # Use make_response

        token = auth_header.split(" ")[1] # Extract the token part
        if token != API_AUTH_TOKEN:
            logger.warning(f"Unauthorized access attempt: Invalid API token. Provided: {token}")
            return make_response(jsonify({"error": "Unauthorized: Invalid API token"}), 401) # Use make_response
        
        # In a real app, you'd verify the JWT token here and extract user_id.
        # For this example, we'll pass a dummy current_user.
        current_user = {"id": "auth_user_id"} # Replace with actual user ID from token validation if available
        return f(current_user=current_user, *args, **kwargs)
    return decorated

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

def build_profile_context(profile_json):
    """Builds a human-readable context string from the user's profile data."""
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
            lines.append("- Known Medical Conditions: " + ", ".join(medical_conditions))
        elif isinstance(medical_conditions, str):
            lines.append("- Known Medical Conditions: " + medical_conditions)
    if current_medications := profile.get("medications"):
        if isinstance(current_medications, list):
            lines.append("- Current Medications: " + ", ".join(current_medications))
        elif isinstance(current_medications, str):
            lines.append("- Current Medications: " + current_medications)
    if family_history := profile.get("family_history"):
        if isinstance(family_history, list):
            lines.append("- Family History of: " + ", ".join(family_history))
        elif isinstance(family_history, str):
            lines.append("- Family History of: " + family_history)
    if known_diseases := profile.get("known_diseases"):
        if isinstance(known_diseases, list):
            lines.append("- Other Known Diseases: " + ", ".join(known_diseases))
        elif isinstance(known_diseases, str):
            lines.append("- Other Known Diseases: " + known_diseases)

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


def generate_openai_response(user_input_text, language, profile_context, prompt_type="symptoms"):
    """
    Generates a detailed, nurse-like response from OpenAI based on input and profile.
    Adapted for different prompt types (symptoms, photo, lab report).
    """
    
    health_metric_context = """
    Normal Ranges for reference (use only if explicitly mentioned, otherwise ignore):
    - Blood Sugar (Fasting): 70-100 mg/dL (or 3.9-5.6 mmol/L). Below 70 mg/dL is Hypoglycemia (low). Above 125 mg/dL is Hyperglycemia (high).
    - Blood Pressure: Systolic < 120 mmHg, Diastolic < 80 mmHg.
    - Temperature: Oral ~98.6°F (37°C). Fever generally >100.4°F (38°C).
    """

    base_prompt = f"""
    You are a highly knowledgeable, empathetic, and responsible virtual health assistant. Your role is to act as a compassionate nurse or health educator.
    You must *always* provide information that is easy to understand for a layperson.
    Your initial greeting must *always* be a disclaimer.

    Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment.

    {health_metric_context}

    --- User's Health Profile ---
    {profile_context}

    --- Task Instructions ---
    Based on the provided information and the user's health profile, provide a structured and detailed analysis.
    Ensure the language is simple, supportive, and actionable, like a compassionate nurse explaining things.
    **Crucially, explicitly use and reference information from the user's health profile to personalize the analysis, advice, and tips.** For example, if they have diabetes and report low sugar, tailor the advice by explicitly mentioning their diabetes. If they smoke, weave in advice related to smoking cessation for their condition.
    Be very careful with numerical values for health metrics (like blood sugar); explicitly state if a number indicates "low," "normal," or "high" and specify units if implied.

    Generate your response as a JSON object with the following keys. All explanations should be concise but informative, aiming for clarity and actionability for a layperson. If a field is not applicable or information is insufficient, you can state "Not applicable" or "Insufficient information.":

    1.  detected_condition: A concise, most likely medical condition (e.g., 'Hypoglycemia', 'Common Cold', 'Muscle Strain').
    2.  medical_analysis: A comprehensive overview of the condition and symptoms. Explain it in simple, layman's terms. **Directly relate it to the user's profile where relevant.**
    3.  why_happening_explanation: Explain *why* the condition might be happening in simple, understandable terms. Consider profile factors like medications, habits, or pre-existing conditions.
    4.  immediate_action: What the person should *do immediately* or in the very short term. Be specific, actionable, and prioritize safety.
    5.  nurse_tips: **Proactive education and practical advice, like a nurse would provide.** This is where you significantly personalize guidance based on their profile. Include prevention, monitoring, or lifestyle advice tailored to their known conditions, habits (smoking, drinking, exercise), or family history.
    6.  remedies: General suggestions for self-care or lifestyle adjustments for recovery or management.
    7.  medicines: Common over-the-counter or general types of prescribed medications *related to the condition*. **Explicitly state this is NOT a prescription and they must consult a doctor.**
    8.  urgency: Categorize the urgency (e.g., 'Immediate Emergency', 'Urgent Consult', 'Moderate', 'Low').
    9.  suggested_doctor: The type of medical specialist they might need to see.
    10. nursing_explanation: A simplified nursing explanation of the condition or situation.
    11. personal_notes: Any additional personalized notes or considerations for the user.
    12. relevant_information: Any other relevant health information or context.
    13. hipaa_disclaimer: The exact disclaimer text: "Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment."
    14. citations: (NEW) An array of objects, where each object has "title" (string) and "url" (string) for source links. Provide at least 2-3 credible sources relevant to the generated analysis (e.g., Mayo Clinic, CDC, WebMD). If no specific source is directly applicable, return an empty array.
    """

    if prompt_type == "symptoms":
        user_content = f"Symptoms: \"{user_input_text}\""
    elif prompt_type == "photo_analysis":
        user_content = f"Image shows: \"{user_input_text}\"" # user_input_text will be image labels/description
    elif prompt_type == "lab_report":
        user_content = f"Lab Report Text: \"{user_input_text}\"" # user_input_text will be extracted lab report text
    else:
        user_content = f"Input: \"{user_input_text}\""

    full_prompt = base_prompt + f"\n--- User's Input ---\n{user_content}"
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o", # Recommended for better JSON reliability, gpt-3.5-turbo might be less consistent
            messages=[
                {"role": "system", "content": "You are a helpful multilingual health assistant. Adhere strictly to the requested JSON format. Provide citations in the 'citations' array."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.4, # Keep temperature low for factual consistency
            response_format={"type": "json_object"} # Explicitly request JSON object (for newer OpenAI versions)
        )
        return response['choices'][0]['message']['content']
    except openai.APIError as e: # Use openai.APIError for new versions
        logger.error(f"OpenAI API error: {e.status_code} - {e.response}")
        return None
    except Exception as e:
        logger.error(f"Error in generate_openai_response: {e}")
        return None

def parse_openai_json(reply):
    """
    Parses the JSON string from OpenAI's reply.
    It's robust to cases where the reply might contain extra text outside the JSON block.
    Ensures 'remedies' and 'medicines' are always lists, and adds default for new fields.
    """
    try:
        # Try to find a JSON block wrapped in markdown code fences first
        # FIX: Ensure regex pattern is correctly formed as a multiline string
        match = re.search(r'```json\s*(\{.*?\})\s*```', reply, re.DOTALL)
        if match:
            json_str = match.group(1)
            logger.info(f"Found JSON in markdown block: {json_str[:100]}...")
        else:
            json_str = reply
            logger.info(f"Attempting to parse full reply as JSON: {json_str[:100]}...")
            
        parsed_data = json.loads(json_str)

        remedies = parsed_data.get('remedies')
        if not isinstance(remedies, list):
            parsed_data['remedies'] = [remedies] if remedies else []
            
        medicines = parsed_data.get('medicines')
        if not isinstance(medicines, list):
            parsed_data['medicines'] = [medicines] if medicines else []

        parsed_data.setdefault('nursing_explanation', 'Not provided.')
        parsed_data.setdefault('personal_notes', 'Not provided.')
        parsed_data.setdefault('relevant_information', 'Not provided.')
        parsed_data.setdefault('why_happening_explanation', 'Not provided.')
        parsed_data.setdefault('immediate_action', 'Not provided.')
        parsed_data.setdefault('nurse_tips', 'Not provided.')
        parsed_data.setdefault('citations', [])

        return parsed_data
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {e}. Raw reply: {reply}")
        return {
            "medical_analysis": "I'm sorry, I couldn't fully process the request. Please try again or rephrase your symptoms. (JSON Parse Error)",
            "root_cause": "Parsing error or unclear AI response.",
            "remedies": [], "medicines": [], "detected_condition": "unsure",
            "why_happening_explanation": "Insufficient information.", "immediate_action": "Consult a healthcare professional.",
            "nurse_tips": "It's important to provide clear and concise information for accurate analysis. Always seek medical advice from a qualified doctor.",
            "hipaa_disclaimer": "Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment.",
            "urgency": "unknown", "suggested_doctor": "general",
            "nursing_explanation": "Not provided.", "personal_notes": "Not provided.", "relevant_information": "Not provided.",
            "citations": []
        }
    except Exception as e:
        logger.error(f"Unexpected error in JSON parsing: {e}")
        return {
            "medical_analysis": "An unexpected error occurred during analysis. Please try again. (Unknown Error)",
            "root_cause": "Unknown error.",
            "remedies": [], "medicines": [], "detected_condition": "unsure",
            "why_happening_explanation": "An internal error occurred.", "immediate_action": "Consult a healthcare professional.",
            "nurse_tips": "If issues persist, please contact support. Always seek medical advice from a qualified doctor.",
            "hipaa_disclaimer": "Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment.",
            "urgency": "unknown", "suggested_doctor": "general",
            "nursing_explanation": "Not provided.", "personal_notes": "Not provided.", "relevant_information": "Not provided.",
            "citations": []
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
    """Fetches nearby doctors using Google Places API."""
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
    """Uses Google Vision API to get labels from an image."""
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
    """Uses Google Vision API to perform OCR (Text Detection) on an image."""
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
@token_required # Apply the decorator directly
def analyze_symptoms(current_user=None): # Accept current_user
    try:
        data = request.get_json()
        symptoms = data.get('symptoms')
        profile_data = data.get('profile', {})
        location = data.get('location')
        language = data.get("language", "English")

        if not symptoms:
            return jsonify({'error': 'Symptoms required'}), 400

        logger.info(f"[ANALYZE] Input: {symptoms}")
        profile_context = build_profile_context(profile_data)
        
        ai_response = generate_openai_response(symptoms, language, profile_context, prompt_type="symptoms")
        if not ai_response:
            return jsonify({"error": "AI analysis failed to generate response from OpenAI"}), 500
            
        result = parse_openai_json(ai_response)

        if location and result.get("suggested_doctor"):
            result["nearby_doctors"] = get_nearby_doctors(result["suggested_doctor"], location)
        else:
            result["nearby_doctors"] = []

        return jsonify(result), 200

    except Exception as e:
        logger.exception("Error in /analyze route")
        return jsonify({'error': 'Failed to analyze symptoms'}), 500
        
@app.route('/analyze-trends', methods=['POST'])
@cross_origin()
@token_required
def analyze_trends(current_user=None):
    try:
        data = request.get_json()

        symptoms = data.get("symptoms", [])
        profile_context = data.get("profile_context", "")

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
You are a medical AI assistant analyzing a user's symptom timeline to identify health trends.
{profile_context}

The user has logged the following symptoms over time:

{trend_input}

Please generate a concise and actionable health trend summary based on the provided timeline.
The summary should be in 4-6 bullet points and adhere to the following:
- Identify and describe **patterns or recurring symptoms** (e.g., "Headaches appearing every Tuesday").
- Mention if the overall **condition seems to be improving, worsening, or remaining stable** based on severity and status.
- **Suggest if medical attention is advised** (e.g., "Consult a doctor if symptoms persist").
- Offer **AI-generated general tips** (e.g., "Ensure adequate hydration," "Prioritize consistent sleep," "Consider stress reduction techniques.").
- Include **citations** (at least 1-2 credible sources like CDC, Mayo Clinic, WebMD) related to common trends or general health advice in the format: "Citations: [Title](URL), [Title](URL)". If no direct citation applies, state "No specific citations for trends."

Example of desired output format for trends:
- Pattern identified: ...
- Trend observed: ...
- Medical advice: ...
- AI tips: ...
Citations: [Title](URL), [Title](URL)
"""

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful medical AI assistant summarizing health trends based on provided symptom timelines."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=600
        )

        summary_text = response['choices'][0]['message']['content'].strip()

        citations_match = re.search(r'Citations:\s*(.*)', summary_text, re.IGNORECASE)
        citations_list = []
        if citations_match:
            citations_str = citations_match.group(1).strip()
            summary_text = summary_text.replace(citations_match.group(0), "").strip()

            if citations_str.lower() != "no specific citations for trends.":
                link_pattern = re.compile(r'\[(.*?)\]\((.*?)\)')
                for match in link_pattern.finditer(citations_str):
                    citations_list.append({"title": match.group(1), "url": match.group(2)})
        
        if not citations_list:
            citations_list.append({
                "title": "General Health Trends & Wellness",
                "url": "https://www.who.int/health-topics/health-and-wellness"
            })


        return jsonify({ 
            "summary": summary_text,
            "citations": citations_list
        })

    except openai.APIError as e:
        logger.error(f"OpenAI API error in /analyze-trends: {e.status_code} - {e.response}")
        return jsonify({"error": "AI trend analysis failed due to API error", "details": str(e.response)}), 500
    except Exception as e:
        logger.exception("AI trend summary error:")
        return jsonify({"error": "Trend analysis failed", "details": str(e)}), 500

@app.route("/api/ask", methods=["POST"])
@cross_origin()
@token_required # Apply the decorator directly
def ask(current_user=None): # Accept current_user
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
@token_required # Apply the decorator directly
def analyze_photo(current_user=None): # Accept current_user
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

    if location_data and parsed_analysis.get("suggested_doctor"):
        parsed_analysis["nearby_doctors"] = get_nearby_doctors(parsed_analysis["suggested_doctor"], location_data)
    else:
        parsed_analysis["nearby_doctors"] = []
    
    parsed_analysis["image_labels"] = labels
    parsed_analysis["image_description"] = image_description_for_llm

    return jsonify(parsed_analysis)

@app.route("/analyze-lab-report", methods=["POST"])
@cross_origin()
@token_required # Apply the decorator directly
def analyze_lab_report(current_user=None): # Accept current_user
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

    if location and parsed_response.get("suggested_doctor"):
        parsed_response["nearby_doctors"] = get_nearby_doctors(parsed_response["suggested_doctor"], location)
    else:
        parsed_response["nearby_doctors"] = []

    parsed_response["extracted_text"] = final_text_for_ai
    return jsonify(parsed_response)
    

@app.route('/api/history', methods=['POST'])
@cross_origin()
@token_required # Apply the decorator directly
def save_history(current_user=None): # Accept current_user
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        query = data.get('query')
        response = data.get('response')

        if not user_id or not query or not response:
            return jsonify({"error": "Missing user_id, query, or response"}), 400

        parsed_response = response if isinstance(response, dict) else json.loads(response)

        medicines = parsed_response.get("medicines")
        remedies = parsed_response.get("remedies")
        citations = parsed_response.get("citations")

        if not isinstance(medicines, list):
            medicines = [medicines] if medicines else []
        if not isinstance(remedies, list):
            remedies = [remedies] if remedies else []
        if not isinstance(citations, list):
            citations = [citations] if citations else []

        payload = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "query": query,
            "detected_condition": parsed_response.get("detected_condition"),
            "medical_analysis": parsed_response.get("medical_analysis"),
            "remedies": remedies,
            "urgency": parsed_response.get("urgency"),
            "medicines": medicines,
            "suggested_doctor": parsed_response.get("suggested_doctor"),
            "raw_text": json.dumps(parsed_response),
            "timestamp": datetime.utcnow().isoformat(),
            "nursing_explanation": parsed_response.get("nursing_explanation"),
            "personal_notes": parsed_response.get("personal_notes"),
            "relevant_information": parsed_response.get("relevant_information"),
            "why_happening_explanation": parsed_response.get("why_happening_explanation"),
            "immediate_action": parsed_response.get("immediate_action"),
            "nurse_tips": parsed_response.get("nurse_tips"),
            "citations": citations
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
@token_required # Apply the decorator directly
def get_history(current_user=None): # Accept current_user
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
                    if 'citations' in entry['response'] and not isinstance(entry['response']['citations'], list):
                        entry['response']['citations'] = [entry['response']['citations']]
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse raw_text for history entry {entry.get('id')}")
                    entry['response'] = {}
            else:
                entry['response'] = entry.get('response', {}) 
            
            if 'citations' in entry and not isinstance(entry['citations'], list):
                entry['citations'] = [entry['citations']]

        return jsonify(history_data), 200

    except Exception as e:
        logger.exception("Exception while fetching history")
        return jsonify({"error": str(e)}), 500


# --- NEW PASSWORD RESET ENDPOINTS ---

@app.route("/request-password-reset", methods=["POST"])
@cross_origin()
@token_required # Apply the decorator directly
def request_password_reset(current_user=None): # Accept current_user
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




@app.route("/verify-password-reset", methods=["GET"])
@cross_origin()
# This endpoint typically doesn't need @token_required as it's the target of an external email link
# and acts as a redirector. If you apply @token_required, then the external email link won't work
# because it won't send an Authorization header.
def verify_password_reset():
    """
    This endpoint is designed to be the 'redirectTo' target from Supabase's email link.
    It will extract tokens and redirect to the frontend password reset page.
    """
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
