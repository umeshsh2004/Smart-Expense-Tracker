(function () {
  const btn = document.getElementById("voiceBtn");
  const status = document.getElementById("voiceStatus");
  if (!btn || !("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
    if (btn) btn.disabled = true;
    if (status) status.textContent = "Voice input not supported in this browser.";
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new SpeechRecognition();
  rec.lang = "en-IN";
  rec.interimResults = false;

  btn.addEventListener("click", () => {
    status.textContent = "Listening...";
    rec.start();
  });

  rec.onresult = (event) => {
    const text = event.results[0][0].transcript;
    status.textContent = `Heard: "${text}"`;
    parseVoice(text);
  };

  rec.onerror = () => {
    status.textContent = "Could not capture voice. Try again.";
  };

  function parseVoice(text) {
    const lower = text.toLowerCase();
    const amountMatch = lower.match(/(\d+(?:\.\d+)?)/);
    if (amountMatch) {
      document.getElementById("amount").value = amountMatch[1];
    }
    if (lower.includes("yesterday")) {
      const d = new Date();
      d.setDate(d.getDate() - 1);
      document.getElementById("date").value = d.toISOString().slice(0, 10);
    }
    const desc = text
      .replace(/spent|rupees|rs|on|for|yesterday|today/gi, "")
      .replace(amountMatch ? amountMatch[0] : "", "")
      .trim();
    if (desc) document.getElementById("description").value = desc.slice(0, 120);
  }
})();
