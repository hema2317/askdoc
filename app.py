from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from openai import OpenAI
from fpdf import FPDF
import tempfile
import os

app = Flask(__name__)
CORS(app)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # Set this in Render env

# Store chat history in memory
chat_history = []

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    query = request.form.get("query")
    file = request.files.get("file")

    if not query and not file:
        return jsonify({"response": "❌ No question or file provided."}), 400

    file_content = ""
    if file:
        try:
            file_content = file.read().decode("utf-8")
        except Exception:
            file_content = "[Error reading file]"

    # Combine input
    full_prompt = f"{query}\n\nAttached info:\n{file_content}" if file_content else query

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful health assistant. Keep it simple and useful."},
                {"role": "user", "content": full_prompt}
            ]
        )
        answer = response.choices[0].message.content.strip()
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
        return "No conversation found.", 400

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "AskDoc Chat Summary", ln=True, align='C')
    pdf.ln(10)

    for i, item in enumerate(chat_history, 1):
        pdf.multi_cell(0, 10, f"{i}. Q: {item['q']}\nA: {item['a']}\n")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp.name)
    return send_file(tmp.name, as_attachment=True, download_name="AskDoc_Conversation.pdf")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
