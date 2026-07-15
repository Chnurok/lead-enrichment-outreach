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
from pathlib import Path
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
EMAIL_PLACEHOLDER_LOCALPARTS = (
    "tu",
    "your",
    "example",
    "correo",
    "mail",
    "email",
)
PHONE_MIN_DIGITS = 10
PHONE_MAX_DIGITS = 15
SOCIAL_RE = re.compile(r"(linkedin\.com|facebook\.com|instagram\.com|t\.me|telegram\.me|vk\.com|youtube\.com)", re.I)
BAD_HOST_HINTS = ("yandex.ru", "2gis.ru", "zoon.ru", "yellowpages", "facebook.com", "instagram.com", "linkedin.com", "wikipedia.org")
DIRECTORY_HOST_HINTS = (
    "list-org.",
    "spark-interfax.",
    "checko.",
    "rusprofile.",
    "sbis.ru",
    "audit-it.",
    "zachestnyibiznes.",
    "companies.rbc.",
    "orgpage.",
    "flagma.",
)
ENTITY_DISCOVERY_HOST_HINTS = (
    "2gis.ru",
    "yandex.ru",
    "yandex.com",
    "yandex.by",
    "zoon.ru",
    "orgpage.",
    "flagma.",
)
CONTACT_HINTS = ("contact", "contacts", "about", "team", "company", "support")
WEAK_CONTACT_PATH_HINTS = (
    "privacy", "legal", "terms", "policy", "gdpr", "compliance", "press", "media",
    "news", "blog", "careers", "career", "jobs", "vacancy", "join-us", "join_us",
    "investor", "security", "trust", "status"
)
STRONG_CONTACT_PATH_HINTS = (
    "contact", "contacts", "sales", "demo", "book", "call", "consult", "quote",
    "support", "customer", "talk", "reach", "partner"
)
WEAK_CONTACT_LOCALPARTS = (
    "press", "privacy", "legal", "abuse", "noreply", "no-reply", "careers", "jobs", "career",
    "hr", "admin", "webmaster", "postmaster", "block"
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
    r"menu[^.?!]*[.?!]?",
    r"contact sales[^.?!]*[.?!]?",
    r"start building[^.?!]*[.?!]?",
    r"join us[^.?!]*[.?!]?",
    r"in conversation with[^.?!]*[.?!]?",
    r"meet [^.?!]*[.?!]?",
    r"trabajamos principalmente con[^.?!]*[.?!]?",
    r"qué pasa si[^.?!]*[.?!]?",
    r"subes o bajas de cancha[^.?!]*[.?!]?",
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
VERIFIED_FINDINGS_PATH = Path(
    os.getenv(
        "LEO_VERIFIED_FINDINGS_PATH",
        str(Path.home() / ".cache" / "lead-enrichment-outreach" / "verified-findings.json"),
    )
)

LANGUAGE_MESSAGES = {
    "en": {
        "No primary domain was identified": "No primary domain was identified",
        "Official site could not be strongly verified": "Official site could not be strongly verified",
        "No outreach email was found": "No outreach email was found",
        "Best available contact looks weak for outreach": "Best available contact looks weak for outreach",
        "Overall dossier confidence is too low": "Overall dossier confidence is too low",
        "Dossier needs human review before outreach": "Dossier needs human review before outreach",
        "No direct outreach email found, but identity signals suggest a reviewable lead": "No direct outreach email found, but identity signals suggest a reviewable lead",
        "Only business-linked contact paths were found": "Only business-linked contact paths were found",
        "Only directory, map, or registry identity hints were found": "Only directory, map, or registry identity hints were found",
        "Lead is contactable via business-linked public sources, but official web presence is unverified": "Lead is contactable via business-linked public sources, but official web presence is unverified",
        "find a better official site or stronger contact before drafting outreach": "find a better official site or stronger contact before drafting outreach",
        "review sources and edit the dossier before using any outreach draft": "review sources and edit the dossier before using any outreach draft",
        "draft outreach and personalize it before sending": "draft outreach and personalize it before sending",
        "No blocking trust concerns detected": "No blocking trust concerns detected",
        "matches primary domain": "matches primary domain",
        "does not match primary domain": "does not match primary domain",
        "local part looks outreach-friendly": "local part looks outreach-friendly",
        "local part looks weak for outreach": "local part looks weak for outreach",
        "local part is neutral": "local part is neutral",
        "public contact path": "public contact path",
        "contact path looks outreach-friendly": "contact path looks outreach-friendly",
        "contact path looks weak for outreach": "contact path looks weak for outreach",
        "linked social business page": "linked social business page",
        "No official-domain outreach email found": "No official-domain outreach email found",
        "Only weak outreach contacts found": "Only weak outreach contacts found",
        "matches official domain": "matches official domain",
        "linked from official site": "linked from official site",
        "confirmed by multiple source signals": "confirmed by multiple source signals",
        "legacy best contact on official domain": "legacy best contact on official domain",
        "Lead looks like an event, listing, or community page rather than a buyer business site": "Lead looks like an event, listing, or community page rather than a buyer business site",
        "Only social or indirect public contact paths were found": "Only social or indirect public contact paths were found",
        "confirmed by memory": "confirmed by memory",
    },
    "ru": {
        "No primary domain was identified": "Не удалось определить основной домен",
        "Official site could not be strongly verified": "Официальный сайт не удалось уверенно подтвердить",
        "No outreach email was found": "Не найден email для первого контакта",
        "Best available contact looks weak for outreach": "Лучший найденный контакт выглядит слабым для первого контакта",
        "Overall dossier confidence is too low": "Общая уверенность по досье слишком низкая",
        "Dossier needs human review before outreach": "Досье требует ручной проверки перед первым контактом",
        "No direct outreach email found, but identity signals suggest a reviewable lead": "Прямой email для первого контакта не найден, но сигналы по идентичности позволяют отправить лид на ручную проверку",
        "Only business-linked contact paths were found": "Найдены только косвенные публичные пути для связи",
        "Only directory, map, or registry identity hints were found": "Найдены только сигналы идентичности из справочников, карт или реестров",
        "Lead is contactable via business-linked public sources, but official web presence is unverified": "С лидом можно связаться через косвенные публичные источники, но официальный сайт не подтверждён",
        "find a better official site or stronger contact before drafting outreach": "найти более надёжный официальный сайт или более сильный контакт перед подготовкой первого сообщения",
        "review sources and edit the dossier before using any outreach draft": "проверить источники и отредактировать досье перед использованием черновика первого сообщения",
        "draft outreach and personalize it before sending": "подготовить первое сообщение и персонализировать его перед отправкой",
        "No blocking trust concerns detected": "Блокирующих проблем доверия не найдено",
        "matches primary domain": "совпадает с основным доменом",
        "does not match primary domain": "не совпадает с основным доменом",
        "local part looks outreach-friendly": "локальная часть email подходит для первого контакта",
        "local part looks weak for outreach": "локальная часть email выглядит слабой для первого контакта",
        "local part is neutral": "локальная часть email нейтральная",
        "public contact path": "публичный путь для связи",
        "contact path looks outreach-friendly": "путь для связи подходит для первого контакта",
        "contact path looks weak for outreach": "путь для связи выглядит слабым для первого контакта",
        "linked social business page": "привязанная страница компании в соцсети",
        "No official-domain outreach email found": "Не найден email для первого контакта на официальном домене",
        "Only weak outreach contacts found": "Найдены только слабые контакты для первого сообщения",
        "matches official domain": "совпадает с официальным доменом",
        "linked from official site": "ссылка найдена на официальном сайте",
        "confirmed by multiple source signals": "подтверждено несколькими сигналами источников",
        "legacy best contact on official domain": "унаследованный лучший контакт на официальном домене",
        "Lead looks like an event, listing, or community page rather than a buyer business site": "Похоже, это страница события, листинг или сообщество, а не сайт компании-покупателя",
        "Only social or indirect public contact paths were found": "Найдены только соцсети или косвенные публичные пути для связи",
        "confirmed by memory": "подтверждено памятью прошлых находок",
    },
    "es": {
        "No primary domain was identified": "No se pudo identificar el dominio principal",
        "Official site could not be strongly verified": "No se pudo verificar con suficiente confianza el sitio oficial",
        "No outreach email was found": "No se encontró un email válido para el primer contacto",
        "Best available contact looks weak for outreach": "El mejor contacto disponible parece débil para el primer contacto",
        "Overall dossier confidence is too low": "La confianza general del expediente es demasiado baja",
        "Dossier needs human review before outreach": "El expediente necesita revisión humana antes del primer contacto",
        "No direct outreach email found, but identity signals suggest a reviewable lead": "No se encontró un email directo para el primer contacto, pero las señales de identidad sugieren un lead revisable",
        "Only business-linked contact paths were found": "Solo se encontraron vías públicas indirectas de contacto",
        "Only directory, map, or registry identity hints were found": "Solo se encontraron señales de identidad en directorios, mapas o registros",
        "Lead is contactable via business-linked public sources, but official web presence is unverified": "Se puede contactar al lead mediante fuentes públicas indirectas, pero la presencia web oficial no está verificada",
        "find a better official site or stronger contact before drafting outreach": "encontrar un sitio oficial mejor o un contacto más sólido antes de redactar el primer mensaje",
        "review sources and edit the dossier before using any outreach draft": "revisar las fuentes y editar el expediente antes de usar cualquier borrador del primer mensaje",
        "draft outreach and personalize it before sending": "redactar el primer mensaje y personalizarlo antes de enviarlo",
        "No blocking trust concerns detected": "No se detectaron problemas de confianza bloqueantes",
        "matches primary domain": "coincide con el dominio principal",
        "does not match primary domain": "no coincide con el dominio principal",
        "local part looks outreach-friendly": "la parte local del email parece adecuada para el primer contacto",
        "local part looks weak for outreach": "la parte local del email parece débil para el primer contacto",
        "local part is neutral": "la parte local del email es neutral",
        "public contact path": "ruta pública de contacto",
        "contact path looks outreach-friendly": "la ruta de contacto parece adecuada para el primer contacto",
        "contact path looks weak for outreach": "la ruta de contacto parece débil para el primer contacto",
        "linked social business page": "página social de la empresa enlazada",
        "No official-domain outreach email found": "No se encontró un email de primer contacto en el dominio oficial",
        "Only weak outreach contacts found": "Solo se encontraron contactos débiles para el primer mensaje",
        "matches official domain": "coincide con el dominio oficial",
        "linked from official site": "enlazado desde el sitio oficial",
        "confirmed by multiple source signals": "confirmado por múltiples señales de origen",
        "legacy best contact on official domain": "mejor contacto heredado en el dominio oficial",
        "Lead looks like an event, listing, or community page rather than a buyer business site": "Parece una página de evento, listado o comunidad, no un sitio de una empresa compradora",
        "Only social or indirect public contact paths were found": "Solo se encontraron redes sociales o vías públicas indirectas de contacto",
        "confirmed by memory": "confirmado por memoria de hallazgos previos",
    },
}

EVENT_LEAD_PATTERNS = (
    r"\btorneo(?:s)?\b",
    r"\bpadel\b",
    r"\bamericano\b",
    r"\brey de la cancha\b",
    r"\bparejas\b",
    r"\bpartido(?:s)?\b",
    r"\bcancha\b",
    r"\brankings?\b",
    r"\btournament(?:s)?\b",
    r"\bleague\b",
    r"\bfixtures\b",
    r"\bschedule\b",
    r"\bclub ladder\b",
    r"\bcommunity\b",
    r"\bevent(?:s)?\b",
    r"\bregistration\b",
)

BUYER_BUSINESS_PATTERNS = (
    r"\bsoftware\b",
    r"\bplatform\b",
    r"\bservice(?:s)?\b",
    r"\bsolutions?\b",
    r"\bagency\b",
    r"\bconsult(?:ing)?\b",
    r"\bautomation\b",
    r"\bempresa\b",
    r"\bnegocio\b",
    r"\bsaas\b",
    r"\bteam\b",
    r"\bfor businesses\b",
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


def count_search_domain_consensus(search_results):
    domains = [
        domain_of(item.get("url"))
        for item in (search_results or [])
        if item.get("url")
    ]
    domains = [item for item in domains if item and not is_entity_discovery_domain(item)]
    if not domains:
        return 0
    counts = {}
    for item in domains:
        counts[item] = counts.get(item, 0) + 1
    return max(counts.values())


def classify_social_links(social_links, primary_domain):
    total = len(social_links or [])
    company_pages = 0
    matching_company_pages = 0
    domain_linked_pages = 0
    for record in social_links or []:
        if isinstance(record, str):
            value = record.lower()
            source_url = ""
        else:
            value = (record.get("value") or "").lower()
            source_url = record.get("source_url") or ""
        if any(token in value for token in ("/company/", "/showcase/", "/pages/", "/business/", "/brand/")):
            company_pages += 1
            if primary_domain and primary_domain.replace(".", "-") in value:
                matching_company_pages += 1
        if primary_domain and domain_of(source_url) == primary_domain:
            domain_linked_pages += 1
    return {
        "count": total,
        "company_pages": company_pages,
        "matching_company_pages": matching_company_pages,
        "domain_linked_pages": domain_linked_pages,
    }


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


def is_directory_like_domain(domain):
    dom = (domain or "").lower()
    return any(hint in dom for hint in DIRECTORY_HOST_HINTS)


def is_entity_discovery_domain(domain):
    dom = (domain or "").lower()
    return is_directory_like_domain(dom) or any(hint in dom for hint in ENTITY_DISCOVERY_HOST_HINTS)


def clean_text(text):
    text = html.unescape(text or "")
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_content_language(*chunks):
    text = " ".join(chunk for chunk in chunks if isinstance(chunk, str) and chunk).strip()
    if not text:
        return "en"
    lower = text.lower()
    if re.search(r"[а-яё]", lower):
        return "ru"
    if re.search(r"\b(el|la|los|las|una|torneo|torneos|parejas|partido|partidos|cancha|subes|bajas|trabajamos|principalmente|qué|pierdo|con|durante)\b", lower):
        return "es"
    return "en"


def translate_message(message, language):
    bucket = LANGUAGE_MESSAGES.get(language) or LANGUAGE_MESSAGES["en"]
    return bucket.get(message, message)


def translate_messages(messages, language):
    return [translate_message(item, language) for item in (messages or [])]


def load_verified_findings_store(path=None):
    target = Path(path or VERIFIED_FINDINGS_PATH)
    try:
        if not target.exists():
            return {"version": 1, "domains": {}, "companies": {}}
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "domains": {}, "companies": {}}
        return {
            "version": 1,
            "domains": data.get("domains") if isinstance(data.get("domains"), dict) else {},
            "companies": data.get("companies") if isinstance(data.get("companies"), dict) else {},
        }
    except Exception:
        return {"version": 1, "domains": {}, "companies": {}}


def save_verified_findings_store(store, path=None):
    target = Path(path or VERIFIED_FINDINGS_PATH)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def normalize_company_key(company):
    return re.sub(r"[^a-zа-я0-9]", "", (company or "").lower())


def build_verified_memory_context(company, primary_domain, store=None):
    store = store or load_verified_findings_store()
    domain_key = (primary_domain or "").lower()
    company_key = normalize_company_key(company)
    domain_record = store.get("domains", {}).get(domain_key, {}) if domain_key else {}
    company_record = store.get("companies", {}).get(company_key, {}) if company_key else {}
    return {
        "domain": domain_record if isinstance(domain_record, dict) else {},
        "company": company_record if isinstance(company_record, dict) else {},
    }


def merge_memory_contacts(primary_domain, contacts, memory_context, *, contact_type, source_url):
    merged = list(contacts or [])
    seen = {item.get("value") for item in merged if isinstance(item, dict)}
    domain_memory = memory_context.get("domain", {}) if isinstance(memory_context, dict) else {}
    for value in domain_memory.get(contact_type, []) or []:
        if not isinstance(value, str) or not value.strip() or value in seen:
            continue
        merged.append({
            "value": value,
            "source_url": source_url or (f"https://{primary_domain}" if primary_domain else None),
            "source_type": "memory",
        })
        seen.add(value)
    return merged


def persist_verified_findings(company, primary_domain, contact_candidates, summary_record=None, store=None):
    if not primary_domain:
        return
    verified_candidates = []
    for candidate in contact_candidates or []:
        if not candidate.get("official"):
            continue
        source_types = {
            item.get("source_type")
            for item in (candidate.get("source_records") or [])
            if item.get("source_type")
        }
        if candidate.get("contact_type") == "email" and ("mailto" in source_types or "jsonld" in source_types):
            verified_candidates.append(candidate)
        elif candidate.get("contact_type") in {"phone", "contact_page"} and candidate.get("primary_domain_match"):
            verified_candidates.append(candidate)
    if not verified_candidates and not summary_record:
        return
    store = store or load_verified_findings_store()
    domains = store.setdefault("domains", {})
    companies = store.setdefault("companies", {})
    domain_bucket = domains.setdefault(primary_domain, {"email": [], "phone": [], "contact_page": [], "summary": None, "updated_at": None})
    company_key = normalize_company_key(company)
    company_bucket = companies.setdefault(company_key, {"primary_domain": primary_domain, "verified_contact_count": 0, "updated_at": None}) if company_key else None
    for candidate in verified_candidates:
        bucket_key = candidate.get("contact_type")
        if bucket_key not in {"email", "phone", "contact_page"}:
            continue
        values = domain_bucket.setdefault(bucket_key, [])
        if candidate.get("value") and candidate["value"] not in values:
            values.append(candidate["value"])
    if summary_record and summary_record.get("value"):
        domain_bucket["summary"] = summary_record.get("value")
    timestamp = time.strftime("%Y-%m-%d")
    domain_bucket["updated_at"] = timestamp
    if company_bucket is not None:
        company_bucket["primary_domain"] = primary_domain
        company_bucket["verified_contact_count"] = sum(len(domain_bucket.get(key, []) or []) for key in ("email", "phone", "contact_page"))
        company_bucket["updated_at"] = timestamp
    save_verified_findings_store(store)


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
        return [joined, f"{joined} сайт", f"{joined} контакты"]
    looks_russian = bool(re.search(r"[а-яА-Я]", joined))
    if looks_russian:
        queries = [
            f"{joined} официальный сайт",
            f"{joined} сайт контакты",
            f"{joined} компания",
            f"{joined} site:2gis.ru",
            f"{joined} site:yandex.ru/maps",
            f"{joined} site:zoon.ru",
        ]
        if region:
            queries.append(f"{company} {region} контакты")
            queries.append(f"{company} {region} site:2gis.ru")
            queries.append(f"{company} {region} site:yandex.ru/maps")
        if "ооо" not in company.lower():
            queries.append(f"ООО {joined} сайт")
        return dedupe(queries)
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
    if is_directory_like_domain(dom):
        return -15
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
    if is_directory_like_domain(dom):
        result["reason"] = "directory-like source cannot be treated as an official website"
        return result
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


def build_directory_entity_hints(search_results, company, region=None):
    hints = []
    company_words = [w for w in re.split(r"\W+", company.lower()) if len(w) > 2]
    for item in search_results or []:
        url = item.get("url")
        dom = domain_of(url)
        if not is_entity_discovery_domain(dom):
            continue
        snippet = clean_text(item.get("snippet") or "")[:240]
        title = clean_text(item.get("title") or "")[:180]
        haystack = f"{title} {snippet}".lower()
        matches = [word for word in company_words[:4] if word in haystack]
        score = min(0.3, 0.1 * len(matches))
        if region and region.lower() in haystack:
            score += 0.05
        if is_directory_like_domain(dom):
            score += 0.03
        if score <= 0:
            continue
        hints.append({
            "url": url,
            "domain": dom,
            "source": item.get("source"),
            "rank": item.get("rank"),
            "title": title or None,
            "snippet": snippet or None,
            "score": round(score, 2),
            "matched_terms": matches,
        })
    hints.sort(key=lambda item: item["score"], reverse=True)
    return hints[:3]


def extract_contacts_from_search_results(search_results):
    emails = []
    phones = []
    names = []
    region_hints = []
    for item in search_results or []:
        url = item.get("url")
        dom = domain_of(url)
        if not is_entity_discovery_domain(dom):
            continue
        title = clean_text(item.get("title") or "")[:180]
        snippet = clean_text(item.get("snippet") or "")[:240]
        haystack = f"{title} {snippet}"
        for match in EMAIL_RE.findall(haystack):
            email = clean_email(match)
            if email:
                emails.append({"value": email, "source_url": url, "source_type": item.get("source") or "search_result"})
        for match in PHONE_RE.findall(haystack):
            phone = plausible_phone(match)
            if phone:
                phones.append({"value": phone, "source_url": url, "source_type": item.get("source") or "search_result"})
        if title:
            names.append({"value": title, "source_url": url, "source_type": item.get("source") or "search_result"})
        if snippet:
            parts = [part.strip() for part in re.split(r"[,/|-]", snippet) if len(part.strip()) > 3]
            for part in parts[:3]:
                if any(char.isdigit() for char in part) or any(token in part.lower() for token in ("обл", "область", "район", "город", "волгоград", "moscow", "berlin")):
                    region_hints.append({"value": part[:120], "source_url": url, "source_type": item.get("source") or "search_result"})
    return (
        dedupe_records(emails, ("value",)),
        dedupe_records(phones, ("value",)),
        dedupe_records(names, ("value",)),
        dedupe_records(region_hints, ("value",)),
    )


def choose_site(company, region, explicit_domain, search_results):
    warnings = []
    directory_hints = build_directory_entity_hints(search_results, company, region)
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
            "directory_entity_hints": directory_hints,
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
            "directory_entity_hints": directory_hints,
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
    elif is_directory_like_domain(chosen["domain"]):
        warnings.append("Best candidate looks like a directory or registry, not an official website")
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
        "directory_entity_hints": directory_hints,
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
    local = email_localpart(email)
    if local in EMAIL_PLACEHOLDER_LOCALPARTS:
        return None
    if any(
        local == f"{prefix}{suffix}"
        for prefix in EMAIL_PLACEHOLDER_LOCALPARTS
        for suffix in ("email", "mail", "correo")
    ):
        return None
    return email


def plausible_phone(phone):
    phone = normalize_phone(phone)
    if not phone:
        return None
    if phone.count(".") >= 1:
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
    if len(grouped) <= 2 and any(len(part) >= 5 for part in grouped):
        return None
    if any(len(part) == 4 and part.startswith("19") or part.startswith("20") for part in grouped):
        return None
    if "." in phone and " " not in phone and "(" not in phone and ")" not in phone and "-" not in phone and not phone.startswith("+"):
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
        "page_language": None,
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
    lang_match = re.search(r"<html[^>]+lang=[\"']?([a-zA-Z-]+)", raw, flags=re.I)
    if lang_match:
        result["page_language"] = lang_match.group(1).split("-", 1)[0].lower()
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


def classify_contact_page(url, primary_domain):
    value = (url or "").lower()
    official = bool(primary_domain and domain_of(url) == primary_domain)
    weak = any(token in value for token in WEAK_CONTACT_PATH_HINTS)
    strong = any(token in value for token in STRONG_CONTACT_PATH_HINTS)
    if official and strong:
        tier = "official_strong"
    elif official and weak:
        tier = "official_weak"
    elif official:
        tier = "official_general"
    elif strong:
        tier = "external_strong"
    elif weak:
        tier = "external_weak"
    else:
        tier = "external_general"
    return {
        "official": official,
        "weak": weak,
        "strong": strong,
        "tier": tier,
    }


def explain_contact_page_score(meta):
    reasons = []
    reasons.append("matches official domain" if meta["official"] else "public contact path")
    if meta["strong"]:
        reasons.append("contact path looks outreach-friendly")
    if meta["weak"]:
        reasons.append("contact path looks weak for outreach")
    return reasons


def classify_social_contact(url, primary_domain):
    value = (url or "").lower()
    official = bool(primary_domain and primary_domain.replace(".", "-") in value)
    strong = any(token in value for token in ("/company/", "/business/", "/brand/", "/pages/"))
    weak = any(token in value for token in ("/p/", "/reel/", "/post/", "/channel/", "/video/"))
    return {
        "official": official,
        "strong": strong,
        "weak": weak,
        "tier": "social_company" if strong and not weak else "social_generic",
    }


def localize_candidate_reason_list(reasons, language):
    return translate_messages(reasons, language)


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


def build_contact_review(ranked_contacts, language="en"):
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
            "reasons": translate_messages(reasons, language),
        })
    return review


