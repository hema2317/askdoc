document.getElementById('askForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(document.getElementById('askForm'));

  const response = await fetch('/ask', {
    method: 'POST',
    body: formData
  });
  const data = await response.json();
  document.getElementById('response').innerText = data.response;
});

function startListening() {
  const recognition = new webkitSpeechRecognition() || new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.start();
  recognition.onresult = function(event) {
    document.getElementById('query').value = event.results[0][0].transcript;
  };
}
