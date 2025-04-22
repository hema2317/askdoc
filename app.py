import os
import psycopg2
from psycopg2 import OperationalError
from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import logging
import openai
import json
from datetime import datetime

logging.getLogger('flask_cors').level = logging.DEBUG

app = Flask(__name__)
CORS(app, origins=["*"])

# OpenAI setup
openai.api_key = os.getenv('OPENAI_API_KEY')

# Medical prompt
SYSTEM_PROMPT = """
You are a medical assistant AI. From the user's text, extract:
- The main condition or symptom described
- Any medications mentioned (with dosage if given)
- Any simple remedies or next steps
- Whether there's any urgency or emergency signal
Respond only with a JSON in this format:
{
  "detected_condition": "...",
  "medicines": ["..."],
  "remedies": ["..."],
  "urgency": "..."
}
"""

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        user_input = data.get("symptoms", "")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ]

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.3
        )

        ai_content = response['choices'][0]['message']['content']
        try:
            parsed = json.loads(ai_content)
        except json.JSONDecodeError:
            parsed = {
                "detected_condition": "Unknown",
                "medicines": [],
                "remedies": [],
                "urgency": "Not specified"
            }

        return jsonify({
            "query": user_input,
            "medical_analysis": ai_content,
            "detected_condition": parsed.get("detected_condition", ""),
            "medicines": parsed.get("medicines", []),
            "remedies": parsed.get("remedies", []),
            "urgency": parsed.get("urgency", "")
        })
    except Exception as e:
        logging.error(f"Error in analyze route: {str(e)}")
        return jsonify({"error": "Something went wrong.", "details": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(debug=True)