def build_evidence_sources(search_results, parsed_pages):
    sources = []
    seen = {}

    def add_source(url=None, domain=None, kind=None, source_type=None, query=None, title=None, snippet=None, rank=None):
        key = (url or "", source_type or "", query or "", rank or 0, kind or "")
        if key in seen:
            return seen[key]
        source_id = f"src_{len(seen) + 1}"
        record = {
            "source_id": source_id,
            "url": url,
            "domain": domain or domain_of(url),
            "kind": kind,
            "source_type": source_type,
            "query": query,
            "title": title,
            "snippet": snippet,
            "rank": rank,
        }
        seen[key] = record
        sources.append(record)
        return record

    for item in search_results or []:
        dom = domain_of(item.get("url"))
        kind = "search_result"
        if is_directory_like_domain(dom):
            kind = "directory"
        elif any(token in dom for token in ("2gis.", "yandex.ru", "yandex.com", "zoon.ru")):
            kind = "map"
        add_source(
            url=item.get("url"),
            domain=dom,
            kind=kind,
            source_type=item.get("source"),
            query=item.get("query"),
            title=item.get("title"),
            snippet=item.get("snippet"),
            rank=item.get("rank"),
        )

    for page in parsed_pages or []:
        add_source(
            url=page.get("url"),
            domain=page.get("domain"),
            kind="contact_page" if page.get("is_contact_page") else "page",
            source_type=page.get("source_type") or "page",
            title=page.get("title"),
        )

    return sources


