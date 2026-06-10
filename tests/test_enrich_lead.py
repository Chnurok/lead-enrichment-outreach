import importlib.util
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

    def test_plausible_phone_filters_numeric_noise(self):
        self.assertIsNone(mod.plausible_phone("201708291325"))
        self.assertIsNone(mod.plausible_phone("174078830"))
        self.assertEqual(mod.plausible_phone("+49 40 1234 5678"), "+49 40 1234 5678")

    def test_build_queries_smart(self):
        qs = mod.build_queries("Acme", "Berlin", None, "smart")
        self.assertEqual(len(qs), 3)
        self.assertIn("official site email", qs[0])

    def test_choose_site_prefers_company_domain(self):
        results = [([
            "https://facebook.com/acme",
            "https://acme-logistics.de/contact",
            "https://directory.example/acme"
        ], ["snippet"])]
        original_verify = mod.verify_site_identity
        mod.verify_site_identity = lambda url, company, region=None: {"verified": True, "score": 2.5, "title": "Acme Logistics", "reason": None}
        try:
            chosen, domain, warnings, snippets, verification = mod.choose_site("Acme Logistics", "Berlin", None, results)
        finally:
            mod.verify_site_identity = original_verify
        self.assertEqual(domain, "acme-logistics.de")
        self.assertEqual(warnings, [])
        self.assertEqual(snippets, ["snippet"])
        self.assertTrue(verification["verified"])

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

    def test_compute_confidence_penalizes_weak_external_contact(self):
        weak_meta = mod.classify_contact_email("press@gmail.com", "acme.com")
        strong_meta = mod.classify_contact_email("hello@acme.com", "acme.com")
        weak, weak_signals = mod.compute_confidence("acme.com", ["press@gmail.com"], [], "summary", ["Only weak outreach contacts found"], weak_meta)
        strong, strong_signals = mod.compute_confidence("acme.com", ["hello@acme.com"], [], "summary", [], strong_meta)
        self.assertLess(weak, strong)
        self.assertTrue(weak_signals["best_contact"]["weak"])
        self.assertTrue(strong_signals["best_contact"]["official"])

    def test_enrich_warns_when_only_weak_contacts_exist(self):
        original_build_queries = mod.build_queries
        original_search_query = mod.search_query
        original_parse_page = mod.parse_page
        original_verify_site_identity = mod.verify_site_identity
        try:
            mod.build_queries = lambda company, region=None, domain=None, mode="smart": ["Acme"]
            mod.search_query = lambda query: (["https://acme.com"], ["Acme makes tools for field teams."])
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
        results = [([
            "https://acme-tools.com",
            "https://acme-group.com"
        ], ["Acme tools official site", "Acme group software company"])]
        original_verify = mod.verify_site_identity
        try:
            scores = {
                "https://acme-tools.com": {"verified": True, "score": 2.0, "title": "Acme Tools", "reason": None},
                "https://acme-group.com": {"verified": True, "score": 2.1, "title": "Acme Group", "reason": None},
            }
            mod.verify_site_identity = lambda url, company, region=None: scores[url]
            chosen, domain, warnings, snippets, verification = mod.choose_site("Acme", None, None, results)
        finally:
            mod.verify_site_identity = original_verify
        self.assertEqual(domain, "acme-group.com")
        self.assertIn("Official website match is ambiguous", warnings)
        self.assertTrue(verification["verified"])

    def test_parse_page_extracts_mailto_tel_and_jsonld(self):
        original_fetch = mod.fetch
        try:
            mod.fetch = lambda url: '''
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
            mod.fetch = original_fetch
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
            mod.search_query = lambda query: (["https://acme.com"], ["Acme makes tools for field teams."])
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
        self.assertEqual(result["review"]["status"], "ready")
        self.assertGreaterEqual(len(result["site_candidates"]), 1)

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


if __name__ == "__main__":
    unittest.main()
