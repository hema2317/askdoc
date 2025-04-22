from flask import Flask, request, jsonify
from sqlalchemy import create_engine, text, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base
from urllib.parse import urlparse
import os
import logging
import time
import psycopg2
import openai
from datetime import datetime
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "dev"),
    DATABASE_URL=os.getenv("DATABASE_URL"),  # Render provides this
    OPENAI_API_KEY=os.getenv("OPENAI_API_KEY")
)

# Initialize OpenAI
openai.api_key = app.config['OPENAI_API_KEY']

# Database Models
Base = declarative_base()

class Analysis(Base):
    __tablename__ = 'analyses'
    id = Column(Integer, primary_key=True)
    symptoms = Column(Text)
    medications = Column(Text)
    analysis = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Medication(Base):
    __tablename__ = 'medications'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    dosage = Column(String(50))
    frequency = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

# Database Connection
def create_db_engine():
    max_retries = 3
    retry_delay = 5
    
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
                echo=True  # For debugging
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

# Helper Functions
def analyze_symptoms(symptoms, medications):
    """Analyze symptoms using OpenAI"""
    try:
        prompt = f"""
        Analyze these symptoms: {symptoms}
        Current medications: {', '.join(medications) if medications else 'None'}
        
        Provide:
        1. Potential conditions
        2. Recommended actions
        3. Medication interactions to watch for
        4. When to seek emergency care
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return None

# API Endpoints
@app.route('/analyze', methods=['POST'])
def analyze():
    """Endpoint for symptom analysis"""
    try:
        data = request.get_json()
        symptoms = data.get('symptoms', '')
        current_meds = data.get('current_meds', [])
        
        if not symptoms:
            return jsonify({"error": "Symptoms are required"}), 400
        
        # Perform analysis
        analysis_result = analyze_symptoms(symptoms, current_meds)
        
        if not analysis_result:
            return jsonify({"error": "Analysis failed"}), 500
            
        # Save to database
        session = Session()
        try:
            analysis = Analysis(
                symptoms=symptoms,
                medications=', '.join(current_meds),
                analysis=analysis_result
            )
            session.add(analysis)
            session.commit()
            
            # Add any detected medications
            for med in current_meds:
                if med and not session.query(Medication).filter_by(name=med).first():
                    session.add(Medication(name=med))
            session.commit()
            
            return jsonify({
                "status": "success",
                "analysis": analysis_result
            })
            
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            return jsonify({"error": "Database error"}), 500
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Analysis endpoint error: {e}")
        return jsonify({"error": "Server error"}), 500

@app.route('/medications', methods=['GET'])
def get_medications():
    """Get all medications"""
    try:
        session = Session()
        meds = session.query(Medication).order_by(Medication.name).all()
        return jsonify([{
            "id": m.id,
            "name": m.name,
            "dosage": m.dosage,
            "frequency": m.frequency
        } for m in meds])
    except Exception as e:
        logger.error(f"Medications error: {e}")
        return jsonify({"error": "Server error"}), 500
    finally:
        session.close()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return jsonify({"status": "healthy"})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy"}), 500

# Error Handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG", False))
