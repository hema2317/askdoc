// static/script.js

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("askForm");
  const chatLog = document.getElementById("chatLog");
  const queryInput = document.getElementById("query");

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const query = queryInput.value.trim();
    const file = document.getElementById("file").files[0];

    if (!query) return;

    addMessage("user", query);
    queryInput.value = "";

    const formData = new FormData();
    formData.append("query", query);
    if (file) formData.append("file", file);

    addMessage("ai", "🧠 Thinking...");

    try {
      const response = await fetch("/ask", {
        method: "POST",
        body: formData
      });
      const data = await response.json();
      updateLastMessage("ai", data.response);
      fetchChatLog();
    } catch (err) {
      updateLastMessage("ai", "❌ Failed to get a response.");
    }
  });

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
      queryInput.value = transcript;
    };

    recognition.onerror = function (event) {
      alert("Voice recognition error: " + event.error);
    };

    recognition.start();
  };

  function addMessage(role, text) {
    const bubble = document.createElement("div");
    bubble.className = `bubble ${role}`;
    bubble.innerHTML = `<b>${role === "user" ? "You" : "AskDoc"}:</b> ${text}`;
    chatLog.appendChild(bubble);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function updateLastMessage(role, newText) {
    const bubbles = chatLog.querySelectorAll(`.bubble.${role}`);
    const lastBubble = bubbles[bubbles.length - 1];
    if (lastBubble) lastBubble.innerHTML = `<b>${role === "user" ? "You" : "AskDoc"}:</b> ${newText}`;
  }

  async function fetchChatLog() {
    try {
      const res = await fetch("/history");
      const log = await res.json();
      chatLog.innerHTML = "";
      log.forEach(item => {
        addMessage("user", item.q);
        addMessage("ai", item.a);
      });
    } catch (e) {
      console.error("Failed to load chat history");
    }
  }

  window.downloadPDF = function () {
    window.location.href = "/download";
  };

  fetchChatLog();
});
