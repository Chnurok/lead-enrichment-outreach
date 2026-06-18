#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from html.parser import HTMLParser
from functools import lru_cache
from urllib.parse import unquote

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
SEARCH_URL = "https://html.duckduckgo.com/html/?q={query}"
SEARCH_URL_DDG_LITE = "https://lite.duckduckgo.com/lite/?q={query}"
SEARCH_URL_BING = "https://www.bing.com/search?q={query}"
TIMEOUT = 12
BROWSER_TIMEOUT = 20
MAX_CONTACT_FETCH = 3
FETCH_RETRIES = 2
MAX_SEARCH_RESULTS_PER_SOURCE = 5
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
ADDRESS_RE = re.compile(r"\b\d{1,5}[\w\s,./-]{8,}(?:street|st\.|road|rd\.|avenue|ave\.|boulevard|blvd\.|platz|allee|lane|ln\.|drive|dr\.|floor|suite)\b", re.I)
EMAIL_JUNK_PATTERNS = (
    "u003e",
    "u003c",
    "example.com",
)
PHONE_MIN_DIGITS = 10
PHONE_MAX_DIGITS = 15
SOCIAL_RE = re.compile(r"(linkedin\.com|facebook\.com|instagram\.com|t\.me|telegram\.me|vk\.com|youtube\.com)", re.I)
BAD_HOST_HINTS = ("yandex.ru", "2gis.ru", "zoon.ru", "yellowpages", "facebook.com", "instagram.com", "linkedin.com", "wikipedia.org")
CONTACT_HINTS = ("contact", "contacts", "about", "team", "company", "support")
WEAK_CONTACT_LOCALPARTS = (
    "press", "privacy", "legal", "abuse", "noreply", "no-reply", "careers", "jobs", "career",
    "hr", "admin", "webmaster", "postmaster"
)
STRONG_CONTACT_LOCALPARTS = (
    "sales", "hello", "contact", "info", "business", "partnership", "partnerships", "founder",
    "ceo", "owner", "director", "manager", "office", "team", "support"
)
JUNK_SUMMARY_PATTERNS = (
    r"enable javascript[^.?!]*[.?!]?",
    r"cookie[s]?[^.?!]*[.?!]?",
    r"accept all[^.?!]*[.?!]?",
    r"privacy policy[^.?!]*[.?!]?",
    r"all rights reserved[^.?!]*[.?!]?",
    r"sign in[^.?!]*[.?!]?",
)
JS_ONLY_PATTERNS = (
    "enable javascript",
    "javascript is disabled",
    "please turn javascript on",
    "requires javascript",
)
BROWSER_BINARIES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.title = []
        self._in_title = False
        self.json_ld_blocks = []
        self._capture_json_ld = False
        self._json_ld_buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and (attrs.get("type") or "").lower() == "application/ld+json":
            self._capture_json_ld = True
            self._json_ld_buffer = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._capture_json_ld:
            block = "".join(self._json_ld_buffer).strip()
            if block:
                self.json_ld_blocks.append(block)
            self._capture_json_ld = False
            self._json_ld_buffer = []

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        if self._capture_json_ld:
            self._json_ld_buffer.append(data)


def dedupe(items):
    return list(OrderedDict((item, None) for item in items if item))


def dedupe_records(records, key_fields):
    seen = OrderedDict()
    for record in records:
        if not record:
            continue
        key = tuple(record.get(field) for field in key_fields)
        if key not in seen:
            seen[key] = record
    return list(seen.values())


def unwrap_search_result_url(url):
    if not url:
        return url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "" and parsed.netloc == "" and url.startswith("//"):
        parsed = urllib.parse.urlparse(f"https:{url}")
    host = parsed.netloc.lower().removeprefix("www.")
    if host.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
        if target:
            return urllib.parse.unquote(target)
    return url


def domain_of(url):
    try:
        normalized = unwrap_search_result_url(url)
        parsed = urllib.parse.urlparse(normalized)
        netloc = parsed.netloc.lower()
        return netloc.removeprefix("www.")
    except Exception:
        return ""


