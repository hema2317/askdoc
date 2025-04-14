from flask import Flask, request, render_template, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask():
    user_input = request.form.get('query')
    file = request.files.get('file')

    if file:
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))

    # Fake AI answer
    response = f"🧠 You asked: {user_input or '(via file)'} (Pretend AI answer here)"
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(debug=True)
