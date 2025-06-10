import os
import json
import logging
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import requests
import psycopg2
from psycopg2 import OperationalError
from typing import Dict, Any, Optional, List, Tuple


app = Flask(__name__)
## REFACTOR: More specific CORS for production, but "*" is fine for development.
CORS(app, resources={r"/api/*": {"origins": "*"}}) 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load configuration from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")

# Initialize OpenAI client
if not OPENAI_API_KEY:
    logger.critical("OPENAI_API_KEY environment variable not set.")
openai.api_key = OPENAI_API_KEY


# ==============================================================================
# Helper and Utility Functions
# ==============================================================================

def check_api_token() -> Optional[Tuple[Any, int]]:
    """Validates the API authorization token from the request headers."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer ") or auth_header.split(" ")[1] != API_AUTH_TOKEN:
        logger.warning("Unauthorized access attempt.")
        return jsonify({"error": "Unauthorized"}), 401
    return None

def get_db_connection() -> Optional[psycopg2.extensions.connection]:
    """Establishes a connection to the PostgreSQL database."""
    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set.")
        return None
    try:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

def generate_openai_response(prompt_content: str, language: str, profile_data: Dict[str, Any]) -> Optional[str]:
    """Generates a response from OpenAI's ChatCompletion API with error handling."""
    profile_str = json.dumps(profile_data)

    system_message = {
        "role": "system",
        "content": (
            f"You are an expert medical analysis AI. Your response must be a single, valid JSON object "
            f"and nothing else. Do not include any text, explanations, or markdown formatting like ```json "
            f"outside of the JSON object. The entire response must be parsable. Respond ONLY in {language}."
        )
    }
    user_message = {
        "role": "user",
        "content": f"Patient profile:\n{profile_str}\n\nAnalysis Request:\n{prompt_content}"
    }

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[system_message, user_message],
            temperature=0.3
        )
        return response.choices[0].message['content']
    except Exception as e:
        logger.error(f"OpenAI API request failed: {e}")
        return None

def parse_openai_json(reply: Optional[str]) -> Dict[str, Any]:
    """
    ## FIX: Completely rewritten for robustness.
    Safely parses the JSON string from the OpenAI reply.
    - Fixes the UnboundLocalError by defining defaults upfront.
    - Handles None or empty replies.
    - Uses more reliable logic to extract the JSON object.
    - Guarantees a valid dictionary is always returned.
    """
    # Define default keys at the top level to prevent UnboundLocalError
    default_keys = {
        "error": "Failed to parse AI response.",
        "detected_condition": "Unspecified",
        "medical_analysis": "No analysis provided.",
        "root_cause": "Not identified",
        "remedies": [],
        "urgency": "low",
        "medicines": [],
        "suggested_doctor": "General Practitioner",
        "good_results": [],
        "bad_results": [],
        "actionable_advice": []
    }

    if not reply or not isinstance(reply, str) or not reply.strip():
        logger.warning("Received an empty or invalid reply from OpenAI.")
        default_keys["medical_analysis"] = "Received no response from the AI assistant. Please try again."
        return default_keys

    try:
        # Find the first '{' and the last '}' to reliably extract the JSON object
        start = reply.find('{')
        end = reply.rfind('}') + 1
        if start == -1 or end == 0:
            raise json.JSONDecodeError("No JSON object found in the reply.", reply, 0)
        
        json_str = reply[start:end]
        parsed = json.loads(json_str)
        
        # Ensure all default keys are present and have the correct type
        parsed.pop("error", None) # Remove the error key if parsing was successful
        for key, default_value in default_keys.items():
            parsed[key] = parsed.get(key, default_value)
            # Ensure lists are actually lists
            if isinstance(default_value, list) and not isinstance(parsed[key], list):
                parsed[key] = [str(parsed[key])] if parsed[key] else []
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}. Raw reply was: '{reply}'")
        default_keys["medical_analysis"] = f"A parsing error occurred. The AI's raw response was: {reply}"
        return default_keys


def get_image_text_and_labels(base64_image: str) -> Tuple[str, List[str]]:
    """Uses Google Vision API to extract text and labels from a base64 encoded image."""
    try:
        url = f"[https://vision.googleapis.com/v1/images:annotate?key=](https://vision.googleapis.com/v1/images:annotate?key=){GOOGLE_VISION_API_KEY}"
        body = {
            "requests": [{
                "image": {"content": base64_image},
                "features": [
                    {"type": "TEXT_DETECTION"},
                    {"type": "LABEL_DETECTION", "maxResults": 10}
                ]
            }]
        }
        res = requests.post(url, json=body)
        res.raise_for_status()
        response_data = res.json()["responses"][0]

        full_text = response_data.get("fullTextAnnotation", {}).get("text", "")
        labels = [label['description'] for label in response_data.get("labelAnnotations", [])]
        return full_text, labels
    except Exception as e:
        logger.error(f"Google Vision API error: {e}")
        return "", []

