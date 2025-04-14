document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("askForm");
  const responseBox = document.getElementById("responseBox");
  const chatLog = document.getElementById("chatLog");

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const query = document.getElementById("query").value;
    const file = document.getElementById("file").files[0];
    const formData = new FormData();
    formData.append("query", query);
    if (file) formData.append("file", file);

    responseBox.innerHTML = "🧠 Thinking...";

    try {
      const response = await fetch("/ask", {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      responseBox.innerHTML = `<b>🩺 AskDoc:</b> ${data.response}`;

      await fetchChatLog();
    } catch (err) {
      responseBox.innerHTML = "❌ Failed to get a response.";
    }
  });

  window.startListening = function () {
    if (!("webkitSpeechRecognition" in window)) {
      alert("Voice recognition not supported");
      return;
    }

    const recognition = new webkitSpeechRecognition();
    recognition.lang = "en-US";
    recognition.start();
    recognition.onresult = function (event) {
      document.getElementById("query").value = event.results[0][0].transcript;
    };
  };

  async function fetchChatLog() {
    try {
      const res = await fetch("/history");
      const log = await res.json();
      chatLog.innerHTML = "";
      log.forEach((item, i) => {
        chatLog.innerHTML += `
          <div class="qa">
            <b>Q${i + 1}:</b> ${item.q}<br/>
            <b>A${i + 1}:</b> ${item.a}
          </div>`;
      });
    } catch (e) {
      chatLog.innerHTML = "Failed to load chat history.";
    }
  }

  window.downloadPDF = function () {
    window.location.href = "/download";
  };

  fetchChatLog(); // Load on first load
});
