from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    try:
        # Support both FormData and JSON
        if request.content_type.startswith("multipart/form-data"):
            query = request.form.get("query", "")
        elif request.is_json:
            query = request.json.get("query", "")
        else:
            return jsonify({"response": "Unsupported content type"}), 400

        if not query:
            return jsonify({"response": "Please enter a health question."}), 400

        # Simulate AI reply
        response_text = f"You asked: {query} (Pretend AI answer here)"
        return jsonify({"response": response_text})

    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"}), 500
