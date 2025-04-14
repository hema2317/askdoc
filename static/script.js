document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("askForm");
  const responseBox = document.getElementById("responseBox");

  if (form) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      const query = document.getElementById("query").value;
      const file = document.getElementById("file").files[0];
      const formData = new FormData();
      formData.append("query", query);
      if (file) formData.append("file", file);

      responseBox.innerHTML = "🧠 Thinking...";

      const response = await fetch("/ask", {
        method: "POST",
        body: formData
      });

      const result = await response.json();
      responseBox.innerHTML = `<b>🩺 AskDoc:</b> ${result.response}`;
    });
  }

  // Voice input
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
});
