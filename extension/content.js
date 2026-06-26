function detectPageType(hostname) {
  const host = (hostname || "").toLowerCase();
  if (host.includes("linkedin.")) {
    return "linkedin_company";
  }
  if (host.includes("google.")) {
    return "google_results";
  }
  if (host.includes("2gis")) {
    return "map_listing";
  }
  if (host.includes("zoon") || host.includes("yell") || host.includes("tripadvisor") || host.includes("yandex")) {
    return "directory_listing";
  }
  if (!host) {
    return "unknown";
  }
  return "company_website";
}

function collectUnique(matches) {
  return Array.from(new Set((matches || []).filter(Boolean))).slice(0, 10);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "extension:collectPageContext") {
    return false;
  }

  const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
  const visibleText = text.slice(0, 4000);
  const selectedText = String(window.getSelection?.() || "").trim();
  const emailMatches = collectUnique(visibleText.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi));
  const phoneMatches = collectUnique(visibleText.match(/(?:\+?\d[\d\s().-]{7,}\d)/g));

  sendResponse({
    ok: true,
    pageContext: {
      url: window.location.href,
      title: document.title || "",
      selected_text: selectedText,
      visible_text: visibleText,
      emails: emailMatches,
      phones: phoneMatches,
      page_type: detectPageType(window.location.hostname)
    }
  });
  return false;
});
