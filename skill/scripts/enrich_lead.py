#!/usr/bin/env python3
import argparse
import html
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from collections import OrderedDict
from html.parser import HTMLParser

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
SEARCH_URL = "https://html.duckduckgo.com/html/?q={query}"
TIMEOUT = 12
MAX_CONTACT_FETCH = 3
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
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


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.title = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)


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


def domain_of(url):
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
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
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return resp.read(350000).decode("utf-8", errors="replace")


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


def search_query(query):
    body = fetch(SEARCH_URL.format(query=urllib.parse.quote(query)))
    urls = re.findall(r'nofollow" class="[^\"]*result__a[^\"]*" href="(.*?)"', body)
    if not urls:
        urls = re.findall(r'<a rel="nofollow" class="result__url" href="(.*?)"', body)
    snippets = [clean_text(s)[:240] for s in re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', body, flags=re.S)[:8]]
    return [html.unescape(u) for u in urls], snippets


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
    score += min(2.0, sum(0.75 for word in company_words[:4] if word in title))
    score += min(2.0, sum(0.5 for word in company_words[:4] if word in text[:800]))
    if region and region.lower() in text[:800]:
        score += 0.5
    result["score"] = round(score, 2)
    result["verified"] = score >= 2.0
    if not result["verified"]:
        result["reason"] = "weak company match on candidate site"
    return result


def choose_site(company, region, explicit_domain, query_results):
    warnings = []
    if explicit_domain:
        clean = explicit_domain.lower().removeprefix("www.")
        return f"https://{clean}", clean, warnings, query_results[0][1] if query_results else [], None

    seen = []
    snippets = []
    for urls, snips in query_results:
        snippets.extend(snips)
        for idx, url in enumerate(urls):
            snippet = snips[idx] if idx < len(snips) else ""
            seen.append((score_candidate(url, company, region, snippet), url, snippet))
    seen.sort(key=lambda item: item[0], reverse=True)
    if not seen or seen[0][0] < 0:
        warnings.append("No strong official website match found")
        return None, None, warnings, snippets[:5], None

    top_candidates = seen[:2]
    verified = []
    for score, url, snippet in top_candidates:
        verification = verify_site_identity(url, company, region)
        verified.append((score + verification["score"], url, snippet, verification))
    verified.sort(key=lambda item: item[0], reverse=True)
    chosen_score, chosen, _, verification = verified[0]
    if not verification["verified"]:
        warnings.append("Official website candidate could not be strongly verified")
    if len(verified) > 1 and abs(verified[0][0] - verified[1][0]) < 1.0:
        warnings.append("Official website match is ambiguous")
    if chosen_score < 1.0:
        warnings.append("No strong official website match found")
        return None, None, warnings, snippets[:5], verification
    return chosen, domain_of(chosen), warnings, snippets[:5], verification


def parse_page(url, base_domain):
    result = {
        "title": None,
        "summary_text": None,
        "emails": [],
        "phones": [],
        "contact_pages": [],
        "social_links": [],
    }
    try:
        raw = fetch(url)
    except Exception as e:
        return result, f"fetch failed for {url}: {e}"

    parser = LinkParser()
    try:
        parser.feed(raw)
    except Exception:
        pass
    text = clean_text(raw)
    result["title"] = clean_text(" ".join(parser.title))[:140] if parser.title else None
    result["summary_text"] = text[:2000]
    result["emails"] = dedupe_records([
        {"value": e.lower(), "source_url": url, "source_type": "page"}
        for e in EMAIL_RE.findall(raw)
        if not e.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ], ("value",))[:10]
    result["phones"] = dedupe_records([
        {"value": p.strip(), "source_url": url, "source_type": "page"}
        for p in PHONE_RE.findall(text)
    ], ("value",))[:10]

    links = []
    for href in parser.links:
        full = urllib.parse.urljoin(url, html.unescape(href))
        links.append(full)
    result["contact_pages"] = dedupe_records([
        {"value": link, "source_url": url, "source_type": "page"}
        for link in links
        if domain_of(link).endswith(base_domain or "") and any(h in link.lower() for h in CONTACT_HINTS)
    ], ("value",))[:10]
    result["social_links"] = dedupe_records([
        {"value": link, "source_url": url, "source_type": "page"}
        for link in links if SOCIAL_RE.search(link)
    ], ("value",))[:10]
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


def choose_best_contacts(emails, primary_domain):
    ranked = []
    unique = dedupe_records(emails, ("value",))
    for record in unique:
        email = record["value"]
        score, meta = rank_contact_email(email, primary_domain)
        ranked.append((score, email, meta, record))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    ordered = [email for _, email, _, _ in ranked]
    best = ordered[0] if ordered else None
    meta = ranked[0][2] if ranked else None
    best_record = ranked[0][3] if ranked else None
    return ordered, best, meta, best_record, ranked


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


def compute_confidence(domain, emails, phones, summary, warnings, best_contact_meta=None):
    score = 0.05
    if domain:
        score += 0.3
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
    score -= min(0.3, 0.05 * len(warnings))
    return round(max(0.0, min(1.0, score)), 2)


def enrich(company, region=None, domain=None, query_mode="smart"):
    queries = build_queries(company, region, domain, query_mode)
    query_results = []
    warnings = []
    for query in queries:
        try:
            urls, snippets = search_query(query)
            query_results.append((urls, snippets))
        except Exception as e:
            warnings.append(f"search failed for '{query}': {e}")
    query_str = queries[0] if queries else company
    site_url, primary_domain, choose_warnings, snippets, site_verification = choose_site(company, region, domain, query_results)
    warnings.extend(choose_warnings)

    website_title = None
    summary_record = None
    emails = []
    phones = []
    contact_pages = []
    social_links = []

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

        for extra_url in [r["value"] for r in dedupe_records(contact_pages, ("value",))[:MAX_CONTACT_FETCH]]:
            extra, err = parse_page(extra_url, primary_domain or "")
            if err:
                warnings.append(err)
                continue
            emails.extend(extra["emails"])
            phones.extend(extra["phones"])
            social_links.extend(extra["social_links"])
            if not summary_record:
                summary_record = summarize(extra["summary_text"], snippets, extra_url)
    else:
        summary_record = summarize(None, snippets)

    ordered_emails, best_email, best_contact_meta, best_contact_record, ranked_contacts = choose_best_contacts(emails, primary_domain)
    if best_contact_meta and best_contact_meta["weak"]:
        warnings.append(f"Best available email looks weak for outreach: {best_email}")
    if ordered_emails and (not best_contact_meta or not best_contact_meta["official"]):
        warnings.append("No official-domain outreach email found")
    if ordered_emails and all(meta["weak"] for _, _, meta, _ in ranked_contacts):
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
        "primary_domain": primary_domain,
        "website_title": website_title,
        "site_verification": site_verification,
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
        "snippets": snippets[:5],
        "confidence": 0.0,
        "warnings": dedupe(warnings),
    }
    result["confidence"] = compute_confidence(result["primary_domain"], result["emails"], result["phones"], result["summary"], result["warnings"], best_contact_meta)
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
