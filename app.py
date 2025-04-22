import os
import logging
import time
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from sqlalchemy import create_engine, text, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base
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
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "fallback-secret-key"),
    DATABASE_URL=os.getenv("DATABASE_URL"),
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

# Database Connection with Robust SSL Handling
def create_db_engine():
    max_retries = 5
    retry_delay = 3
    
    db_url = app.config['DATABASE_URL']
    
    # Ensure proper URL format
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    # Add SSL parameters if not present
    if '?sslmode=' not in db_url.lower():
        separator = '?' if '?' not in db_url else '&'
        db_url += f"{separator}sslmode=require"
    
    for attempt in range(max_retries):
        try:
            # Test direct connection first
            test_direct_connection()
            
            # Create SQLAlchemy engine with explicit SSL context
            engine = create_engine(
                db_url,
                connect_args={
                    'sslmode': 'require',
                    'sslrootcert': '/etc/ssl/certs/ca-certificates.crt',
                    'connect_timeout': 10
                },
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=5,
                max_overflow=10,
                echo=True  # For debugging
            )
            
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("✅ Database connection established successfully")
            return engine
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            logger.critical("Failed to connect to database after multiple attempts")
            raise RuntimeError("Database connection failed")

def test_direct_connection():
    """Test direct psycopg2 connection with SSL"""
    try:
        db_url = urlparse(app.config['DATABASE_URL'])
        
        # Force postgresql:// scheme
        db_url_str = app.config['DATABASE_URL'].replace(
            'postgres://', 'postgresql://', 1
        )
        
        # Connect with explicit SSL
        conn = psycopg2.connect(
            dbname=db_url.path[1:],
            user=db_url.username,
            password=db_url.password,
            host=db_url.hostname,
            port=db_url.port,
            sslmode='require',
            sslrootcert='/etc/ssl/certs/ca-certificates.crt',
            connect_timeout=5
        )
        conn.close()
        logger.info("✅ Direct PostgreSQL connection successful!")
        return True
    except Exception as e:
        logger.error(f"Direct connection failed: {str(e)}")
        raise

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
        Analyze these symptoms: {symptoms}
        Current medications: {', '.join(medications) if medications else 'None'}
        
        Provide:
        1. Potential conditions (most likely first)
        2. Recommended actions
        3. Red flags for emergency care
        4. Medication interactions to watch for
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
    session = Session()
    try:
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
        # Test database connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        # Test OpenAI connection
        if app.config['OPENAI_API_KEY']:
            openai.Model.list()
        
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "openai": "connected" if app.config['OPENAI_API_KEY'] else "not_configured"
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG", False))
