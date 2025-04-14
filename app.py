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
    try:
        query = request.form.get("query") or ""
        uploaded_file = request.files.get("file")
        
        print("User Query:", query)
        if uploaded_file:
            print("File uploaded:", uploaded_file.filename)

        # Simulate AI reply
        response_text = f"You asked: {query} (Pretend AI answer here)"
        return jsonify({"response": response_text})

    except Exception as e:
        print("Error:", str(e))
        return jsonify({"error": str(e)}), 400


if __name__ == '__main__':
    app.run(debug=True)
