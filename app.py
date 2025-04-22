import os
import json
import time
import logging
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
from datetime import datetime

app = Flask(__name__)
CORS(app, origins=["https://snack.expo.dev", "*"])  # Enable CORS

# Logging
logging.basicConfig(level=logging.INFO)

# OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# DB config
DB_CONFIG = {
    'host': os.getenv("DB_HOST"),
    'database': os.getenv("DB_NAME"),
    'user': os.getenv("DB_USER"),
    'password': os.getenv("DB_PASSWORD"),
    'port': os.getenv("DB_PORT", "5432")
}

# Connect to DB
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_CONFIG['host'],
            database=DB_CONFIG['database'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            port=DB_CONFIG['port'],
            sslmode='require'
        )
        return conn
    except Exception as e:
        logging.error(f"DB connection failed: {e}")
        return None

# Extract medicine names and urgency from AI
def get_medical_analysis(symptoms):
    prompt = f"""
You are a highly skilled AI medical assistant. Analyze the user's symptoms and provide:

1. A clear and helpful medical assessment
2. Any medicine names mentioned
3. Home remedies if applicable
4. Whether urgent attention is needed

User: "{symptoms}"
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are DoctorAI, a smart medical assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )

        content = response['choices'][0]['message']['content']
        return parse_response(content, symptoms)
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        return {
            "medical_analysis": "Sorry, we couldn't analyze your symptoms right now.",
            "query": symptoms
        }

# Parse OpenAI response
def parse_response(text, symptoms):
    medicines = []
    remedies = []
    urgency = ""
    lines = text.splitlines()

    for line in lines:
        lower = line.lower()
        if "take" in lower or "mg" in lower:
            medicines.append(line.strip())
        if "home remedy" in lower or "drink" in lower or "rest" in lower:
            remedies.append(line.strip())
        if "emergency" in lower or "see a doctor" in lower or "immediate attention" in lower:
            urgency += line.strip()

    return {
        "query": symptoms,
        "medical_analysis": text,
        "medicines": medicines,
        "remedies": remedies,
        "urgency": urgency
    }

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    symptoms = data.get("symptoms", "")
    if not symptoms:
        return jsonify({"error": "Missing symptoms"}), 400

    result = get_medical_analysis(symptoms)

    # Optional DB logging
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO medical_analyses (symptoms, analysis, created_at)
                VALUES (%s, %s, %s)
            """, (symptoms, result["medical_analysis"], datetime.now()))
            conn.commit()
            cur.close()
            conn.close()
    except Exception as db_err:
        logging.warning(f"Could not store to DB: {db_err}")

    return jsonify(result)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "OK"})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
