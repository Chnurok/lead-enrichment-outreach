import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skill" / "scripts" / "enrich_lead.py"
spec = importlib.util.spec_from_file_location("enrich_lead", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EnrichLeadTests(unittest.TestCase):
    def test_unwraps_duckduckgo_redirect_urls(self):
        wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.deepl.com%2Fen%2Ftranslator&rut=abc"
        self.assertEqual(
            mod.unwrap_search_result_url(wrapped),
            "https://www.deepl.com/en/translator",
        )
        self.assertEqual(mod.domain_of(wrapped), "deepl.com")

    def test_clean_email_filters_escaped_junk(self):
        self.assertEqual(mod.clean_email("Support@DeepL.com"), "support@deepl.com")
        self.assertIsNone(mod.clean_email("u003eblock@deepl.com"))
        self.assertIsNone(mod.clean_email("tu@email.com"))
        self.assertIsNone(mod.clean_email("your@email.com"))

    def test_plausible_phone_filters_numeric_noise(self):
        self.assertIsNone(mod.plausible_phone("201708291325"))
        self.assertIsNone(mod.plausible_phone("174078830"))
        self.assertIsNone(mod.plausible_phone("69.6861 11.5687"))
        self.assertEqual(mod.plausible_phone("+49 40 1234 5678"), "+49 40 1234 5678")

    def test_build_queries_smart(self):
        qs = mod.build_queries("Acme", "Berlin", None, "smart")
        self.assertEqual(len(qs), 3)
        self.assertIn("official site email", qs[0])

    def test_build_queries_russian_local_business(self):
        qs = mod.build_queries('ООО "Стройфонд"', "Волгоградская область", None, "smart")
        self.assertTrue(any("официальный сайт" in q for q in qs))
        self.assertTrue(any("контакты" in q for q in qs))
        self.assertTrue(any("компания" in q for q in qs))
        self.assertTrue(any("site:2gis.ru" in q for q in qs))
        self.assertTrue(any("site:yandex.ru/maps" in q for q in qs))

    def test_choose_site_prefers_company_domain(self):
        results = [
            {"url": "https://facebook.com/acme", "snippet": "facebook page", "source": "duckduckgo_html", "rank": 1},
            {"url": "https://acme-logistics.de/contact", "snippet": "Acme Logistics official contact", "source": "bing_html", "rank": 1},
            {"url": "https://directory.example/acme", "snippet": "directory", "source": "duckduckgo_lite", "rank": 2},
        ]
        original_verify = mod.verify_site_identity
        mod.verify_site_identity = lambda url, company, region=None: {"verified": True, "score": 2.5, "title": "Acme Logistics", "reason": None}
        try:
            chosen = mod.choose_site("Acme Logistics", "Berlin", None, results)
        finally:
            mod.verify_site_identity = original_verify
        self.assertEqual(chosen["primary_domain"], "acme-logistics.de")
        self.assertEqual(chosen["warnings"], [])
        self.assertTrue(chosen["site_verification"]["verified"])
        self.assertIn("best combined score", chosen["why_chosen"])

    def test_choose_best_contacts_prefers_official_non_weak_email(self):
        emails, best, meta, best_record, _ = mod.choose_best_contacts([
            {"value": "press@acme.com", "source_url": "https://acme.com/contact", "source_type": "page"},
            {"value": "hello@acme.com", "source_url": "https://acme.com", "source_type": "page"},
            {"value": "founder@gmail.com", "source_url": "https://acme.com/team", "source_type": "page"},
        ], "acme.com")
        self.assertEqual(best, "hello@acme.com")
        self.assertEqual(emails[0], "hello@acme.com")
        self.assertTrue(meta["official"])
        self.assertFalse(meta["weak"])
        self.assertEqual(best_record["source_url"], "https://acme.com")

    def test_build_contact_review_explains_ranking(self):
        _, _, _, _, ranked = mod.choose_best_contacts([
            {"value": "press@acme.com", "source_url": "https://acme.com/contact", "source_type": "page"},
            {"value": "hello@acme.com", "source_url": "https://acme.com", "source_type": "page"},
        ], "acme.com")
        review = mod.build_contact_review(ranked)
        self.assertEqual(review[0]["email"], "hello@acme.com")
        self.assertIn("matches primary domain", review[0]["reasons"])
        self.assertIn("local part looks outreach-friendly", review[0]["reasons"])

    def test_summarize_removes_obvious_junk(self):
        out = mod.summarize(
            "Enable JavaScript to continue. Acme builds warehouse software for logistics teams across Europe. Privacy policy.",
            [],
        )
        self.assertIn("Acme builds warehouse software", out["value"])
        self.assertNotIn("Enable JavaScript", out["value"])
        self.assertNotIn("Privacy policy", out["value"])

    def test_summarize_filters_nav_marketing_noise(self):
        out = mod.summarize(
            "Contact sales. Menu Products Solutions Research Developers Blog Customers Company. "
            "Mistral Forge trains and evaluates custom AI models for enterprise teams.",
            [],
        )
        self.assertIn("Mistral Forge trains and evaluates custom AI models", out["value"])
        self.assertNotIn("Contact sales", out["value"])
        self.assertNotIn("Developers Blog Customers Company", out["value"])

    def test_cleanup_summary_text_collapses_marketing_nav_clusters(self):
        cleaned = mod.cleanup_summary_text(
            "Platform Pricing API Developers Research Blog Customers Company "
            "DeepL provides AI translation and writing tools for global teams."
        )
        self.assertEqual(cleaned, "DeepL provides AI translation and writing tools for global teams.")

    def test_summarize_skips_event_rules_copy(self):
        out = mod.summarize(
            "Trabajamos principalmente con Americano Parejas durante todo el torneo. "
            "PadelConnect organizes tournaments and league operations for local clubs and communities. "
            "Qué pasa si pierdo el partido.",
            [],
        )
        self.assertIn("PadelConnect organizes tournaments and league operations", out["value"])
        self.assertNotIn("Trabajamos principalmente", out["value"])

    def test_compute_confidence_penalizes_weak_external_contact(self):
        weak_meta = mod.classify_contact_email("press@gmail.com", "acme.com")
        strong_meta = mod.classify_contact_email("hello@acme.com", "acme.com")
        weak, weak_signals = mod.compute_confidence("acme.com", ["press@gmail.com"], [], "summary", ["Only weak outreach contacts found"], weak_meta)
        strong, strong_signals = mod.compute_confidence("acme.com", ["hello@acme.com"], [], "summary", [], strong_meta)
        self.assertLess(weak, strong)
        self.assertTrue(weak_signals["best_contact"]["weak"])
        self.assertTrue(strong_signals["best_contact"]["official"])
        self.assertIn("identity_confidence", strong_signals)
        self.assertIn("contact_confidence", strong_signals)

    def test_build_contact_candidates_upgrades_memory_backed_official_email(self):
        contacts = mod.build_contact_candidates(
            [{"value": "hello@acme.com", "source_url": "https://acme.com", "source_type": "memory"}],
            [],
            [],
            [],
            "acme.com",
            [],
            [{"candidate_id": "ent_1"}],
            verified_memory={"domain": {"email": ["hello@acme.com"]}},
        )
        self.assertEqual(contacts[0]["trust_class"], "official")
        self.assertTrue(contacts[0]["reused_verified_finding"])
        self.assertGreaterEqual(contacts[0]["confidence"], 0.8)

    def test_build_contact_candidates_demotes_weak_official_contact_page(self):
        contacts = mod.build_contact_candidates(
            [],
            [],
            [
                {"value": "https://acme.com/privacy", "source_url": "https://acme.com", "source_type": "page"},
                {"value": "https://acme.com/contact", "source_url": "https://acme.com", "source_type": "page"},
            ],
            [],
            "acme.com",
            [],
            [{"candidate_id": "ent_1"}],
        )
        self.assertEqual(contacts[0]["value"], "https://acme.com/contact")
        weak_page = next(item for item in contacts if item["value"] == "https://acme.com/privacy")
        self.assertEqual(weak_page["trust_class"], "weak")
        self.assertEqual(weak_page["outreach_usability"], "low")

    def test_verified_findings_store_roundtrip_and_memory_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verified-findings.json"
            store = {"version": 1, "domains": {}, "companies": {}}
            mod.persist_verified_findings(
                "Acme",
                "acme.com",
                [{
                    "official": True,
                    "contact_type": "email",
                    "value": "hello@acme.com",
                    "source_records": [{"source_type": "mailto"}],
                }],
                summary_record={"value": "Acme makes tools.", "source_type": "page"},
                store=store,
            )
            mod.save_verified_findings_store(store, path)
            loaded = mod.load_verified_findings_store(path)
            ctx = mod.build_verified_memory_context("Acme", "acme.com", loaded)
            merged = mod.merge_memory_contacts("acme.com", [], ctx, contact_type="email", source_url="https://acme.com")
        self.assertEqual(loaded["domains"]["acme.com"]["email"], ["hello@acme.com"])
        self.assertEqual(loaded["domains"]["acme.com"]["summary"], "Acme makes tools.")
        self.assertEqual(merged[0]["source_type"], "memory")
        self.assertEqual(merged[0]["value"], "hello@acme.com")

    def test_count_search_domain_consensus_ignores_directory_like_hosts(self):
        consensus = mod.count_search_domain_consensus([
            {"url": "https://2gis.ru/volgograd/firm/1"},
            {"url": "https://yandex.ru/maps/org/acme/1"},
            {"url": "https://spark-interfax.ru/company/acme"},
            {"url": "https://acme.com"},
            {"url": "https://acme.com/contact"},
        ])
        self.assertEqual(consensus, 2)

    def test_enrich_warns_when_only_weak_contacts_exist(self):
        original_build_queries = mod.build_queries
        original_search_query = mod.search_query
        original_parse_page = mod.parse_page
        original_verify_site_identity = mod.verify_site_identity
        original_memory_path = os.environ.get("LEO_VERIFIED_FINDINGS_PATH")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LEO_VERIFIED_FINDINGS_PATH"] = str(Path(tmp) / "verified-findings.json")
                mod.VERIFIED_FINDINGS_PATH = Path(os.environ["LEO_VERIFIED_FINDINGS_PATH"])
                mod.build_queries = lambda company, region=None, domain=None, mode="smart": ["Acme"]
                mod.search_query = lambda query: ([{
                    "url": "https://acme.com",
                    "title": "Acme",
                    "snippet": "Acme makes tools for field teams.",
                    "source": "duckduckgo_html",
                    "rank": 1,
                }], [])
                mod.verify_site_identity = lambda url, company, region=None: {"verified": True, "score": 2.5, "title": "Acme", "reason": None}

                def fake_parse_page(url, base_domain):
                    if url == "https://acme.com":
                        return ({
                            "title": "Acme",
                            "summary_text": "Acme makes tools for field teams across Europe and Latin America.",
                            "emails": [
                                {"value": "privacy@acme.com", "source_url": url, "source_type": "page"},
                                {"value": "jobs@acme.com", "source_url": url, "source_type": "page"},
                            ],
                            "phones": [],
                            "contact_pages": [],
                            "social_links": [],
                        }, None)
                    raise AssertionError(f"unexpected url {url}")

                mod.parse_page = fake_parse_page
                result = mod.enrich("Acme")
        finally:
            mod.build_queries = original_build_queries
            mod.search_query = original_search_query
            mod.parse_page = original_parse_page
            mod.verify_site_identity = original_verify_site_identity
            if original_memory_path is None:
                os.environ.pop("LEO_VERIFIED_FINDINGS_PATH", None)
                mod.VERIFIED_FINDINGS_PATH = Path.home() / ".cache" / "lead-enrichment-outreach" / "verified-findings.json"
            else:
                os.environ["LEO_VERIFIED_FINDINGS_PATH"] = original_memory_path
                mod.VERIFIED_FINDINGS_PATH = Path(original_memory_path)

        self.assertEqual(result["best_contact_email"], "jobs@acme.com")
        self.assertEqual(result["best_contact_source"]["source_url"], "https://acme.com")
        self.assertIn("Only weak outreach contacts found", result["warnings"])
        self.assertLess(result["confidence"], 0.6)
        self.assertTrue(result["trust_signals"]["best_contact"]["weak"])
        self.assertEqual(result["review"]["status"], "review_required")

    def test_summarize_uses_longest_snippet_fallback(self):
        out = mod.summarize(None, ["short", "this is a much longer snippet about a company and what it does"])
        self.assertIn("longer snippet", out["value"])
        self.assertEqual(out["source_type"], "serp")

    def test_choose_site_warns_on_ambiguous_match(self):
        results = [
            {"url": "https://acme-tools.com", "snippet": "Acme tools official site", "source": "duckduckgo_html", "rank": 1},
            {"url": "https://acme-group.com", "snippet": "Acme group software company", "source": "bing_html", "rank": 1},
        ]
        original_verify = mod.verify_site_identity
        try:
            scores = {
                "https://acme-tools.com": {"verified": True, "score": 2.0, "title": "Acme Tools", "reason": None},
                "https://acme-group.com": {"verified": True, "score": 2.1, "title": "Acme Group", "reason": None},
            }
            mod.verify_site_identity = lambda url, company, region=None: scores[url]
            chosen = mod.choose_site("Acme", None, None, results)
        finally:
            mod.verify_site_identity = original_verify
        self.assertEqual(chosen["primary_domain"], "acme-group.com")
        self.assertIn("Official website match is ambiguous", chosen["warnings"])
        self.assertTrue(chosen["site_verification"]["verified"])

    def test_choose_site_rejects_directory_like_domains_as_primary(self):
        results = [
            {"url": "https://spark-interfax.ru/company/acme", "snippet": "Acme company profile", "source": "duckduckgo_html", "rank": 1},
            {"url": "https://list-org.com/company/acme", "snippet": "Acme registry profile", "source": "bing_html", "rank": 2},
        ]
        chosen = mod.choose_site("Acme", None, None, results)
        self.assertIsNone(chosen["primary_domain"])
        self.assertIn("No strong official website match found", chosen["warnings"])
        self.assertTrue(chosen["directory_entity_hints"])

    def test_build_review_result_uses_directory_hint_as_weak_identity(self):
        result = {
            "primary_domain": None,
            "site_verification": {"verified": False, "score": 0.0},
            "best_contact_email": None,
            "contact_pages": [],
            "confidence": 0.38,
            "trust_signals": {
                "identity_confidence": 0.41,
                "contact_confidence": 0.0,
                "best_contact": {"weak": False},
                "social_identity": {"company_pages": 0},
                "directory_entity_hints": [{"domain": "spark-interfax.ru", "score": 0.2}],
            },
        }
        review = mod.build_review_result(result, [])
        self.assertEqual(review["status"], "review_required")
        self.assertIn("Only directory, map, or registry identity hints were found", " ".join(review["reasons"]))

    def test_build_review_result_blocks_event_like_social_only_lead(self):
        result = {
            "company": "1-Padel",
            "website_title": "1-Padel - Torneos de padel",
            "summary": "Torneos de padel para parejas y comunidad local.",
            "snippets": ["Americano parejas, rey de la cancha, torneos locales."],
            "primary_domain": None,
            "site_verification": {"verified": False, "score": 0.0},
            "official_site_confidence": 0.0,
            "best_contact_email": None,
            "phones": [],
            "contact_pages": [],
            "social_links": ["https://instagram.com/example"],
            "confidence": 0.32,
            "trust_signals": {
                "identity_confidence": 0.33,
                "contact_confidence": 0.2,
                "best_contact": {"weak": False},
                "social_identity": {"company_pages": 1},
                "directory_entity_hints": [],
            },
            "entity_candidates": [],
            "contact_candidates": [{"trust_class": "business_linked"}],
        }
        review = mod.build_review_result(result, [])
        self.assertEqual(review["status"], "blocked")
        joined = " ".join(review["reasons"])
        self.assertIn("event, listing, or community page", joined)
        self.assertIn("Only social or indirect public contact paths were found", joined)

    def test_choose_site_keeps_map_results_as_entity_hints_not_primary(self):
        results = [
            {"url": "https://yandex.ru/maps/org/acme/123", "snippet": "Acme, Волгоград, контакты", "source": "duckduckgo_html", "rank": 1, "title": "Acme на карте"},
            {"url": "https://2gis.ru/volgograd/firm/70000000000000000", "snippet": "Acme, телефон, адрес", "source": "bing_html", "rank": 2, "title": "Acme, Волгоград"},
        ]
        chosen = mod.choose_site("Acme", "Волгоград", None, results)
        self.assertIsNone(chosen["primary_domain"])
        self.assertTrue(chosen["directory_entity_hints"])
        self.assertTrue(any("yandex.ru" in item["domain"] or "2gis.ru" in item["domain"] for item in chosen["directory_entity_hints"]))

    def test_extract_contacts_from_search_results_uses_directory_snippets(self):
        emails, phones, names, region_hints = mod.extract_contacts_from_search_results([
            {
                "url": "https://2gis.ru/volgograd/firm/1",
                "title": "Acme, Волгоград",
                "snippet": "Волгоград, +7 8442 12-34-56, info@gmail.com",
                "source": "bing_html",
            }
        ])
        self.assertEqual(emails[0]["value"], "info@gmail.com")
        self.assertEqual(phones[0]["value"], "+7 8442 12-34-56")
        self.assertTrue(names)
        self.assertTrue(region_hints)

    def test_detect_content_language_ru_and_es(self):
        self.assertEqual(mod.detect_content_language("Турниры по падел-теннису", "Контакты и расписание"), "ru")
        self.assertEqual(mod.detect_content_language("Trabajamos principalmente con Americano Parejas durante todo el torneo"), "es")

    def test_parse_page_extracts_mailto_tel_and_jsonld(self):
        original_fetch = mod.cached_fetch
        try:
            mod.cached_fetch = lambda url: '''
                <html>
                  <head>
                    <title>Acme</title>
                    <script type="application/ld+json">{"email":"schema@acme.com","telephone":"+49 30 777777"}</script>
                  </head>
                  <body>
                    <a href="mailto:hello@acme.com">Email</a>
                    <a href="tel:+49 30 123456">Call</a>
                    Contact us at support@acme.com
                  </body>
                </html>
            '''
            parsed, err = mod.parse_page("https://acme.com", "acme.com")
        finally:
            mod.cached_fetch = original_fetch
        self.assertIsNone(err)
        emails = [record["value"] for record in parsed["emails"]]
        phones = [record["value"] for record in parsed["phones"]]
        self.assertIn("schema@acme.com", emails)
        self.assertIn("hello@acme.com", emails)
        self.assertIn("support@acme.com", emails)
        self.assertIn("+49 30 777777", phones)
        self.assertIn("+49 30 123456", phones)
        self.assertEqual(parsed["emails"][0]["source_type"], "jsonld")

    def test_enrich_returns_sources_for_contacts_and_summary(self):
        original_build_queries = mod.build_queries
        original_search_query = mod.search_query
        original_parse_page = mod.parse_page
        original_verify_site_identity = mod.verify_site_identity
        try:
            mod.build_queries = lambda company, region=None, domain=None, mode="smart": ["Acme"]
            mod.search_query = lambda query: ([{
                "url": "https://acme.com",
                "title": "Acme",
                "snippet": "Acme makes tools for field teams.",
                "source": "duckduckgo_html",
                "rank": 1,
            }], [])
            mod.verify_site_identity = lambda url, company, region=None: {"verified": True, "score": 2.5, "title": "Acme", "reason": None}

            def fake_parse_page(url, base_domain):
                if url == "https://acme.com":
                    return ({
                        "title": "Acme",
                        "summary_text": "Acme makes tools for field teams across Europe and Latin America.",
                        "emails": [{"value": "hello@acme.com", "source_url": url, "source_type": "page"}],
                        "phones": [{"value": "+49 30 123456", "source_url": url, "source_type": "page"}],
                        "contact_pages": [{"value": "https://acme.com/contact", "source_url": url, "source_type": "page"}],
                        "social_links": [{"value": "https://linkedin.com/company/acme", "source_url": url, "source_type": "page"}],
                    }, None)
                if url == "https://acme.com/contact":
                    return ({
                        "title": "Contact Acme",
                        "summary_text": "",
                        "emails": [{"value": "sales@acme.com", "source_url": url, "source_type": "page"}],
                        "phones": [],
                        "contact_pages": [],
                        "social_links": [],
                    }, None)
                raise AssertionError(f"unexpected url {url}")

            mod.parse_page = fake_parse_page
            result = mod.enrich("Acme")
        finally:
            mod.build_queries = original_build_queries
            mod.search_query = original_search_query
            mod.parse_page = original_parse_page
            mod.verify_site_identity = original_verify_site_identity

        self.assertEqual(result["best_contact_email"], "hello@acme.com")
        self.assertEqual(result["email_sources"]["sales@acme.com"]["source_url"], "https://acme.com/contact")
        self.assertEqual(result["phone_sources"]["+49 30 123456"]["source_url"], "https://acme.com")
        self.assertEqual(result["summary_source"]["source_url"], "https://acme.com")
        self.assertTrue(result["site_verification"]["verified"])
        self.assertTrue(result["trust_signals"]["site_verified"])
        self.assertEqual(result["trust_signals"]["email_count"], 2)
        self.assertIn("entity_candidates", result)
        self.assertIn("contact_candidates", result)
        self.assertIn("evidence_sources", result)
        self.assertIn("entity_confidence", result)
        self.assertIn("contact_confidence", result)
        self.assertIn("official_site_confidence", result)
        self.assertIn("evidence_summary", result)
        self.assertEqual(result["entity_candidates"][0]["primary_domain"], "acme.com")
        self.assertEqual(result["contact_candidates"][0]["trust_class"], "official")
        self.assertEqual(result["review"]["status"], "ready")
        self.assertGreaterEqual(len(result["site_candidates"]), 1)
        self.assertEqual(result["primary_site_url"], "https://acme.com")
        self.assertTrue(result["search_results"])
        self.assertIn("duckduckgo_html", result["extraction"]["search_sources"])
        self.assertIn("best combined score", result["why_chosen"])
        self.assertEqual(result["review_reason"], "No blocking trust concerns detected")

    def test_build_review_result_localizes_russian(self):
        result = {
            "primary_domain": "primer.ru",
            "site_verification": {"verified": False, "score": 0.0},
            "best_contact_email": None,
            "contact_pages": [],
            "confidence": 0.4,
            "content_language": "ru",
            "entity_confidence": 0.4,
            "contact_confidence": 0.2,
            "trust_signals": {
                "best_contact": {"weak": False},
                "social_identity": {"company_pages": 0},
                "directory_entity_hints": [],
            },
            "evidence_summary": {"official_site_confidence": 0.0},
            "contact_candidates": [],
            "entity_candidates": [{"confidence": 0.4, "source_diversity": 1, "is_primary": True}],
        }
        review = mod.build_review_result(result, [])
        self.assertIn("Официальный сайт не удалось уверенно подтвердить", " ".join(review["reasons"]))
        self.assertIn("найти более надёжный официальный сайт", review["next_step"])

    def test_parse_page_extracts_addresses_and_region_hints(self):
        original_fetch = mod.cached_fetch
        try:
            mod.cached_fetch = lambda url: """
                <html>
                  <head>
                    <title>Acme Berlin</title>
                    <script type=\"application/ld+json\">
                      {"name":"Acme GmbH","address":{"streetAddress":"12 Alexanderplatz","addressLocality":"Berlin","addressCountry":"DE"}}
                    </script>
                  </head>
                  <body>
                    Visit us at 12 Alexanderplatz, Berlin, Germany
                  </body>
                </html>
            """
            parsed, err = mod.parse_page("https://acme.com", "acme.com")
        finally:
            mod.cached_fetch = original_fetch
        self.assertIsNone(err)
        self.assertIn("Acme GmbH", [item["value"] for item in parsed["org_names"]])
        self.assertTrue(parsed["addresses"])
        self.assertTrue(any("Berlin" in item["value"] for item in parsed["region_hints"]))

    def test_parse_page_uses_browser_fallback_for_js_gated_page(self):
        original_fetch = mod.cached_fetch
        original_browser = mod.render_page_with_browser
        try:
            mod.cached_fetch = lambda url: "<html><body>Enable JavaScript to continue.</body></html>"
            mod.render_page_with_browser = lambda url: ("""
                <html>
                  <head><title>Acme Rendered</title></head>
                  <body>
                    <a href=\"mailto:hello@acme.com\">Email</a>
                    Acme builds logistics software for field teams.
                  </body>
                </html>
            """, None)
            parsed, err = mod.parse_page("https://acme.com", "acme.com")
        finally:
            mod.cached_fetch = original_fetch
            mod.render_page_with_browser = original_browser
        self.assertIsNone(err)
        self.assertEqual(parsed["render_mode"], "browser_fallback")
        self.assertEqual(parsed["title"], "Acme Rendered")
        self.assertIn("hello@acme.com", [item["value"] for item in parsed["emails"]])

    def test_parse_page_uses_browser_fallback_when_fetch_fails(self):
        original_fetch = mod.cached_fetch
        original_browser = mod.render_page_with_browser
        try:
            def boom(url):
                raise RuntimeError("network down")
            mod.cached_fetch = boom
            mod.render_page_with_browser = lambda url: ("<html><head><title>Acme Browser</title></head><body>Acme browser render.</body></html>", None)
            parsed, err = mod.parse_page("https://acme.com", "acme.com")
        finally:
            mod.cached_fetch = original_fetch
            mod.render_page_with_browser = original_browser
        self.assertIsNone(err)
        self.assertEqual(parsed["render_mode"], "browser_fallback")
        self.assertEqual(parsed["title"], "Acme Browser")

    def test_build_review_result_blocks_low_confidence_dossier(self):
        result = {
            "primary_domain": None,
            "site_verification": {"verified": False, "score": 0.5},
            "best_contact_email": None,
            "confidence": 0.2,
            "trust_signals": {"best_contact": {"weak": False}},
        }
        review = mod.build_review_result(result, [])
        self.assertEqual(review["status"], "blocked")
        self.assertFalse(review["ready_for_outreach"])
        self.assertIn("No primary domain was identified", review["reasons"])

    def test_build_review_result_allows_social_identity_review_without_email(self):
        result = {
            "primary_domain": "acme.com",
            "site_verification": {"verified": False, "score": 1.1},
            "best_contact_email": None,
            "contact_pages": [],
            "confidence": 0.56,
            "trust_signals": {
                "identity_confidence": 0.58,
                "contact_confidence": 0.12,
                "best_contact": {"weak": False},
                "social_identity": {"company_pages": 1},
            },
        }
        review = mod.build_review_result(result, [])
        self.assertEqual(review["status"], "review_required")
        self.assertIn("No direct outreach email found", " ".join(review["reasons"]))

    def test_contact_candidates_allow_business_linked_contact_without_primary_domain(self):
        entity_candidates = [{
            "candidate_id": "ent_1",
            "display_name": "Acme",
            "primary_domain": None,
            "official_site_url": None,
            "confidence": 0.42,
            "official_site_confidence": 0.0,
            "source_kinds": ["directory"],
            "is_primary": True,
        }]
        evidence_sources = [{
            "source_id": "src_1",
            "url": "https://directory.example/acme",
            "domain": "directory.example",
            "kind": "directory",
            "source_type": "page",
        }]
        contacts = mod.build_contact_candidates(
            [{"value": "info@gmail.com", "source_url": "https://directory.example/acme", "source_type": "page"}],
            [],
            [],
            [],
            None,
            evidence_sources,
            entity_candidates,
        )
        self.assertEqual(contacts[0]["trust_class"], "business_linked")
        compat = mod.derive_compatibility_fields(entity_candidates, contacts, None, {"directory_entity_hints": []})
        result = {
            "primary_domain": compat["primary_domain"],
            "best_contact_email": compat["best_contact_email"],
            "contact_pages": compat["contact_pages"],
            "confidence": 0.42,
            "site_verification": {"verified": False, "score": 0.0},
            "trust_signals": {
                "identity_confidence": 0.42,
                "contact_confidence": contacts[0]["confidence"],
                "social_identity": {"company_pages": 0},
                "directory_entity_hints": compat["directory_entity_hints"],
                "best_contact": {"weak": False},
            },
        }
        review = mod.build_review_result(result, [])
        self.assertEqual(review["status"], "review_required")

    def test_derive_compatibility_fields_prefers_official_email(self):
        entity_candidates = [{
            "candidate_id": "ent_1",
            "display_name": "Acme",
            "primary_domain": "acme.com",
            "official_site_url": "https://acme.com",
            "confidence": 0.8,
            "official_site_confidence": 2.5,
            "source_kinds": ["page"],
            "is_primary": True,
        }]
        contacts = [
            {
                "candidate_id": "con_1",
                "value": "hello@acme.com",
                "contact_type": "email",
                "channel": "email",
                "trust_class": "official",
                "source_records": [{"source_url": "https://acme.com", "source_type": "page"}],
                "is_primary": True,
            },
            {
                "candidate_id": "con_2",
                "value": "contact@gmail.com",
                "contact_type": "email",
                "channel": "email",
                "trust_class": "business_linked",
                "source_records": [{"source_url": "https://dir.example/acme", "source_type": "page"}],
                "is_primary": False,
            },
        ]
        compat = mod.derive_compatibility_fields(entity_candidates, contacts, None, {"directory_entity_hints": []})
        self.assertEqual(compat["best_contact_email"], "hello@acme.com")

    def test_derive_compatibility_fields_skips_weak_official_email_when_better_one_exists(self):
        entity_candidates = [{
            "candidate_id": "ent_1",
            "display_name": "Acme",
            "primary_domain": "acme.com",
            "official_site_url": "https://acme.com",
            "confidence": 0.8,
            "official_site_confidence": 2.5,
            "source_kinds": ["page"],
            "is_primary": True,
        }]
        contacts = [
            {
                "candidate_id": "con_1",
                "value": "privacy@acme.com",
                "contact_type": "email",
                "channel": "email",
                "trust_class": "weak",
                "source_records": [{"source_url": "https://acme.com/privacy", "source_type": "page"}],
                "outreach_usability": "low",
                "is_primary": True,
            },
            {
                "candidate_id": "con_2",
                "value": "hello@acme.com",
                "contact_type": "email",
                "channel": "email",
                "trust_class": "official",
                "source_records": [{"source_url": "https://acme.com/contact", "source_type": "page"}],
                "outreach_usability": "high",
                "is_primary": False,
            },
        ]
        compat = mod.derive_compatibility_fields(entity_candidates, contacts, None, {"directory_entity_hints": []})
        self.assertEqual(compat["best_contact_email"], "hello@acme.com")
        self.assertEqual(compat["best_contact_source"]["source_url"], "https://acme.com/contact")

    def test_enrich_directory_contact_path_becomes_review_required(self):
        original_build_queries = mod.build_queries
        original_search_query = mod.search_query
        try:
            mod.build_queries = lambda company, region=None, domain=None, mode="smart": ["Acme"]
            mod.search_query = lambda query: ([{
                "url": "https://2gis.ru/volgograd/firm/1",
                "title": "Acme, Волгоград",
                "snippet": "Волгоград, +7 8442 12-34-56, info@gmail.com",
                "source": "bing_html",
                "rank": 1,
            }], [])
            result = mod.enrich("Acme", region="Волгоград")
        finally:
            mod.build_queries = original_build_queries
            mod.search_query = original_search_query

        self.assertIsNone(result["primary_domain"])
        self.assertTrue(result["entity_candidates"])
        self.assertTrue(result["contact_candidates"])
        self.assertIn("info@gmail.com", result["emails"])
        self.assertEqual(result["review"]["status"], "review_required")


if __name__ == "__main__":
    unittest.main()
