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
        self.assertIn("That often points to a need", out["body"])
        self.assertEqual(out["target_contact"], "hi@acme.com")

    def test_draft_uses_safer_subject_and_fallback_clue(self):
        dossier = {"company": "Acme", "summary": "Hi there. We sell tools."}
        out = mod.draft(dossier, "AI-assisted outreach workflows", "Would Tuesday work?")
        self.assertEqual(out["subject"], "Idea for Acme's outreach flow")
        self.assertIn("I noticed i reviewed Acme's public company information.", out["body"])
        self.assertNotIn("Hi there", out["body"])

    def test_clean_clue_trims_noise_and_length(self):
        noisy = "  Acme builds freight software   across Europe. Second sentence here."
        clue = mod.clean_clue(noisy, "Acme")
        self.assertEqual(clue, "Acme builds freight software across Europe")
        self.assertLessEqual(len(clue), 180)

    def test_choose_contact_falls_back_to_contact_page_then_social(self):
        dossier = {"contact_pages": ["https://acme.com/contact"], "social_links": ["https://linkedin.com/company/acme"]}
        self.assertEqual(mod.choose_contact(dossier), "https://acme.com/contact")
        self.assertEqual(mod.choose_contact({"social_links": dossier["social_links"]}), "https://linkedin.com/company/acme")


if __name__ == "__main__":
    unittest.main()
