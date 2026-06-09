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
        emails, best, meta, _ = mod.choose_best_contacts([
            "press@acme.com",
            "hello@acme.com",
            "founder@gmail.com",
        ], "acme.com")
        self.assertEqual(best, "hello@acme.com")
        self.assertEqual(emails[0], "hello@acme.com")
        self.assertTrue(meta["official"])
        self.assertFalse(meta["weak"])

    def test_summarize_removes_obvious_junk(self):
        out = mod.summarize(
            "Enable JavaScript to continue. Acme builds warehouse software for logistics teams across Europe. Privacy policy.",
            [],
        )
        self.assertIn("Acme builds warehouse software", out)
        self.assertNotIn("Enable JavaScript", out)
        self.assertNotIn("Privacy policy", out)

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
                        "emails": ["privacy@acme.com", "jobs@acme.com"],
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
        self.assertIn("Only weak outreach contacts found", result["warnings"])
        self.assertLess(result["confidence"], 0.6)

    def test_summarize_uses_longest_snippet_fallback(self):
        out = mod.summarize(None, ["short", "this is a much longer snippet about a company and what it does"])
        self.assertIn("longer snippet", out)


if __name__ == "__main__":
    unittest.main()
