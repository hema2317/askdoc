// 🎤 Voice to Text
function startListening() {
  if (!('webkitSpeechRecognition' in window)) {
    alert("Your browser doesn't support speech recognition");
    return;
  }

  const recognition = new webkitSpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = false;

  recognition.onresult = function(event) {
    const transcript = event.results[0][0].transcript;
    document.getElementById('query').value = transcript;
  };

  recognition.onerror = function() {
    alert("Voice input failed. Try again.");
  };

  recognition.start();
}

// 📨 Handle form submission
document.getElementById('askForm').addEventListener('submit', async function(event) {
  event.preventDefault();

  const query = document.getElementById('query').value.trim();
  const file = document.getElementById('file').files[0];
  const responseBox = document.getElementById('responseBox');
  responseBox.innerHTML = "⏳ Processing...";

  if (!query && !file) {
    responseBox.innerHTML = "❌ Please enter a question or upload a file.";
    return;
  }

  const formData = new FormData();
  formData.append('query', query);
  if (file) formData.append('file', file);

  try {
    const res = await fetch("/ask", {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    responseBox.innerHTML = `🧠 <strong>AskDoc:</strong> ${data.response}`;
  } catch (error) {
    console.error("Error:", error);
    responseBox.innerHTML = "❌ Something went wrong. Please try again.";
  }
});
