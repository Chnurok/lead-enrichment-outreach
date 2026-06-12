import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skill" / "scripts"
WORKFLOW_SCRIPT = SCRIPTS_DIR / "workflow.py"
BATCH_SCRIPT = SCRIPTS_DIR / "batch_workflow_csv.py"

workflow_spec = importlib.util.spec_from_file_location("workflow", WORKFLOW_SCRIPT)
workflow = importlib.util.module_from_spec(workflow_spec)
sys.path.insert(0, str(SCRIPTS_DIR))
workflow_spec.loader.exec_module(workflow)

batch_spec = importlib.util.spec_from_file_location("batch_workflow_csv", BATCH_SCRIPT)
batch = importlib.util.module_from_spec(batch_spec)
batch_spec.loader.exec_module(batch)


class BatchWorkflowCsvTests(unittest.TestCase):
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
        )
        self.assertEqual(artifact["artifact_type"], "lead_enrichment_outreach_batch_workflow")
        self.assertEqual(artifact["summary"]["ready"], 1)
        self.assertEqual(artifact["input"]["source_csv"], "examples/demo-leads.csv")

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
                    "python3",
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


if __name__ == "__main__":
    unittest.main()
