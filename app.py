import os
import logging
import time
from flask import Flask, request, jsonify
from sqlalchemy import create_engine, text, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base
import psycopg2
from psycopg2.extras import RealDictCursor
import openai
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "fallback-secret-key"),
    DATABASE_URL=os.getenv("DATABASE_URL").replace('postgres://', 'postgresql://', 1),
    OPENAI_API_KEY=os.getenv("OPENAI_API_KEY"),
    DB_CONNECT_RETRIES=5,
    DB_CONNECT_DELAY=3
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

def create_db_engine():
    """Create SQLAlchemy engine with guaranteed SSL connection for Render"""
    max_retries = app.config['DB_CONNECT_RETRIES']
    retry_delay = app.config['DB_CONNECT_DELAY']
    
    db_url = app.config['DATABASE_URL']
    
    # Ensure SSL parameters are included
    if '?sslmode=' not in db_url.lower():
        db_url += '?sslmode=require'
    
    for attempt in range(max_retries):
        try:
            # Create engine with explicit SSL configuration
            engine = create_engine(
                db_url,
                connect_args={
                    'sslmode': 'require',
                    'connect_timeout': 10
                },
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=5,
                max_overflow=10
            )
            
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("✅ Database connection established successfully")
            return engine
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                continue
            logger.critical("Failed to connect to database after multiple attempts")
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
def analyze_symptoms(symptoms, medications):
    """Analyze symptoms using OpenAI"""
    try:
        prompt = f"""
        As a medical professional, analyze these symptoms:
        {symptoms}
        
        Current medications: {', '.join(medications) if medications else 'None'}
        
        Provide:
        1. Potential diagnoses (most likely first)
        2. Recommended actions
        3. Red flags requiring emergency care
        4. Possible medication interactions
        5. When to consult a doctor
        
        Use clear, concise language suitable for patients.
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=600
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
        symptoms = data.get('symptoms', '').strip()
        current_meds = [m.strip() for m in data.get('current_meds', []) if m.strip()]
        
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
            
            # Add any detected medications
            for med in current_meds:
                if med and not session.query(Medication).filter_by(name=med).first():
                    session.add(Medication(name=med))
            
            session.commit()
            
            return jsonify({
                "status": "success",
                "analysis": analysis_result,
                "analysis_id": analysis.id
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
    session = Session()
    try:
        meds = session.query(Medication).order_by(Medication.name).all()
        return jsonify([{
            "id": m.id,
            "name": m.name,
            "dosage": m.dosage,
            "frequency": m.frequency,
            "created_at": m.created_at.isoformat()
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
