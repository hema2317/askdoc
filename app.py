from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import openai, os
from datetime import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["OPTIONS", "POST"],
        "allow_headers": ["Content-Type"]
    }
})

app.config['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
openai.api_key = app.config['OPENAI_API_KEY']

# In-memory storage
medical_history = []

def generate_medical_prompt(symptoms, user_context=None):
    base_prompt = f"""As a medical AI assistant, analyze these symptoms: {symptoms}

Provide a structured response with these sections:
1. Potential Conditions (list 3 most likely, with brief explanations)
2. Recommended Actions:
   - Immediate steps (if urgent)
   - Self-care measures
   - Monitoring advice
3. Diagnostic Suggestions:
   - Tests to consider
   - Physical exam findings to look for
4. Red Flags (when to seek immediate care)
5. Prevention Tips (if applicable)

Format the response in clear, markdown-friendly sections.
Always include this disclaimer: "Consult a healthcare professional for proper evaluation."
"""
    
    if user_context:
        base_prompt += f"\n\nPatient Context: {user_context}"
    
    return base_prompt

@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def analyze_symptoms():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    try:
        data = request.get_json()
        if not data or 'symptoms' not in data:
            return jsonify({"error": "Symptoms parameter required"}), 400

        symptoms = data['symptoms']
        user_context = data.get('context', '')
        
        prompt = generate_medical_prompt(symptoms, user_context)
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a medical assistant that provides information but never diagnoses."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # More conservative responses
            max_tokens=600
        )
        
        analysis = response.choices[0].message.content
        
        # Log the interaction
        medical_history.append({
            "timestamp": datetime.now().isoformat(),
            "symptoms": symptoms,
            "analysis": analysis,
            "context": user_context
        })
        
        return jsonify({
            "analysis": analysis,
            "context": user_context
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "message": "Medical analysis failed"
        }), 500

@app.route('/api/emergency_check', methods=['POST', 'OPTIONS'])
def emergency_check():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    try:
        data = request.get_json()
        symptoms = data.get('symptoms', '')
        
        prompt = f"""Evaluate if these symptoms require emergency care: {symptoms}

Respond ONLY with:
- "EMERGENCY: [reason]" if immediate care is needed
- "Non-emergency" otherwise
Include vital sign thresholds if relevant."""
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Very conservative
            max_tokens=100
        )
        
        return jsonify({
            "assessment": response.choices[0].message.content
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
