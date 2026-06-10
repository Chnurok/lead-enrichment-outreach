import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from ui.review_server import ApiError, ReviewStore, build_demo_review, validate_review_payload, ThreadedHTTPServer, Handler


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

    def test_http_get_and_post_review(self):
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
                with urllib.request.urlopen(f"{base}/health") as resp:
                    health = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(health["ok"])

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


if __name__ == "__main__":
    unittest.main()
