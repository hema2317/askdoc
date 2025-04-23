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
You are a senior medical assistant AI. Given a patient's message, perform the following:
1. Rephrase their query like a medical note.
2. Provide a professional medical interpretation (like a second opinion).
3. Suggest simple remedies.
4. Indicate urgency level.
5. Recommend a doctor specialty if needed.

Respond in this JSON format only:
{
  "query_summary": "...",
  "medical_analysis": "...",
  "remedies": ["..."],
  "urgency": "...",
  "recommended_doctor": "..."
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
                "query_summary": user_input,
                "medical_analysis": "Could not interpret.",
                "remedies": [],
                "urgency": "Not specified",
                "recommended_doctor": "General Physician"
            }

        return jsonify({
            "query": parsed.get("query_summary", user_input),
            "medical_analysis": parsed.get("medical_analysis", ""),
            "remedies": parsed.get("remedies", []),
            "urgency": parsed.get("urgency", ""),
            "recommended_doctor": parsed.get("recommended_doctor", "")
        })
    except Exception as e:
        logging.error(f"Error in analyze route: {str(e)}")
        return jsonify({"error": "Something went wrong.", "details": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(debug=True)
