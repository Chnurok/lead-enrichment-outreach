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

function normalizeBaseUrl(value) {
  const candidate = value.trim() || DEFAULT_BASE_URL;
  const parsed = new URL(candidate);
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error("Use an http:// or https:// backend URL without embedded credentials.");
  }
  return parsed.href.replace(/\/+$/, "");
}

async function ensureBackendPermission(baseUrl) {
  const parsed = new URL(baseUrl);
  const originPattern = `${parsed.protocol}//${parsed.hostname}/*`;
  const granted = await chrome.permissions.contains({ origins: [originPattern] });
  if (granted) {
    return;
  }
  const approved = await chrome.permissions.request({ origins: [originPattern] });
  if (!approved) {
    throw new Error("Backend access was not granted. Allow this origin to save or test it.");
  }
}

async function loadSettings() {
  const stored = await chrome.storage.local.get(["backendBaseUrl", "reviewToken"]);
  backendBaseUrl.value = stored.backendBaseUrl || DEFAULT_BASE_URL;
  reviewToken.value = stored.reviewToken || DEFAULT_REVIEW_TOKEN;
}

saveButton.addEventListener("click", async () => {
  try {
    const baseUrl = normalizeBaseUrl(backendBaseUrl.value);
    await ensureBackendPermission(baseUrl);
    await chrome.storage.local.set({
      backendBaseUrl: baseUrl,
      reviewToken: reviewToken.value.trim() || DEFAULT_REVIEW_TOKEN
    });
    backendBaseUrl.value = baseUrl;
    setStatus("Settings saved.", "ok");
  } catch (error) {
    setStatus(error.message || String(error), "error");
  }
});

testButton.addEventListener("click", async () => {
  let baseUrl;
  const token = reviewToken.value.trim() || DEFAULT_REVIEW_TOKEN;
  try {
    baseUrl = normalizeBaseUrl(backendBaseUrl.value);
    await ensureBackendPermission(baseUrl);
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
