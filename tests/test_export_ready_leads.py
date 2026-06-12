import csv
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skill" / "scripts" / "export_ready_leads.py"
spec = importlib.util.spec_from_file_location("export_ready_leads", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ExportReadyLeadsTests(unittest.TestCase):
    def sample_batch(self):
        return {
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "artifact_version": "v1",
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {
                            "company": "DeepL",
                            "primary_domain": "deepl.com",
                            "best_contact_email": "support@deepl.com",
                            "best_contact_source": {"source_url": "https://deepl.com/contact"},
                            "summary": "DeepL summary",
                        },
                        "review": {"status": "ready", "next_step": "draft outreach"},
                        "draft": {
                            "subject": "Idea for DeepL's outreach flow",
                            "body": "Draft body",
                            "target_contact": "support@deepl.com",
                        },
                    },
                },
                {
                    "input": {"company": "Mistral AI", "domain": "mistral.ai"},
                    "result": {"status": "review_required"},
                    "artifacts": {
                        "dossier": {"company": "Mistral AI", "primary_domain": "mistral.ai"},
                        "review": {"status": "review_required", "next_step": "review sources"},
                        "draft": None,
                    },
                },
            ],
        }

    def test_ready_results_filters_non_ready(self):
        ready = mod.ready_results(self.sample_batch())
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["input"]["company"], "DeepL")

    def test_build_ready_export_shapes_operational_items(self):
        export = mod.build_ready_export(self.sample_batch())
        self.assertEqual(export["summary"]["ready_count"], 1)
        self.assertEqual(export["summary"]["total_results"], 2)
        self.assertEqual(export["items"][0]["company"], "DeepL")
        self.assertEqual(export["items"][0]["draft_target_contact"], "support@deepl.com")

    def test_cli_writes_json_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            batch_path = tmp / "batch.json"
            out_json = tmp / "ready.json"
            out_csv = tmp / "ready.csv"
            batch_path.write_text(json.dumps(self.sample_batch()), encoding="utf-8")

            subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(batch_path),
                    "--output-json",
                    str(out_json),
                    "--output-csv",
                    str(out_csv),
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["ready_count"], 1)

            with out_csv.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["company"], "DeepL")


if __name__ == "__main__":
    unittest.main()