def score_entity_candidate(candidate):
    score = 0.0
    score += min(0.3, 0.08 * len(candidate.get("names") or []))
    score += min(0.2, 0.08 * len(candidate.get("source_kinds") or []))
    score += min(0.2, 0.06 * len(candidate.get("phones") or []))
    score += min(0.15, 0.05 * len(candidate.get("emails") or []))
    score += min(0.15, 0.05 * len(candidate.get("regions") or []))
    if candidate.get("primary_domain"):
        score += 0.15
    if candidate.get("official_site_url"):
        score += 0.1
    return round(max(0.0, min(1.0, score)), 2)


def build_entity_candidates(company, region, chosen_site, search_results, parsed_pages):
    hints = chosen_site.get("directory_entity_hints") or []
    names = []
    regions = []
    addresses = []
    phones = []
    emails = []
    source_ids = []
    source_kinds = []
    match_reasons = []
    for item in hints:
        source_ids.append(item.get("source_id"))
        kind = item.get("kind") or ("directory" if is_directory_like_domain(item.get("domain")) else "map")
        source_kinds.append(kind)
        title = item.get("title")
        snippet = item.get("snippet")
        if title:
            names.append({"value": title, "source_ids": [item.get("source_id")]})
            match_reasons.append("name match in title")
        if region and snippet and region.lower() in snippet.lower():
            regions.append({"value": region, "source_ids": [item.get("source_id")]})
            match_reasons.append("region match in snippet")

    for page in parsed_pages or []:
        page_source_id = page.get("source_id")
        source_ids.append(page_source_id)
        source_kinds.append("page")
        for org_name in page.get("org_names") or []:
            names.append({"value": org_name.get("value"), "source_ids": [page_source_id]})
        for hint in page.get("region_hints") or []:
            regions.append({"value": hint.get("value"), "source_ids": [page_source_id]})
        for address in page.get("addresses") or []:
            addresses.append({"value": address.get("value"), "source_ids": [page_source_id]})
        for phone in page.get("phones") or []:
            phones.append({"value": phone.get("value"), "source_ids": [page_source_id]})
        for email in page.get("emails") or []:
            emails.append({"value": email.get("value"), "source_ids": [page_source_id]})

    display_name = company
    normalized_name = re.sub(r"[^a-zа-я0-9]", "", company.lower())
    candidate = {
        "candidate_id": "ent_1",
        "display_name": display_name,
        "normalized_name": normalized_name,
        "legal_form": "ООО" if "ооо" in company.lower() else None,
        "primary_domain": chosen_site.get("primary_domain"),
        "official_site_url": chosen_site.get("primary_site_url"),
        "confidence": 0.0,
        "official_site_confidence": round((chosen_site.get("site_verification") or {}).get("score", 0.0), 2),
        "match_reasons": dedupe(match_reasons),
        "names": dedupe_records(names, ("value",)),
        "regions": dedupe_records(regions, ("value",)),
        "addresses": dedupe_records(addresses, ("value",)),
        "phones": dedupe_records(phones, ("value",)),
        "emails": dedupe_records(emails, ("value",)),
        "source_ids": dedupe([item for item in source_ids if item]),
        "source_kinds": dedupe([item for item in source_kinds if item]),
        "source_diversity": len(dedupe([item for item in source_kinds if item])),
        "is_primary": True,
    }
    candidate["confidence"] = score_entity_candidate(candidate)
    return [candidate]


