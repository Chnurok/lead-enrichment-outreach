const contextLine = document.getElementById("contextLine");
const companyInput = document.getElementById("companyInput");
const recoverButton = document.getElementById("recoverButton");
const optionsButton = document.getElementById("optionsButton");
const statusBox = document.getElementById("statusBox");
const resultBox = document.getElementById("resultBox");
const companyName = document.getElementById("companyName");
const resultSubline = document.getElementById("resultSubline");
const reviewBadge = document.getElementById("reviewBadge");
const summaryText = document.getElementById("summaryText");
const nextStepValue = document.getElementById("nextStepValue");
const reviewReasonMeta = document.getElementById("reviewReasonMeta");
const contextDomainValue = document.getElementById("contextDomainValue");
const contextMeta = document.getElementById("contextMeta");
const bestContactValue = document.getElementById("bestContactValue");
const bestContactMeta = document.getElementById("bestContactMeta");
const bestEmailValue = document.getElementById("bestEmailValue");
const bestEmailMeta = document.getElementById("bestEmailMeta");
const domainValue = document.getElementById("domainValue");
const confidenceMeta = document.getElementById("confidenceMeta");
const entityConfidenceValue = document.getElementById("entityConfidenceValue");
const contactConfidenceValue = document.getElementById("contactConfidenceValue");
const siteConfidenceValue = document.getElementById("siteConfidenceValue");
const contactsList = document.getElementById("contactsList");
const toggleCandidatesButton = document.getElementById("toggleCandidatesButton");
const verifiedList = document.getElementById("verifiedList");
const rejectedList = document.getElementById("rejectedList");
const warningsList = document.getElementById("warningsList");
const draftBlock = document.getElementById("draftBlock");
const draftSubjectValue = document.getElementById("draftSubjectValue");
const draftBodyValue = document.getElementById("draftBodyValue");
const recentList = document.getElementById("recentList");
const contactsCount = document.getElementById("contactsCount");
const verifiedCount = document.getElementById("verifiedCount");
const rejectedCount = document.getElementById("rejectedCount");
const warningsCount = document.getElementById("warningsCount");
const copyBestButton = document.getElementById("copyBestButton");
const copyBestEmailButton = document.getElementById("copyBestEmailButton");
const openBestButton = document.getElementById("openBestButton");
const openSiteButton = document.getElementById("openSiteButton");
const copySummaryButton = document.getElementById("copySummaryButton");
const copyDraftSubjectButton = document.getElementById("copyDraftSubjectButton");
const copyDraftBodyButton = document.getElementById("copyDraftBodyButton");
const backendStatus = document.getElementById("backendStatus");
const usageHint = document.getElementById("usageHint");
const usageCount = document.getElementById("usageCount");
const pageTypeValue = document.getElementById("pageTypeValue");

let currentPageContext = null;
let currentResult = null;
let currentTab = null;
let isRecovering = false;
let candidatesExpanded = false;

function setStatus(text, isError = false) {
  statusBox.textContent = text;
  statusBox.style.color = isError ? "#8b1e1e" : "";
}

function setBackendStatus(text, mode = "subtle") {
  backendStatus.textContent = text;
  backendStatus.className = `pill ${mode}`;
}

function setRecoveringState(nextValue) {
  isRecovering = nextValue;
  recoverButton.disabled = nextValue;
  optionsButton.disabled = nextValue;
  recoverButton.textContent = nextValue ? "Recovering…" : "Recover contact";
}

function renderList(node, items, emptyText) {
  node.innerHTML = "";
  if (!items || !items.length) {
    const li = document.createElement("li");
    li.textContent = emptyText;
    node.appendChild(li);
    return;
  }
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    node.appendChild(li);
  });
}

function formatVerificationItem(item) {
  const parts = [];
  if (item.value) {
    parts.push(item.value);
  }
  const meta = [item.contact_type, item.trust_class].filter(Boolean).join(" · ");
  if (meta) {
    parts.push(meta);
  }
  if (item.why_verified?.length) {
    parts.push(item.why_verified.join(", "));
  } else if (item.reasons?.length) {
    parts.push(item.reasons.join(", "));
  }
  return parts.join(" — ");
}

