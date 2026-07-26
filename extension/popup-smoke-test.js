const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "popup.js"), "utf8");
const elementIds = [...source.matchAll(/getElementById\("([^"]+)"\)/g)].map((match) => match[1]);

class FakeClassList {
  constructor(initial = []) {
    this.values = new Set(initial);
  }

  add(value) { this.values.add(value); }
  remove(value) { this.values.delete(value); }
  contains(value) { return this.values.has(value); }
  toggle(value, force) {
    const next = force === undefined ? !this.contains(value) : Boolean(force);
    if (next) this.add(value); else this.remove(value);
    return next;
  }
}

function fakeElement(id) {
  const initiallyHidden = new Set(["resultBox", "demoControls", "draftBlock", "contactsList", "toggleCandidatesButton"]);
  return {
    id,
    textContent: "",
    className: "",
    classList: new FakeClassList(initiallyHidden.has(id) ? ["hidden"] : []),
    style: {},
    value: id === "demoScenario" ? "ready" : "",
    placeholder: "",
    disabled: false,
    children: [],
    listeners: {},
    appendChild(child) { this.children.push(child); },
    addEventListener(type, handler) { this.listeners[type] = handler; },
    get childElementCount() { return this.children.length; },
    set innerHTML(_value) { this.children = []; },
    get innerHTML() { return ""; },
  };
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function runPopup({ stateResponse, enrichResult = null, enrichError = null }) {
  const elements = Object.fromEntries(elementIds.map((id) => [id, fakeElement(id)]));
  const messages = [];
  const context = {
    console,
    setTimeout,
    clearTimeout,
    navigator: { clipboard: { writeText: async () => {} } },
    document: {
      getElementById: (id) => elements[id],
      createElement: (tag) => fakeElement(tag),
    },
    chrome: {
      tabs: {
        query: async () => [{ id: 1, url: "https://acme.example/", title: "Acme" }],
        sendMessage: async () => ({
          ok: true,
          pageContext: {
            url: "https://acme.example/",
            title: "Acme",
            entity_name: "Acme",
            page_type: "company_website",
            selected_text: "",
            visible_text: "",
            emails: [],
            phones: [],
          },
        }),
        create: () => {},
      },
      runtime: {
        openOptionsPage: () => {},
        sendMessage: async (message) => {
          messages.push(message);
          if (message.type === "extension:enrich") {
            if (enrichError) {
              return { ok: false, error: enrichError };
            }
            return {
              ok: true,
              payload: { result: enrichResult },
              settings: { backendBaseUrl: "http://127.0.0.1:8095" },
            };
          }
          return stateResponse;
        },
      },
    },
  };
  vm.runInNewContext(source, context, { filename: "popup.js" });
  await settle();
  return { elements, messages, settle };
}

(async () => {
  const offline = await runPopup({
    stateResponse: {
      ok: false,
      error: "Could not reach the review server.",
      recentRecoveries: [{ company: "Acme", review_status: "ready", best_contact: "hello@acme.example" }],
    },
  });
  assert.equal(offline.elements.backendStatus.textContent, "Backend: unavailable");
  assert.equal(offline.elements.statusBox.textContent, "Could not reach the review server.");
  assert.equal(offline.elements.recentList.children.length, 1);

  const readyResult = {
    company: "Acme",
    primary_domain: "acme.example",
    primary_site_url: "https://acme.example/",
    summary: "Acme summary",
    review: { status: "ready", reasons: [], next_step: "Review and send manually" },
    best_contact: { value: "hello@acme.example", contact_type: "email", trust_class: "official", verification_status: "verified" },
    best_verified_email: { value: "hello@acme.example", contact_type: "email", trust_class: "official" },
    verified_contacts: [],
    unverified_candidates: [],
    rejected_noise: [],
    warnings: [],
    detected_context: { page_type: "company_website", title: "Acme", inferred_domain: "acme.example" },
    outreach_opener: { subject: "Hello Acme", opener: "A careful opener." },
  };
  const online = await runPopup({
    stateResponse: {
      ok: true,
      health: { demo_mode: true, demo_batch_summary: { ready: 1 } },
      recentRecoveries: [],
    },
    enrichResult: readyResult,
  });
  assert.equal(online.elements.statusBox.textContent, "Ready to recover.");
  assert.equal(online.elements.demoControls.classList.contains("hidden"), false);
  await online.elements.recoverButton.listeners.click();
  await online.settle();
  assert.equal(online.elements.reviewBadge.textContent, "ready");
  assert.equal(online.elements.statusBox.textContent, "Recovery ready. Review the evidence before outreach.");
  assert.equal(online.elements.resultBox.classList.contains("hidden"), false);
  assert.equal(online.elements.draftSubjectValue.textContent, "Hello Acme");
  assert.equal(online.elements.draftBodyValue.textContent, "A careful opener.");
  assert(online.messages.some((message) => message.payload?.demo_scenario === "ready"));

  const stateResponse = {
    ok: true,
    health: { demo_mode: true, demo_batch_summary: { ready: 1 } },
    recentRecoveries: [],
  };
  for (const [status, statusText] of [
    ["review_required", "Recovery needs human review. Follow the next step below."],
    ["blocked", "Recovery blocked. Do not start outreach."],
  ]) {
    const scenario = await runPopup({
      stateResponse,
      enrichResult: {
        ...readyResult,
        review: { status, reasons: ["Needs review"], next_step: "Review manually" },
        draft: null,
        outreach_opener: null,
      },
    });
    scenario.elements.demoScenario.value = status;
    await scenario.elements.recoverButton.listeners.click();
    await scenario.settle();
    assert.equal(scenario.elements.reviewBadge.textContent, status);
    assert.equal(scenario.elements.statusBox.textContent, statusText);
    assert.equal(scenario.elements.resultBox.classList.contains("hidden"), false);
    assert(scenario.messages.some((message) => message.payload?.demo_scenario === status));
  }

  const failedRetry = await runPopup({ stateResponse, enrichError: "Backend error 500" });
  await failedRetry.elements.recoverButton.listeners.click();
  await failedRetry.settle();
  assert.equal(failedRetry.elements.statusBox.textContent, "Backend error 500");
  assert.equal(failedRetry.elements.resultBox.classList.contains("hidden"), true);

  console.log("EXTENSION_POPUP_SMOKE_OK");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
