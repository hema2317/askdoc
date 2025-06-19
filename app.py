import os
import json
import logging
import re
from datetime import datetime
from flask import Flask, request, jsonify, redirect, url_for
from flask_cors import CORS
import openai
import requests
import psycopg2
from psycopg2 import OperationalError
import base64
import jwt # NEW: For decoding JWT to get user_id

app = Flask(__name__)
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
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://askdocapp-92cc3.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5sZnZ3YmpwZXl3Y2Vzc3F5cWFjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU4NTczNjQsImV4cCI6MjA2MTQzMzM2NH0.zL84P7bK7qHxJt8MtkTPkqNe4U_K512ZgtpPvD9PoRI")
# NEW: Supabase JWT Secret is needed to verify and decode user JWTs on the backend
# This is NOT the Anon Key. It's found under Project Settings -> API -> JWT Secret.
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET") 

openai.api_key = OPENAI_API_KEY

# --- NEW: Helper to extract user ID from Supabase JWT ---
def get_user_id_from_jwt():
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1] # Extract the token part
        # If your frontend is sending the custom API_AUTH_TOKEN in Authorization header
        # instead of the Supabase JWT, you'll need to send the Supabase JWT separately
        # or change check_api_token to just check for JWT validity.
        
        # This assumes the frontend sends the Supabase user JWT as the Authorization header
        try:
            # Decode the JWT. Audience 'authenticated' is standard for Supabase user tokens.
            # Make sure SUPABASE_JWT_SECRET is correctly set in your environment variables.
            decoded_token = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
            return decoded_token.get("sub") # 'sub' claim is the user ID (UUID)
        except jwt.ExpiredSignatureError:
            logger.warning("Expired JWT provided.")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT provided: {e}")
        except Exception as e:
            logger.error(f"Error decoding JWT: {e}")
    return None

# --- Authentication Middleware ---
def check_api_token():
    auth_header = request.headers.get("Authorization")
    # This function now expects the Authorization header to contain your static API_AUTH_TOKEN
    # If your frontend sends the Supabase JWT here, you might want to modify this check
    # to validate the JWT instead, or send the API_AUTH_TOKEN in a different header.
    
    if not auth_header:
        logger.warning("Unauthorized access attempt: No Authorization header.")
        return jsonify({"error": "Unauthorized: No Authorization header"}), 401
        
    if API_AUTH_TOKEN and auth_header != f"Bearer {API_AUTH_TOKEN}":
        logger.warning(f"Unauthorized access attempt: Invalid API_AUTH_TOKEN.")
        return jsonify({"error": "Unauthorized: Invalid API key"}), 401
    
    return None # Return None if authorized

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

# --- NEW: Function to save analysis to database ---
def save_analysis_to_db(user_id, analysis_type, query_input, response_data):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if not conn:
            logger.error("Could not get DB connection to save analysis.")
            return None

        cur = conn.cursor()
        # Ensure your history table exists and has these columns:
        # id (UUID, PK), user_id (UUID, FK to auth.users.id), analysis_type (TEXT),
        # query (TEXT), response_data (JSONB), created_at (TIMESTAMP WITH TIME ZONE, DEFAULT now())
        cur.execute(
            "INSERT INTO history (user_id, analysis_type, query, response_data) VALUES (%s, %s, %s, %s) RETURNING id;",
            (user_id, analysis_type, query_input, json.dumps(response_data))
        )
        history_item_id = cur.fetchone()[0] # Get the ID of the newly inserted row
        conn.commit()
        logger.info(f"Analysis saved for user {user_id}, type {analysis_type}, ID {history_item_id}")
        return history_item_id # Return the ID for frontend reference
    except Exception as e:
        logger.error(f"Failed to save analysis to database: {e}")
        if conn: # Ensure conn exists before rollback
            conn.rollback() # Rollback changes on error
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ... (rest of your existing functions: build_profile_context, generate_openai_response, parse_openai_json, get_nearby_doctors, get_image_labels, get_image_text) ...

# NOTE: I am including the helper functions here as well, in case your local file differs.
# Please ensure you copy these exactly.

