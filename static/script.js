async function predictRisk() {
  const question = document.getElementById("question").value;
  const file = document.getElementById("file").files[0];
  const responseBox = document.getElementById("responseBox");
  responseBox.innerText = "⏳ Thinking...";

  const formData = new FormData();
  formData.append("question", question);
  if (file) formData.append("file", file);

  try {
    const response = await fetch("/ask", {
      method: "POST",
      body: formData
    });

    const data = await response.json();
    responseBox.innerHTML = `🧠 ${data.response}`;
  } catch (err) {
    responseBox.innerText = "❌ Something went wrong. Try again.";
  }
}

function startVoiceInput() {
  const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
  recognition.lang = "en-US";
  recognition.start();
  recognition.onresult = function (event) {
    document.getElementById("question").value = event.results[0][0].transcript;
  };
}
