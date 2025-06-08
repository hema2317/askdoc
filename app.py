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

# --- App Setup ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
# Ensure these are set in your deployment environment (e.g., Render, Heroku)
# or in a .env file for local development (e.g., using python-dotenv)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN") # Custom token for your app

# Set OpenAI API key
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    logger.warning("OPENAI_API_KEY is not set. OpenAI calls will fail.")

# --- Auth Check Decorator ---
# This decorator can be applied to routes that require authentication
def auth_required(f):
    def decorated_function(*args, **kwargs):
        auth = request.headers.get("Authorization")
        if not auth or auth != f"Bearer {API_AUTH_TOKEN}":
            logger.warning(f"Unauthorized access attempt from {request.remote_addr}. Auth header: {auth}")
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__ # Preserve original function name for Flask
    return decorated_function

# --- DB Connection ---
def get_db_connection():
    """Establishes and returns a PostgreSQL database connection."""
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        logger.info("Database connection successful.")
        return conn
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

# --- OpenAI Response Generation ---
def generate_openai_response(symptoms, language, profile_data):
    """
    Generates a structured medical analysis response using OpenAI's GPT model.
    :param symptoms: The patient's reported symptoms.
    :param language: The desired response language (e.g., "English").
    :param profile_data: Dictionary containing patient profile information.
    :return: Parsed JSON response from OpenAI, or None on failure.
    """
    # Convert profile_data dictionary to a string for the prompt
    profile_str = ""
    if profile_data:
        profile_str = "\nPatient Profile:\n"
        for key, value in profile_data.items():
            if isinstance(value, (dict, list)):
                profile_str += f"- {key.replace('_', ' ').title()}: {json.dumps(value)}\n"
            else:
                profile_str += f"- {key.replace('_', ' ').title()}: {value}\n"

    prompt = f"""
    You are a professional medical assistant. Your primary goal is to provide a comprehensive health analysis based on the given symptoms and patient profile.
    Respond ONLY in {language}.
    You MUST return valid JSON inside triple backticks.

    {profile_str}

    Symptoms:
    "{symptoms}"

    Provide a concise "medical_analysis", identify the "root_cause", list "remedies", suggest "medicines" (note: these are suggestions, not prescriptions), assess "health_risks" (cardiac, diabetic, etc.), determine "urgency", and suggest a "suggested_doctor".

    Return JSON only in this format (inside ```json):

    ```json
    {{
      "detected_condition": "string (e.g., Common Cold, Migraine, Dermatitis)",
      "medical_analysis": "string (Detailed summary of the condition and its implications)",
      "root_cause": "string (Most probable cause, e.g., Viral infection, Stress, Allergic reaction)",
      "remedies": ["string (Home remedy 1)", "string (Home remedy 2)"],
      "urgency": "low | moderate | high | emergency",
      "suggested_doctor": "string (e.g., General Practitioner, Cardiologist, Dermatologist)",
      "medicines": ["string (Suggested OTC/prescription medicine 1)", "string (Suggested OTC/prescription medicine 2)"],
      "health_risks": [
        {{"type": "cardiac", "level": "low|moderate|high"}},
        {{"type": "diabetic", "level": "low|moderate|high"}}
        // Add other relevant risk types as needed
      ],
      "disclaimer": "This analysis is for informational purposes only and does not constitute medical advice. Consult a healthcare professional for diagnosis and treatment."
    }}
    ```
    If any field is not applicable or unsure, provide a reasonable placeholder (e.g., "Not applicable", "Unknown", "None"). Ensure all strings are correctly escaped for JSON.
    """

    try:
        if not OPENAI_API_KEY:
            raise ValueError("OpenAI API key is not set.")

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", # Consider using "gpt-4" or "gpt-4o" for better quality if budget allows
            messages=[
                {"role": "system", "content": f"You are a helpful multilingual medical assistant specializing in health analysis. Always prioritize patient safety and suggest consulting a doctor when appropriate. Respond in {language}."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5, # Slightly higher temperature for more varied remedies, etc.
            max_tokens=1000 # Limit response length to prevent excessive tokens
        )
        return response['choices'][0]['message']['content']
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error: {e}")
        return None
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return None
    except Exception as e:
        logger.error(f"General OpenAI request failed: {e}")
        return None

# --- JSON Parsing ---
def parse_openai_json(reply_content):
    """
    Parses the JSON string from OpenAI's response, handling triple backticks.
    Provides a default structured response if parsing fails.
    """
    try:
        # Attempt to find JSON within triple backticks
        match = re.search(r'```json\s*(\{.*?\})\s*```', reply_content, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Fallback if no triple backticks, try to load directly (less robust)
            json_str = reply_content

        parsed_json = json.loads(json_str)

        # Ensure all expected top-level keys are present, provide defaults if missing
        default_structured_response = {
            "detected_condition": "Unsure/Not specified",
            "medical_analysis": "No detailed analysis provided from AI.",
            "root_cause": "Unknown",
            "remedies": [],
            "urgency": "low",
            "suggested_doctor": "General Practitioner",
            "medicines": [],
            "health_risks": [],
            "disclaimer": "This analysis is for informational purposes only and does not constitute medical advice. Consult a healthcare professional for diagnosis and treatment."
        }

        # Merge parsed JSON with defaults to ensure all keys exist
        final_response = {**default_structured_response, **parsed_json}

        # Ensure lists are actually lists
        if not isinstance(final_response.get("remedies"), list):
            final_response["remedies"] = [final_response["remedies"]] if final_response["remedies"] else []
        if not isinstance(final_response.get("medicines"), list):
            final_response["medicines"] = [final_response["medicines"]] if final_response["medicines"] else []
        if not isinstance(final_response.get("health_risks"), list):
            final_response["health_risks"] = [final_response["health_risks"]] if final_response["health_risks"] else []

        return final_response

    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding failed: {e} for reply: {reply_content[:200]}...")
        return {
            "detected_condition": "Parsing Error",
            "medical_analysis": "Could not parse AI response. Please try again. Raw response might be malformed.",
            "root_cause": "Parsing error",
            "remedies": [],
            "urgency": "unknown",
            "medicines": [],
            "suggested_doctor": "general",
            "health_risks": [],
            "disclaimer": "Error in AI response format."
        }
    except Exception as e:
        logger.error(f"Unexpected error during JSON parsing: {e} for reply: {reply_content[:200]}...")
        return {
            "detected_condition": "Error",
            "medical_analysis": "An unexpected error occurred while processing AI response.",
            "root_cause": "Internal error",
            "remedies": [],
            "urgency": "unknown",
            "medicines": [],
            "suggested_doctor": "general",
            "health_risks": [],
            "disclaimer": "Internal system error."
        }

# --- Nearby Doctor Lookup (Google Places API) ---
def get_nearby_doctors(specialty, location):
    """
    Fetches nearby doctors using Google Places API.
    :param specialty: The doctor's specialty (e.g., "Cardiologist").
    :param location: Latitude and longitude string (e.g., "34.0522,-118.2437").
    :return: A list of doctor dictionaries.
    """
    if not GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY is not set. Google Maps API calls will fail.")
        return []
    if not specialty or not location:
        logger.warning("Specialty or location is missing for doctor lookup.")
        return []

    try:
        # Attempt to parse location string into lat, lng
        try:
            lat, lng = map(float, location.split(","))
        except ValueError:
            logger.error(f"Invalid location format: {location}. Expected 'lat,lng'.")
            return []

        url = "[https://maps.googleapis.com/maps/api/place/nearbysearch/json](https://maps.googleapis.com/maps/api/place/nearbysearch/json)"
        params = {
            "keyword": f"{specialty} doctor", # Add "doctor" to the keyword
            "location": f"{lat},{lng}",
            "radius": 5000, # 5 kilometers radius
            "type": "doctor", # Explicitly search for doctors
            "key": GOOGLE_API_KEY
        }

        response = requests.get(url, params=params)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

        results = response.json().get("results", [])
        doctors = []
        for place in results[:5]: # Limit to top 5 results
            doctors.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "open_now": place.get("opening_hours", {}).get("open_now", "N/A"),
                "place_id": place.get("place_id") # Include place_id for more details if needed
            })
        logger.info(f"Found {len(doctors)} doctors for {specialty} near {location}.")
        return doctors

    except requests.exceptions.RequestException as e:
        logger.error(f"Google Maps API request failed: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in Google Maps API call: {e}")
        return []

