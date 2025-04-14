document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("askForm");
  const queryInput = document.getElementById("query");
  const chatLog = document.getElementById("chatLog");

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const query = queryInput.value.trim();
    const file = document.getElementById("file").files[0];
    if (!query) return;

    const formData = new FormData();
    formData.append("query", query);
    if (file) formData.append("file", file);

    appendQA("You", query); // Show user question
    queryInput.value = "";

    try {
      const response = await fetch("/ask", {
        method: "POST",
        body: formData
      });
      const data = await response.json();
      appendQA("AskDoc", data.response || "No response");
    } catch {
      appendQA("AskDoc", "❌ Error getting response");
    }

    loadHistory();
  });

  function appendQA(role, text) {
    const div = document.createElement("div");
    div.className = "qa";
    div.innerHTML = `<strong>${role}:</strong> ${text}`;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  async function loadHistory() {
    const res = await fetch("/history");
    const data = await res.json();
    chatLog.innerHTML = "";
    data.forEach(entry => {
      appendQA("You", entry.q);
      appendQA("AskDoc", entry.a);
    });
  }

  window.downloadPDF = () => window.location.href = "/download";

  window.startListening = () => {
    if (!("webkitSpeechRecognition" in window)) {
      alert("Speech not supported");
      return;
    }

    const recognition = new webkitSpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.onresult = e => {
      queryInput.value = e.results[0][0].transcript;
    };
    recognition.onerror = e => alert("Voice error: " + e.error);
    recognition.start();
  };

  loadHistory();
});