def score_contact_candidate(candidate):
    score = 0.0
    if candidate.get("official"):
        score += 0.5
    if candidate.get("primary_domain_match"):
        score += 0.2
    if candidate.get("trust_class") == "business_linked":
        score += 0.22
    if candidate.get("trust_class") == "weak":
        score -= 0.2
    if candidate.get("source_strength") == "strong":
        score += 0.15
    elif candidate.get("source_strength") == "memory":
        score += 0.1
    if candidate.get("reused_verified_finding"):
        score += 0.08
    usefulness = candidate.get("outreach_usability")
    if usefulness == "high":
        score += 0.18
    elif usefulness == "medium":
        score += 0.06
    elif usefulness == "low":
        score -= 0.2
    score += min(0.15, 0.05 * len(candidate.get("reasons") or []))
    return round(max(0.0, min(1.0, score)), 2)


def build_contact_candidates(emails, phones, contact_pages, social_links, primary_domain, evidence_sources, entity_candidates, verified_memory=None):
    source_by_url_type = {(item.get("url"), item.get("source_type")): item.get("source_id") for item in evidence_sources or []}
    candidates = []
    entity_ids = [item.get("candidate_id") for item in entity_candidates or [] if item.get("candidate_id")]
    domain_memory = (verified_memory or {}).get("domain", {}) if isinstance(verified_memory, dict) else {}
    memory_sets = {
        "email": set(domain_memory.get("email") or []),
        "phone": set(domain_memory.get("phone") or []),
        "contact_page": set(domain_memory.get("contact_page") or []),
    }

    for record in dedupe_records(emails, ("value",)):
        score, meta = rank_contact_email(record["value"], primary_domain)
        source_id = source_by_url_type.get((record.get("source_url"), record.get("source_type")))
        source_type = record.get("source_type")
        reused_verified_finding = source_type == "memory" or record["value"] in memory_sets["email"]
        source_strength = "strong" if source_type in {"mailto", "jsonld"} else ("memory" if reused_verified_finding else "page")
        trust_class = "official" if meta["official"] else ("weak" if meta["weak"] else "business_linked")
        if meta["official"] and source_strength in {"strong", "memory"} and not meta["weak"]:
            trust_class = "official"
        outreach_usability = "low" if meta["weak"] else ("high" if meta["official"] and meta["strong"] else ("medium" if meta["official"] or meta["strong"] else "low"))
        candidate = {
            "candidate_id": f"con_{len(candidates) + 1}",
            "value": record["value"],
            "contact_type": "email",
            "channel": "email",
            "trust_class": trust_class,
            "confidence": 0.0,
            "official": meta["official"],
            "primary_domain_match": meta["official"],
            "label": meta["tier"],
            "source_ids": [source_id] if source_id else [],
            "source_records": [{"source_id": source_id, "source_url": record.get("source_url"), "source_type": record.get("source_type")}],
            "reasons": explain_contact_score(meta) + (["confirmed by memory"] if reused_verified_finding else []),
            "entity_candidate_ids": entity_ids,
            "rank": score,
            "ranking_score": score + (30 if outreach_usability == "high" else 8 if outreach_usability == "medium" else -18),
            "source_strength": source_strength,
            "reused_verified_finding": reused_verified_finding,
            "outreach_usability": outreach_usability,
            "is_primary": False,
        }
        candidate["confidence"] = score_contact_candidate(candidate)
        candidates.append(candidate)

    for record in dedupe_records(phones, ("value",)):
        source_id = source_by_url_type.get((record.get("source_url"), record.get("source_type")))
        source_type = record.get("source_type")
        reused_verified_finding = source_type == "memory" or record["value"] in memory_sets["phone"]
        official = bool(primary_domain and domain_of(record.get("source_url")) == primary_domain)
        source_strength = "strong" if source_type in {"tel", "jsonld"} else ("memory" if reused_verified_finding else "page")
        outreach_usability = "medium" if official else "low"
        candidate = {
            "candidate_id": f"con_{len(candidates) + 1}",
            "value": record["value"],
            "contact_type": "phone",
            "channel": "phone",
            "trust_class": "official" if official and source_strength in {"strong", "memory"} else "business_linked",
            "confidence": 0.45,
            "official": official,
            "primary_domain_match": official,
            "label": "phone",
            "source_ids": [source_id] if source_id else [],
            "source_records": [{"source_id": source_id, "source_url": record.get("source_url"), "source_type": record.get("source_type")}],
            "reasons": ["public business phone"] + (["confirmed by memory"] if reused_verified_finding else []),
            "entity_candidate_ids": entity_ids,
            "rank": 30,
            "ranking_score": 55 if official else 18,
            "source_strength": source_strength,
            "reused_verified_finding": reused_verified_finding,
            "outreach_usability": outreach_usability,
            "is_primary": False,
        }
        candidate["confidence"] = score_contact_candidate(candidate)
        candidates.append(candidate)

    for record in dedupe_records(contact_pages, ("value",)):
        source_id = source_by_url_type.get((record.get("source_url"), record.get("source_type")))
        source_type = record.get("source_type")
        reused_verified_finding = source_type == "memory" or record["value"] in memory_sets["contact_page"]
        primary_match = bool(primary_domain and domain_of(record.get("value")) == primary_domain)
        source_strength = "memory" if reused_verified_finding else ("strong" if primary_match else "page")
        page_meta = classify_contact_page(record["value"], primary_domain)
        outreach_usability = "low" if page_meta["weak"] else ("high" if page_meta["official"] and page_meta["strong"] else "medium")
        candidate = {
            "candidate_id": f"con_{len(candidates) + 1}",
            "value": record["value"],
            "contact_type": "contact_page",
            "channel": "web",
            "trust_class": "weak" if page_meta["weak"] else ("official" if primary_match and source_strength in {"strong", "memory"} else "business_linked"),
            "confidence": 0.35,
            "official": primary_match,
            "primary_domain_match": primary_match,
            "label": page_meta["tier"],
            "source_ids": [source_id] if source_id else [],
            "source_records": [{"source_id": source_id, "source_url": record.get("source_url"), "source_type": record.get("source_type")}],
            "reasons": explain_contact_page_score(page_meta) + (["confirmed by memory"] if reused_verified_finding else []),
            "entity_candidate_ids": entity_ids,
            "rank": 20,
            "ranking_score": 72 if outreach_usability == "high" else 36 if outreach_usability == "medium" else 6,
            "source_strength": source_strength,
            "reused_verified_finding": reused_verified_finding,
            "outreach_usability": outreach_usability,
            "is_primary": False,
        }
        candidate["confidence"] = score_contact_candidate(candidate)
        candidates.append(candidate)

    for record in dedupe_records(social_links, ("value",)):
        source_id = source_by_url_type.get((record.get("source_url"), record.get("source_type")))
        social_meta = classify_social_contact(record["value"], primary_domain)
        candidates.append({
            "candidate_id": f"con_{len(candidates) + 1}",
            "value": record["value"],
            "contact_type": "vk" if "vk.com" in record["value"] else "social",
            "channel": "social",
            "trust_class": "weak" if social_meta["weak"] else "business_linked",
            "confidence": 0.2,
            "official": social_meta["official"],
            "primary_domain_match": bool(primary_domain and domain_of(record.get("source_url")) == primary_domain),
            "label": social_meta["tier"],
            "source_ids": [source_id] if source_id else [],
            "source_records": [{"source_id": source_id, "source_url": record.get("source_url"), "source_type": record.get("source_type")}],
            "reasons": ["linked social business page"],
            "entity_candidate_ids": entity_ids,
            "rank": 10,
            "ranking_score": 12 if social_meta["strong"] and not social_meta["weak"] else 2,
            "source_strength": "page",
            "reused_verified_finding": False,
            "outreach_usability": "low",
            "is_primary": False,
        })

    candidates.sort(key=lambda item: (-item.get("ranking_score", item.get("rank", 0)), -(item.get("confidence") or 0), item.get("value") or ""))
    for index, candidate in enumerate(candidates, start=1):
        candidate["rank"] = index
        candidate["is_primary"] = index == 1
    return candidates


