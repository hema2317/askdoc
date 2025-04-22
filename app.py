import os
import psycopg2
from psycopg2 import OperationalError
from flask import Flask, request, jsonify
import time
import logging
from openai import OpenAI

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Database configuration
DB_CONFIG = {
    'host': "dpg-d03h39adb0a6c738c1t50-a.oregon-postgres.render.com",
    'database': "healthdb",
    'user': "healthdb_user",
    'password': os.getenv('DB_PASSWORD'),
    'port': "5432"
}

# System prompt for medical analysis
MEDICAL_SYSTEM_PROMPT = """
You are DoctorAI, a professional medical analysis system. Analyze the patient's vitals and provide:

1. Professional assessment of each vital sign
2. Potential health implications
3. Recommended actions or remedies
4. When to seek immediate medical attention

Present your analysis in clear, professional medical language suitable for patients.
Format your response with clear sections for each vital sign and overall recommendations.
"""

def get_db_connection(max_retries=3, retry_delay=2):
    """Get database connection with retry logic"""
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
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    logger.error("Failed to connect to database after multiple attempts")
    return None

async def get_openai_analysis(data):
    """Get professional medical analysis from OpenAI"""
    try:
        # Prepare the prompt
        user_prompt = f"""
        Analyze these patient vitals:
        - Blood Pressure: {data.get('systolic_bp')}/{data.get('diastolic_bp')} mmHg
        - Heart Rate: {data.get('heart_rate')} bpm
        - Temperature: {data.get('temperature')} °C
        - Oxygen Saturation: {data.get('spo2', 'N/A')}%
        - Additional Notes: {data.get('notes', 'None')}
        """
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": MEDICAL_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3  # More deterministic medical responses
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        return None

@app.route('/analyze', methods=['POST'])
async def analyze():
    try:
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
        
        data = request.get_json()
        logger.info(f"Received data: {data}")
        
        # Validate required fields
        required_fields = ['systolic_bp', 'diastolic_bp', 'heart_rate', 'temperature']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'missing_fields': missing_fields
            }), 400
        
        # Get OpenAI analysis
        analysis = await get_openai_analysis(data)
        
        if not analysis:
            return jsonify({
                'error': 'Failed to generate medical analysis',
                'details': 'AI service unavailable'
            }), 503
        
        # Prepare response
        response = {
            'status': 'analysis_complete',
            'medical_analysis': analysis,
            'vitals': {
                'blood_pressure': f"{data['systolic_bp']}/{data['diastolic_bp']}",
                'heart_rate': data['heart_rate'],
                'temperature': data['temperature']
            }
        }
        
        # Store in database if available
        db_conn = get_db_connection()
        if db_conn:
            try:
                cursor = db_conn.cursor()
                cursor.execute(
                    """INSERT INTO medical_analyses 
                    (vitals, analysis, created_at) 
                    VALUES (%s, %s, NOW())""",
                    (str(data), analysis)
                )
                db_conn.commit()
                response['database_status'] = 'stored'
                logger.info("Analysis stored in database")
            except Exception as e:
                db_conn.rollback()
                response['database_status'] = 'storage_failed'
                logger.error(f"Database storage failed: {str(e)}")
            finally:
                db_conn.close()
        else:
            response['database_status'] = 'database_unavailable'
            logger.warning("Analysis performed without database storage")
        
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    # Check database connection
    db_conn = get_db_connection()
    db_status = 'connected' if db_conn else 'unavailable'
    if db_conn:
        db_conn.close()
    
    # Check OpenAI connection
    try:
        client.models.list()  # Simple API call to check connectivity
        openai_status = 'connected'
    except Exception as e:
        openai_status = 'unavailable'
        logger.error(f"OpenAI health check failed: {str(e)}")
    
    return jsonify({
        'status': 'operational',
        'services': {
            'database': db_status,
            'openai': openai_status
        },
        'endpoints': {
            '/analyze': 'POST medical data for professional analysis',
            '/health': 'GET service status'
        }
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
