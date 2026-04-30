import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skill" / "scripts" / "generate_outreach.py"
spec = importlib.util.spec_from_file_location("generate_outreach", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GenerateOutreachTests(unittest.TestCase):
    def test_choose_contact_prefers_email(self):
        dossier = {"emails": ["hi@acme.com"], "contact_pages": ["https://acme.com/contact"]}
        self.assertEqual(mod.choose_contact(dossier), "hi@acme.com")

    def test_draft_contains_offer_and_cta(self):
        dossier = {"company": "Acme", "summary": "Acme provides logistics services.", "emails": ["hi@acme.com"]}
        out = mod.draft(dossier, "AI-assisted outreach workflows", "Would Tuesday work?")
        self.assertIn("AI-assisted outreach workflows", out["body"])
        self.assertIn("Would Tuesday work?", out["body"])
        self.assertEqual(out["target_contact"], "hi@acme.com")


if __name__ == "__main__":
    unittest.main()
