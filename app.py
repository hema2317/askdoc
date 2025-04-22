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

# Load environment variables
load_dotenv()

# Initialize Flask
app = Flask(__name__)
CORS(app)

# Configuration
app.config.update({
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY', 'fallback-secret-key'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'DATABASE_URL': os.getenv('DATABASE_URL', 'sqlite:///healthassistant.db'),
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

# Database setup
Base = declarative_base()
engine = create_engine(app.config['DATABASE_URL'])
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

# Create tables
try:
    Base.metadata.create_all(engine)
    logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Error creating database tables: {str(e)}")
    raise

# Error handler
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"An error occurred: {str(e)}")
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    return jsonify({"error": "Internal server error"}), 500

# Database teardown
@app.teardown_appcontext
def shutdown_session(exception=None):
    Session.remove()

# Auth Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            logger.warning("No authorization token provided")
            return jsonify({"error": "Authorization token is missing"}), 401

        try:
            token = auth_header.split()[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = data['user_id']
        except jwt.ExpiredSignatureError:
            logger.warning("Expired token")
            return jsonify({"error": "Token has expired"}), 401
        except (jwt.InvalidTokenError, IndexError) as e:
            logger.warning(f"Invalid token: {str(e)}")
            return jsonify({"error": "Token is invalid"}), 401

        return f(current_user, *args, **kwargs)
    return decorated

# Prompt Generator
def generate_medical_prompt(symptoms, meds):
    return f"""As a medical AI assistant, analyze these symptoms: {symptoms}

Patient's Current Medications: {', '.join(meds) if meds else 'None'}

Provide a structured response with:
1. Possible Conditions (most likely first)
2. Recommended Actions (considering current medications)
3. Medication Interactions to Watch For
4. When to Seek Medical Attention
5. Prevention Tips (if applicable)

Format in clear markdown sections.
Always include: "Consult a healthcare professional for proper diagnosis."
"""

# Routes
@app.route('/api/auth', methods=['POST'])
def login():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user or user.password != password:
            return jsonify({"error": "Invalid credentials"}), 401

        token = jwt.encode(
            {'user_id': user.username, 'exp': datetime.utcnow() + timedelta(hours=24)},
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )
        return jsonify({
            "token": token,
            "username": user.username,
            "medications": [m.name for m in user.medications]
        })
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        session.close()

@app.route('/api/medications', methods=['GET', 'POST'])
@token_required
def medications(current_user):
    session = Session()
    try:
        user = session.query(User).filter_by(username=current_user).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        if request.method == 'POST':
            if not request.is_json:
                return jsonify({"error": "Request must be JSON"}), 400

            data = request.get_json()
            if not data.get('name'):
                return jsonify({"error": "Medication name required"}), 400

            new_med = Medication(
                name=data['name'],
                dosage=data.get('dosage', ''),
                frequency=data.get('frequency', ''),
                user=user
            )
            session.add(new_med)
            session.commit()
            return jsonify({
                "id": new_med.id,
                "name": new_med.name,
                "dosage": new_med.dosage,
                "frequency": new_med.frequency,
                "timestamp": new_med.timestamp.isoformat()
            })

        # GET request
        meds = [{
            "id": m.id,
            "name": m.name,
            "dosage": m.dosage,
            "frequency": m.frequency,
            "timestamp": m.timestamp.isoformat()
        } for m in user.medications]
        return jsonify({"medications": meds})

    except Exception as e:
        session.rollback()
        logger.error(f"Medications error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        session.close()

@app.route('/api/analyze', methods=['POST'])
@token_required
def analyze(current_user):
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    symptoms = data.get('symptoms')
    if not symptoms:
        return jsonify({"error": "Symptoms required"}), 400

    session = Session()
    try:
        user = session.query(User).filter_by(username=current_user).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        meds = [m.name for m in user.medications]
        prompt = generate_medical_prompt(symptoms, meds)

        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600
            )
            result = response.choices[0].message.content

            # Log interaction
            interaction = Interaction(
                type="symptom_analysis",
                content=result,
                user=user
            )
            session.add(interaction)
            session.commit()

            return jsonify({
                "analysis": result,
                "medications_considered": meds,
                "timestamp": interaction.timestamp.isoformat()
            })

        except openai.error.OpenAIError as e:
            logger.error(f"OpenAI error: {str(e)}")
            return jsonify({"error": "AI service unavailable"}), 503
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}")
            return jsonify({"error": "Analysis failed"}), 500

    except Exception as e:
        session.rollback()
        logger.error(f"Database error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        session.close()

@app.route('/api/history', methods=['GET'])
@token_required
def history(current_user):
    session = Session()
    try:
        user = session.query(User).filter_by(username=current_user).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        logs = [{
            "id": i.id,
            "type": i.type,
            "summary": i.content[:100] + "..." if len(i.content) > 100 else i.content,
            "timestamp": i.timestamp.isoformat()
        } for i in user.interactions]

        return jsonify({
            "history": logs,
            "count": len(logs)
        })
    except Exception as e:
        logger.error(f"History error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        session.close()

@app.route('/api/emergency', methods=['POST'])
@token_required
def emergency(current_user):
    session = Session()
    try:
        user = session.query(User).filter_by(username=current_user).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Log emergency
        interaction = Interaction(
            type="emergency_triggered",
            content="Emergency assistance requested",
            user=user
        )
        session.add(interaction)
        session.commit()

        return jsonify({
            "message": f"Contact emergency services at {app.config['EMERGENCY_CONTACT']}",
            "user_medications": [m.name for m in user.medications],
            "nearest_facilities": [
                {"name": "General Hospital", "contact": "911"},
                {"name": "Poison Control", "contact": "1-800-222-1222"}
            ],
            "timestamp": interaction.timestamp.isoformat()
        })
    except Exception as e:
        session.rollback()
        logger.error(f"Emergency error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        session.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
