# app.py
import os
import psycopg2
from psycopg2 import OperationalError
from flask import Flask, request, jsonify
from flask_cors import CORS  # ✅ new
import time
import logging
import openai
import json
from datetime import datetime

app = Flask(__name__)
CORS(app, origins=["https://snack.expo.dev"])  # ✅ enables frontend access

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI
try:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    openai_version = "new"
except ImportError:
    openai.api_key = os.getenv('OPENAI_API_KEY')
    openai_version = "old"

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT', '5432')
}

# System prompt for DoctorAI
DOCTOR_SYSTEM_PROMPT = """
You are DoctorAI, an expert global medical assistant. 
Analyze the patient's message and do the following:

1. Detect any symptoms, vitals, or health concerns.
2. If a medicine or supplement is mentioned, extract the name, dose, and timing.
3. Suggest potential conditions and causes.
4. Provide remedies (medical or home-based).
5. Recommend if a doctor visit is needed and which type.
6. Summarize the case in 1-2 bullet points for doctor review.
7. Save medication and condition history if relevant.

Keep your tone helpful, avoid guessing, and clearly separate each section.
"""

def get_db_connection(max_retries=3, retry_delay=2):
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(
                host=DB_CONFIG['host'],
                database=DB_CONFIG['database'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                port=DB_CONFIG['port'],
                sslmode='require'
            )
            logger.info("Database connection established")
            return conn
        except OperationalError as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            time.sleep(retry_delay)
    logger.error("Failed to connect to database after multiple attempts")
    return None

def analyze_message_with_openai(user_text):
    try:
        messages = [
            {"role": "system", "content": DOCTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_text}
        ]

        if openai_version == "new":
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.4
            )
            return response.choices[0].message.content
        else:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.4
            )
            return response['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        return None

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.get_json()
        user_text = data.get('query')

        if not user_text:
            return jsonify({'error': 'Missing query field'}), 400

        logger.info(f"User input: {user_text}")

        ai_response = analyze_message_with_openai(user_text)

        if not ai_response:
            return jsonify({
                'error': 'OpenAI failed to generate a response'
            }), 503

        db_conn = get_db_connection()
        if db_conn:
            try:
                cursor = db_conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO chat_history (user_input, ai_response, created_at)
                    VALUES (%s, %s, %s)
                    """,
                    (user_text, ai_response, datetime.now())
                )
                db_conn.commit()
                logger.info("Chat stored successfully")
            except Exception as e:
                db_conn.rollback()
                logger.error(f"Failed to store chat: {str(e)}")
            finally:
                db_conn.close()

        return jsonify({
            'status': 'success',
            'query': user_text,
            'response': ai_response
        }), 200

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    db_conn = get_db_connection()
    db_status = 'connected' if db_conn else 'unavailable'
    if db_conn:
        db_conn.close()

    try:
        if openai_version == "new":
            client.models.list()
        else:
            openai.Model.list()
        openai_status = 'connected'
    except Exception as e:
        openai_status = 'unavailable'
        logger.error(f"OpenAI health check failed: {str(e)}")

    return jsonify({
        'status': 'operational',
        'services': {
            'database': db_status,
            'openai': openai_status,
            'openai_version': openai_version
        }
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