def build_profile_context(profile_json):
    """Builds a human-readable context string from the user's profile data."""
    try:
        # Ensure profile_json is treated as a dict if it comes as a string JSON
        profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
    except Exception:
        logger.warning("Could not parse profile_json. Returning empty context.")
        return "No specific health profile provided by the user."

    lines = []
    # Add primary demographic info first
    if name := profile.get("name"):
        lines.append(f"Name: {name}")
    if age := profile.get("age"):
        lines.append(f"Age: {age} years")
    if gender := profile.get("gender"):
        lines.append(f"Gender: {gender}")
    if state := profile.get("state"):
        lines.append(f"State of Residence: {state}")

    lines.append("\n--- Health Details ---")
    if medical_conditions := profile.get("medical_conditions"):
        # Ensure it's a list for join
        if isinstance(medical_conditions, list):
            lines.append("Known Medical Conditions: " + ", ".join(medical_conditions))
        elif isinstance(medical_conditions, str): # Handle if AI returns string accidentally
            lines.append("Known Medical Conditions: " + medical_conditions)
    if current_medications := profile.get("medications"):
        if isinstance(current_medications, list):
            lines.append("Current Medications: " + ", ".join(current_medications))
        elif isinstance(current_medications, str):
            lines.append("Current Medications: " + current_medications)
    if family_history := profile.get("family_history"):
        if isinstance(family_history, list):
            lines.append("Family History of: " + ", ".join(family_history))
        elif isinstance(family_history, str):
            lines.append("Family History of: " + family_history)
    if known_diseases := profile.get("known_diseases"):
        if isinstance(known_diseases, list):
            lines.append("Other Known Diseases: " + ", ".join(known_diseases))
        elif isinstance(known_diseases, str):
            lines.append("Other Known Diseases: " + known_diseases)

    lines.append("\n--- Lifestyle Details ---")
    if smoker := profile.get("smoker"):
        lines.append(f"Smoker: {smoker}")
    if drinker := profile.get("drinker"):
        lines.append(f"Drinker: {drinker}")
    if exercise_habits := profile.get("exercise_habits"): # Use exercise_habits
        if isinstance(exercise_habits, list):
            lines.append("Exercise Habits: " + ", ".join(exercise_habits))
        elif isinstance(exercise_habits, str):
            lines.append("Exercise Habits: " + exercise_habits)

    if not lines:
        return "No specific health profile provided by the user."
    
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
                {"role": "system", "content": "You are a helpful multilingual health assistant. Adhere strictly to the requested JSON format."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.4, # Keep temperature low for factual consistency
            response_format={"type": "json_object"} # Explicitly request JSON object (for newer OpenAI versions)
        )
        return response['choices'][0]['message']['content']
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error in generate_openai_response: {e}")
        return None

def parse_openai_json(reply):
    """
    Parses the JSON string from OpenAI's reply.
    It's robust to cases where the reply might contain extra text outside the JSON block.
    Ensures 'remedies' and 'medicines' are always lists.
    """
    try:
        # Try to find a JSON block wrapped in markdown code fences first
        match = re.search(r'```json\s*(\{.*?\})\s*```', reply, re.DOTALL)
        if match:
            json_str = match.group(1)
            logger.info(f"Found JSON in markdown block: {json_str[:100]}...") # Log snippet for debugging
        else:
            # If no markdown block, try to parse the whole reply as JSON
            json_str = reply
            logger.info(f"Attempting to parse full reply as JSON: {json_str[:100]}...") # Log snippet for debugging
            
        parsed_data = json.loads(json_str)

        # Ensure 'remedies' and 'medicines' are lists, even if AI returns strings or null
        # Use .get() with default to prevent KeyError if the key is missing entirely
        remedies = parsed_data.get('remedies')
        if not isinstance(remedies, list):
            parsed_data['remedies'] = [remedies] if remedies else []
        
        medicines = parsed_data.get('medicines')
        if not isinstance(medicines, list):
            parsed_data['medicines'] = [medicines] if medicines else []

        # Add setdefault for new fields to ensure they always exist, even if AI misses them
        parsed_data.setdefault('nursing_explanation', 'Not provided.')
        parsed_data.setdefault('personal_notes', 'Not provided.')
        parsed_data.setdefault('relevant_information', 'Not provided.')
        parsed_data.setdefault('why_happening_explanation', 'Not provided.')
        parsed_data.setdefault('immediate_action', 'Not provided.')
        parsed_data.setdefault('nurse_tips', 'Not provided.')


        return parsed_data
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {e}. Raw reply: {reply}")
        # Return a fallback structure to prevent frontend crash
        return {
            "medical_analysis": "I'm sorry, I couldn't fully process the request. Please try again or rephrase your symptoms. (JSON Parse Error)",
            "root_cause": "Parsing error or unclear AI response.",
            "remedies": [], "medicines": [], "detected_condition": "unsure",
            "why_happening_explanation": "Insufficient information.", "immediate_action": "Consult a healthcare professional.",
            "nurse_tips": "It's important to provide clear and concise information for accurate analysis. Always seek medical advice from a qualified doctor.",
            "hipaa_disclaimer": "Disclaimer: I am a virtual AI assistant and not a medical doctor. This information is for educational purposes only and is not a substitute for professional medical advice. Always consult a qualified healthcare provider for diagnosis and treatment.",
            "urgency": "unknown", "suggested_doctor": "general",
            "nursing_explanation": "Not provided.", "personal_notes": "Not provided.", "relevant_information": "Not provided."
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
            "nursing_explanation": "Not provided.", "personal_notes": "Not provided.", "relevant_information": "Not provided."
        }


