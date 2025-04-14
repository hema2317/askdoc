from flask import Flask, request, render_template, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'

@app.route('/')
def index():
    return render_template('index.html')

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    if request.is_json:
        data = request.get_json()
        question = data.get("query", "")
        return jsonify({"response": f"🧠 AskDoc: You asked: {question} (Pretend AI answer here)"})
    else:
        return jsonify({"error": "Invalid input, must be JSON"}), 400

if __name__ == '__main__':
    app.run(debug=True)
