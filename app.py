import os
import json
import logging
import re
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import requests
import psycopg2
from psycopg2 import OperationalError
import base64

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")

openai.api_key = OPENAI_API_KEY

def check_api_token():
    auth = request.headers.get("Authorization")
    if not auth or auth != f"Bearer {API_AUTH_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

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

    lines = []
    # Add primary demographic info first
    if name := profile.get("name"):
        lines.append(f"Name: {name}")
    if age := profile.get("age"):
        lines.append(f"Age: {age} years") # Added unit
    if gender := profile.get("gender"):
        lines.append(f"Gender: {gender}")
    if state := profile.get("state"):
        lines.append(f"State of Residence: {state}")

    lines.append("\n--- Health Details ---") # Separator for clarity
    if blood := profile.get("blood_type"):
        lines.append(f"Blood Type: {blood}")
    if medical_conditions := profile.get("medical_conditions"): # Use medical_conditions
        lines.append("Known Medical Conditions: " + ", ".join(medical_conditions))
    if current_medications := profile.get("medications"): # Use medications
        lines.append("Current Medications: " + ", ".join(current_medications))
    if family_history := profile.get("family_history"): # Use family_history
        lines.append("Family History of: " + ", ".join(family_history))
    if known_diseases := profile.get("known_diseases"): # Use known_diseases
        lines.append("Other Known Diseases: " + ", ".join(known_diseases))

    lines.append("\n--- Lifestyle Details ---") # Separator for clarity
    if smoker := profile.get("smoker"):
        lines.append(f"Smoker: {smoker}")
    if drinker := profile.get("drinker"):
        lines.append(f"Drinker: {drinker}")
    if exercise_habits := profile.get("exercise_habits"): # Use exercise_habits
        lines.append("Exercise Habits: " + ", ".join(exercise_habits))

    if not lines:
        return "No specific health profile provided by the user."
    
    return "\n".join(lines)


# Removed calculate_age as age is now passed directly from frontend profile

