import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from ui.review_server import ApiError, ReviewStore, approve_ready_saved_reviews, bootstrap_demo_artifacts, build_approved_bundle, build_approved_bundle_zip_base64, build_approved_export, build_demo_batch, build_demo_review, build_handoff_bundle, build_handoff_bundle_zip_base64, build_saved_review_path, export_ready_batch, export_ready_batch_csv_text, generate_missing_ready_drafts, list_saved_reviews, load_approved_bundle_zip_base64, load_handoff_bundle_zip_base64, load_saved_review, run_batch_from_csv_text, save_review_payloads, validate_review_payload, ThreadedHTTPServer, Handler


class ReviewServerTests(unittest.TestCase):
    def sample_payload(self):
        return {
            "lead": {"company": "Acme", "domain": "acme.com", "offer": "Offer"},
            "dossier": {
                "company": "Acme",
                "review": {"status": "review_required", "reasons": [], "next_step": "check", "top_contact_candidates": []},
            },
            "draft": {"subject": "Hi", "body": "Body", "target_contact": "hi@acme.com"},
            "review_decision": {"status": "needs_review", "notes": "", "updated_at": "now"},
        }

    def test_validate_review_payload_accepts_minimal_valid_shape(self):
        validate_review_payload(self.sample_payload())

    def test_validate_review_payload_rejects_invalid_decision(self):
        payload = self.sample_payload()
        payload["review_decision"]["status"] = "ready"
        with self.assertRaises(ApiError):
            validate_review_payload(payload)

    def test_validate_review_payload_rejects_approval_for_non_ready_dossier(self):
        payload = self.sample_payload()
        payload["review_decision"]["status"] = "approved"
        with self.assertRaises(ApiError):
            validate_review_payload(payload)

    def test_review_store_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            store = ReviewStore(path)
            payload = self.sample_payload()
            store.save(payload)
            loaded = store.load()
        self.assertEqual(loaded["draft"]["subject"], "Hi")
        self.assertEqual(loaded["review_decision"]["status"], "needs_review")

    def test_build_demo_review_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dossier = tmp / "dossier.json"
            draft = tmp / "draft.json"
            output = tmp / "review.json"
            dossier.write_text(json.dumps({
                "company": "Acme",
                "primary_domain": "acme.com",
                "review": {"status": "ready", "reasons": [], "next_step": "draft", "top_contact_candidates": []}
            }), encoding="utf-8")
            draft.write_text(json.dumps({"subject": "Subj", "body": "Body", "target_contact": "x@acme.com"}), encoding="utf-8")
            payload = build_demo_review(dossier, draft, output)
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["draft"]["subject"], "Subj")
        self.assertEqual(saved["lead"]["company"], "Acme")
        self.assertEqual(saved["review_decision"]["status"], "needs_review")

    def test_build_demo_batch_writes_artifact(self):
        import ui.review_server as review_server

        original_csv = review_server.DEFAULT_DEMO_LEADS_CSV_PATH
        original_run = review_server.run_batch_from_csv_text
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            csv_path = tmp / "demo.csv"
            output = tmp / "demo-output.json"
            csv_path.write_text("company,domain\nAcme,acme.com\n", encoding="utf-8")

            def fake_run_batch(csv_text, offer=None, query_mode="smart", allow_review_required=False):
                self.assertIn("Acme", csv_text)
                self.assertEqual(offer, "Offer")
                self.assertEqual(query_mode, "basic")
                return {"artifact_type": "lead_enrichment_outreach_batch_workflow", "summary": {"total": 1}, "results": []}

            review_server.DEFAULT_DEMO_LEADS_CSV_PATH = csv_path
            review_server.run_batch_from_csv_text = fake_run_batch
            try:
                artifact = build_demo_batch(output, offer="Offer", query_mode="basic")
            finally:
                review_server.DEFAULT_DEMO_LEADS_CSV_PATH = original_csv
                review_server.run_batch_from_csv_text = original_run

            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(artifact["summary"]["total"], 1)
        self.assertEqual(saved["artifact_type"], "lead_enrichment_outreach_batch_workflow")

    def test_bootstrap_demo_artifacts_seeds_review_and_batch(self):
        import ui.review_server as review_server

        original_build_review = review_server.build_demo_review
        original_build_batch = review_server.build_demo_batch
        calls = []

        def fake_build_review(dossier_path, draft_path, output_path):
            calls.append(("review", output_path))
            output_path.write_text("{}", encoding="utf-8")
            return {"ok": True}

        def fake_build_batch(output_path, offer=None, query_mode="smart", allow_review_required=False):
            calls.append(("batch", output_path, offer, query_mode))
            output_path.write_text("{}", encoding="utf-8")
            return {"artifact_type": "lead_enrichment_outreach_batch_workflow"}

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            review_path = tmp / "demo-review.json"
            batch_path = tmp / "demo-output.json"
            review_server.build_demo_review = fake_build_review
            review_server.build_demo_batch = fake_build_batch
            try:
                bootstrap_demo_artifacts(review_path, batch_path, offer="Offer", query_mode="basic")
            finally:
                review_server.build_demo_review = original_build_review
                review_server.build_demo_batch = original_build_batch

        self.assertEqual(calls[0][0], "review")
        self.assertEqual(calls[1], ("batch", batch_path, "Offer", "basic"))

    def test_build_saved_review_path_uses_company_slug(self):
        payload = self.sample_payload()
        path = build_saved_review_path(payload)
        self.assertTrue(str(path).endswith("examples/saved-reviews/acme-review.json"))

    def test_run_batch_from_csv_text_builds_batch_artifact(self):
        import ui.review_server as review_server

        original = review_server.batch_workflow_csv.workflow.run_workflow
        calls = []

        def fake_run_workflow(company, domain=None, offer=None, region=None, query_mode="smart", allow_review_required=False):
            calls.append({
                "company": company,
                "domain": domain,
                "offer": offer,
                "region": region,
                "query_mode": query_mode,
                "allow_review_required": allow_review_required,
            })
            return {
                "input": {"company": company, "domain": domain, "offer": offer},
                "result": {"status": "ready", "draft_generated": bool(offer)},
                "artifacts": {"dossier": {"company": company, "primary_domain": domain, "review": {"status": "ready"}}, "draft": {"subject": "Hi", "body": "Body"}},
            }

        review_server.batch_workflow_csv.workflow.run_workflow = fake_run_workflow
        try:
            artifact = run_batch_from_csv_text(
                "company,region,domain\nAcme,US,acme.com\nDeepL,,deepl.com\n",
                offer="Offer",
                query_mode="basic",
                allow_review_required=True,
            )
        finally:
            review_server.batch_workflow_csv.workflow.run_workflow = original

        self.assertEqual(artifact["summary"]["total"], 2)
        self.assertEqual(artifact["summary"]["ready"], 2)
        self.assertEqual(calls[0]["company"], "Acme")
        self.assertEqual(calls[0]["query_mode"], "basic")
        self.assertTrue(calls[0]["allow_review_required"])

    def test_run_batch_from_csv_text_rejects_missing_company_column(self):
        with self.assertRaises(ApiError):
            run_batch_from_csv_text("name,domain\nAcme,acme.com\n")

    def test_export_ready_batch_shapes_ops_artifact(self):
        export = export_ready_batch({
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
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                    },
                }
            ],
        })
        self.assertEqual(export["summary"]["ready_count"], 1)
        self.assertEqual(export["items"][0]["company"], "DeepL")

    def test_export_ready_batch_csv_text_includes_headers(self):
        csv_text = export_ready_batch_csv_text({
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {"company": "DeepL", "primary_domain": "deepl.com"},
                        "review": {"status": "ready"},
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                    },
                }
            ],
        })
        self.assertIn("company,domain", csv_text)
        self.assertIn("DeepL,deepl.com", csv_text)

    def test_list_and_load_saved_reviews(self):
        import ui.review_server as review_server

        with tempfile.TemporaryDirectory() as tmp:
            original_root = review_server.ROOT
            try:
                review_server.ROOT = Path(tmp)
                saved_dir = review_server.ROOT / "examples" / "saved-reviews"
                payload = self.sample_payload()
                ReviewStore(saved_dir / "acme-review.json").save(payload)

                items = list_saved_reviews()
                loaded = load_saved_review("acme-review.json")
            finally:
                review_server.ROOT = original_root

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["company"], "Acme")
        self.assertEqual(loaded["lead"]["company"], "Acme")

    def test_load_saved_review_rejects_invalid_filename(self):
        with self.assertRaises(ApiError):
            load_saved_review("../bad.json")

    def test_save_review_payloads_saves_many(self):
        import ui.review_server as review_server

        with tempfile.TemporaryDirectory() as tmp:
            original_root = review_server.ROOT
            try:
                review_server.ROOT = Path(tmp)
                saved = save_review_payloads([self.sample_payload(), {
                    "lead": {"company": "DeepL", "domain": "deepl.com", "offer": "Offer"},
                    "dossier": {"company": "DeepL", "review": {"status": "ready", "reasons": [], "next_step": "draft", "top_contact_candidates": []}},
                    "draft": {"subject": "Hi", "body": "Body", "target_contact": "hi@deepl.com"},
                    "review_decision": {"status": "needs_review", "notes": "", "updated_at": "now"},
                }])
            finally:
                review_server.ROOT = original_root
        self.assertEqual(len(saved), 2)

    def test_generate_missing_ready_drafts_fills_ready_items(self):
        batch = {
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "summary": {"draft_generated": 0},
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com", "offer": "AI-assisted lead enrichment and outreach"},
                    "result": {"status": "ready", "draft_generated": False},
                    "artifacts": {
                        "dossier": {"company": "DeepL", "summary": "DeepL provides translation APIs.", "emails": ["support@deepl.com"], "review": {"status": "ready"}},
                        "draft": None,
                    },
                }
            ],
        }
        result = generate_missing_ready_drafts(batch)
        draft = result["batch"]["results"][0]["artifacts"]["draft"]
        self.assertEqual(result["generated_count"], 1)
        self.assertIn("Idea for DeepL's outreach flow", draft["subject"])

    def test_approve_ready_saved_reviews_marks_ready_reviews_approved(self):
        import ui.review_server as review_server

        payload = {
            "lead": {"company": "DeepL", "domain": "deepl.com", "offer": "Offer"},
            "dossier": {"company": "DeepL", "review": {"status": "ready", "reasons": [], "next_step": "draft", "top_contact_candidates": []}},
            "draft": {"subject": "Hi", "body": "Body", "target_contact": "hi@deepl.com"},
            "review_decision": {"status": "needs_review", "notes": "", "updated_at": "now"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            original_root = review_server.ROOT
            try:
                review_server.ROOT = Path(tmp)
                path = build_saved_review_path(payload)
                ReviewStore(path).save(payload)
                approved = approve_ready_saved_reviews([path.name])
                saved = ReviewStore(path).load()
            finally:
                review_server.ROOT = original_root
        self.assertEqual(len(approved), 1)
        self.assertEqual(saved["review_decision"]["status"], "approved")

    def test_build_approved_export_filters_by_approved_saved_reviews(self):
        batch = {
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "artifact_version": "v1",
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {"company": "DeepL", "primary_domain": "deepl.com", "best_contact_email": "support@deepl.com", "summary": "DeepL summary"},
                        "review": {"status": "ready", "next_step": "draft outreach"},
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                    },
                },
                {
                    "input": {"company": "Acme", "domain": "acme.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {"company": "Acme", "primary_domain": "acme.com", "best_contact_email": "hi@acme.com", "summary": "Acme summary"},
                        "review": {"status": "ready", "next_step": "draft outreach"},
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "hi@acme.com"},
                    },
                }
            ],
        }
        export = build_approved_export(batch, saved_reviews=[
            {"company": "DeepL", "review_status": "ready", "decision_status": "approved"},
            {"company": "Acme", "review_status": "ready", "decision_status": "needs_review"},
        ])
        self.assertEqual(export["summary"]["approved_ready_count"], 1)
        self.assertEqual(export["items"][0]["company"], "DeepL")

    def test_build_approved_bundle_contains_only_approved_ready_assets(self):
        batch = {
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "artifact_version": "v1",
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {"company": "DeepL", "primary_domain": "deepl.com", "best_contact_email": "support@deepl.com", "summary": "DeepL summary"},
                        "review": {"status": "ready", "next_step": "draft outreach"},
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                    },
                }
            ],
        }
        bundle = build_approved_bundle(batch, saved_reviews=[
            {"company": "DeepL", "review_status": "ready", "decision_status": "approved", "filename": "deepl-review.json"}
        ])
        self.assertEqual(bundle["summary"]["approved_ready_count"], 1)
        self.assertEqual(bundle["saved_reviews"][0]["filename"], "deepl-review.json")

    def test_build_approved_bundle_zip_base64_contains_expected_files(self):
        import base64
        import zipfile

        batch = {
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "artifact_version": "v1",
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {"company": "DeepL", "primary_domain": "deepl.com", "best_contact_email": "support@deepl.com", "summary": "DeepL summary"},
                        "review": {"status": "ready", "next_step": "draft outreach"},
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                    },
                }
            ],
        }
        encoded = build_approved_bundle_zip_base64(batch, saved_reviews=[
            {"company": "DeepL", "review_status": "ready", "decision_status": "approved", "filename": "deepl-review.json"}
        ])
        archive_bytes = base64.b64decode(encoded.encode("ascii"))
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
            names = set(zf.namelist())
        self.assertIn("approved-bundle-summary.json", names)
        self.assertIn("approved-ready-leads.json", names)
        self.assertIn("approved-ready-leads.csv", names)
        self.assertIn("approved-saved-reviews.json", names)

    def test_load_approved_bundle_zip_base64_restores_batch_and_saved_reviews(self):
        batch = {
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "artifact_version": "v1",
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {"company": "DeepL", "primary_domain": "deepl.com", "best_contact_email": "support@deepl.com", "summary": "DeepL summary"},
                        "review": {"status": "ready", "next_step": "draft outreach"},
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                    },
                }
            ],
        }
        encoded = build_approved_bundle_zip_base64(batch, saved_reviews=[
            {"company": "DeepL", "review_status": "ready", "decision_status": "approved", "filename": "deepl-review.json"}
        ])
        imported = load_approved_bundle_zip_base64(encoded)
        self.assertEqual(imported["bundle_summary"]["approved_ready_count"], 1)
        self.assertEqual(imported["batch"]["results"][0]["input"]["company"], "DeepL")
        self.assertEqual(imported["saved_reviews"][0]["filename"], "deepl-review.json")

    def test_build_handoff_bundle_includes_ready_and_saved_reviews(self):
        batch = {
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "artifact_version": "v1",
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {"company": "DeepL", "primary_domain": "deepl.com"},
                        "review": {"status": "ready"},
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                    },
                }
            ],
        }
        bundle = build_handoff_bundle(batch, saved_reviews=[{"filename": "acme-review.json"}])
        self.assertEqual(bundle["summary"]["ready_count"], 1)
        self.assertEqual(bundle["summary"]["saved_reviews_count"], 1)

    def test_build_handoff_bundle_zip_base64_contains_expected_files(self):
        import base64
        import zipfile

        batch = {
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "artifact_version": "v1",
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {"company": "DeepL", "primary_domain": "deepl.com"},
                        "review": {"status": "ready"},
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                    },
                }
            ],
        }
        encoded = build_handoff_bundle_zip_base64(batch, saved_reviews=[{"filename": "acme-review.json"}])
        archive_bytes = base64.b64decode(encoded.encode("ascii"))
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
            names = set(zf.namelist())
        self.assertIn("bundle-summary.json", names)
        self.assertIn("ready-leads.json", names)
        self.assertIn("ready-leads.csv", names)
        self.assertIn("saved-reviews.json", names)

    def test_load_handoff_bundle_zip_base64_restores_batch_and_saved_reviews(self):
        batch = {
            "artifact_type": "lead_enrichment_outreach_batch_workflow",
            "artifact_version": "v1",
            "results": [
                {
                    "input": {"company": "DeepL", "domain": "deepl.com"},
                    "result": {"status": "ready"},
                    "artifacts": {
                        "dossier": {"company": "DeepL", "primary_domain": "deepl.com", "best_contact_email": "support@deepl.com"},
                        "review": {"status": "ready", "next_step": "draft outreach"},
                        "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                    },
                }
            ],
        }
        encoded = build_handoff_bundle_zip_base64(batch, saved_reviews=[{"filename": "acme-review.json"}])
        imported = load_handoff_bundle_zip_base64(encoded)
        self.assertEqual(imported["bundle_summary"]["ready_count"], 1)
        self.assertEqual(imported["batch"]["results"][0]["input"]["company"], "DeepL")
        self.assertEqual(imported["saved_reviews"][0]["filename"], "acme-review.json")

    def test_http_get_and_post_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)
            demo_batch_path = Path(tmp) / "demo-output.json"
            demo_batch_path.write_text(json.dumps({
                "artifact_type": "lead_enrichment_outreach_batch_workflow",
                "summary": {"ready": 1, "review_required": 0, "blocked": 0, "total": 1},
                "results": [],
            }), encoding="utf-8")

            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            server.demo_batch_path = demo_batch_path
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urllib.request.urlopen(f"{base}/healthz") as resp:
                    health = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(health["ok"])
                self.assertEqual(health["review_file"], str(path))
                self.assertEqual(health["demo_batch_file"], str(demo_batch_path))
                self.assertTrue(health["demo_batch_exists"])
                self.assertEqual(health["demo_batch_summary"]["ready"], 1)

                with urllib.request.urlopen(f"{base}/api/review") as resp:
                    review = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(review["lead"]["company"], "Acme")

                payload["dossier"]["review"]["status"] = "ready"
                payload["review_decision"]["status"] = "approved"
                req = urllib.request.Request(
                    f"{base}/api/review",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    saved = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(saved["ok"])
                self.assertEqual(saved["review"]["review_decision"]["status"], "approved")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_rejects_approving_non_ready_dossier(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                payload["review_decision"]["status"] = "approved"
                req = urllib.request.Request(
                    f"{base}/api/review",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req)
                body = json.loads(ctx.exception.read().decode("utf-8"))
                self.assertIn("Cannot mark review approved", body["error"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_serves_demo_batch_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            demo_batch_path = Path(__file__).resolve().parents[1] / "examples" / "demo-output.json"
            original = demo_batch_path.read_text(encoding="utf-8") if demo_batch_path.exists() else None
            demo_batch_path.write_text(json.dumps([{"company": "DeepL", "review": {"status": "ready"}}]), encoding="utf-8")

            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urllib.request.urlopen(f"{base}/api/demo-batch") as resp:
                    batch = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(batch[0]["company"], "DeepL")
            finally:
                if original is None:
                    demo_batch_path.unlink(missing_ok=True)
                else:
                    demo_batch_path.write_text(original, encoding="utf-8")
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_save_as_review_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            saved_path = build_saved_review_path(payload)
            try:
                if saved_path.exists():
                    saved_path.unlink()
                base = f"http://127.0.0.1:{server.server_address[1]}"
                req = urllib.request.Request(
                    f"{base}/api/review/save-as",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    saved = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(saved["ok"])
                self.assertTrue(saved_path.exists())
            finally:
                saved_path.unlink(missing_ok=True)
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_batch_run(self):
        import ui.review_server as review_server

        original = review_server.batch_workflow_csv.workflow.run_workflow

        def fake_run_workflow(company, domain=None, offer=None, region=None, query_mode="smart", allow_review_required=False):
            return {
                "input": {"company": company, "domain": domain, "offer": offer},
                "result": {"status": "ready", "draft_generated": True},
                "artifacts": {
                    "dossier": {
                        "company": company,
                        "primary_domain": domain,
                        "best_contact_email": f"hi@{domain}",
                        "review": {"status": "ready", "reasons": [], "next_step": "draft", "top_contact_candidates": []},
                    },
                    "draft": {"subject": "Subj", "body": "Body", "target_contact": f"hi@{domain}"},
                },
            }

        review_server.batch_workflow_csv.workflow.run_workflow = fake_run_workflow
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "review.json"
                payload = self.sample_payload()
                ReviewStore(path).save(payload)

                server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
                server.store = ReviewStore(path)
                server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base = f"http://127.0.0.1:{server.server_address[1]}"
                    req = urllib.request.Request(
                        f"{base}/api/batch/run",
                        data=json.dumps({
                            "csv_text": "company,region,domain\nAcme,US,acme.com\n",
                            "offer": "Offer",
                            "query_mode": "smart",
                            "allow_review_required": False,
                        }).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req) as resp:
                        batch = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(batch["ok"])
                    self.assertEqual(batch["batch"]["summary"]["ready"], 1)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
        finally:
            review_server.batch_workflow_csv.workflow.run_workflow = original

    def test_http_batch_export_ready_json_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                batch = {
                    "artifact_type": "lead_enrichment_outreach_batch_workflow",
                    "results": [
                        {
                            "input": {"company": "DeepL", "domain": "deepl.com"},
                            "result": {"status": "ready"},
                            "artifacts": {
                                "dossier": {"company": "DeepL", "primary_domain": "deepl.com", "best_contact_email": "support@deepl.com"},
                                "review": {"status": "ready", "next_step": "draft outreach"},
                                "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                            },
                        }
                    ],
                }

                json_req = urllib.request.Request(
                    f"{base}/api/batch/export-ready",
                    data=json.dumps({"batch": batch}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(json_req) as resp:
                    export_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(export_payload["ok"])
                self.assertEqual(export_payload["export"]["summary"]["ready_count"], 1)

                csv_req = urllib.request.Request(
                    f"{base}/api/batch/export-ready-csv",
                    data=json.dumps({"batch": batch}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(csv_req) as resp:
                    csv_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(csv_payload["ok"])
                self.assertIn("DeepL", csv_payload["csv_text"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_batch_generate_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                batch = {
                    "artifact_type": "lead_enrichment_outreach_batch_workflow",
                    "summary": {"draft_generated": 0},
                    "results": [
                        {
                            "input": {"company": "DeepL", "domain": "deepl.com", "offer": "AI-assisted lead enrichment and outreach"},
                            "result": {"status": "ready", "draft_generated": False},
                            "artifacts": {
                                "dossier": {"company": "DeepL", "summary": "DeepL provides translation APIs.", "emails": ["support@deepl.com"], "review": {"status": "ready"}},
                                "draft": None,
                            },
                        }
                    ],
                }
                req = urllib.request.Request(
                    f"{base}/api/batch/generate-drafts",
                    data=json.dumps({"batch": batch, "offer": "AI-assisted lead enrichment and outreach"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    generated_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(generated_payload["ok"])
                self.assertEqual(generated_payload["generated_count"], 1)
                self.assertIn("Idea for DeepL's outreach flow", generated_payload["batch"]["results"][0]["artifacts"]["draft"]["subject"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_saved_reviews_list_and_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            saved_path = build_saved_review_path(payload)
            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                saved_path.parent.mkdir(parents=True, exist_ok=True)
                ReviewStore(saved_path).save(payload)
                base = f"http://127.0.0.1:{server.server_address[1]}"

                with urllib.request.urlopen(f"{base}/api/saved-reviews") as resp:
                    list_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(list_payload["ok"])
                self.assertEqual(list_payload["items"][0]["company"], "Acme")

                req = urllib.request.Request(
                    f"{base}/api/saved-reviews/open",
                    data=json.dumps({"filename": saved_path.name}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    open_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(open_payload["ok"])
                self.assertEqual(open_payload["review"]["lead"]["company"], "Acme")
            finally:
                saved_path.unlink(missing_ok=True)
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_saved_reviews_save_many(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            saved_path = build_saved_review_path(payload)
            deep_payload = {
                "lead": {"company": "DeepL", "domain": "deepl.com", "offer": "Offer"},
                "dossier": {"company": "DeepL", "review": {"status": "ready", "reasons": [], "next_step": "draft", "top_contact_candidates": []}},
                "draft": {"subject": "Hi", "body": "Body", "target_contact": "hi@deepl.com"},
                "review_decision": {"status": "needs_review", "notes": "", "updated_at": "now"},
            }
            deep_path = build_saved_review_path(deep_payload)
            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                req = urllib.request.Request(
                    f"{base}/api/saved-reviews/save-many",
                    data=json.dumps({"reviews": [payload, deep_payload]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    saved_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(saved_payload["ok"])
                self.assertEqual(saved_payload["count"], 2)
                self.assertTrue(saved_path.exists())
                self.assertTrue(deep_path.exists())
            finally:
                saved_path.unlink(missing_ok=True)
                deep_path.unlink(missing_ok=True)
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_saved_reviews_approve_many_and_export_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            deep_payload = {
                "lead": {"company": "DeepL", "domain": "deepl.com", "offer": "Offer"},
                "dossier": {"company": "DeepL", "review": {"status": "ready", "reasons": [], "next_step": "draft", "top_contact_candidates": []}},
                "draft": {"subject": "Hi", "body": "Body", "target_contact": "hi@deepl.com"},
                "review_decision": {"status": "needs_review", "notes": "", "updated_at": "now"},
            }
            deep_path = build_saved_review_path(deep_payload)
            batch = {
                "artifact_type": "lead_enrichment_outreach_batch_workflow",
                "results": [
                    {
                        "input": {"company": "DeepL", "domain": "deepl.com"},
                        "result": {"status": "ready"},
                        "artifacts": {
                            "dossier": {"company": "DeepL", "primary_domain": "deepl.com", "best_contact_email": "hi@deepl.com", "summary": "DeepL summary"},
                            "review": {"status": "ready", "next_step": "draft outreach"},
                            "draft": {"subject": "Hi", "body": "Body", "target_contact": "hi@deepl.com"},
                        },
                    }
                ],
            }

            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                ReviewStore(deep_path).save(deep_payload)
                base = f"http://127.0.0.1:{server.server_address[1]}"
                approve_req = urllib.request.Request(
                    f"{base}/api/saved-reviews/approve-many",
                    data=json.dumps({"filenames": [deep_path.name]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(approve_req) as resp:
                    approve_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(approve_payload["ok"])
                self.assertEqual(approve_payload["count"], 1)

                export_req = urllib.request.Request(
                    f"{base}/api/batch/export-approved",
                    data=json.dumps({"batch": batch}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(export_req) as resp:
                    export_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(export_payload["ok"])
                self.assertEqual(export_payload["export"]["summary"]["approved_ready_count"], 1)

                bundle_req = urllib.request.Request(
                    f"{base}/api/batch/export-approved-bundle-zip",
                    data=json.dumps({"batch": batch}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(bundle_req) as resp:
                    bundle_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(bundle_payload["ok"])
                self.assertEqual(bundle_payload["filename"], "approved-ready-bundle.zip")

                import_req = urllib.request.Request(
                    f"{base}/api/batch/import-approved-bundle-zip",
                    data=json.dumps({"zip_base64": bundle_payload["zip_base64"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(import_req) as resp:
                    import_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(import_payload["ok"])
                self.assertEqual(import_payload["imported"]["bundle_summary"]["approved_ready_count"], 1)
            finally:
                deep_path.unlink(missing_ok=True)
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_batch_export_bundle_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            saved_path = build_saved_review_path(payload)
            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                saved_path.parent.mkdir(parents=True, exist_ok=True)
                ReviewStore(saved_path).save(payload)
                base = f"http://127.0.0.1:{server.server_address[1]}"
                batch = {
                    "artifact_type": "lead_enrichment_outreach_batch_workflow",
                    "results": [
                        {
                            "input": {"company": "DeepL", "domain": "deepl.com"},
                            "result": {"status": "ready"},
                            "artifacts": {
                                "dossier": {"company": "DeepL", "primary_domain": "deepl.com", "best_contact_email": "support@deepl.com"},
                                "review": {"status": "ready", "next_step": "draft outreach"},
                                "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                            },
                        }
                    ],
                }
                req = urllib.request.Request(
                    f"{base}/api/batch/export-bundle-zip",
                    data=json.dumps({"batch": batch}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    bundle_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(bundle_payload["ok"])
                self.assertEqual(bundle_payload["filename"], "lead-handoff-bundle.zip")
                self.assertTrue(bundle_payload["zip_base64"])
            finally:
                saved_path.unlink(missing_ok=True)
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_http_batch_import_bundle_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            payload = self.sample_payload()
            ReviewStore(path).save(payload)

            server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
            server.store = ReviewStore(path)
            server.html_path = Path(__file__).resolve().parents[1] / "ui" / "index.html"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                batch = {
                    "artifact_type": "lead_enrichment_outreach_batch_workflow",
                    "artifact_version": "v1",
                    "results": [
                        {
                            "input": {"company": "DeepL", "domain": "deepl.com"},
                            "result": {"status": "ready"},
                            "artifacts": {
                                "dossier": {"company": "DeepL", "primary_domain": "deepl.com", "best_contact_email": "support@deepl.com"},
                                "review": {"status": "ready", "next_step": "draft outreach"},
                                "draft": {"subject": "Subj", "body": "Body", "target_contact": "support@deepl.com"},
                            },
                        }
                    ],
                }
                encoded = build_handoff_bundle_zip_base64(batch, saved_reviews=[{"filename": "acme-review.json"}])
                req = urllib.request.Request(
                    f"{base}/api/batch/import-bundle-zip",
                    data=json.dumps({"zip_base64": encoded}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    imported_payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(imported_payload["ok"])
                self.assertEqual(imported_payload["imported"]["batch"]["results"][0]["input"]["company"], "DeepL")
                self.assertEqual(imported_payload["imported"]["saved_reviews"][0]["filename"], "acme-review.json")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
