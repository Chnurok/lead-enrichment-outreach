const NORMALIZED_PAGE_TYPES = new Set([
  "company_website",
  "map_listing",
  "directory_listing",
  "google_results",
  "linkedin_company",
  "unknown"
]);

function hostMatches(hostname, domain) {
  return hostname === domain || hostname.endsWith(`.${domain}`);
}

function detectPageType(rawUrl) {
  let url;
  try {
    url = new URL(rawUrl);
  } catch (_error) {
    return "unknown";
  }
  if (!['http:', 'https:'].includes(url.protocol)) {
    return "unknown";
  }

  const host = url.hostname.toLowerCase().replace(/^www\./, "");
  const path = url.pathname.toLowerCase();
  if (!host || !host.includes(".")) {
    return "unknown";
  }

  if (hostMatches(host, "linkedin.com")) {
    return /^\/(company|showcase|school)(\/|$)/.test(path)
      ? "linkedin_company"
      : "directory_listing";
  }

  if (hostMatches(host, "google.com") || /^google\.[a-z.]+$/.test(host)) {
    if (host.startsWith("maps.") || path.startsWith("/maps")) {
      return "map_listing";
    }
    if (path === "/search" || (path === "/" && url.searchParams.has("q"))) {
      return "google_results";
    }
    return "unknown";
  }

  if (hostMatches(host, "2gis.ru") || hostMatches(host, "2gis.com") || hostMatches(host, "maps.app.goo.gl")) {
    return "map_listing";
  }
  if ((hostMatches(host, "yandex.ru") || hostMatches(host, "yandex.com")) && path.startsWith("/maps")) {
    return "map_listing";
  }

  const directoryDomains = [
    "zoon.ru", "yell.ru", "yelp.com", "tripadvisor.com", "yellowpages.com",
    "avito.ru", "facebook.com", "instagram.com", "vk.com", "yandex.ru", "yandex.com"
  ];
  if (directoryDomains.some((domain) => hostMatches(host, domain))) {
    return "directory_listing";
  }
  return "company_website";
}

function collectUnique(matches) {
  return Array.from(new Set((matches || []).filter(Boolean))).slice(0, 10);
}

function collectPageContext() {
  const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
  const visibleText = text.slice(0, 4000);
  const selectedText = String(window.getSelection?.() || "").trim().slice(0, 500);
  const emailMatches = collectUnique(visibleText.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi));
  const phoneMatches = collectUnique(visibleText.match(/(?:\+?\d[\d\s().-]{7,}\d)/g));
  const pageType = detectPageType(window.location.href);
  const heading = document.querySelector("main h1, h1")?.textContent || "";
  const siteName = document.querySelector('meta[property="og:site_name"]')?.content || "";
  const entityName = (
    pageType === "google_results"
      ? ""
      : (pageType === "company_website" ? (siteName || heading) : heading)
  ).replace(/\s+/g, " ").trim().slice(0, 200);
  return {
    url: window.location.href,
    title: document.title || "",
    entity_name: entityName,
    selected_text: selectedText,
    visible_text: visibleText,
    emails: emailMatches,
    phones: phoneMatches,
    page_type: NORMALIZED_PAGE_TYPES.has(pageType) ? pageType : "unknown"
  };
}

if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || message.type !== "extension:collectPageContext") {
      return false;
    }

    sendResponse({
      ok: true,
      pageContext: collectPageContext()
    });
    return false;
  });
}

if (typeof module !== "undefined") {
  module.exports = { collectPageContext, collectUnique, detectPageType, hostMatches, NORMALIZED_PAGE_TYPES };
}
