const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const extensionDir = __dirname;
const read = (name) => fs.readFileSync(path.join(extensionDir, name), "utf8");
const manifest = JSON.parse(read("manifest.json"));
const background = read("background.js");
const popupHtml = read("popup.html");
const popupJs = read("popup.js");
const optionsHtml = read("options.html");
const optionsJs = read("options.js");

assert.equal(manifest.manifest_version, 3);
assert.equal(manifest.background.service_worker, "background.js");
assert.deepEqual(manifest.content_scripts[0].matches, ["http://*/*", "https://*/*"]);
assert(manifest.host_permissions.includes("http://127.0.0.1/*"));
assert(manifest.optional_host_permissions.includes("https://*/*"));
assert(background.includes('const DEFAULT_BASE_URL = "http://127.0.0.1:8095"'));
assert(background.includes("/healthz"));
assert(background.includes("/api/extension/enrich"));
assert(optionsJs.includes("chrome.permissions.request"));

function assertElementBindings(script, html, scriptName) {
  const ids = [...script.matchAll(/getElementById\("([^"]+)"\)/g)].map((match) => match[1]);
  for (const id of ids) {
    assert(html.includes(`id="${id}"`), `${scriptName} references missing #${id}`);
  }
}

assertElementBindings(popupJs, popupHtml, "popup.js");
assertElementBindings(optionsJs, optionsHtml, "options.js");
assert(popupHtml.indexOf('id="recentList"') > popupHtml.indexOf('id="resultBox"'));

const { collectPageContext, detectPageType, NORMALIZED_PAGE_TYPES } = require("./content.js");
const pageCases = new Map([
  ["https://acme.example/about", "company_website"],
  ["https://www.google.com/search?q=acme", "google_results"],
  ["https://www.google.com/maps/place/acme", "map_listing"],
  ["https://2gis.ru/moscow/firm/123", "map_listing"],
  ["https://yandex.ru/maps/org/acme/123", "map_listing"],
  ["https://www.linkedin.com/company/acme/", "linkedin_company"],
  ["https://www.linkedin.com/in/person/", "directory_listing"],
  ["https://www.yelp.com/biz/acme", "directory_listing"],
  ["chrome://extensions", "unknown"],
  ["not a url", "unknown"]
]);
for (const [url, expected] of pageCases) {
  const actual = detectPageType(url);
  assert.equal(actual, expected, `${url} should normalize to ${expected}`);
  assert(NORMALIZED_PAGE_TYPES.has(actual));
}

global.window = {
  location: { href: "https://www.google.com/search?q=acme" },
  getSelection: () => "Acme selected lead",
};
global.document = {
  title: "Acme - Google Search",
  body: { innerText: "Contact hello@acme.example or +1 555 010 2000" },
  querySelector: (selector) => selector.includes("h1")
    ? { textContent: "Search Results" }
    : { content: "Google" },
};
const searchContext = collectPageContext();
assert.equal(searchContext.page_type, "google_results");
assert.equal(searchContext.entity_name, "");
assert.equal(searchContext.selected_text, "Acme selected lead");
assert.deepEqual(searchContext.emails, ["hello@acme.example"]);
delete global.window;
delete global.document;

console.log("EXTENSION_STATIC_SMOKE_OK");
