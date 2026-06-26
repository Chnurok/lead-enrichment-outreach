const backendBaseUrl = document.getElementById("backendBaseUrl");
const reviewToken = document.getElementById("reviewToken");
const saveButton = document.getElementById("saveButton");
const testButton = document.getElementById("testButton");
const statusBox = document.getElementById("statusBox");

function setStatus(text, mode = "subtle") {
  statusBox.textContent = text;
  statusBox.className = `status ${mode}`;
}

async function loadSettings() {
  const stored = await chrome.storage.local.get(["backendBaseUrl", "reviewToken"]);
  backendBaseUrl.value = stored.backendBaseUrl || "http://127.0.0.1:8095";
  reviewToken.value = stored.reviewToken || "";
}

saveButton.addEventListener("click", async () => {
  await chrome.storage.local.set({
    backendBaseUrl: backendBaseUrl.value.trim() || "http://127.0.0.1:8095",
    reviewToken: reviewToken.value.trim()
  });
  setStatus("Saved.", "ok");
});

testButton.addEventListener("click", async () => {
  const baseUrl = backendBaseUrl.value.trim() || "http://127.0.0.1:8095";
  const token = reviewToken.value.trim();
  const headers = {};
  if (token) {
    headers["X-Review-Token"] = token;
  }
  try {
    setStatus("Checking backend…");
    const response = await fetch(`${baseUrl.replace(/\/+$/, "")}/healthz`, { headers });
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok || payload?.ok === false) {
      if (response.status === 401 || response.status === 403) {
        throw new Error("Token rejected. Check the Review token value.");
      }
      throw new Error(payload?.error || `Backend error ${response.status}`);
    }
    setStatus(`Backend ok. Ready leads: ${payload?.demo_batch_summary?.ready ?? "n/a"}`, "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
  }
});

loadSettings().catch((error) => {
  setStatus(error.message || String(error), "error");
});