def get_nearby_doctors(specialty, location):
    """Fetches nearby doctors using Google Places API."""
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY is not set for Places API.")
        return []
        
    try:
        # Check if location is a dictionary (from frontend), or assume it's a string if it's not
        if isinstance(location, dict):
            lat = location.get("lat")
            lng = location.get("lng")
            if lat is None or lng is None:
                logger.error("Location dictionary missing 'lat' or 'lng' keys.")
                return []
            location_str = f"{lat},{lng}" # Format as "latitude,longitude" string
        elif isinstance(location, str) and "," in location: # Handle if it somehow comes as "lat,lng" string
            location_str = location
        else:
            logger.error(f"Invalid location format received: {location}. Expected dict or 'lat,lng' string.")
            return []

        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "keyword": f"{specialty} doctor",
            "location": location_str, # Use the correctly formatted string
            "radius": 10000, # 10km radius
            "type": "doctor",
            "key": GOOGLE_API_KEY,
            "rankby": "prominence" # Prioritize higher-rated and more significant places
        }
        response = requests.get(url, params=params)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        
        results = response.json().get("results", [])
        
        # Filter for results that have a rating and sort them
        filtered_results = [p for p in results if p.get("rating") is not None]
        sorted_results = sorted(
            filtered_results, 
            key=lambda x: (x.get("rating", 0), x.get("opening_hours", {}).get("open_now", False)), 
            reverse=True
        )

        doctors = []
        # Limit to top 5 doctors
        for place in sorted_results[:5]:
            doctors.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "open_now": place.get("opening_hours", {}).get("open_now", False),
                # Ensure the maps_link is correctly formatted and URL-encoded
                "maps_link": f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(place.get('name', '') + ',' + place.get('vicinity', ''))}&query_place_id={place.get('place_id')}"
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
                "features": [{"type": "LABEL_DETECTION", "maxResults": 10}] # Increased maxResults
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
    profile_data = data.get("profile", {}) # Expecting dict, not empty string
    location = data.get("location", "")

    if not symptoms:
        return jsonify({"error": "No symptoms provided"}), 400

    logger.info(f"[ANALYZE] Input: {symptoms}")
    profile_context = build_profile_context(profile_data) # Build context string
    
    # Generate response from OpenAI using the detailed prompt
    reply_content = generate_openai_response(symptoms, language, profile_context, prompt_type="symptoms")

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
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error in /ask: {e}")
        return jsonify({ "error": "OpenAI request failed" }), 500
    except Exception as e:
        logger.error(f"Error in /ask: {e}")
        return jsonify({ "error": "An unexpected error occurred" }), 500

@app.route("/photo-analyze", methods=["POST"])
def analyze_photo():
    auth_result = check_api_token()
    if auth_result:
        return auth_result

    data = request.get_json()
    image_base64 = data.get("image_base64")
    profile_data = data.get("profile", {}) # Pass profile for photo analysis
    location_data = data.get("location", "")
    
    if not image_base64:
        return jsonify({"error": "No image provided"}), 400

    logger.info("📸 /photo-analyze: Analyzing image for labels and text")

    # Step 1: Get labels and text from Google Vision API
    labels = get_image_labels(image_base64) # This gets labels
    detected_text = get_image_text(image_base64) # This gets text (OCR)

    # Combine labels and text for LLM input
    image_description_for_llm = f"The image provides visual cues: {', '.join(labels)}."
    if detected_text:
        image_description_for_llm += f" Additionally, text detected in the image: \"{detected_text}\""
    
    profile_context = build_profile_context(profile_data)

    # Step 2: Send compiled description and profile to the main LLM for analysis
    llm_reply_content = generate_openai_response(image_description_for_llm, "English", profile_context, prompt_type="photo_analysis")

    if not llm_reply_content:
        return jsonify({"error": "AI analysis failed to generate response."}), 500

    parsed_analysis = parse_openai_json(llm_reply_content)

    # Add nearby doctors if applicable
    if location_data and parsed_analysis.get("suggested_doctor"):
        parsed_analysis["nearby_doctors"] = get_nearby_doctors(parsed_analysis["suggested_doctor"], location_data)
    else:
        parsed_analysis["nearby_doctors"] = []
    
    parsed_analysis["image_labels"] = labels # For frontend to display original labels if needed
    parsed_analysis["image_description"] = image_description_for_llm # For frontend to display AI's interpretation input

    return jsonify(parsed_analysis)