# --- Google Vision Labeling ---
def get_image_labels(base64_image):
    """
    Detects labels in an image using Google Cloud Vision API.
    :param base64_image: Base64 encoded image content.
    :return: A list of detected labels (strings).
    """
    if not GOOGLE_VISION_API_KEY:
        logger.warning("GOOGLE_VISION_API_KEY is not set. Google Vision API calls will fail.")
        return []
    if not base64_image:
        return []

    try:
        url = f"[https://vision.googleapis.com/v1/images:annotate?key=](https://vision.googleapis.com/v1/images:annotate?key=){GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [{
                "image": {"content": base64_image},
                "features": [{"type": "LABEL_DETECTION", "maxResults": 5}] # Get top 5 labels
            }]
        }

        res = requests.post(url, json=body)
        res.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

        response_data = res.json()
        labels = [
            label['description']
            for label in response_data.get("responses", [{}])[0].get("labelAnnotations", [])
        ]
        return labels
    except requests.exceptions.RequestException as e:
        logger.error(f"Google Vision API request failed: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in Google Vision API call: {e}")
        return []

# --- API Routes ---

@app.route("/health", methods=["GET"])
def health():
    """Simple health check endpoint."""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route("/analyze", methods=["POST"])
@auth_required # Apply authentication decorator
def analyze():
    """
    Analyzes symptoms and provides medical insights.
    Expects JSON with 'symptoms', 'language', 'profile', 'location'.
    """
    data = request.json
    symptoms = data.get("symptoms", "").strip()
    language = data.get("language", "English").strip()
    profile = data.get("profile", {}) # Expects a dictionary
    location = data.get("location", "").strip() # Expects "lat,lng" string

    if not symptoms:
        return jsonify({"error": "No symptoms provided for analysis."}), 400

    logger.info(f"[ANALYZE] Symptoms: '{symptoms[:100]}...', Language: {language}, Profile: {profile}, Location: {location}")

    # Generate OpenAI response
    reply_content = generate_openai_response(symptoms, language, profile)
    if not reply_content:
        return jsonify({"error": "Failed to get a response from AI."}), 500

    # Parse OpenAI's structured JSON response
    parsed_response = parse_openai_json(reply_content)

    # If location and suggested doctor are available, lookup nearby doctors
    if location and parsed_response.get("suggested_doctor"):
        logger.info(f"Looking up doctors for: {parsed_response['suggested_doctor']} at {location}")
        parsed_response["nearby_doctors"] = get_nearby_doctors(parsed_response["suggested_doctor"], location)
    else:
        parsed_response["nearby_doctors"] = [] # Ensure this key always exists

    logger.info(f"[ANALYZE] Analysis complete. Detected condition: {parsed_response.get('detected_condition')}, Urgency: {parsed_response.get('urgency')}")
    return jsonify(parsed_response)

