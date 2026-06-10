import json
import tempfile
import unittest
from pathlib import Path

from ui.review_server import ApiError, ReviewStore, build_demo_review, validate_review_payload


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


if __name__ == "__main__":
    unittest.main()