@app.route("/analyze-lab-report", methods=["POST"])
def analyze_lab_report():
    auth_result = check_api_token()
    if auth_result:
        return auth_result

    data = request.get_json()
    image_base64 = data.get("image_base64") # For PDF OCR on backend
    extracted_text_from_frontend = data.get("extracted_text", "") # Text OCR'd by frontend (for images)
    location = data.get("location", "")
    profile_data = data.get("profile", {})
    language = data.get("language", "English")

    final_text_for_ai = ""

    # Prioritize extracted_text from frontend if present (means frontend did OCR for image)
    if extracted_text_from_frontend and extracted_text_from_frontend != "PDF document uploaded. Extracting text on backend...":
        final_text_for_ai = extracted_text_from_frontend
        logger.info("🧪 Using frontend extracted text for lab report analysis.")
    elif image_base64: # If no frontend text, but image_base64 (likely PDF) is present
        logger.info("🧪 Performing OCR on backend for lab report image...")
        extracted_text_from_backend = get_image_text(image_base64) # Backend OCR
        if not extracted_text_from_backend:
            return jsonify({"error": "OCR failed to extract text from backend for image"}), 500
        final_text_for_ai = extracted_text_from_backend
        # Add extracted_text to response for frontend preview
        # NOTE: This modifies the 'data' dict which is then returned by jsonify.
        # It's better to add it directly to 'parsed_response' later.
        # data['extracted_text'] = final_text_for_ai 

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

    # Ensure extracted_text is part of the final response for frontend preview
    parsed_response["extracted_text"] = final_text_for_ai 
    return jsonify(parsed_response)

# --- NEW PASSWORD RESET ENDPOINTS ---

@app.route("/request-password-reset", methods=["POST"])
def request_password_reset():
    auth_result = check_api_token()
    if auth_result:
        return auth_result

    data = request.get_json()
    email = data.get("email")
    frontend_redirect_url = data.get("redirect_to") # Expected from frontend (e.g., https://askdocapp-92cc3.web.app/reset-password.html)

    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    if not frontend_redirect_url:
        return jsonify({"error": "Redirect URL for password reset is required"}), 400

    logger.info(f"Received password reset request for email: {email}")

    # Call Supabase Auth API to send the magic link/reset email
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
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        logger.info(f"Supabase password reset request sent for {email}. Status: {response.status_code}")
        return jsonify({"message": "Password reset email sent. Please check your inbox (and spam folder!)."}), 200
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending password reset request to Supabase: {e}")
        # Return a generic error message to the user for security
        return jsonify({"error": "Failed to send password reset email. Please try again later."}), 500
    except Exception as e:
        logger.error(f"Unexpected error in /request-password-reset: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500


@app.route("/verify-password-reset", methods=["GET"])
def verify_password_reset():
    """
    This endpoint is designed to be the 'redirectTo' target from Supabase's email link.
    It will extract tokens and redirect to the frontend password reset page.
    """
    # If Supabase is configured to redirect to THIS endpoint (`/verify-password-reset`),
    # it would pass tokens as query parameters, NOT hash parameters.
    # Example: http://yourbackend.com/verify-password-reset?access_token=...&refresh_token=...

    access_token = request.args.get("access_token")
    refresh_token = request.args.get("refresh_token")
    # You might also get 'type=recovery' and 'expires_in' etc.

    if access_token and refresh_token:
        # Construct the URL for your frontend reset page, appending tokens as hash
        # This assumes your frontend `reset-password.html` page is designed to
        # read these from the hash.
        frontend_reset_url = "https://askdocapp-92cc3.web.app/reset-password.html" # Ensure this matches your actual frontend URL
        full_redirect_url = f"{frontend_reset_url}#access_token={access_token}&refresh_token={refresh_token}"
        logger.info(f"Redirecting to frontend reset page: {full_redirect_url}")
        return redirect(full_redirect_url)
    else:
        logger.warning("Missing access_token or refresh_token in /verify-password-reset. Redirecting to error.")
        # If tokens are missing, redirect to your frontend with an error status or specific error page
        return redirect("https://askdocapp-92cc3.web.app/reset-password.html?error=invalid_link") # Ensure this matches your actual frontend URL


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  
    app.run(host='0.0.0.0', port=port)