def generate_openai_response(symptoms, language, profile_context): # Renamed profile to profile_context
    """
    Generates a detailed, nurse-like response from OpenAI based on symptoms and profile.
    This prompt is significantly expanded to elicit more detailed and personalized advice.
    """
    
    # Define normal ranges for common metrics the AI might encounter in symptoms
    # This helps the AI interpret numbers correctly, especially blood sugar.
    health_metric_context = """
    Normal Ranges for reference (use only if explicitly mentioned in symptoms, otherwise ignore):
    - Blood Sugar (Fasting): 70-100 mg/dL (or 3.9-5.6 mmol/L). Below 70 mg/dL is Hypoglycemia (low). Above 125 mg/dL is Hyperglycemia (high).
    - Blood Pressure: Systolic < 120 mmHg, Diastolic < 80 mmHg.
    - Temperature: Oral ~98.6°F (37°C). Fever generally >100.4°F (38°C).
    """

    prompt = f"""
    You are a highly knowledgeable, empathetic, and responsible virtual health assistant. Your role is to act as a compassionate nurse or health educator.
    You must *always* provide information that is easy to understand for a layperson.
    Your initial greeting must *always* be a disclaimer.

    Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment.

    {health_metric_context}

    --- User's Health Profile ---
    {profile_context}

    --- User's Current Symptoms ---
    Symptoms: "{symptoms}"

    --- Task Instructions ---
    Based on the provided symptoms and the user's health profile, provide a structured and detailed analysis.
    Ensure the language is simple, supportive, and actionable, like a compassionate nurse explaining things.
    **Crucially, explicitly use and reference information from the user's health profile to personalize the analysis, advice, and tips.** For example, if they have diabetes and report low sugar, tailor the advice by explicitly mentioning their diabetes. If they smoke, weave in advice related to smoking cessation for their condition.

    Generate your response as a JSON object with the following keys. All explanations should be concise but informative, aiming for clarity and actionability for a layperson. If a field is not applicable or information is insufficient, you can state "Not applicable" or "Insufficient information.":

    1.  `detected_condition`: A concise, most likely medical condition (e.g., 'Hypoglycemia', 'Common Cold', 'Muscle Strain').
    2.  `medical_analysis`: A comprehensive overview of the symptoms and the detected condition. Explain it in simple, layman's terms. **Directly relate it to the user's profile where relevant.**
    3.  `why_happening_explanation`: Explain *why* the condition might be happening in simple, understandable terms. Consider profile factors like medications, habits, or pre-existing conditions.
    4.  `immediate_action`: What the person should *do immediately* or in the very short term. Be specific, actionable, and prioritize safety.
    5.  `nurse_tips`: **Proactive education and practical advice, like a nurse would provide.** This is where you significantly personalize guidance based on their profile. Include prevention, monitoring, or lifestyle advice tailored to their known conditions, habits (smoking, drinking, exercise), or family history.
    6.  `remedies`: General suggestions for self-care or lifestyle adjustments for recovery or management.
    7.  `medicines`: Common over-the-counter or general types of prescribed medications *related to the condition*. **Explicitly state this is NOT a prescription and they must consult a doctor.**
    8.  `urgency`: Categorize the urgency (e.g., 'Immediate Emergency', 'Urgent Consult', 'Moderate', 'Low').
    9.  `suggested_doctor`: The type of medical specialist they might need to see.
    10. `hipaa_disclaimer`: The exact disclaimer text: "I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment."
    """
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", # Consider "gpt-4" or "gpt-4o" for better reasoning and JSON formatting
            messages=[
                {"role": "system", "content": "You are a helpful multilingual health assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4, # Keep temperature low for factual consistency
            # max_tokens=1000 # Consider setting a max_tokens if responses are too long
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"OpenAI request failed: {e}")
        return None

def parse_openai_json(reply):
    """
    Parses the JSON string from OpenAI's reply.
    It's robust to cases where the reply might contain extra text outside the JSON block.
    """
    try:
        match = re.search(r'```json\s*(\{.*?\})\s*```', reply, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # If no ```json``` block, try to parse the whole reply as JSON
            json_str = reply
        
        parsed_data = json.loads(json_str)
        return parsed_data
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {e}. Raw reply: {reply}")
        # Return a fallback structure to prevent frontend crash
        return {
            "medical_analysis": "I'm sorry, I couldn't fully process the request. Please try again or rephrase your symptoms.",
            "root_cause": "Parsing error or unclear AI response.",
            "remedies": [],
            "urgency": "unknown",
            "suggested_doctor": "general",
            "medicines": [],
            "detected_condition": "unsure",
            "why_happening_explanation": "Insufficient information.",
            "immediate_action": "Consult a healthcare professional.",
            "nurse_tips": "It's important to provide clear and concise information for accurate analysis. Always seek medical advice from a qualified doctor.",
            "hipaa_disclaimer": "Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment."
        }
    except Exception as e:
        logger.error(f"Unexpected error in JSON parsing: {e}")
        return {
            "medical_analysis": "An unexpected error occurred during analysis. Please try again.",
            "root_cause": "Unknown error.",
            "remedies": [],
            "urgency": "unknown",
            "suggested_doctor": "general",
            "medicines": [],
            "detected_condition": "unsure",
            "why_happening_explanation": "An internal error occurred.",
            "immediate_action": "Consult a healthcare professional.",
            "nurse_tips": "If issues persist, please contact support. Always seek medical advice from a qualified doctor.",
            "hipaa_disclaimer": "Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment."
        }


def get_nearby_doctors(specialty, location):
    """Fetches nearby doctors using Google Places API."""
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY is not set.")
        return []
    
    try:
        lat, lng = location.split(",")
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "keyword": f"{specialty} doctor", # Added 'doctor' to keyword for better results
            "location": f"{lat},{lng}",
            "radius": 10000, # Increased radius to 10km for more results
            "type": "doctor", # Explicitly request type doctor
            "key": GOOGLE_API_KEY,
            "rankby": "prominence" # Sort by prominence (default)
        }
        response = requests.get(url, params=params)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        
        results = response.json().get("results", [])
        
        # Filter for only those with ratings and sort by rating, then by open_now
        filtered_results = [p for p in results if p.get("rating") is not None]
        sorted_results = sorted(
            filtered_results, 
            key=lambda x: (x.get("rating", 0), x.get("opening_hours", {}).get("open_now", False)), 
            reverse=True
        )

        doctors = []
        for place in sorted_results[:5]: # Limit to top 5
            doctors.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "open_now": place.get("opening_hours", {}).get("open_now", False),
                "maps_link": f"https://www.google.com/maps/search/?api=1&query={place.get('name')},{place.get('vicinity')}&query_place_id={place.get('place_id')}" # More robust Maps link
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
        logger.error("GOOGLE_VISION_API_KEY is not set.")
        return []
        
    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [{
                "image": {"content": base64_image},
                "features": [{"type": "LABEL_DETECTION", "maxResults": 5}]
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
        logger.error("GOOGLE_VISION_API_KEY is not set.")
        return ""

    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [{
                "image": {"content": base64_image},
                "features": [{"type": "TEXT_DETECTION"}] # Request TEXT_DETECTION
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
    return jsonify({"status": "ok"})

@app.route("/analyze", methods=["POST"])
def analyze():
    # Authentication check
    auth_result = check_api_token()
    if auth_result:
        return auth_result # Return Unauthorized if check fails

    data = request.json
    symptoms = data.get("symptoms", "")
    language = data.get("language", "English")
    profile = data.get("profile", {}) # Expecting dict, not empty string
    location = data.get("location", "")

    if not symptoms:
        return jsonify({"error": "No symptoms provided"}), 400

    logger.info(f"[ANALYZE] Input: {symptoms}")
    profile_context = build_profile_context(profile) # Build context string
    
    # Generate response from OpenAI using the detailed prompt
    reply_content = generate_openai_response(symptoms, language, profile_context)

    if not reply_content:
        return jsonify({"error": "OpenAI failed to generate response"}), 500

    # Parse the JSON response from OpenAI
    parsed_response = parse_openai_json(reply_content)

    # Add nearby doctors if location and suggested doctor are available
    if location and parsed_response.get("suggested_doctor"):
        parsed_response["nearby_doctors"] = get_nearby_doctors(parsed_response["suggested_doctor"], location)
    else:
        parsed_response["nearby_doctors"] = [] # Ensure it's always an empty list if not found

    return jsonify(parsed_response)


@app.route("/api/ask", methods=["POST"])
def ask():
    auth_result = check_api_token()
    if auth_result:
        return auth_result

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
    except Exception as e:
        logger.error(f"OpenAI Error in /ask: {e}")
        return jsonify({ "error": "OpenAI request failed" }), 500

@app.route("/photo-analyze", methods=["POST"])
def analyze_photo():
    auth_result = check_api_token()
    if auth_result:
        return auth_result

    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image_file = request.files['image']
    profile_json = request.form.get('profile', '{}')
    try:
        profile = json.loads(profile_json)
    except Exception:
        profile = {}

    image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
    labels = get_image_labels(image_base64)
    profile_context = json.dumps(profile)  # Minimal formatting

    ai_reply = generate_openai_response(labels, profile_context)
    if not ai_reply:
        return jsonify({"error": "AI analysis failed"}), 500

    try:
        parsed = json.loads(ai_reply)
    except Exception:
        parsed = {"medical_analysis": ai_reply, "error": "Could not parse JSON, raw text returned"}

    parsed["image_labels"] = labels
    return jsonify(parsed)

@app.route("/analyze-lab-report", methods=["POST"])
def analyze_lab_report():
    auth_result = check_api_token()
    if auth_result:
        return auth_result

    data = request.get_json()
    image_base64 = data.get("image_base64")
    extracted_text = data.get("extracted_text", "")
    location = data.get("location", "")
    profile = data.get("profile", {}) # Pass profile for lab report analysis too
    language = data.get("language", "English")

    if not extracted_text and not image_base64:
        return jsonify({"error": "Missing lab report text or image"}), 400

    # If text not provided, extract from image
    if not extracted_text and image_base64:
        logger.info("Performing OCR on lab report image...")
        extracted_text = get_image_text(image_base64) # Use the more robust get_image_text
        if not extracted_text:
            return jsonify({"error": "OCR failed to extract text from image"}), 500

    logger.info("🧪 /analyze-lab-report analyzing extracted lab report text")
    profile_context = build_profile_context(profile) # Build profile context

    # Updated prompt for lab report analysis to be more descriptive and use profile
    prompt_for_lab = f"""
    Analyze the following lab report text for a patient with this profile:
    Lab Report Text: "{extracted_text}"
    User Profile: {profile_context}
    
    Based on this lab report and profile, provide a detailed medical analysis, highlight good/bad results with explanations, actionable advice, urgency, and suggested doctor, in the same detailed JSON format as the /analyze endpoint.
    Crucially, start with the standard AI disclaimer.
    """

    reply = generate_openai_response(prompt_for_lab, language, profile_context) # Reusing general response generator

    if not reply:
        return jsonify({"error": "OpenAI failed to generate response"}), 500

    parsed = parse_openai_json(reply)

    # For lab reports, you might need specific parsing for good_results and bad_results
    # If your AI prompt can produce them in this format, collect them from parsed_response
    # For now, let's assume LLM returns a more general medical_analysis for text.
    # If LLM produces specific good/bad results, ensure parse_openai_json handles them.
    parsed["extracted_text"] = extracted_text # Keep extracted text for context

    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)
    else:
        parsed["nearby_doctors"] = []

    return jsonify(parsed)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  
    app.run(host='0.0.0.0', port=port)