function renderRecent(recentRecoveries) {
  usageHint.textContent = "Recent recoveries";
  usageCount.textContent = String(recentRecoveries.length);
  recentList.innerHTML = "";
  if (!recentRecoveries.length) {
    const li = document.createElement("li");
    li.textContent = "No recent recoveries yet.";
    recentList.appendChild(li);
    return;
  }
  recentRecoveries.forEach((item) => {
    const li = document.createElement("li");
    const bits = [item.company];
    if (item.review_status) {
      bits.push(item.review_status);
    }
    if (item.best_contact) {
      bits.push(item.best_contact);
    }
    li.textContent = bits.join(" · ");
    recentList.appendChild(li);
  });
}

function renderResult(result) {
  currentResult = result;
  const verified = result.verified_contacts || [];
  const unverified = result.unverified_candidates || [];
  const rejected = result.rejected_noise || [];
  const warnings = result.warnings || [];
  const reviewReasons = result.review?.reasons || [];
  const detectedContext = result.detected_context || {};
  const draft = result.draft || null;
  resultBox.classList.remove("hidden");
  companyName.textContent = result.company || "Untitled company";
  resultSubline.textContent = result.primary_domain || result.detected_context?.url || "Recovered from the current page context.";
  reviewBadge.textContent = result.review?.status || "unknown";
  reviewBadge.className = `badge ${result.review?.status || ""}`;
  summaryText.textContent = result.summary || "No summary yet.";
  nextStepValue.textContent = result.review?.next_step || "Review manually";
  reviewReasonMeta.textContent = reviewReasons.length ? reviewReasons.join(" · ") : "No blocking reasons.";
  contextDomainValue.textContent = detectedContext.inferred_domain || detectedContext.provided_domain || "No domain inferred";
  contextMeta.textContent = [detectedContext.page_type, detectedContext.title].filter(Boolean).join(" · ");
  if (result.best_contact?.value) {
    bestContactValue.textContent = result.best_contact.value;
    bestContactMeta.textContent = [result.best_contact?.contact_type, result.best_contact?.trust_class].filter(Boolean).join(" · ");
  } else {
    bestContactValue.textContent = "No verified direct contact";
    bestContactMeta.textContent = "Only unverified candidates or rejected noise were found.";
  }
  if (result.best_verified_email?.value) {
    bestEmailValue.textContent = result.best_verified_email.value;
    bestEmailMeta.textContent = [result.best_verified_email?.contact_type, result.best_verified_email?.trust_class].filter(Boolean).join(" · ");
  } else {
    bestEmailValue.textContent = "No verified email";
    bestEmailMeta.textContent = "No email passed verification.";
  }
  domainValue.textContent = result.primary_domain || "No official domain";
  confidenceMeta.textContent = `entity ${result.entity_confidence ?? "n/a"} · contact ${result.contact_confidence ?? "n/a"}`;
  entityConfidenceValue.textContent = String(result.entity_confidence ?? "n/a");
  contactConfidenceValue.textContent = String(result.contact_confidence ?? "n/a");
  siteConfidenceValue.textContent = String(result.official_site_confidence ?? "n/a");
  verifiedCount.textContent = String(verified.length);
  contactsCount.textContent = String(unverified.length);
  rejectedCount.textContent = String(rejected.length);
  warningsCount.textContent = String(warnings.length);
  renderList(verifiedList, verified.map(formatVerificationItem), "No verified contacts.");
  renderList(contactsList, unverified.map(formatVerificationItem), "No unverified candidates.");
  candidatesExpanded = false;
  contactsList.classList.toggle("hidden", !unverified.length || !candidatesExpanded);
  toggleCandidatesButton.classList.toggle("hidden", !unverified.length);
  toggleCandidatesButton.textContent = unverified.length ? `Show candidates (${unverified.length})` : "Show candidates";
  renderList(rejectedList, rejected.map(formatVerificationItem), "No rejected noise.");
  renderList(warningsList, warnings, "No warnings.");
  if (draft && (draft.subject || draft.body)) {
    draftBlock.classList.remove("hidden");
    draftSubjectValue.textContent = draft.subject || "No subject line";
    draftBodyValue.textContent = draft.body || "No draft body";
  } else {
    draftBlock.classList.add("hidden");
    draftSubjectValue.textContent = "—";
    draftBodyValue.textContent = "—";
  }
}

async function getCurrentTab() {
  if (currentTab) {
    return currentTab;
  }
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTab = tabs[0];
  return currentTab;
}

function buildFallbackContext(tab) {
  return {
    url: tab?.url || "",
    title: tab?.title || "",
    selected_text: "",
    visible_text: "",
    emails: [],
    phones: [],
    page_type: "unknown"
  };
}