def clean_text(text):
    text = html.unescape(text or "")
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch(url):
    last_error = None
    for attempt in range(FETCH_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                return resp.read(350000).decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = exc
            if attempt >= FETCH_RETRIES:
                raise
            time.sleep(0.15 * (attempt + 1))
    raise last_error


@lru_cache(maxsize=256)
def cached_fetch(url):
    return fetch(url)


def find_browser_binary():
    configured = os.getenv("LEAD_ENRICH_BROWSER_BIN")
    if configured:
        return configured
    for candidate in BROWSER_BINARIES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def render_page_with_browser(url):
    browser = find_browser_binary()
    if not browser:
        return None, "no headless browser binary available"
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--dump-dom",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=BROWSER_TIMEOUT,
            check=False,
        )
    except Exception as exc:
        return None, f"browser fallback failed: {exc}"
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or f"browser exited {proc.returncode}"
        return None, f"browser fallback failed: {message[:200]}"
    rendered = proc.stdout or ""
    if not rendered.strip():
        return None, "browser fallback returned empty DOM"
    return rendered, None


def build_queries(company, region=None, domain=None, mode="smart"):
    if domain:
        return [company]
    base = [company]
    if region:
        base.append(region)
    joined = " ".join(base)
    if mode == "basic":
        return [joined]
    return [
        f"{joined} official site email",
        f"{joined} contacts",
        f"{joined} about company",
    ]


