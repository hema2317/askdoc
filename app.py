import os
import psycopg2
from psycopg2 import OperationalError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from flask import Flask, request, jsonify
import time
from functools import wraps

app = Flask(__name__)

# Configuration - replace with your actual credentials
DB_CONFIG = {
    'host': "dpg-d03h39adb0a6c738c1t50-a.oregon-postgres.render.com",
    'database': "healthdb",
    'user': "healthdb_user",
    'password': "your_password_here",
    'port': "5432"
}

# Database connection with retry logic
def get_db_connection(max_retries=5, retry_delay=2):
    retry_count = 0
    last_exception = None
    
    while retry_count < max_retries:
        try:
            # Try to create a connection
            conn = psycopg2.connect(
                host=DB_CONFIG['host'],
                database=DB_CONFIG['database'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                port=DB_CONFIG['port'],
                sslmode='require'  # Important for Render.com PostgreSQL
            )
            return conn
        except OperationalError as e:
            last_exception = e
            retry_count += 1
            app.logger.error(f"Attempt {retry_count} failed: {e}")
            if retry_count < max_retries:
                time.sleep(retry_delay)
    
    app.logger.error(f"Failed to connect to database after {max_retries} attempts")
    return None

# Decorator for routes that need DB but can work without it
def with_db_fallback(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            conn = get_db_connection()
            if conn is None:
                return func(*args, **kwargs, db_available=False)
            try:
                return func(*args, **kwargs, db_available=True, db_conn=conn)
            finally:
                conn.close()
        except Exception as e:
            app.logger.error(f"Database operation failed: {e}")
            return func(*args, **kwargs, db_available=False)
    return wrapper

# Medical analysis function (works without DB)
def analyze_medical_data(data):
    # Example analysis - replace with your actual medical analysis logic
    analysis = {
        'status': 'completed',
        'findings': {
            'blood_pressure': 'normal' if 110 <= data.get('systolic_bp', 0) <= 120 else 'elevated',
            'heart_rate': 'normal' if 60 <= data.get('heart_rate', 0) <= 100 else 'abnormal',
            'temperature': 'normal' if 36.5 <= data.get('temperature', 0) <= 37.5 else 'fever'
        },
        'recommendations': [
            'Follow up in 3 months',
            'Maintain healthy diet'
        ]
    }
    return analysis

@app.route('/analyze', methods=['POST'])
@with_db_fallback
def analyze(db_available=False, db_conn=None):
    try:
        data = request.json
        
        # Perform medical analysis (works without DB)
        analysis = analyze_medical_data(data)
        
        # Store in database if available
        if db_available and db_conn:
            try:
                cursor = db_conn.cursor()
                cursor.execute(
                    "INSERT INTO medical_records (patient_data, analysis) VALUES (%s, %s)",
                    (str(data), str(analysis))
                )
                db_conn.commit()
                analysis['database_status'] = 'stored'
            except Exception as e:
                db_conn.rollback()
                analysis['database_status'] = 'storage_failed'
                app.logger.error(f"Failed to store analysis: {e}")
        else:
            analysis['database_status'] = 'database_unavailable'
        
        return jsonify(analysis), 200
    
    except Exception as e:
        app.logger.error(f"Analysis failed: {e}")
        return jsonify({'error': 'Analysis failed', 'details': str(e)}), 500

@app.route('/health')
def health_check():
    # Simple health check endpoint
    conn = get_db_connection()
    db_status = 'healthy' if conn else 'unavailable'
    if conn:
        conn.close()
    return jsonify({
        'status': 'running',
        'database': db_status
    }), 200

if __name__ == '__main__':
    app.run(debug=True)