async function collectContext() {
  const tab = await getCurrentTab();
  if (!tab?.id) {
    throw new Error("No active tab");
  }
  try {
    const response = await chrome.tabs.sendMessage(tab.id, { type: "extension:collectPageContext" });
    if (!response?.ok) {
      throw new Error("Could not read the current page.");
    }
    currentPageContext = response.pageContext;
  } catch (_error) {
    currentPageContext = buildFallbackContext(tab);
    setStatus("Using basic tab context only. This page blocks deeper content inspection.");
  }
  contextLine.textContent = `${currentPageContext.page_type || "unknown"} · ${currentPageContext.title || currentPageContext.url}`;
  pageTypeValue.textContent = currentPageContext.page_type || "unknown";
}

async function refreshState() {
  const response = await chrome.runtime.sendMessage({ type: "extension:getState" });
  if (!response?.ok) {
    setBackendStatus("Backend: unavailable", "error");
    setStatus(response?.error || "Review server is unavailable. Open Settings to verify the backend URL and review token.", true);
    renderRecent([]);
    return;
  }
  const health = response.health || {};
  const summary = health.demo_batch_summary || {};
  setBackendStatus(`Backend: ok · ready ${summary.ready ?? "n/a"}`, "ok");
  renderRecent(response.recentRecoveries || []);
}

async function recoverContact() {
  if (!currentPageContext) {
    await collectContext();
  }
  setRecoveringState(true);
  setStatus("Recovering the best contact path…");
  const payload = {
    company: companyInput.value.trim() || undefined,
    page_context: currentPageContext,
    allow_review_required: true,
    fast_mode: true
  };
  try {
    const response = await chrome.runtime.sendMessage({ type: "extension:enrich", payload });
    if (!response?.ok) {
      throw new Error(response?.error || "Unknown backend error.");
    }
    renderResult(response.payload.result);
    setStatus(`Done via ${response.settings.backendBaseUrl}`);
    await refreshState();
  } finally {
    setRecoveringState(false);
  }
}

async function copyText(value, successText) {
  if (!value) {
    return;
  }
  await navigator.clipboard.writeText(value);
  setStatus(successText);
}

function openUrl(url) {
  if (!url) {
    return;
  }
  chrome.tabs.create({ url });
}

function openBestContact() {
  const best = currentResult?.best_contact?.value;
  if (!best) {
    return;
  }
  if (best.includes("@")) {
    openUrl(`mailto:${best}`);
    return;
  }
  if (/^\+?[\d\s().-]+$/.test(best)) {
    openUrl(`tel:${best.replace(/\s+/g, "")}`);
    return;
  }
  if (/^https?:\/\//.test(best)) {
    openUrl(best);
  }
}

function openPrimarySite() {
  const site = currentResult?.primary_site_url || (currentResult?.primary_domain ? `https://${currentResult.primary_domain}` : null);
  openUrl(site);
}

recoverButton.addEventListener("click", async () => {
  try {
    await recoverContact();
  } catch (error) {
    setStatus(error.message || String(error), true);
  }
});

optionsButton.addEventListener("click", () => chrome.runtime.openOptionsPage());
copyBestButton.addEventListener("click", () => copyText(currentResult?.best_contact?.value, "Best contact copied."));
copyBestEmailButton.addEventListener("click", () => copyText(currentResult?.best_verified_email?.value, "Best email copied."));
copySummaryButton.addEventListener("click", () => copyText(currentResult?.summary, "Summary copied."));
copyDraftSubjectButton.addEventListener("click", () => copyText(currentResult?.draft?.subject, "Draft subject copied."));
copyDraftBodyButton.addEventListener("click", () => copyText(currentResult?.draft?.body, "Draft body copied."));
openBestButton.addEventListener("click", openBestContact);
openSiteButton.addEventListener("click", openPrimarySite);
toggleCandidatesButton.addEventListener("click", () => {
  candidatesExpanded = !candidatesExpanded;
  contactsList.classList.toggle("hidden", !candidatesExpanded);
  toggleCandidatesButton.textContent = candidatesExpanded
    ? "Hide candidates"
    : `Show candidates (${currentResult?.unverified_candidates?.length || 0})`;
});

Promise.all([
  collectContext(),
  refreshState()
]).then(() => {
  if (!isRecovering) {
    setStatus("Ready to recover.");
  }
}).catch((error) => setStatus(error.message || String(error), true));
