const DEFAULT_BASE_URL = "http://127.0.0.1:8095";
const DEFAULT_REVIEW_TOKEN = "";
const MAX_RECENT_RECOVERIES = 8;

function normalizeBaseUrl(value) {
  const candidate = String(value || DEFAULT_BASE_URL).trim() || DEFAULT_BASE_URL;
  let parsed;
  try {
    parsed = new URL(candidate);
  } catch (_error) {
    throw new Error("Backend URL must be a valid http:// or https:// URL.");
  }
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error("Backend URL must use http:// or https:// and must not contain credentials.");
  }
  return parsed.href.replace(/\/+$/, "");
}

async function getSettings() {
  const stored = await chrome.storage.local.get(["backendBaseUrl", "reviewToken"]);
  return {
    backendBaseUrl: normalizeBaseUrl(stored.backendBaseUrl),
    reviewToken: (stored.reviewToken || DEFAULT_REVIEW_TOKEN).trim()
  };
}

async function getRecentRecoveries() {
  const stored = await chrome.storage.local.get(["recentRecoveries"]);
  return Array.isArray(stored.recentRecoveries) ? stored.recentRecoveries : [];
}

async function saveRecentRecovery(result, pageContext) {
  const recent = await getRecentRecoveries();
  const entry = {
    company: result.company || "Untitled company",
    primary_domain: result.primary_domain || null,
    primary_site_url: result.primary_site_url || null,
    best_contact: result.best_contact?.value || null,
    best_contact_type: result.best_contact?.contact_type || null,
    review_status: result.review?.status || "unknown",
    summary: result.summary || "",
    source_url: pageContext?.url || null,
    saved_at: new Date().toISOString()
  };
  const deduped = [entry, ...recent.filter((item) => {
    return !(item.company === entry.company && item.source_url === entry.source_url);
  })];
  await chrome.storage.local.set({ recentRecoveries: deduped.slice(0, MAX_RECENT_RECOVERIES) });
}

async function fetchJson(url, options = {}, timeoutMs = 15000) {
  let response;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    response = await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error("The review server timed out.");
    }
    throw new Error("Could not reach the review server.");
  } finally {
    clearTimeout(timer);
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }
  if (!response.ok || payload?.ok === false) {
    if (response.status === 401 || response.status === 403) {
      throw new Error("Backend rejected the request. Check the review token in Settings.");
    }
    throw new Error(payload?.error || `Backend error ${response.status}`);
  }
  return payload;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message) {
    return false;
  }

  if (message.type === "extension:getState") {
    (async () => {
      try {
        const settings = await getSettings();
        const recentRecoveries = await getRecentRecoveries();
        const headers = {};
        if (settings.reviewToken) {
          headers["X-Review-Token"] = settings.reviewToken;
        }
        const health = await fetchJson(`${settings.backendBaseUrl}/healthz`, { headers }, 8000);
        sendResponse({ ok: true, settings, recentRecoveries, health });
      } catch (error) {
        const stored = await chrome.storage.local.get(["backendBaseUrl", "reviewToken", "recentRecoveries"]);
        sendResponse({
          ok: false,
          error: error.message || String(error),
          settings: {
            backendBaseUrl: stored.backendBaseUrl || DEFAULT_BASE_URL,
            reviewToken: stored.reviewToken || DEFAULT_REVIEW_TOKEN
          },
          recentRecoveries: Array.isArray(stored.recentRecoveries) ? stored.recentRecoveries : []
        });
      }
    })();
    return true;
  }

  if (message.type === "extension:testBackend") {
    (async () => {
      try {
        const settings = {
          backendBaseUrl: normalizeBaseUrl(message.backendBaseUrl),
          reviewToken: String(message.reviewToken || DEFAULT_REVIEW_TOKEN).trim()
        };
        const headers = {};
        if (settings.reviewToken) {
          headers["X-Review-Token"] = settings.reviewToken;
        }
        const health = await fetchJson(`${settings.backendBaseUrl}/healthz`, { headers }, 8000);
        sendResponse({ ok: true, settings, health });
      } catch (error) {
        sendResponse({ ok: false, error: error.message || String(error) });
      }
    })();
    return true;
  }

  if (message.type === "extension:enrich") {
    (async () => {
      try {
        const settings = await getSettings();
        const headers = {
          "Content-Type": "application/json"
        };
        if (settings.reviewToken) {
          headers["X-Review-Token"] = settings.reviewToken;
        }
        const payload = await fetchJson(`${settings.backendBaseUrl}/api/extension/enrich`, {
          method: "POST",
          headers,
          body: JSON.stringify(message.payload || {})
        }, 60000);
        if (!payload?.result || typeof payload.result !== "object") {
          throw new Error("Backend returned an invalid extension result.");
        }
        await saveRecentRecovery(payload.result, message.payload?.page_context || null);
        sendResponse({ ok: true, payload, settings });
      } catch (error) {
        sendResponse({ ok: false, error: error.message || String(error) });
      }
    })();
    return true;
  }

  return false;
});
