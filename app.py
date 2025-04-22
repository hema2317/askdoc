# app.py
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from datetime import datetime
import openai
import os
import logging
import time
import psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv

# Initialize
load_dotenv()
app = Flask(__name__)
CORS(app)

# Configuration
app.config.update({
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'DATABASE_URL': os.getenv('DATABASE_URL'),
})

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Models
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True)
    # Add other fields as needed

class Medication(Base):
    __tablename__ = 'medications'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    dosage = Column(String(50))
    user_id = Column(Integer, ForeignKey('users.id'))
    # Add other fields

# Database Connection
def create_db_engine():
    max_retries = 5
    retry_delay = 3
    
    db_url = app.config['DATABASE_URL']
    
    # Fix URL format
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    # Ensure SSL
    if '?sslmode=' not in db_url.lower():
        db_url += '?sslmode=require'
    
    for attempt in range(max_retries):
        try:
            engine = create_engine(
                db_url,
                connect_args={
                    'sslmode': 'require',
                    'sslrootcert': '/etc/ssl/certs/ca-certificates.crt',
                    'connect_timeout': 10
                },
                pool_pre_ping=True,
                pool_recycle=300,
                echo=True  # Log SQL queries for debugging
            )
            
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("✅ Database connected successfully")
            return engine
            
        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            logger.critical("Failed to connect to database")
            raise RuntimeError("Database connection failed")

# Initialize database
try:
    engine = create_db_engine()
    Session = scoped_session(sessionmaker(bind=engine))
    Base.metadata.create_all(engine)
except Exception as e:
    logger.critical(f"Database initialization failed: {e}")
    exit(1)

# Analysis Functions
def perform_analysis(data):
    """Example analysis function using OpenAI"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": f"Analyze this data: {data}"}]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return None

# Routes
@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        # Get data from request
        data = request.json
        
        # Get medications from database
        with Session() as session:
            medications = session.query(Medication).all()
            med_data = [{'name': m.name, 'dosage': m.dosage} for m in medications]
        
        # Perform analysis
        analysis_result = perform_analysis(med_data)
        
        if not analysis_result:
            raise ValueError("Analysis returned no results")
        
        return jsonify({
            'status': 'success',
            'analysis': analysis_result,
            'medications': med_data
        })
        
    except Exception as e:
        logger.error(f"Route error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# Health Check
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
