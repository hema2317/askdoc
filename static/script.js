
// Wait for DOM to load
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("askForm");
  const responseBox = document.getElementById("responseBox");
  const chatLog = document.getElementById("chatLog");

  // Submit health query
  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const query = document.getElementById("query").value;
    const file = document.getElementById("file").files[0];
    const formData = new FormData();
    formData.append("query", query);
    if (file) formData.append("file", file);

    chatLog.innerHTML += `<div class='user-msg'><b>You:</b> ${query}</div>`;
    chatLog.innerHTML += `<div class='ai-msg'><b>AskDoc:</b> 🧠 Thinking...</div>`;

    try {
      const response = await fetch("/ask", {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      chatLog.lastElementChild.innerHTML = `<b>AskDoc:</b> ${data.response}`;
      fetchChatLog();
    } catch (err) {
      chatLog.lastElementChild.innerHTML = `<b>AskDoc:</b> ❌ Failed to get response.`;
    }
  });

  // Voice input handler
  window.startListening = function () {
    if (!("webkitSpeechRecognition" in window)) {
      alert("Voice recognition not supported");
      return;
    }
    const recognition = new webkitSpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = function (event) {
      const transcript = event.results[0][0].transcript;
      document.getElementById("query").value = transcript;
    };
    recognition.onerror = function (event) {
      alert("Voice recognition error: " + event.error);
    };
    recognition.start();
  };

  // Load chat history from server
  async function fetchChatLog() {
    try {
      const res = await fetch("/history");
      const log = await res.json();
      chatLog.innerHTML = "";
      log.forEach((item, i) => {
        chatLog.innerHTML += `<div class='user-msg'><b>You:</b> ${item.q}</div>`;
        chatLog.innerHTML += `<div class='ai-msg'><b>AskDoc:</b> ${item.a}</div>`;
      });
    } catch (e) {
      chatLog.innerHTML = "<div class='ai-msg'>❌ Failed to load chat history.</div>";
    }
  }

  // Trigger download
  window.downloadPDF = function () {
    window.location.href = "/download";
  };

  fetchChatLog(); // Load history on startup
});
