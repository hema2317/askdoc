document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("askForm");
  const responseBox = document.getElementById("responseBox");

  if (form) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      const query = document.getElementById("query").value.trim();
      const file = document.getElementById("file").files[0];
      const formData = new FormData();

      if (!query && !file) {
        responseBox.innerHTML = "❗Please enter a question or upload a file.";
        return;
      }

      formData.append("query", query);
      if (file) formData.append("file", file);

      responseBox.innerHTML = "🧠 Thinking...";

      try {
        const response = await fetch("/ask", {
          method: "POST",
          body: formData
        });

        const result = await response.json();
        responseBox.innerHTML = `<b>🩺 AskDoc:</b> ${result.response || "No response received."}`;
      } catch (err) {
        responseBox.innerHTML = "❌ Something went wrong. Please try again.";
        console.error("Fetch error:", err);
      }
    });
  }

  // 🎤 Voice input
  window.startListening = function () {
    if (!("webkitSpeechRecognition" in window)) {
      alert("Voice recognition not supported in this browser.");
      return;
    }

    const recognition = new webkitSpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = function (event) {
      const transcript = event.results[0][0].transcript;
      document.getElementById("query").value = transcript;
    };

    recognition.onerror = function (event) {
      alert("Voice error: " + event.error);
    };

    recognition.start();
  };
});
