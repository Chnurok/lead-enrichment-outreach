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


def score_candidate(url, company, region=None):
    dom = domain_of(url)
    if not dom:
        return -999
    if any(hint in dom for hint in BAD_HOST_HINTS):
        return -50
    score = 0
    cname = re.sub(r"[^a-zа-я0-9]", "", company.lower())
    droot = re.sub(r"[^a-zа-я0-9]", "", dom)
    if cname:
        if cname[:8] and cname[:8] in droot:
            score += 4
        elif droot[:8] and droot[:8] in cname:
            score += 3
    if region and region.lower() in url.lower():
        score += 1
    if dom.endswith(".ru") or dom.endswith(".com") or dom.endswith(".ai"):
        score += 0.5
    return score


def choose_site(company, region, explicit_domain, query_results):
    warnings = []
    if explicit_domain:
        clean = explicit_domain.lower().removeprefix("www.")
        return f"https://{clean}", clean, warnings, query_results[0][1] if query_results else []

    seen = []
    snippets = []
    for urls, snips in query_results:
        snippets.extend(snips)
        for url in urls:
            seen.append((score_candidate(url, company, region), url))
    seen.sort(reverse=True)
    if not seen or seen[0][0] < 0:
        warnings.append("No strong official website match found")
        return None, None, warnings, snippets[:5]
    chosen = seen[0][1]
    return chosen, domain_of(chosen), warnings, snippets[:5]


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
    result["emails"] = dedupe([e.lower() for e in EMAIL_RE.findall(raw) if not e.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))])[:10]
    result["phones"] = dedupe([p.strip() for p in PHONE_RE.findall(text)])[:10]

    links = []
    for href in parser.links:
        full = urllib.parse.urljoin(url, html.unescape(href))
        links.append(full)
    result["contact_pages"] = dedupe([
        link for link in links
        if domain_of(link).endswith(base_domain or "") and any(h in link.lower() for h in CONTACT_HINTS)
    ])[:10]
    result["social_links"] = dedupe([link for link in links if SOCIAL_RE.search(link)])[:10]
    return result, None


def summarize(text, snippets):
    if text:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        useful = [s.strip() for s in sentences if len(s.strip()) > 50]
        if useful:
            return " ".join(useful[:2])[:320]
    if snippets:
        return max(snippets, key=len)[:320]
    return None


def compute_confidence(domain, emails, phones, summary, warnings):
    score = 0.1
    if domain:
        score += 0.3
    if emails:
        score += 0.25
    if phones:
        score += 0.15
    if summary:
        score += 0.15
    score -= min(0.2, 0.05 * len(warnings))
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
    site_url, primary_domain, choose_warnings, snippets = choose_site(company, region, domain, query_results)
    warnings.extend(choose_warnings)

    website_title = None
    summary = None
    emails = []
    phones = []
    contact_pages = []
    social_links = []

    if site_url:
        parsed, err = parse_page(site_url, primary_domain or "")
        if err:
            warnings.append(err)
        website_title = parsed["title"]
        summary = summarize(parsed["summary_text"], snippets)
        emails.extend(parsed["emails"])
        phones.extend(parsed["phones"])
        contact_pages.extend(parsed["contact_pages"])
        social_links.extend(parsed["social_links"])

        for extra_url in dedupe(contact_pages)[:MAX_CONTACT_FETCH]:
            extra, err = parse_page(extra_url, primary_domain or "")
            if err:
                warnings.append(err)
                continue
            emails.extend(extra["emails"])
            phones.extend(extra["phones"])
            social_links.extend(extra["social_links"])
            if not summary:
                summary = summarize(extra["summary_text"], snippets)
    else:
        summary = summarize(None, snippets)

    result = {
        "company": company,
        "region": region,
        "query": query_str,
        "primary_domain": primary_domain,
        "website_title": website_title,
        "summary": summary,
        "emails": dedupe(emails)[:10],
        "phones": dedupe(phones)[:10],
        "contact_pages": dedupe(contact_pages)[:10],
        "social_links": dedupe(social_links)[:10],
        "snippets": snippets[:5],
        "confidence": 0.0,
        "warnings": dedupe(warnings),
    }
    result["confidence"] = compute_confidence(result["primary_domain"], result["emails"], result["phones"], result["summary"], result["warnings"])
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
