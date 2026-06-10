import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skill" / "scripts"
SCRIPT = SCRIPTS_DIR / "generate_outreach.py"
spec = importlib.util.spec_from_file_location("generate_outreach", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

WORKFLOW_SCRIPT = SCRIPTS_DIR / "workflow.py"
workflow_spec = importlib.util.spec_from_file_location("workflow", WORKFLOW_SCRIPT)
workflow = importlib.util.module_from_spec(workflow_spec)
sys.path.insert(0, str(SCRIPTS_DIR))
workflow_spec.loader.exec_module(workflow)


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

    def test_dossier_is_ready_uses_review_status(self):
        self.assertTrue(mod.dossier_is_ready({"review": {"status": "ready"}}))
        self.assertFalse(mod.dossier_is_ready({"review": {"status": "review_required"}}))

    def test_cli_refuses_weak_dossier_without_override(self):
        dossier = {
            "company": "Acme",
            "summary": "Acme provides logistics services.",
            "review": {"status": "review_required", "reasons": ["Best available contact looks weak for outreach"]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            dossier_path = Path(tmp) / "dossier.json"
            dossier_path.write_text(json.dumps(dossier), encoding="utf-8")
            proc = subprocess.run([
                "python3", str(SCRIPT), str(dossier_path),
                "--offer", "AI-assisted outreach workflows"
            ], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Refusing to draft outreach", proc.stderr)

    def test_cli_allows_override_for_review_required_dossier(self):
        dossier = {
            "company": "Acme",
            "summary": "Acme provides logistics services.",
            "emails": ["hi@acme.com"],
            "review": {"status": "review_required", "reasons": ["Needs review"]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            dossier_path = Path(tmp) / "dossier.json"
            dossier_path.write_text(json.dumps(dossier), encoding="utf-8")
            proc = subprocess.run([
                "python3", str(SCRIPT), str(dossier_path),
                "--offer", "AI-assisted outreach workflows",
                "--allow-review-required"
            ], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Idea for Acme's outreach flow", proc.stdout)

    def test_workflow_artifact_ready_path_includes_draft(self):
        dossier = {
            "company": "DeepL",
            "primary_domain": "deepl.com",
            "summary": "DeepL provides translation and API products.",
            "emails": ["support@deepl.com"],
            "review": {"status": "ready", "ready_for_outreach": True, "reasons": []},
        }
        artifact = workflow.build_artifact(
            company="DeepL",
            domain="deepl.com",
            offer="AI-assisted lead enrichment and outreach",
            dossier=dossier,
            draft=mod.draft(dossier, "AI-assisted lead enrichment and outreach", "Would Tuesday work?"),
        )
        self.assertEqual(artifact["result"]["status"], "ready")
        self.assertTrue(artifact["result"]["draft_generated"])
        self.assertEqual(artifact["artifacts"]["draft"]["target_contact"], "support@deepl.com")

    def test_workflow_artifact_review_required_has_no_draft_by_default(self):
        dossier = {
            "company": "Mistral AI",
            "primary_domain": "mistral.ai",
            "summary": "Mistral AI provides frontier language models.",
            "emails": ["press@mistral.ai"],
            "review": {"status": "review_required", "ready_for_outreach": False, "reasons": ["Needs review"]},
        }
        artifact = workflow.build_artifact(
            company="Mistral AI",
            domain="mistral.ai",
            offer="AI-assisted lead enrichment and outreach",
            dossier=dossier,
            draft=None,
        )
        self.assertEqual(artifact["result"]["status"], "review_required")
        self.assertTrue(artifact["result"]["requires_review"])
        self.assertFalse(artifact["result"]["draft_generated"])

    def test_workflow_artifact_blocked_path(self):
        dossier = {
            "company": "Unknown Co",
            "primary_domain": None,
            "review": {"status": "blocked", "ready_for_outreach": False, "reasons": ["No primary domain was identified"]},
        }
        artifact = workflow.build_artifact(
            company="Unknown Co",
            offer="AI-assisted lead enrichment and outreach",
            dossier=dossier,
            draft=None,
        )
        self.assertEqual(artifact["result"]["status"], "blocked")
        self.assertFalse(artifact["result"]["ready_for_outreach"])
        self.assertEqual(artifact["artifacts"]["review"]["reasons"][0], "No primary domain was identified")


if __name__ == "__main__":
    unittest.main()