def parse_duckduckgo_html_results(body):
    urls = re.findall(r'nofollow" class="[^\"]*result__a[^\"]*" href="(.*?)"', body)
    if not urls:
        urls = re.findall(r'<a rel="nofollow" class="result__url" href="(.*?)"', body)
    titles = [clean_text(s)[:180] for s in re.findall(r'class="result__a"[^>]*>(.*?)</a>', body, flags=re.S)[:8]]
    snippets = [clean_text(s)[:240] for s in re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', body, flags=re.S)[:8]]
    results = []
    for idx, raw_url in enumerate(urls[:MAX_SEARCH_RESULTS_PER_SOURCE]):
        results.append({
            "source": "duckduckgo_html",
            "rank": idx + 1,
            "url": unwrap_search_result_url(html.unescape(raw_url)),
            "title": titles[idx] if idx < len(titles) else None,
            "snippet": snippets[idx] if idx < len(snippets) else None,
        })
    return results


def parse_duckduckgo_lite_results(body):
    matches = re.findall(r'<a rel="nofollow" href="(.*?)"[^>]*>(.*?)</a>', body, flags=re.S)
    results = []
    for idx, (raw_url, raw_title) in enumerate(matches[:MAX_SEARCH_RESULTS_PER_SOURCE]):
        results.append({
            "source": "duckduckgo_lite",
            "rank": idx + 1,
            "url": unwrap_search_result_url(html.unescape(raw_url)),
            "title": clean_text(raw_title)[:180],
            "snippet": None,
        })
    return results


def parse_bing_results(body):
    blocks = re.findall(r'<li class="b_algo"[\s\S]*?</li>', body, flags=re.S)
    results = []
    for idx, block in enumerate(blocks[:MAX_SEARCH_RESULTS_PER_SOURCE]):
        href_match = re.search(r'<h2><a href="(.*?)"', block)
        if not href_match:
            continue
        title_match = re.search(r'<h2><a [^>]*>(.*?)</a>', block, flags=re.S)
        snippet_match = re.search(r'<p>(.*?)</p>', block, flags=re.S)
        results.append({
            "source": "bing_html",
            "rank": idx + 1,
            "url": html.unescape(href_match.group(1)),
            "title": clean_text(title_match.group(1))[:180] if title_match else None,
            "snippet": clean_text(snippet_match.group(1))[:240] if snippet_match else None,
        })
    return results


def search_query(query):
    encoded = urllib.parse.quote(query)
    search_results = []
    errors = []
    for source_name, url_template, parser in (
        ("duckduckgo_html", SEARCH_URL, parse_duckduckgo_html_results),
        ("duckduckgo_lite", SEARCH_URL_DDG_LITE, parse_duckduckgo_lite_results),
        ("bing_html", SEARCH_URL_BING, parse_bing_results),
    ):
        try:
            body = cached_fetch(url_template.format(query=encoded))
            parsed = parser(body)
            if parsed:
                search_results.extend(parsed)
        except Exception as exc:
            errors.append(f"{source_name}: {exc}")
    return dedupe_records(search_results, ("source", "url")), errors


def score_candidate(url, company, region=None, snippet=None):
    dom = domain_of(url)
    if not dom:
        return -999
    if any(hint in dom for hint in BAD_HOST_HINTS):
        return -50
    score = 0
    cname = re.sub(r"[^a-zа-я0-9]", "", company.lower())
    droot = re.sub(r"[^a-zа-я0-9]", "", dom)
    snippet_text = (snippet or "").lower()
    company_words = [w for w in re.split(r"\W+", company.lower()) if len(w) > 2]
    if cname:
        if cname[:8] and cname[:8] in droot:
            score += 4
        elif droot[:8] and droot[:8] in cname:
            score += 3
    matches = sum(1 for word in company_words[:4] if word in dom or word in snippet_text)
    score += min(3, matches)
    if region and (region.lower() in url.lower() or region.lower() in snippet_text):
        score += 1
    if any(token in url.lower() for token in CONTACT_HINTS):
        score += 0.5
    if dom.endswith(".ru") or dom.endswith(".com") or dom.endswith(".ai"):
        score += 0.5
    return score


def verify_site_identity(url, company, region=None):
    dom = domain_of(url)
    company_words = [w for w in re.split(r"\W+", company.lower()) if len(w) > 2]
    result = {
        "verified": False,
        "score": 0.0,
        "title": None,
        "reason": None,
        "matched_title_terms": [],
        "matched_body_terms": [],
    }
    try:
        parsed, err = parse_page(url, dom)
        if err:
            result["reason"] = err
            return result
    except Exception as e:
        result["reason"] = str(e)
        return result
    title = (parsed.get("title") or "").lower()
    text = (parsed.get("summary_text") or "").lower()
    result["title"] = parsed.get("title")
    score = 0.0
    if any(word in dom for word in company_words):
        score += 1.5
    matched_title_terms = [word for word in company_words[:4] if word in title]
    matched_body_terms = [word for word in company_words[:4] if word in text[:800]]
    score += min(2.0, sum(0.75 for _ in matched_title_terms))
    score += min(2.0, sum(0.5 for _ in matched_body_terms))
    if region and region.lower() in text[:800]:
        score += 0.5
    result["score"] = round(score, 2)
    result["verified"] = score >= 2.0
    result["matched_title_terms"] = matched_title_terms
    result["matched_body_terms"] = matched_body_terms
    if not result["verified"]:
        result["reason"] = "weak company match on candidate site"
    return result


def choose_site(company, region, explicit_domain, search_results):
    warnings = []
    if explicit_domain:
        clean = explicit_domain.lower().removeprefix("www.")
        return {
            "primary_site_url": f"https://{clean}",
            "primary_domain": clean,
            "why_chosen": "Explicit domain provided by input",
            "warnings": warnings,
            "site_verification": None,
            "search_snippets": [item.get("snippet") for item in search_results if item.get("snippet")][:5],
            "site_candidates": [],
            "alternative_candidates": [],
        }

    seen = []
    snippets = [item.get("snippet") for item in search_results if item.get("snippet")]
    for item in search_results:
        url = item.get("url")
        snippet = item.get("snippet") or ""
        title = item.get("title") or ""
        seen.append((score_candidate(url, company, region, f"{title} {snippet}".strip()), item))
    seen.sort(key=lambda item: item[0], reverse=True)
    if not seen or seen[0][0] < 0:
        warnings.append("No strong official website match found")
        return {
            "primary_site_url": None,
            "primary_domain": None,
            "why_chosen": None,
            "warnings": warnings,
            "site_verification": None,
            "search_snippets": snippets[:5],
            "site_candidates": [],
            "alternative_candidates": [],
        }

    top_candidates = seen[:5]
    verified = []
    for base_score, item in top_candidates:
        url = item["url"]
        verification = verify_site_identity(url, company, region)
        combined_score = base_score + verification["score"]
        verified.append({
            "url": url,
            "domain": domain_of(url),
            "source": item.get("source"),
            "rank": item.get("rank"),
            "title": verification.get("title") or item.get("title"),
            "snippet": item.get("snippet"),
            "base_score": round(base_score, 2),
            "verification_score": round(verification.get("score", 0.0), 2),
            "combined_score": round(combined_score, 2),
            "verified": bool(verification.get("verified")),
            "reason": verification.get("reason"),
        })
    verified.sort(key=lambda item: item["combined_score"], reverse=True)
    chosen = verified[0]
    verification = {
        "verified": chosen["verified"],
        "score": chosen["verification_score"],
        "title": chosen["title"],
        "reason": chosen["reason"],
    }
    if not verification["verified"]:
        warnings.append("Official website candidate could not be strongly verified")
    if len(verified) > 1 and abs(verified[0]["combined_score"] - verified[1]["combined_score"]) < 1.0:
        warnings.append("Official website match is ambiguous")
    if chosen["combined_score"] < 1.0:
        warnings.append("No strong official website match found")
        primary_site_url = None
        primary_domain = None
    else:
        primary_site_url = chosen["url"]
        primary_domain = chosen["domain"]
    why_chosen_parts = [
        f"best combined score {chosen['combined_score']}",
        f"source {chosen.get('source') or 'unknown'} rank {chosen.get('rank') or 'n/a'}",
    ]
    if chosen.get("verified"):
        why_chosen_parts.append("candidate site verified against company terms")
    if chosen.get("snippet"):
        why_chosen_parts.append(f"snippet: {chosen['snippet'][:120]}")
    return {
        "primary_site_url": primary_site_url,
        "primary_domain": primary_domain,
        "why_chosen": "; ".join(why_chosen_parts),
        "warnings": warnings,
        "site_verification": verification,
        "search_snippets": snippets[:5],
        "site_candidates": verified,
        "alternative_candidates": verified[1:4],
    }


def normalize_phone(phone):
    phone = re.sub(r"\s+", " ", (phone or "").strip())
    return phone.strip(" .,-") or None


def clean_email(email):
    email = (email or "").strip().lower()
    email = html.unescape(email)
    email = email.strip(" <>\"'()[]{}.,;:")
    if any(token in email for token in EMAIL_JUNK_PATTERNS):
        return None
    if not EMAIL_RE.fullmatch(email):
        return None
    return email


def plausible_phone(phone):
    phone = normalize_phone(phone)
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) < PHONE_MIN_DIGITS or len(digits) > PHONE_MAX_DIGITS:
        return None
    if digits.startswith("00") and len(digits) < 11:
        return None
    has_separator = bool(re.search(r"[\s().+-]", phone))
    if not has_separator and not phone.startswith("+"):
        return None
    grouped = [part for part in re.split(r"[^0-9]+", phone) if part]
    if grouped and len(grouped) > 2 and any(len(part) >= 6 for part in grouped[1:-1]):
        return None
    return phone