def derive_primary_entity(entity_candidates):
    for candidate in entity_candidates or []:
        if candidate.get("is_primary"):
            return candidate
    return entity_candidates[0] if entity_candidates else None


def derive_primary_contact(contact_candidates):
    for candidate in contact_candidates or []:
        if candidate.get("is_primary"):
            return candidate
    return contact_candidates[0] if contact_candidates else None


def derive_compatibility_fields(entity_candidates, contact_candidates, summary_record, chosen_site):
    primary_entity = derive_primary_entity(entity_candidates)
    primary_contact = derive_primary_contact(contact_candidates)
    email_candidates = [item for item in contact_candidates if item.get("contact_type") == "email"]
    phone_candidates = [item for item in contact_candidates if item.get("contact_type") == "phone"]
    page_candidates = [item for item in contact_candidates if item.get("contact_type") == "contact_page"]
    social_candidates = [item for item in contact_candidates if item.get("channel") == "social"]
    preferred_email = next((
        item for item in email_candidates
        if item.get("outreach_usability") in {"high", "medium"}
    ), email_candidates[0] if email_candidates else None)

    directory_entity_hints = []
    for candidate in entity_candidates or []:
        if candidate.get("primary_domain"):
            continue
        if not any(kind in candidate.get("source_kinds", []) for kind in ("directory", "map", "registry")):
            continue
        directory_entity_hints.append({
            "domain": (chosen_site.get("directory_entity_hints") or [{}])[0].get("domain") if chosen_site.get("directory_entity_hints") else None,
            "score": candidate.get("confidence"),
            "source_kinds": candidate.get("source_kinds"),
            "display_name": candidate.get("display_name"),
        })

    email_sources = {}
    for candidate in email_candidates:
        if candidate.get("source_records"):
            email_sources[candidate["value"]] = {
                "source_url": candidate["source_records"][0].get("source_url"),
                "source_type": candidate["source_records"][0].get("source_type"),
            }
    phone_sources = {}
    for candidate in phone_candidates:
        if candidate.get("source_records"):
            phone_sources[candidate["value"]] = {
                "source_url": candidate["source_records"][0].get("source_url"),
                "source_type": candidate["source_records"][0].get("source_type"),
            }

    return {
        "primary_domain": (primary_entity or {}).get("primary_domain"),
        "primary_site_url": (primary_entity or {}).get("official_site_url"),
        "emails": [item.get("value") for item in email_candidates[:10]],
        "email_sources": email_sources,
        "best_contact_email": (preferred_email or {}).get("value") if preferred_email else (primary_contact.get("value") if primary_contact and primary_contact.get("contact_type") == "email" else None),
        "best_contact_source": (preferred_email or primary_contact).get("source_records", [{}])[0] if (preferred_email or primary_contact) else None,
        "phones": [item.get("value") for item in phone_candidates[:10]],
        "phone_sources": phone_sources,
        "contact_pages": [item.get("value") for item in page_candidates[:10]],
        "social_links": [item.get("value") for item in social_candidates[:10]],
        "directory_entity_hints": directory_entity_hints or chosen_site.get("directory_entity_hints") or [],
        "summary": summary_record["value"] if summary_record else None,
        "summary_source": {
            "source_url": summary_record.get("source_url"),
            "source_type": summary_record.get("source_type"),
        } if summary_record else None,
    }


