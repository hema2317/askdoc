from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import openai, os

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

app.config['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
openai.api_key = app.config['OPENAI_API_KEY']

# Mock database
symptoms_db = []
medications_db = []

@app.route('/api/symptoms', methods=['POST', 'OPTIONS'])
def handle_symptoms():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    data = request.json
    symptoms = data.get('name', '')
    
    prompt = f"""Patient reported symptom: {symptoms}
    Provide:
    1. Possible explanations
    2. Self-care recommendations
    3. When to see a doctor"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400
        )
        analysis = response.choices[0].message.content
    except Exception as e:
        analysis = f"AI analysis failed: {str(e)}"
    
    symptoms_db.append({
        "symptom": symptoms,
        "analysis": analysis,
        "timestamp": datetime.now().isoformat()
    })
    
    return jsonify({
        "symptom": symptoms,
        "analysis": analysis
    })

@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def handle_analysis():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    data = request.json
    symptoms = data.get('symptoms', '')
    
    disclaimer = "⚠️ DISCLAIMER: This is not a medical diagnosis. Always consult a doctor."
    
    prompt = f"""Symptoms: {symptoms}
    Provide:
    1. 3 possible conditions
    2. Recommended tests
    3. Urgency level (1-5)"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        analysis = disclaimer + "\n\n" + response.choices[0].message.content
    except Exception as e:
        analysis = f"{disclaimer}\n\nAnalysis failed: {str(e)}"
    
    return jsonify({
        "analysis": analysis
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
