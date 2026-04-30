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

    def test_summarize_uses_longest_snippet_fallback(self):
        out = mod.summarize(None, ["short", "this is a much longer snippet about a company and what it does"])
        self.assertIn("longer snippet", out)

    def test_compute_confidence_increases_with_signals(self):
        low = mod.compute_confidence(None, [], [], None, [])
        high = mod.compute_confidence("acme.com", ["a@acme.com"], ["+123456789"], "summary", [])
        self.assertGreater(high, low)


if __name__ == "__main__":
    unittest.main()