def get_nearby_doctors(specialty: str, location: str) -> List[Dict[str, Any]]:
    """Searches for doctors using the Google Places API."""
    try:
        if not re.fullmatch(r"^-?\d+\.?\d*,-?\d+\.?\d*$", location):
            logger.warning(f"Invalid location format received: '{location}'")
            return []

        params = {
            "keyword": f"{specialty}",
            "location": location,
            "radius": 15000, # When using rankby=prominence, radius defines the bias area
            "type": "doctor",
            "key": GOOGLE_API_KEY
        }
        response = requests.get("[https://maps.googleapis.com/maps/api/place/nearbysearch/json](https://maps.googleapis.com/maps/api/place/nearbysearch/json)", params=params)
        response.raise_for_status()
        results = response.json().get("results", [])

        # Sort by rating, handling cases where rating is missing or not a number
        sorted_results = sorted(results, key=lambda x: float(x.get("rating", 0)), reverse=True)
        
        doctors = []
        for place in sorted_results[:5]:
            ## FIX: The Google Maps link was incorrect. This is a valid, working format.
            query = requests.utils.quote(f"{place.get('name', '')}, {place.get('vicinity', '')}")
            maps_link = f"[https://www.google.com/maps/search/?api=1&query=](https://www.google.com/maps/search/?api=1&query=){query}&query_place_id={place.get('place_id', '')}"
            
            doctors.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "open_now": place.get("opening_hours", {}).get("open_now", "N/A"),
                "maps_link": maps_link
            })
        return doctors
    except Exception as e:
        logger.error(f"Google Maps API error: {e}")
        return []


@app.route("/api/health", methods=["GET"])
def health_check():
    """A simple health check endpoint."""
    return jsonify({"status": "ok"})


def process_analysis_request(prompt: str, data: Dict[str, Any], analysis_type: str, extra_info: Dict = None):
    """## REFACTOR: A single function to handle the logic for all analysis endpoints."""
    language = data.get("language", "English")
    profile_data = data.get("profile", {})
    location = data.get("location", "")

    # Step 1: Get analysis from OpenAI
    reply = generate_openai_response(prompt, language, profile_data)
    if not reply:
        return jsonify({"error": "Failed to get a response from the AI assistant."}), 502 # Bad Gateway

    # Step 2: Parse the response
    parsed = parse_openai_json(reply)
    parsed["type"] = analysis_type
    if extra_info:
        parsed.update(extra_info)

    # Step 3: If parsing failed, return the error
    if "error" in parsed:
        return jsonify(parsed), 500

    # Step 4: Get nearby doctors if applicable
    if location and parsed.get("suggested_doctor"):
        parsed["nearby_doctors"] = get_nearby_doctors(parsed["suggested_doctor"], location)

    return jsonify(parsed)

@app.route("/api/analyze-symptoms", methods=["POST"])
def analyze_symptoms():
    auth_response = check_api_token()
    if auth_response: return auth_response

    data = request.get_json()
    symptoms = data.get("symptoms", "")
    if not symptoms:
        return jsonify({"error": "Symptom data is required."}), 400

    return process_analysis_request(symptoms, data, "symptom_analysis")

@app.route("/api/analyze-photo", methods=["POST"])
def analyze_photo():
    auth_response = check_api_token()
    if auth_response: return auth_response
    
    data = request.get_json()
    image_base64 = data.get("image_base64")
    if not image_base64:
        return jsonify({"error": "Base64 encoded image is required."}), 400

    image_text, labels = get_image_text_and_labels(image_base64)
    prompt = f"Analyze the visual symptoms in this image. "
    if labels: prompt += f"The image appears to contain: {', '.join(labels)}. "
    if image_text: prompt += f"Text detected in the image: '{image_text}'. "

    extra_info = {"image_labels": labels, "image_text_detected": image_text}
    return process_analysis_request(prompt, data, "photo_analysis", extra_info)

@app.route("/api/analyze-lab-report", methods=["POST"])
def analyze_lab_report():
    auth_response = check_api_token()
    if auth_response: return auth_response
    
    data = request.get_json()
    image_base64 = data.get("image_base64")
    if not image_base64:
        return jsonify({"error": "Base64 encoded lab report image is required."}), 400

    full_text, _ = get_image_text_and_labels(image_base64)
    if not full_text:
        return jsonify({"error": "Could not extract any text from the lab report image."}), 400
    
    ## FIX: Prompt no longer redundantly includes profile data.
    prompt = f"Analyze the following medical lab report text:\n\n{full_text}"
    return process_analysis_request(prompt, data, "lab_report")


if __name__ == '__main__':
    # Use 0.0.0.0 to be accessible from outside the container.
    # Use a port from an environment variable if available, otherwise default to 8080.
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