def compute_staged_confidence(entity_candidates, contact_candidates, site_verification, warnings, summary=None, search_results=None):
    primary_entity = derive_primary_entity(entity_candidates)
    primary_contact = derive_primary_contact(contact_candidates)
    entity_confidence = round((primary_entity or {}).get("confidence", 0.0), 2)
    contact_confidence = round((primary_contact or {}).get("confidence", 0.0), 2)
    official_site_confidence = round((primary_entity or {}).get("official_site_confidence", round((site_verification or {}).get("score", 0.0), 2)), 2)
    emails = [item.get("value") for item in contact_candidates if item.get("contact_type") == "email"]
    phones = [item.get("value") for item in contact_candidates if item.get("contact_type") == "phone"]
    pages = [item.get("value") for item in contact_candidates if item.get("contact_type") == "contact_page"]
    socials = [item.get("value") for item in contact_candidates if item.get("channel") == "social"]
    best_contact_meta = None
    if primary_contact and primary_contact.get("contact_type") == "email":
        best_contact_meta = classify_contact_email(primary_contact.get("value"), (primary_entity or {}).get("primary_domain"))
    confidence, trust_signals = compute_confidence(
        (primary_entity or {}).get("primary_domain"),
        emails,
        phones,
        summary,
        warnings,
        best_contact_meta,
        site_verification,
        socials,
        pages,
        search_results,
        [],
    )
    trust_signals["identity_confidence"] = entity_confidence
    trust_signals["contact_confidence"] = contact_confidence
    return {
        "entity_confidence": entity_confidence,
        "contact_confidence": contact_confidence,
        "official_site_confidence": official_site_confidence,
        "confidence": confidence,
        "trust_signals": trust_signals,
    }


def summarize_evidence(entity_candidates, contact_candidates, site_verification):
    primary_entity = derive_primary_entity(entity_candidates)
    primary_contact = derive_primary_contact(contact_candidates)
    entity_confidence = round((primary_entity or {}).get("confidence", 0.0), 2)
    contact_confidence = round((primary_contact or {}).get("confidence", 0.0), 2)
    official_site_confidence = round((primary_entity or {}).get("official_site_confidence", round((site_verification or {}).get("score", 0.0), 2)), 2)

    def status_for(score, strong_at, weak_at):
        if score >= strong_at:
            return "strong"
        if score >= weak_at:
            return "partial"
        return "weak"

    return {
        "entity_confidence": entity_confidence,
        "contact_confidence": contact_confidence,
        "official_site_confidence": official_site_confidence,
        "entity_status": status_for(entity_confidence, 0.55, 0.35),
        "contact_status": status_for(contact_confidence, 0.45, 0.2),
        "official_site_status": status_for(official_site_confidence, 2.0, 1.0),
        "verified_contact_count": sum(1 for item in (contact_candidates or []) if item.get("official") and (item.get("confidence") or 0) >= 0.55),
        "memory_reused_contact_count": sum(1 for item in (contact_candidates or []) if item.get("reused_verified_finding")),
        "useful_contact_count": sum(1 for item in (contact_candidates or []) if item.get("outreach_usability") in {"high", "medium"}),
        "high_usability_contact_count": sum(1 for item in (contact_candidates or []) if item.get("outreach_usability") == "high"),
        "low_usability_contact_count": sum(1 for item in (contact_candidates or []) if item.get("outreach_usability") == "low"),
    }


