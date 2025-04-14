from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import openai
import os
from fpdf import FPDF
import tempfile

app = Flask(__name__)
CORS(app)

openai.api_key = os.environ.get("OPENAI_API_KEY")  # Set in Render dashboard

chat_history = []

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    query = request.form.get("query")
    if not query:
        return jsonify({"response": "❌ No query received."}), 400

    try:
        # ChatGPT Response
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful health assistant."},
                {"role": "user", "content": query}
            ]
        )
        answer = response["choices"][0]["message"]["content"].strip()
        chat_history.append({"q": query, "a": answer})
        return jsonify({"response": answer})
    except Exception as e:
        return jsonify({"response": f"⚠️ Error: {str(e)}"}), 500

@app.route("/history", methods=["GET"])
def history():
    return jsonify(chat_history)

@app.route("/download", methods=["GET"])
def download_pdf():
    if not chat_history:
        return "No conversation to download.", 400

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, "AskDoc Conversation Log\n", align="L")
    pdf.ln()

    for i, item in enumerate(chat_history, 1):
        pdf.multi_cell(0, 10, f"{i}. Q: {item['q']}\nA: {item['a']}\n", align="L")

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp.name)
    return send_file(temp.name, as_attachment=True, download_name="AskDoc_Conversation.pdf")

if __name__ == "__main__":
    app.run(debug=True)