@app.route("/analyze_lab_report", methods=["POST"])
@auth_required # Apply authentication decorator
def analyze_lab_report():
    """
    Analyzes a lab report image via Google Vision and OpenAI.
    Expects JSON with 'image_base64', 'language', 'profile', 'location'.
    """
    data = request.json
    image_base64 = data.get("image_base64")
    language = data.get("language", "English").strip()
    profile = data.get("profile", {})
    location = data.get("location", "").strip()

    if not image_base64:
        return jsonify({"error": "Missing image_base64 in request."}), 400

    logger.info(f"📸 [LAB_REPORT] Request received for image analysis. Language: {language}")

    # Get labels from Google Vision API
    labels = get_image_labels(image_base64)
    if not labels:
        logger.warning("No labels detected from Vision API for lab report.")
        # You might want to return an error or a specific message if no labels are found.
        # For now, it will proceed with a generic prompt.
        vision_prompt_part = "Could not identify content from the image."
    else:
        vision_prompt_part = f"The image appears to show: {', '.join(labels)}."
    
    # Construct a prompt for OpenAI based on vision labels
    # This prompt needs to guide OpenAI to analyze *lab reports*, not just image content.
    # You might need a more sophisticated prompt based on actual OCR of lab results.
    full_prompt = f"""
    You are a professional medical assistant. Analyze the following information as if it's from a lab report image.
    {vision_prompt_part}
    Based on this, please provide a medical analysis structured as JSON.
    Return JSON in the same format as for symptom analysis, including:
    medical_analysis, root_cause, remedies, urgency, suggested_doctor, medicines, and health_risks.
    Assume normal ranges if specific values are not inferred from labels. Focus on potential interpretations.
    If the image is clearly not a lab report, state that.
    """

    # Generate OpenAI response based on image labels
    reply_content = generate_openai_response(full_prompt, language, profile)
    if not reply_content:
        return jsonify({"error": "Failed to get AI analysis for lab report."}), 500

    parsed_response = parse_openai_json(reply_content)
    parsed_response["image_labels"] = labels # Optionally include labels in response

    # If location and suggested doctor are available, lookup nearby doctors
    if location and parsed_response.get("suggested_doctor"):
        parsed_response["nearby_doctors"] = get_nearby_doctors(parsed_response["suggested_doctor"], location)
    else:
        parsed_response["nearby_doctors"] = []

    logger.info(f"🔬 [LAB_REPORT] Analysis complete. Detected condition: {parsed_response.get('detected_condition')}")
    return jsonify(parsed_response)


# --- Basic /api/ask route (for simpler chat if still needed) ---
@app.route("/api/ask", methods=["POST"])
@auth_required # Apply authentication decorator
def ask():
    """
    Provides a simple chat response to a general question using OpenAI.
    This is separate from the structured symptom analysis.
    """
    data = request.get_json()
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "No question provided."}), 400

    logger.info(f"[ASK] Question: '{question[:100]}...'")

    try:
        if not OPENAI_API_KEY:
            raise ValueError("OpenAI API key is not set.")

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": question}],
            temperature=0.5,
            max_tokens=500 # Limit chat response length
        )
        reply = response["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error in /api/ask: {e}")
        return jsonify({"error": "OpenAI request failed."}), 500
    except ValueError as e:
        logger.error(f"Configuration error in /api/ask: {e}")
        return jsonify({"error": "Server configuration error."}), 500
    except Exception as e:
        logger.error(f"Unexpected error in /api/ask: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500

# --- Entrypoint ---
if __name__ == '__main__':
    # For local development, set debug=True. In production, ensure debug=False.
    # The host='0.0.0.0' is important for deployment to Render.
    app.run(debug=True, host='0.0.0.0', port=os.getenv('PORT', 5000))