def cleanup_summary_text(text):
    cleaned = text or ""
    for pattern in JUNK_SUMMARY_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.I)
    cleaned = re.sub(
        r"^(?:(?:menu|products?|solutions?|platform|pricing|api|developers?|research|blog|customers?|company|resources?|docs|login|demo|sales|get started|book|request|contact)\b[\s,:;/|>.-]+){3,}",
        " ",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|•")
    return cleaned or None


def count_pattern_hits(text, patterns):
    lowered = (text or "").lower()
    return sum(1 for pattern in patterns if re.search(pattern, lowered))


def looks_like_event_or_community_lead(*chunks):
    text = " ".join(chunk for chunk in chunks if isinstance(chunk, str) and chunk).strip()
    if not text:
        return False
    event_hits = count_pattern_hits(text, EVENT_LEAD_PATTERNS)
    buyer_hits = count_pattern_hits(text, BUYER_BUSINESS_PATTERNS)
    return event_hits >= 2 and buyer_hits == 0


def score_summary_candidate(candidate):
    lower = candidate.lower()
    score = 0
    score += min(80, sum(ch.isalpha() for ch in candidate))
    score -= min(20, sum(ch.isdigit() for ch in candidate) * 2)
    score += len(re.findall(r"\b(?:builds?|provides?|helps?|offers?|develops?|supports?|organizes?|runs?|operates?|specializes?)\b", lower)) * 8
    score += len(re.findall(r"\b(?:software|platform|service|services|solutions|tools|translation|ai|logistics|automation|company|business)\b", lower)) * 6
    score -= len(re.findall(r"\b(?:menu|pricing|developers|blog|customers|company|contact sales|book demo|request demo)\b", lower)) * 8
    score -= count_pattern_hits(lower, EVENT_LEAD_PATTERNS) * 10
    return score


def summarize(text, snippets, source_url=None):
    marketing_noise_tokens = (
        "contact sales",
        "menu products",
        "research developers",
        "developers blog",
        "customers company",
        "pricing plans api pricing",
        "book demo",
        "request demo",
        "start free",
    )
    if text:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        useful = []
        for sentence in sentences:
            candidate = cleanup_summary_text(sentence.strip())
            if not candidate:
                continue
            lower = candidate.lower()
            if len(candidate) < 50:
                continue
            if candidate.count("-->") >= 2:
                continue
            if sum(ch.isdigit() for ch in candidate) > 12:
                continue
            if lower.count(" > ") >= 2 or lower.count(" --> ") >= 2:
                continue
            if any(token in lower for token in ("registrarse", "iniciar sesión", "rankings", "todos los torneos")) and len(candidate.split()) < 20:
                continue
            if any(token in lower for token in marketing_noise_tokens):
                continue
            if any(token in lower for token in ("in conversation with", "meet ", "slator", "latest models", "pricing plans api pricing")):
                continue
            if len(re.findall(r"\b(?:menu|products?|solutions?|platform|pricing|api|developers?|research|blog|customers?|company|resources?|docs|login|demo|sales)\b", lower)) >= 4:
                continue
            if looks_like_event_or_community_lead(candidate) and score_summary_candidate(candidate) < 45:
                continue
            if candidate:
                useful.append(candidate)
        if useful:
            useful.sort(key=lambda item: (score_summary_candidate(item), len(item)), reverse=True)
            best_sentence = useful[0]
            return {
                "value": cleanup_summary_text(best_sentence[:220]),
                "source_url": source_url,
                "source_type": "page",
            }
    if snippets:
        cleaned = []
        for snippet in snippets:
            best = cleanup_summary_text(snippet)
            if not best:
                continue
            lower = best.lower()
            if best.count("-->") >= 2:
                continue
            if sum(ch.isdigit() for ch in best) > 12:
                continue
            if any(token in lower for token in ("sign in", "registrarse", "iniciar sesión", "menu")) and len(best.split()) < 20:
                continue
            if any(token in lower for token in marketing_noise_tokens) and len(best.split()) < 18:
                continue
            if any(token in lower for token in ("in conversation with", "meet ", "slator", "latest models", "pricing plans api pricing")):
                continue
            if len(re.findall(r"\b(?:menu|products?|solutions?|platform|pricing|api|developers?|research|blog|customers?|company|resources?|docs|login|demo|sales)\b", lower)) >= 4:
                continue
            if looks_like_event_or_community_lead(best) and score_summary_candidate(best) < 45:
                continue
            cleaned.append(best)
        best = max(cleaned, key=len) if cleaned else None
        if best:
            return {
                "value": best[:220],
                "source_url": None,
                "source_type": "serp",
            }
    return None


def build_trust_signals(domain, emails, phones, summary, warnings, best_contact_meta=None, site_verification=None, social_links=None, contact_pages=None, search_results=None, directory_entity_hints=None):
    social_meta = classify_social_links(social_links, domain)
    warning_penalty = round(min(0.3, 0.05 * len(warnings)), 2)
    signals = {
        "has_domain": bool(domain),
        "has_summary": bool(summary),
        "email_count": len(emails or []),
        "phone_count": len(phones or []),
        "contact_page_count": len(contact_pages or []),
        "social_link_count": len(social_links or []),
        "search_domain_consensus": count_search_domain_consensus(search_results),
        "directory_hint_count": len(directory_entity_hints or []),
        "warning_count": len(warnings or []),
        "warning_penalty": warning_penalty,
        "site_verified": bool(site_verification and site_verification.get("verified")),
        "site_verification_score": round((site_verification or {}).get("score", 0.0), 2),
        "has_official_contact_page": False,
        "js_gated_site": False,
        "social_identity": social_meta,
        "directory_entity_hints": directory_entity_hints or [],
        "best_contact": {
            "present": bool(best_contact_meta),
            "official": bool(best_contact_meta and best_contact_meta.get("official")),
            "strong": bool(best_contact_meta and best_contact_meta.get("strong")),
            "weak": bool(best_contact_meta and best_contact_meta.get("weak")),
            "tier": best_contact_meta.get("tier") if best_contact_meta else None,
        },
    }
    return signals


def compute_confidence(domain, emails, phones, summary, warnings, best_contact_meta=None, site_verification=None, social_links=None, contact_pages=None, search_results=None, directory_entity_hints=None):
    signals = build_trust_signals(domain, emails, phones, summary, warnings, best_contact_meta, site_verification, social_links, contact_pages, search_results, directory_entity_hints)
    identity_score = 0.05
    contact_score = 0.0
    if signals["has_domain"]:
        identity_score += 0.22
    if signals["site_verified"]:
        identity_score += 0.12
    elif signals["site_verification_score"] >= 1.0:
        identity_score += 0.06
    if signals["search_domain_consensus"] >= 2:
        identity_score += 0.08
    if signals["directory_hint_count"]:
        identity_score += min(0.12, 0.06 * signals["directory_hint_count"])
    if signals["contact_page_count"]:
        identity_score += 0.08
        contact_score += 0.08
    social_identity = signals["social_identity"]
    if social_identity["company_pages"]:
        identity_score += 0.06
    if social_identity["domain_linked_pages"]:
        identity_score += 0.04
    if social_identity["matching_company_pages"]:
        identity_score += 0.04
    if summary:
        identity_score += 0.1
    if emails:
        contact_score += 0.15
    if phones:
        contact_score += 0.08
    if best_contact_meta:
        if best_contact_meta["official"]:
            contact_score += 0.15
        if best_contact_meta["strong"]:
            contact_score += 0.05
        if best_contact_meta["weak"]:
            contact_score -= 0.15
        if not best_contact_meta["official"]:
            contact_score -= 0.05
    elif emails:
        contact_score -= 0.08
    identity_score = max(0.0, min(1.0, identity_score))
    contact_score = max(0.0, min(1.0, contact_score))
    overall_score = (identity_score * 0.6) + (contact_score * 0.4) - signals["warning_penalty"]
    signals["identity_confidence"] = round(identity_score, 2)
    signals["contact_confidence"] = round(contact_score, 2)
    return round(max(0.0, min(1.0, overall_score)), 2), signals


def build_review_result(result, ranked_contacts):
    reasons = []
    blockers = []
    language = result.get("content_language") or "en"
    trust = result.get("trust_signals", {})
    evidence_summary = result.get("evidence_summary") or {}
    entity_candidates = result.get("entity_candidates") or []
    contact_candidates = result.get("contact_candidates") or []
    primary_entity = derive_primary_entity(entity_candidates)
    primary_contact = derive_primary_contact(contact_candidates)
    identity_confidence = result.get("entity_confidence")
    if identity_confidence is None:
        identity_confidence = trust.get("identity_confidence", result.get("confidence", 0))
    contact_confidence = result.get("contact_confidence")
    if contact_confidence is None:
        contact_confidence = trust.get("contact_confidence", result.get("confidence", 0))
    official_site_confidence = result.get("official_site_confidence")
    if official_site_confidence is None:
        official_site_confidence = evidence_summary.get("official_site_confidence", round(((result.get("site_verification") or {}).get("score", 0.0)), 2))
    has_contact_proxy = bool(result.get("contact_pages")) or bool((trust.get("social_identity") or {}).get("company_pages"))
    has_directory_hint = bool(trust.get("directory_entity_hints"))
    has_business_linked_contact = any(item.get("trust_class") in ("official", "business_linked") for item in contact_candidates)
    has_entity_candidate = bool(primary_entity and ((primary_entity.get("confidence") or 0) >= 0.35 or (primary_entity.get("source_diversity") or 0) >= 1))
    social_only_contact = (
        not result.get("best_contact_email")
        and not result.get("phones")
        and not result.get("contact_pages")
        and bool(result.get("social_links"))
    )
    event_like_lead = looks_like_event_or_community_lead(
        result.get("company"),
        result.get("website_title"),
        result.get("summary"),
        " ".join(result.get("snippets") or []),
    )
    if not result.get("primary_domain") and not has_entity_candidate and identity_confidence < 0.45 and not has_directory_hint:
        blockers.append("No primary domain was identified")
    if event_like_lead and not result.get("best_contact_email") and official_site_confidence < 2.0:
        blockers.append("Lead looks like an event, listing, or community page rather than a buyer business site")
    if not (result.get("site_verification") or {}).get("verified") and official_site_confidence < 2.0:
        reasons.append("Official site could not be strongly verified")
    if not result.get("best_contact_email") and not has_contact_proxy and not has_directory_hint and not has_business_linked_contact:
        blockers.append("No outreach email was found")
    if social_only_contact and not result.get("primary_domain"):
        blockers.append("Only social or indirect public contact paths were found")
    best = trust.get("best_contact", {})
    if best.get("weak"):
        reasons.append("Best available contact looks weak for outreach")
    if identity_confidence < 0.35 and not (has_entity_candidate and has_business_linked_contact):
        blockers.append("Overall dossier confidence is too low")
    elif result.get("confidence", 0) < 0.55 or contact_confidence < 0.35:
        reasons.append("Dossier needs human review before outreach")
    if has_contact_proxy and not result.get("best_contact_email"):
        reasons.append("No direct outreach email found, but identity signals suggest a reviewable lead")
    if has_business_linked_contact and not result.get("best_contact_email"):
        reasons.append("Only business-linked contact paths were found")
    if has_directory_hint and not result.get("primary_domain"):
        reasons.append("Only directory, map, or registry identity hints were found")
    if primary_contact and primary_contact.get("trust_class") == "business_linked" and not result.get("primary_domain"):
        reasons.append("Lead is contactable via business-linked public sources, but official web presence is unverified")

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
        "reasons": [translate_message(item, language) for item in (blockers + reasons)],
        "next_step": translate_message(next_step, language),
        "top_contact_candidates": build_contact_review(ranked_contacts, language),
    }


