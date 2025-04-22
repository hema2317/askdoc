import os
import logging
import time
import ssl
from urllib.parse import urlparse, parse_qs, urlencode
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
    DATABASE_URL=os.getenv("DATABASE_URL"),
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

def create_ssl_context():
    """Create a custom SSL context for PostgreSQL"""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context

def get_db_config():
    """Parse and enhance database configuration with SSL"""
    db_url = app.config['DATABASE_URL']
    
    # Ensure postgresql:// scheme
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    # Parse URL and query parameters
    parsed = urlparse(db_url)
    query = parse_qs(parsed.query)
    
    # Force SSL parameters
    query['sslmode'] = ['require']
    query['sslrootcert'] = ['/etc/ssl/certs/ca-certificates.crt']
    
    # Rebuild URL
    netloc = parsed.netloc
    if parsed.password and '@' in parsed.netloc:
        # Handle special characters in password
        userinfo = parsed.netloc.split('@')[0]
        hostport = parsed.netloc.split('@')[1]
        userinfo = userinfo.split(':')[0] + ':' + parsed.password
        netloc = f"{userinfo}@{hostport}"
    
    new_query = urlencode(query, doseq=True)
    db_url = f"postgresql://{netloc}{parsed.path}?{new_query}"
    
    return {
        'db_url': db_url,
        'direct_params': {
            'dbname': parsed.path[1:],
            'user': parsed.username,
            'password': parsed.password,
            'host': parsed.hostname,
            'port': parsed.port,
            'sslmode': 'require',
            'sslcontext': create_ssl_context(),
            'connect_timeout': 5
        }
    }

def test_direct_connection(params):
    """Test direct connection with enhanced SSL handling"""
    try:
        conn = psycopg2.connect(
            cursor_factory=RealDictCursor,
            **params
        )
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
            if result and result['?column?'] == 1:
                logger.info("✅ Direct PostgreSQL connection successful!")
                return True
        conn.close()
    except Exception as e:
        logger.error(f"Direct connection failed: {str(e)}")
        raise

def create_db_engine():
    """Create SQLAlchemy engine with robust connection handling"""
    max_retries = app.config['DB_CONNECT_RETRIES']
    retry_delay = app.config['DB_CONNECT_DELAY']
    
    db_config = get_db_config()
    
    for attempt in range(max_retries):
        try:
            # Test direct connection first
            test_direct_connection(db_config['direct_params'])
            
            # Create engine with explicit SSL configuration
            engine = create_engine(
                db_config['db_url'],
                connect_args={
                    'sslmode': 'require',
                    'sslrootcert': '/etc/ssl/certs/ca-certificates.crt',
                    'connect_timeout': 10
                },
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=5,
                max_overflow=10,
                echo=True
            )
            
            # Test engine connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("✅ SQLAlchemy engine connected successfully!")
            return engine
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                continue
            logger.critical("🚨 Failed to connect to PostgreSQL after retries!")
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
    """Analyze symptoms using OpenAI with enhanced error handling"""
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
    """Enhanced analysis endpoint with transaction handling"""
    try:
        data = request.get_json()
        symptoms = data.get('symptoms', '').strip()
        current_meds = [m.strip() for m in data.get('current_meds', []) if m.strip()]
        
        if not symptoms:
            return jsonify({"error": "Symptoms description is required"}), 400
        
        # Perform analysis
        analysis_result = analyze_symptoms(symptoms, current_meds)
        if not analysis_result:
            return jsonify({"error": "Could not analyze symptoms"}), 500
            
        # Database operations
        session = Session()
        try:
            # Start transaction
            analysis = Analysis(
                symptoms=symptoms,
                medications=', '.join(current_meds),
                analysis=analysis_result
            )
            session.add(analysis)
            
            # Add new medications
            for med in current_meds:
                if not session.query(Medication).filter_by(name=med).first():
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
            return jsonify({"error": "Database operation failed"}), 500
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Analysis endpoint error: {e}")
        return jsonify({"error": "Server error"}), 500

@app.route('/medications', methods=['GET'])
def get_medications():
    """Get medications with error handling"""
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
        return jsonify({"error": "Could not retrieve medications"}), 500
    finally:
        session.close()

@app.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check"""
    try:
        # Test database connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        # Test OpenAI if configured
        openai_status = "not_configured"
        if app.config['OPENAI_API_KEY']:
            try:
                openai.Model.list()
                openai_status = "connected"
            except Exception as e:
                openai_status = f"error: {str(e)}"
        
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "openai": openai_status,
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
