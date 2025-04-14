from flask import Flask, request, render_template, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/ask", methods=["POST"])
def ask():
    query = request.form.get("query", "")
    file = request.files.get("file")

    print("User Query:", query)
    if file:
        print("File uploaded:", file.filename)

    # Simulate AI logic
    response_text = f"You asked: {query or '[File Only]'} (Pretend AI answer here)"
    return jsonify({"response": response_text})

if __name__ == '__main__':
    app.run(debug=True)