def extract_json_ld_contacts(blocks, url):
    emails = []
    phones = []
    org_names = []
    addresses = []
    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ("email", "telephone", "phone"):
                value = item.get(key)
                if not value:
                    continue
                values = value if isinstance(value, list) else [value]
                for entry in values:
                    if not isinstance(entry, str):
                        continue
                    if key == "email":
                        email = clean_email(entry.replace("mailto:", ""))
                        if email:
                            emails.append({"value": email, "source_url": url, "source_type": "jsonld"})
                    else:
                        phone = plausible_phone(entry.replace("tel:", ""))
                        if phone:
                            phones.append({"value": phone, "source_url": url, "source_type": "jsonld"})
            name = item.get("name")
            if isinstance(name, str) and len(name.strip()) > 2:
                org_names.append({"value": clean_text(name)[:180], "source_url": url, "source_type": "jsonld"})
            address = item.get("address")
            if isinstance(address, dict):
                flat = " ".join(str(address.get(key) or "").strip() for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"))
                flat = clean_text(flat)
                if flat:
                    addresses.append({"value": flat[:220], "source_url": url, "source_type": "jsonld"})
    return (
        dedupe_records(emails, ("value",)),
        dedupe_records(phones, ("value",)),
        dedupe_records(org_names, ("value",)),
        dedupe_records(addresses, ("value",)),
    )


def extract_mailto_tel_links(links, url):
    emails = []
    phones = []
    for href in links:
        raw = html.unescape(href or "")
        lower = raw.lower()
        if lower.startswith("mailto:"):
            email = clean_email(unquote(raw.split(":", 1)[1].split("?", 1)[0]))
            if email:
                emails.append({"value": email, "source_url": url, "source_type": "mailto"})
        elif lower.startswith("tel:"):
            phone = plausible_phone(unquote(raw.split(":", 1)[1].split("?", 1)[0]))
            if phone:
                phones.append({"value": phone, "source_url": url, "source_type": "tel"})
    return dedupe_records(emails, ("value",)), dedupe_records(phones, ("value",))


def parse_page(url, base_domain):
    result = {
        "title": None,
        "summary_text": None,
        "emails": [],
        "phones": [],
        "contact_pages": [],
        "social_links": [],
        "org_names": [],
        "addresses": [],
        "region_hints": [],
        "render_mode": "static",
        "parse_warnings": [],
    }
    try:
        raw = cached_fetch(url)
    except Exception as e:
        raw = None
        fetch_error = f"fetch failed for {url}: {e}"
    else:
        fetch_error = None

    if raw is None:
        rendered, browser_error = render_page_with_browser(url)
        if rendered is None:
            return result, fetch_error or browser_error or f"fetch failed for {url}"
        raw = rendered
        result["render_mode"] = "browser_fallback"

    parser = LinkParser()
    try:
        parser.feed(raw)
    except Exception:
        pass
    text = clean_text(raw)
    if any(pattern in text.lower()[:1000] for pattern in JS_ONLY_PATTERNS):
        rendered, browser_error = render_page_with_browser(url)
        if rendered:
            raw = rendered
            parser = LinkParser()
            try:
                parser.feed(raw)
            except Exception:
                pass
            text = clean_text(raw)
            result["render_mode"] = "browser_fallback"
        else:
            result["render_mode"] = "js_gated"
            if browser_error:
                result["parse_warnings"].append(browser_error)
    result["title"] = clean_text(" ".join(parser.title))[:140] if parser.title else None
    result["summary_text"] = text[:2000]
    regex_emails = dedupe_records([
        {"value": email, "source_url": url, "source_type": "page"}
        for e in EMAIL_RE.findall(raw)
        for email in [clean_email(e)]
        if email and not email.endswith((".png", ".jpg", ".jpeg", ".webp"))
    ], ("value",))
    regex_phones = dedupe_records([
        {"value": phone, "source_url": url, "source_type": "page"}
        for p in PHONE_RE.findall(text)
        for phone in [plausible_phone(p)]
        if phone
    ], ("value",))

    links = []
    for href in parser.links:
        full = urllib.parse.urljoin(url, html.unescape(href))
        links.append(full)
    jsonld_emails, jsonld_phones, jsonld_org_names, jsonld_addresses = extract_json_ld_contacts(parser.json_ld_blocks, url)
    mailto_emails, tel_phones = extract_mailto_tel_links(parser.links, url)

    result["emails"] = dedupe_records(jsonld_emails + mailto_emails + regex_emails, ("value",))[:10]
    result["phones"] = dedupe_records(jsonld_phones + tel_phones + regex_phones, ("value",))[:10]
    result["contact_pages"] = dedupe_records([
        {"value": link, "source_url": url, "source_type": "page"}
        for link in links
        if domain_of(link).endswith(base_domain or "") and any(h in link.lower() for h in CONTACT_HINTS)
    ], ("value",))[:10]
    result["social_links"] = dedupe_records([
        {"value": link, "source_url": url, "source_type": "page"}
        for link in links if SOCIAL_RE.search(link)
    ], ("value",))[:10]
    result["org_names"] = jsonld_org_names[:5]
    regex_addresses = dedupe_records([
        {"value": clean_text(match)[:220], "source_url": url, "source_type": "page"}
        for match in ADDRESS_RE.findall(text)
        if clean_text(match)
    ], ("value",))
    result["addresses"] = dedupe_records(jsonld_addresses + regex_addresses, ("value",))[:5]
    region_hints = []
    for candidate in result["addresses"]:
        parts = [part.strip() for part in re.split(r"[,/|-]", candidate["value"]) if len(part.strip()) > 2]
        for part in parts[:4]:
            region_hints.append({"value": part[:120], "source_url": candidate["source_url"], "source_type": candidate["source_type"]})
    result["region_hints"] = dedupe_records(region_hints, ("value",))[:5]
    return result, None


def email_domain(email):
    parts = (email or "").rsplit("@", 1)
    return parts[1].lower() if len(parts) == 2 else ""


def email_localpart(email):
    return (email or "").split("@", 1)[0].lower()


def classify_contact_email(email, primary_domain):
    local = email_localpart(email)
    dom = email_domain(email)
    official = bool(primary_domain and dom == primary_domain)
    weak = any(token in local for token in WEAK_CONTACT_LOCALPARTS)
    strong = any(token in local for token in STRONG_CONTACT_LOCALPARTS)
    if official and strong:
        tier = "official_strong"
    elif official and not weak:
        tier = "official_general"
    elif official:
        tier = "official_weak"
    elif strong and not weak:
        tier = "external_strong"
    elif weak:
        tier = "external_weak"
    else:
        tier = "external_general"
    return {
        "email": email,
        "domain": dom,
        "official": official,
        "weak": weak,
        "strong": strong,
        "tier": tier,
    }


def rank_contact_email(email, primary_domain):
    meta = classify_contact_email(email, primary_domain)
    score = 0
    if meta["official"]:
        score += 100
    if meta["strong"]:
        score += 15
    if not meta["weak"]:
        score += 10
    if meta["weak"]:
        score -= 35
    if meta["domain"] and meta["domain"] in BAD_HOST_HINTS:
        score -= 20
    if "info" in email_localpart(email):
        score += 3
    return score, meta


def explain_contact_score(meta):
    reasons = []
    if meta["official"]:
        reasons.append("matches primary domain")
    else:
        reasons.append("does not match primary domain")
    if meta["strong"]:
        reasons.append("local part looks outreach-friendly")
    if meta["weak"]:
        reasons.append("local part looks weak for outreach")
    if not meta["strong"] and not meta["weak"]:
        reasons.append("local part is neutral")
    return reasons


def choose_best_contacts(emails, primary_domain):
    ranked = []
    unique = dedupe_records(emails, ("value",))
    for record in unique:
        email = record["value"]
        score, meta = rank_contact_email(email, primary_domain)
        ranked.append((score, email, meta, record, explain_contact_score(meta)))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    ordered = [email for _, email, _, _, _ in ranked]
    best = ordered[0] if ordered else None
    meta = ranked[0][2] if ranked else None
    best_record = ranked[0][3] if ranked else None
    return ordered, best, meta, best_record, ranked


def build_contact_review(ranked_contacts):
    review = []
    for score, email, meta, record, reasons in ranked_contacts[:5]:
        review.append({
            "email": email,
            "score": score,
            "official": meta["official"],
            "weak": meta["weak"],
            "strong": meta["strong"],
            "tier": meta["tier"],
            "source": {
                "source_url": record.get("source_url"),
                "source_type": record.get("source_type"),
            },
            "reasons": reasons,
        })
    return review


def cleanup_summary_text(text):
    cleaned = text or ""
    for pattern in JUNK_SUMMARY_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|•")
    return cleaned or None


def summarize(text, snippets, source_url=None):
    if text:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        useful = []
        for sentence in sentences:
            candidate = cleanup_summary_text(sentence.strip())
            if candidate and len(candidate) > 50:
                useful.append(candidate)
        if useful:
            return {
                "value": cleanup_summary_text(" ".join(useful[:2])[:320]),
                "source_url": source_url,
                "source_type": "page",
            }
    if snippets:
        best = cleanup_summary_text(max(snippets, key=len))
        if best:
            return {
                "value": best[:320],
                "source_url": None,
                "source_type": "serp",
            }
    return None


def build_trust_signals(domain, emails, phones, summary, warnings, best_contact_meta=None, site_verification=None):
    warning_penalty = round(min(0.3, 0.05 * len(warnings)), 2)
    signals = {
        "has_domain": bool(domain),
        "has_summary": bool(summary),
        "email_count": len(emails or []),
        "phone_count": len(phones or []),
        "warning_count": len(warnings or []),
        "warning_penalty": warning_penalty,
        "site_verified": bool(site_verification and site_verification.get("verified")),
        "site_verification_score": round((site_verification or {}).get("score", 0.0), 2),
        "has_official_contact_page": False,
        "js_gated_site": False,
        "best_contact": {
            "present": bool(best_contact_meta),
            "official": bool(best_contact_meta and best_contact_meta.get("official")),
            "strong": bool(best_contact_meta and best_contact_meta.get("strong")),
            "weak": bool(best_contact_meta and best_contact_meta.get("weak")),
            "tier": best_contact_meta.get("tier") if best_contact_meta else None,
        },
    }
    return signals


def compute_confidence(domain, emails, phones, summary, warnings, best_contact_meta=None, site_verification=None):
    signals = build_trust_signals(domain, emails, phones, summary, warnings, best_contact_meta, site_verification)
    score = 0.05
    if signals["has_domain"]:
        score += 0.25
    if signals["site_verified"]:
        score += 0.1
    elif signals["site_verification_score"] >= 1.0:
        score += 0.05
    if emails:
        score += 0.15
    if phones:
        score += 0.1
    if summary:
        score += 0.1
    if best_contact_meta:
        if best_contact_meta["official"]:
            score += 0.15
        if best_contact_meta["strong"]:
            score += 0.05
        if best_contact_meta["weak"]:
            score -= 0.15
        if not best_contact_meta["official"]:
            score -= 0.1
    elif emails:
        score -= 0.1
    score -= signals["warning_penalty"]
    return round(max(0.0, min(1.0, score)), 2), signals


def build_review_result(result, ranked_contacts):
    reasons = []
    blockers = []
    if not result.get("primary_domain"):
        blockers.append("No primary domain was identified")
    if not (result.get("site_verification") or {}).get("verified"):
        reasons.append("Official site could not be strongly verified")
    if not result.get("best_contact_email"):
        blockers.append("No outreach email was found")
    best = result.get("trust_signals", {}).get("best_contact", {})
    if best.get("weak"):
        reasons.append("Best available contact looks weak for outreach")
    if result.get("confidence", 0) < 0.45:
        blockers.append("Overall dossier confidence is too low")
    elif result.get("confidence", 0) < 0.7:
        reasons.append("Dossier needs human review before outreach")

    if blockers:
        status = "blocked"
        next_step = "find a better official site or stronger contact before drafting outreach"
    elif reasons:
        status = "review_required"
        next_step = "review sources and edit the dossier before using any outreach draft"
    else:
        status = "ready"
        next_step = "draft outreach and personalize it before sending"

    return {
        "status": status,
        "ready_for_outreach": status == "ready",
        "reasons": blockers + reasons,
        "next_step": next_step,
        "top_contact_candidates": build_contact_review(ranked_contacts),
    }


def enrich(company, region=None, domain=None, query_mode="smart"):
    queries = build_queries(company, region, domain, query_mode)
    search_results = []
    warnings = []
    for query in queries:
        try:
            query_items, search_errors = search_query(query)
            search_results.extend([{**item, "query": query} for item in query_items])
            warnings.extend([f"search source failed for '{query}': {message}" for message in search_errors])
        except Exception as e:
            warnings.append(f"search failed for '{query}': {e}")
    query_str = queries[0] if queries else company
    chosen_site = choose_site(company, region, domain, search_results)
    warnings.extend(chosen_site["warnings"])
    site_url = chosen_site["primary_site_url"]
    primary_domain = chosen_site["primary_domain"]
    snippets = chosen_site["search_snippets"]
    site_verification = chosen_site["site_verification"]
    site_candidates = chosen_site["site_candidates"]

    website_title = None
    summary_record = None
    emails = []
    phones = []
    contact_pages = []
    social_links = []
    addresses = []
    region_hints = []
    organization_names = []
    render_mode = "static"

    if site_url:
        parsed, err = parse_page(site_url, primary_domain or "")
        if err:
            warnings.append(err)
        website_title = parsed["title"]
        summary_record = summarize(parsed["summary_text"], snippets, site_url)
        emails.extend(parsed["emails"])
        phones.extend(parsed["phones"])
        contact_pages.extend(parsed["contact_pages"])
        social_links.extend(parsed["social_links"])
        addresses.extend(parsed.get("addresses") or [])
        region_hints.extend(parsed.get("region_hints") or [])
        organization_names.extend(parsed.get("org_names") or [])
        render_mode = parsed.get("render_mode") or render_mode
        warnings.extend(parsed.get("parse_warnings") or [])

        for extra_url in [r["value"] for r in dedupe_records(contact_pages, ("value",))[:MAX_CONTACT_FETCH]]:
            extra, err = parse_page(extra_url, primary_domain or "")
            if err:
                warnings.append(err)
                continue
            emails.extend(extra["emails"])
            phones.extend(extra["phones"])
            social_links.extend(extra["social_links"])
            addresses.extend(extra.get("addresses") or [])
            region_hints.extend(extra.get("region_hints") or [])
            organization_names.extend(extra.get("org_names") or [])
            warnings.extend(extra.get("parse_warnings") or [])
            if not summary_record:
                summary_record = summarize(extra["summary_text"], snippets, extra_url)
    else:
        summary_record = summarize(None, snippets)

    ordered_emails, best_email, best_contact_meta, best_contact_record, ranked_contacts = choose_best_contacts(emails, primary_domain)
    if best_contact_meta and best_contact_meta["weak"]:
        warnings.append(f"Best available email looks weak for outreach: {best_email}")
    if ordered_emails and (not best_contact_meta or not best_contact_meta["official"]):
        warnings.append("No official-domain outreach email found")
    if ordered_emails and all(meta["weak"] for _, _, meta, _, _ in ranked_contacts):
        warnings.append("Only weak outreach contacts found")

    phone_values = [record["value"] for record in dedupe_records(phones, ("value",))[:10]]
    contact_page_values = [record["value"] for record in dedupe_records(contact_pages, ("value",))[:10]]
    social_values = [record["value"] for record in dedupe_records(social_links, ("value",))[:10]]
    email_sources = {record["value"]: {"source_url": record.get("source_url"), "source_type": record.get("source_type")} for record in dedupe_records(emails, ("value",))}
    phone_sources = {record["value"]: {"source_url": record.get("source_url"), "source_type": record.get("source_type")} for record in dedupe_records(phones, ("value",))}
    result = {
        "company": company,
        "region": region,
        "query": query_str,
        "search_results": search_results[:15],
        "primary_domain": primary_domain,
        "primary_site_url": site_url,
        "alternative_candidates": chosen_site["alternative_candidates"],
        "why_chosen": chosen_site["why_chosen"],
        "website_title": website_title,
        "site_verification": site_verification,
        "site_candidates": site_candidates,
        "summary": summary_record["value"] if summary_record else None,
        "summary_source": {
            "source_url": summary_record.get("source_url"),
            "source_type": summary_record.get("source_type"),
        } if summary_record else None,
        "emails": ordered_emails[:10],
        "email_sources": {email: email_sources[email] for email in ordered_emails[:10] if email in email_sources},
        "best_contact_email": best_email,
        "best_contact_source": {
            "source_url": best_contact_record.get("source_url"),
            "source_type": best_contact_record.get("source_type"),
        } if best_contact_record else None,
        "phones": phone_values,
        "phone_sources": {phone: phone_sources[phone] for phone in phone_values if phone in phone_sources},
        "contact_pages": contact_page_values,
        "social_links": social_values,
        "addresses": [record["value"] for record in dedupe_records(addresses, ("value",))[:5]],
        "region_hints": [record["value"] for record in dedupe_records(region_hints, ("value",))[:5]],
        "organization_names": [record["value"] for record in dedupe_records(organization_names, ("value",))[:5]],
        "extraction": {
            "render_mode": render_mode,
            "search_sources": dedupe([item.get("source") for item in search_results if item.get("source")]),
        },
        "snippets": snippets[:5],
        "confidence": 0.0,
        "trust_signals": {},
        "review": {},
        "warnings": dedupe(warnings),
    }
    result["confidence"], result["trust_signals"] = compute_confidence(
        result["primary_domain"],
        result["emails"],
        result["phones"],
        result["summary"],
        result["warnings"],
        best_contact_meta,
        site_verification,
    )
    result["trust_signals"]["has_official_contact_page"] = any(domain_of(url) == (primary_domain or "") for url in result["contact_pages"])
    result["trust_signals"]["js_gated_site"] = render_mode == "js_gated"
    result["review"] = build_review_result(result, ranked_contacts)
    result["review_reason"] = "; ".join(result["review"]["reasons"]) if result["review"]["reasons"] else "No blocking trust concerns detected"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--region")
    parser.add_argument("--domain")
    parser.add_argument("--query-mode", choices=["basic", "smart"], default="smart")
    args = parser.parse_args()
    result = enrich(args.company, args.region, args.domain, args.query_mode)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
