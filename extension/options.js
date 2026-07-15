const DEFAULT_BASE_URL = "http://127.0.0.1:8095";
const DEFAULT_REVIEW_TOKEN = "";

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
  backendBaseUrl.value = stored.backendBaseUrl || DEFAULT_BASE_URL;
  reviewToken.value = stored.reviewToken || DEFAULT_REVIEW_TOKEN;
}

saveButton.addEventListener("click", async () => {
  await chrome.storage.local.set({
    backendBaseUrl: backendBaseUrl.value.trim() || DEFAULT_BASE_URL,
    reviewToken: reviewToken.value.trim() || DEFAULT_REVIEW_TOKEN
  });
  setStatus("Saved.", "ok");
});

testButton.addEventListener("click", async () => {
  const baseUrl = backendBaseUrl.value.trim() || DEFAULT_BASE_URL;
  const token = reviewToken.value.trim() || DEFAULT_REVIEW_TOKEN;
  try {
    setStatus("Checking backend…");
    const response = await chrome.runtime.sendMessage({
      type: "extension:testBackend",
      backendBaseUrl: baseUrl,
      reviewToken: token
    });
    if (!response?.ok) {
      throw new Error(response?.error || "Backend check failed");
    }
    setStatus(`Backend ok. Ready leads: ${response?.health?.demo_batch_summary?.ready ?? "n/a"}`, "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
  }
});

loadSettings().catch((error) => {
  setStatus(error.message || String(error), "error");
});
