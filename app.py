from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
import openai, os, jwt
from datetime import datetime, timedelta
from functools import wraps
import logging
from werkzeug.exceptions import HTTPException
import time
import psycopg2
from psycopg2.extras import RealDictCursor

# Load environment variables
load_dotenv()

# Initialize Flask
app = Flask(__name__)
CORS(app)

# Configuration
app.config.update({
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY', 'fallback-secret-key'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'DATABASE_URL': os.getenv('DATABASE_URL'),
    'EMERGENCY_CONTACT': os.getenv('EMERGENCY_CONTACT', '911'),
    'TWILIO_SID': os.getenv('TWILIO_SID'),
    'TWILIO_TOKEN': os.getenv('TWILIO_TOKEN'),
    'GOOGLE_API_KEY': os.getenv('GOOGLE_API_KEY')
})

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI
openai.api_key = app.config['OPENAI_API_KEY']

# Database setup with retry logic
def create_db_engine():
    max_retries = 5
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            db_url = app.config['DATABASE_URL']
            
            # Ensure we're using postgresql:// instead of postgres://
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql://', 1)
            
            # Add SSL configuration
            engine = create_engine(
                db_url,
                connect_args={
                    'sslmode': 'require',
                    'sslrootcert': '/etc/ssl/certs/ca-certificates.crt',
                    'options': '-c statement_timeout=5000'  # Set timeout to 5 seconds
                },
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30
            )
            
            # Test connection with a simple query
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                
            logger.info("Database connection established successfully")
            return engine
            
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            logger.error("Failed to establish database connection after multiple attempts")
            raise
Base = declarative_base()
engine = create_db_engine()
Session = scoped_session(sessionmaker(bind=engine))

# Models
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password = Column(String(120), nullable=False)
    medications = relationship('Medication', backref='user', cascade='all, delete-orphan')
    interactions = relationship('Interaction', backref='user', cascade='all, delete-orphan')

class Medication(Base):
    __tablename__ = 'medications'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    dosage = Column(String(50))
    frequency = Column(String(50))
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

class Interaction(Base):
    __tablename__ = 'interactions'
    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

# Create tables with retry logic
def initialize_database():
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(engine)
            logger.info("Database tables created successfully")
            return True
        except Exception as e:
            logger.error(f"Database initialization attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            logger.error("Failed to initialize database after multiple attempts")
            return False

if not initialize_database():
    logger.error("Application cannot start without database connection")
    exit(1)

# ... [rest of your routes and other code remains the same] ...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
