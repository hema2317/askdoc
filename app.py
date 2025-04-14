from flask import Flask, request, render_template, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask_doc():
    question = request.form.get("question")
    return jsonify({"response": f"🧠 You asked: {question}. (Pretend AI answer here)"})

if __name__ == "__main__":
    app.run(debug=True)