def enrich(company, region=None, domain=None, query_mode="smart", fast_mode=False, preferred_language=None):
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
    directory_entity_hints = chosen_site["directory_entity_hints"]
    verified_memory = build_verified_memory_context(company, primary_domain)

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
    parsed_pages = []
    content_language = None

    if site_url:
        parsed, err = parse_page(site_url, primary_domain or "")
        if err:
            warnings.append(err)
        website_title = parsed["title"]
        summary_record = summarize(parsed["summary_text"], snippets, site_url)
        content_language = parsed.get("page_language") or content_language
        emails.extend(parsed["emails"])
        phones.extend(parsed["phones"])
        contact_pages.extend(parsed["contact_pages"])
        social_links.extend(parsed["social_links"])
        addresses.extend(parsed.get("addresses") or [])
        region_hints.extend(parsed.get("region_hints") or [])
        organization_names.extend(parsed.get("org_names") or [])
        render_mode = parsed.get("render_mode") or render_mode
        warnings.extend(parsed.get("parse_warnings") or [])
        parsed_pages.append({
            "url": site_url,
            "domain": primary_domain,
            "title": parsed.get("title"),
            "source_type": "page",
            "emails": parsed.get("emails") or [],
            "phones": parsed.get("phones") or [],
            "contact_pages": parsed.get("contact_pages") or [],
            "social_links": parsed.get("social_links") or [],
            "org_names": parsed.get("org_names") or [],
            "addresses": parsed.get("addresses") or [],
            "region_hints": parsed.get("region_hints") or [],
            "is_contact_page": False,
        })

        contact_fetch_limit = 1 if fast_mode else MAX_CONTACT_FETCH
        for extra_url in [r["value"] for r in dedupe_records(contact_pages, ("value",))[:contact_fetch_limit]]:
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
            content_language = content_language or extra.get("page_language")
            parsed_pages.append({
                "url": extra_url,
                "domain": domain_of(extra_url),
                "title": extra.get("title"),
                "source_type": "page",
                "emails": extra.get("emails") or [],
                "phones": extra.get("phones") or [],
                "contact_pages": extra.get("contact_pages") or [],
                "social_links": extra.get("social_links") or [],
                "org_names": extra.get("org_names") or [],
                "addresses": extra.get("addresses") or [],
                "region_hints": extra.get("region_hints") or [],
                "is_contact_page": True,
            })
    else:
        summary_record = summarize(None, snippets)
        fallback_emails, fallback_phones, fallback_names, fallback_region_hints = extract_contacts_from_search_results(search_results)
        emails.extend(fallback_emails)
        phones.extend(fallback_phones)
        region_hints.extend(fallback_region_hints)
        organization_names.extend(fallback_names)

    emails = merge_memory_contacts(primary_domain, emails, verified_memory, contact_type="email", source_url=site_url)
    phones = merge_memory_contacts(primary_domain, phones, verified_memory, contact_type="phone", source_url=site_url)
    contact_pages = merge_memory_contacts(primary_domain, contact_pages, verified_memory, contact_type="contact_page", source_url=site_url)
    if not summary_record and verified_memory.get("domain", {}).get("summary"):
        summary_record = {
            "value": verified_memory["domain"]["summary"],
            "source_url": site_url,
            "source_type": "memory",
        }

    evidence_sources = build_evidence_sources(search_results, parsed_pages)
    for hint in chosen_site.get("directory_entity_hints") or []:
        for source in evidence_sources:
            if source.get("url") == hint.get("url"):
                hint["source_id"] = source.get("source_id")
                hint["kind"] = source.get("kind")
                break
    entity_candidates = build_entity_candidates(company, region, chosen_site, search_results, parsed_pages)
    contact_candidates = build_contact_candidates(emails, phones, contact_pages, social_links, primary_domain, evidence_sources, entity_candidates, verified_memory=verified_memory)
    compat = derive_compatibility_fields(entity_candidates, contact_candidates, summary_record, chosen_site)

    ordered_emails, best_email, best_contact_meta, best_contact_record, ranked_contacts = choose_best_contacts(emails, compat.get("primary_domain"))
    if compat.get("best_contact_email"):
        best_email = compat.get("best_contact_email")
    if compat.get("best_contact_source"):
        best_contact_record = compat.get("best_contact_source")
        if best_email:
            best_contact_meta = classify_contact_email(best_email, compat.get("primary_domain"))
    if best_contact_meta and best_contact_meta["weak"]:
        warnings.append(f"Best available email looks weak for outreach: {best_email}")
    if compat.get("emails") and (not best_contact_meta or not best_contact_meta["official"]):
        warnings.append("No official-domain outreach email found")
    if compat.get("emails") and all(meta["weak"] for _, _, meta, _, _ in ranked_contacts):
        warnings.append("Only weak outreach contacts found")
    result = {
        "company": company,
        "region": region,
        "query": query_str,
        "search_results": search_results[:15],
        "primary_domain": compat.get("primary_domain"),
        "primary_site_url": compat.get("primary_site_url"),
        "alternative_candidates": chosen_site["alternative_candidates"],
        "why_chosen": chosen_site["why_chosen"],
        "website_title": website_title,
        "site_verification": site_verification,
        "site_candidates": site_candidates,
        "directory_entity_hints": compat.get("directory_entity_hints"),
        "summary": compat.get("summary"),
        "summary_source": compat.get("summary_source"),
        "emails": compat.get("emails"),
        "email_sources": compat.get("email_sources"),
        "best_contact_email": compat.get("best_contact_email"),
        "best_contact_source": compat.get("best_contact_source"),
        "phones": compat.get("phones"),
        "phone_sources": compat.get("phone_sources"),
        "contact_pages": compat.get("contact_pages"),
        "social_links": compat.get("social_links"),
        "addresses": [record["value"] for record in dedupe_records(addresses, ("value",))[:5]],
        "region_hints": [record["value"] for record in dedupe_records(region_hints, ("value",))[:5]],
        "organization_names": [record["value"] for record in dedupe_records(organization_names, ("value",))[:5]],
        "content_language": preferred_language or content_language or detect_content_language(company, website_title, compat.get("summary"), " ".join(snippets[:3])),
        "evidence_sources": evidence_sources,
        "entity_candidates": entity_candidates,
        "contact_candidates": contact_candidates,
        "extraction": {
            "render_mode": render_mode,
            "search_sources": dedupe([item.get("source") for item in search_results if item.get("source")]),
        },
        "memory": {
            "verified_domain_memory": bool(verified_memory.get("domain")),
            "verified_company_memory": bool(verified_memory.get("company")),
            "reused_summary": bool(summary_record and summary_record.get("source_type") == "memory"),
        },
        "snippets": snippets[:5],
        "confidence": 0.0,
        "trust_signals": {},
        "review": {},
        "warnings": dedupe(warnings),
    }
    staged = compute_staged_confidence(
        entity_candidates,
        contact_candidates,
        site_verification,
        result["warnings"],
        result["summary"],
        result["search_results"],
    )
    result["entity_confidence"] = staged["entity_confidence"]
    result["contact_confidence"] = staged["contact_confidence"]
    result["official_site_confidence"] = staged["official_site_confidence"]
    result["evidence_summary"] = summarize_evidence(entity_candidates, contact_candidates, site_verification)
    result["confidence"] = staged["confidence"]
    result["trust_signals"] = staged["trust_signals"]
    result["trust_signals"]["directory_entity_hints"] = result["directory_entity_hints"]
    result["trust_signals"]["best_contact"] = {
        "present": bool(best_contact_meta),
        "official": bool(best_contact_meta and best_contact_meta.get("official")),
        "strong": bool(best_contact_meta and best_contact_meta.get("strong")),
        "weak": bool(best_contact_meta and best_contact_meta.get("weak")),
        "tier": best_contact_meta.get("tier") if best_contact_meta else None,
    }
    result["trust_signals"]["has_official_contact_page"] = any(domain_of(url) == ((result.get("primary_domain")) or "") for url in result["contact_pages"])
    result["trust_signals"]["js_gated_site"] = render_mode == "js_gated"
    result["review"] = build_review_result(result, ranked_contacts)
    result["review_reason"] = "; ".join(result["review"]["reasons"]) if result["review"]["reasons"] else translate_message("No blocking trust concerns detected", result["content_language"])
    persist_verified_findings(company, compat.get("primary_domain"), contact_candidates, summary_record=summary_record)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--region")
    parser.add_argument("--domain")
    parser.add_argument("--query-mode", choices=["basic", "smart"], default="smart")
    parser.add_argument("--fast-mode", action="store_true")
    args = parser.parse_args()
    result = enrich(args.company, args.region, args.domain, args.query_mode, args.fast_mode)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
