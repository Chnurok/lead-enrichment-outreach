import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skill" / "scripts" / "enrich_lead.py"
spec = importlib.util.spec_from_file_location("enrich_lead", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EnrichLeadTests(unittest.TestCase):
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
        chosen, domain, warnings, snippets = mod.choose_site("Acme Logistics", "Berlin", None, results)
        self.assertEqual(domain, "acme-logistics.de")
        self.assertEqual(warnings, [])
        self.assertEqual(snippets, ["snippet"])

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
        weak = mod.compute_confidence("acme.com", ["press@gmail.com"], [], "summary", ["Only weak outreach contacts found"], weak_meta)
        strong = mod.compute_confidence("acme.com", ["hello@acme.com"], [], "summary", [], strong_meta)
        self.assertLess(weak, strong)

    def test_enrich_warns_when_only_weak_contacts_exist(self):
        original_build_queries = mod.build_queries
        original_search_query = mod.search_query
        original_parse_page = mod.parse_page
        try:
            mod.build_queries = lambda company, region=None, domain=None, mode="smart": ["Acme"]
            mod.search_query = lambda query: (["https://acme.com"], ["Acme makes tools for field teams."])

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

        self.assertEqual(result["best_contact_email"], "jobs@acme.com")
        self.assertEqual(result["best_contact_source"]["source_url"], "https://acme.com")
        self.assertIn("Only weak outreach contacts found", result["warnings"])
        self.assertLess(result["confidence"], 0.6)

    def test_summarize_uses_longest_snippet_fallback(self):
        out = mod.summarize(None, ["short", "this is a much longer snippet about a company and what it does"])
        self.assertIn("longer snippet", out["value"])
        self.assertEqual(out["source_type"], "serp")

    def test_enrich_returns_sources_for_contacts_and_summary(self):
        original_build_queries = mod.build_queries
        original_search_query = mod.search_query
        original_parse_page = mod.parse_page
        try:
            mod.build_queries = lambda company, region=None, domain=None, mode="smart": ["Acme"]
            mod.search_query = lambda query: (["https://acme.com"], ["Acme makes tools for field teams."])

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

        self.assertEqual(result["best_contact_email"], "hello@acme.com")
        self.assertEqual(result["email_sources"]["sales@acme.com"]["source_url"], "https://acme.com/contact")
        self.assertEqual(result["phone_sources"]["+49 30 123456"]["source_url"], "https://acme.com")
        self.assertEqual(result["summary_source"]["source_url"], "https://acme.com")


if __name__ == "__main__":
    unittest.main()
