from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import openai, os, jwt
from datetime import datetime, timedelta
from functools import wraps

# Load environment variables
load_dotenv()

# Initialize Flask
app = Flask(__name__)
CORS(app)

# Config
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'health-assistant-secret')
app.config['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
app.config['DATABASE_URL'] = os.getenv('DATABASE_URL')
app.config['EMERGENCY_CONTACT'] = os.getenv('EMERGENCY_CONTACT', '911')

openai.api_key = app.config['OPENAI_API_KEY']

# Database setup
Base = declarative_base()
engine = create_engine(app.config['DATABASE_URL'])
Session = sessionmaker(bind=engine)

# Models
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    medications = relationship('Medication', backref='user')
    interactions = relationship('Interaction', backref='user')

class Medication(Base):
    __tablename__ = 'medications'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    dosage = Column(String)
    frequency = Column(String)
    timestamp = Column(DateTime)
    user_id = Column(Integer, ForeignKey('users.id'))

class Interaction(Base):
    __tablename__ = 'interactions'
    id = Column(Integer, primary_key=True)
    type = Column(String)
    content = Column(Text)
    timestamp = Column(DateTime)
    user_id = Column(Integer, ForeignKey('users.id'))

Base.metadata.create_all(engine)

# Auth Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"error": "Token missing"}), 401

        try:
            data = jwt.decode(token.split()[1], app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = data['user_id']
        except:
            return jsonify({"error": "Invalid token"}), 401

        return f(current_user, *args, **kwargs)
    return decorated

# Prompt Generator
def generate_medical_prompt(symptoms, meds):
    return f"""As a medical AI assistant, analyze these symptoms: {symptoms}

Current Medications: {', '.join(meds) if meds else 'None'}

Return:
1. Conditions (likely ones first)
2. Recommended actions
3. Medication concerns
4. When to see a doctor
5. Preventive tips

Use markdown format.
Add: Consult a doctor disclaimer."""

# Routes
@app.route('/api/auth', methods=['POST'])
def login():
    session = Session()
    data = request.json
    user = session.query(User).filter_by(username=data['username']).first()
    if user and user.password == data['password']:
        token = jwt.encode({'user_id': user.username, 'exp': datetime.utcnow() + timedelta(hours=24)}, app.config['SECRET_KEY'], algorithm='HS256')
        return jsonify({"token": token, "username": user.username})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/medications', methods=['GET', 'POST'])
@token_required
def medications(current_user):
    session = Session()
    user = session.query(User).filter_by(username=current_user).first()

    if request.method == 'POST':
        data = request.json
        new_med = Medication(
            name=data['name'],
            dosage=data.get('dosage', ''),
            frequency=data.get('frequency', ''),
            timestamp=datetime.now(),
            user=user
        )
        session.add(new_med)
        session.commit()
        return jsonify({"message": "Medication added"})

    meds = [{"name": m.name, "dosage": m.dosage, "frequency": m.frequency} for m in user.medications]
    return jsonify({"medications": meds})

@app.route('/api/analyze', methods=['POST'])
@token_required
def analyze(current_user):
    session = Session()
    user = session.query(User).filter_by(username=current_user).first()

    data = request.json
    symptoms = data.get('symptoms', '')
    if not symptoms:
        return jsonify({"error": "symptoms required"}), 400

    meds = [m.name for m in user.medications]
    prompt = generate_medical_prompt(symptoms, meds)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        result = response.choices[0].message.content
        session.add(Interaction(type="symptom_analysis", content=result, timestamp=datetime.now(), user=user))
        session.commit()
        return jsonify({"analysis": result})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/history', methods=['GET'])
@token_required
def history(current_user):
    session = Session()
    user = session.query(User).filter_by(username=current_user).first()
    logs = [{"timestamp": i.timestamp.isoformat(), "type": i.type, "summary": i.content[:100]} for i in user.interactions]
    return jsonify({"history": logs})

@app.route('/api/emergency', methods=['POST'])
@token_required
def emergency(current_user):
    return jsonify({
        "message": f"Call emergency contact {app.config['EMERGENCY_CONTACT']}.",
        "nearest_facilities": [
            {"name": "General Hospital", "phone": "555-1000"},
            {"name": "Urgent Care", "phone": "555-2000"}
        ]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
with app.app_context():
    db.create_all()
