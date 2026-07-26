import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skill" / "scripts"
WORKFLOW_SCRIPT = SCRIPTS_DIR / "workflow.py"
BATCH_SCRIPT = SCRIPTS_DIR / "batch_workflow_csv.py"
REVIEW_SERVER_SCRIPT = REPO_ROOT / "ui" / "review_server.py"

workflow_spec = importlib.util.spec_from_file_location("workflow", WORKFLOW_SCRIPT)
workflow = importlib.util.module_from_spec(workflow_spec)
sys.path.insert(0, str(SCRIPTS_DIR))
workflow_spec.loader.exec_module(workflow)

batch_spec = importlib.util.spec_from_file_location("batch_workflow_csv", BATCH_SCRIPT)
batch = importlib.util.module_from_spec(batch_spec)
batch_spec.loader.exec_module(batch)

review_server_spec = importlib.util.spec_from_file_location("review_server", REVIEW_SERVER_SCRIPT)
review_server = importlib.util.module_from_spec(review_server_spec)
review_server_spec.loader.exec_module(review_server)


class BatchWorkflowCsvTests(unittest.TestCase):
    def test_summarize_results_includes_quality_metrics(self):
        summary = batch.summarize_results([
            {
                "result": {"status": "ready", "draft_generated": True},
                "artifacts": {
                    "dossier": {
                        "confidence": 0.8,
                        "entity_confidence": 0.7,
                        "contact_confidence": 0.6,
                        "best_contact_email": "hello@acme.com",
                        "summary_source": {"source_type": "page"},
                        "contact_candidates": [{"contact_type": "email", "official": True, "is_primary": True, "outreach_usability": "high"}],
                        "evidence_summary": {
                            "verified_contact_count": 1,
                            "memory_reused_contact_count": 1,
                            "useful_contact_count": 1,
                            "high_usability_contact_count": 1,
                        },
                    }
                },
            },
            {
                "result": {"status": "review_required", "draft_generated": False},
                "artifacts": {
                    "dossier": {
                        "confidence": 0.4,
                        "entity_confidence": 0.5,
                        "contact_confidence": 0.2,
                        "summary_source": {"source_type": "serp"},
                        "contact_candidates": [{"contact_type": "contact_page", "is_primary": True, "outreach_usability": "low"}],
                        "evidence_summary": {
                            "verified_contact_count": 0,
                            "memory_reused_contact_count": 0,
                            "useful_contact_count": 0,
                            "high_usability_contact_count": 0,
                        },
                    }
                },
            },
        ])
        self.assertEqual(summary["verified_contact_leads"], 1)
        self.assertEqual(summary["official_email_leads"], 1)
        self.assertEqual(summary["memory_reused_leads"], 1)
        self.assertEqual(summary["source_backed_summary_leads"], 2)
        self.assertEqual(summary["useful_contact_leads"], 1)
        self.assertEqual(summary["high_usability_contact_leads"], 1)
        self.assertEqual(summary["low_usability_primary_contact_leads"], 1)
        self.assertEqual(summary["average_confidence"], 0.6)
    def test_summarize_results_counts_statuses_and_drafts(self):
        summary = batch.summarize_results([
            {"result": {"status": "ready", "draft_generated": True}},
            {"result": {"status": "review_required", "draft_generated": False}},
            {"result": {"status": "blocked", "draft_generated": False}},
        ])
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["ready"], 1)
        self.assertEqual(summary["review_required"], 1)
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(summary["draft_generated"], 1)

    def test_build_batch_artifact_wraps_summary(self):
        artifact = batch.build_batch_artifact(
            [{"result": {"status": "ready", "draft_generated": True}}],
            source_csv="examples/demo-leads.csv",
            offer="AI-assisted lead enrichment and outreach",
            fast_mode=True,
        )
        self.assertEqual(artifact["artifact_type"], "lead_enrichment_outreach_batch_workflow")
        self.assertEqual(artifact["summary"]["ready"], 1)
        self.assertEqual(artifact["input"]["source_csv"], "examples/demo-leads.csv")
        self.assertTrue(artifact["input"]["fast_mode"])

    def test_cli_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            csv_path = tmp / "leads.csv"
            out_path = tmp / "batch-output.json"
            with csv_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=["company", "region", "domain"])
                writer.writeheader()
                writer.writerow({"company": "DeepL", "region": "", "domain": "deepl.com"})

            proc = subprocess.run(
                [
                    sys.executable,
                    str(BATCH_SCRIPT),
                    str(csv_path),
                    "--offer",
                    "AI-assisted lead enrichment and outreach",
                    "--output",
                    str(out_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            self.assertEqual(proc.stdout, "")
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total"], 1)
            self.assertEqual(len(payload["results"]), 1)
            self.assertEqual(payload["results"][0]["input"]["company"], "DeepL")
            self.assertIn(
                payload["results"][0]["result"]["status"],
                {"ready", "review_required", "blocked"},
            )

    def test_run_batch_passes_fast_mode_to_workflow(self):
        original_run_workflow = batch.workflow.run_workflow
        try:
            calls = []

            def fake_run_workflow(company, **kwargs):
                calls.append((company, kwargs))
                return {
                    "input": {"company": company},
                    "result": {"status": "review_required", "draft_generated": True},
                }

            batch.workflow.run_workflow = fake_run_workflow
            with tempfile.TemporaryDirectory() as tmp:
                csv_path = Path(tmp) / "leads.csv"
                with csv_path.open("w", encoding="utf-8", newline="") as fh:
                    writer = csv.DictWriter(fh, fieldnames=["company", "region", "domain"])
                    writer.writeheader()
                    writer.writerow({"company": "Acme", "region": "Berlin", "domain": "acme.com"})
                artifact = batch.run_batch(csv_path, offer="Offer", fast_mode=True)
        finally:
            batch.workflow.run_workflow = original_run_workflow

        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1]["fast_mode"])
        self.assertTrue(artifact["input"]["fast_mode"])

    def test_workflow_fast_mode_allows_review_required_draft(self):
        original_enrich = workflow.enrich_lead.enrich
        original_draft = workflow.generate_outreach.draft
        try:
            workflow.enrich_lead.enrich = lambda *args, **kwargs: {
                "company": "Acme",
                "primary_domain": "acme.com",
                "best_contact_email": None,
                "contact_pages": ["https://acme.com/contact"],
                "review": {"status": "review_required", "ready_for_outreach": False},
                "trust_signals": {
                    "identity_confidence": 0.36,
                    "contact_confidence": 0.26,
                    "best_contact": {"official": False, "strong": False, "weak": False},
                    "social_identity": {"company_pages": 1},
                },
            }
            workflow.generate_outreach.draft = lambda dossier, offer, cta: {"company": dossier["company"], "subject": "Draft"}
            artifact = workflow.run_workflow("Acme", domain="acme.com", offer="Offer", fast_mode=True)
        finally:
            workflow.enrich_lead.enrich = original_enrich
            workflow.generate_outreach.draft = original_draft

        self.assertEqual(artifact["result"]["status"], "review_required")
        self.assertTrue(artifact["result"]["draft_generated"])
        self.assertTrue(artifact["input"]["fast_mode"])

    def test_workflow_dossier_json_fast_mode_allows_review_required_draft(self):
        original_draft = workflow.generate_outreach.draft
        try:
            workflow.generate_outreach.draft = lambda dossier, offer, cta: {"company": dossier["company"], "subject": "Draft"}
            with tempfile.TemporaryDirectory() as tmp:
                dossier_path = Path(tmp) / "dossier.json"
                dossier_path.write_text(json.dumps({
                    "company": "Acme",
                    "primary_domain": "acme.com",
                    "best_contact_email": None,
                    "contact_pages": ["https://acme.com/contact"],
                    "review": {"status": "review_required", "ready_for_outreach": False},
                    "trust_signals": {
                        "identity_confidence": 0.36,
                        "contact_confidence": 0.26,
                        "best_contact": {"official": False, "strong": False, "weak": False},
                        "social_identity": {"company_pages": 1},
                    },
                }), encoding="utf-8")
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(WORKFLOW_SCRIPT),
                        "--dossier-json",
                        str(dossier_path),
                        "--offer",
                        "Offer",
                        "--fast-mode",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
        finally:
            workflow.generate_outreach.draft = original_draft

        payload = json.loads(proc.stdout)
        self.assertTrue(payload["result"]["draft_generated"])
        self.assertTrue(payload["input"]["fast_mode"])

    def test_review_server_run_batch_from_csv_text_passes_fast_mode(self):
        original_run_workflow = review_server.batch_workflow_csv.workflow.run_workflow
        try:
            calls = []

            def fake_run_workflow(company, **kwargs):
                calls.append((company, kwargs))
                return {
                    "input": {"company": company},
                    "result": {"status": "review_required", "draft_generated": False},
                }

            review_server.batch_workflow_csv.workflow.run_workflow = fake_run_workflow
            artifact = review_server.run_batch_from_csv_text(
                "company,region,domain\nAcme,Berlin,acme.com\n",
                offer="Offer",
                fast_mode=True,
            )
        finally:
            review_server.batch_workflow_csv.workflow.run_workflow = original_run_workflow

        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1]["fast_mode"])
        self.assertTrue(artifact["input"]["fast_mode"])


if __name__ == "__main__":
    unittest.main()
