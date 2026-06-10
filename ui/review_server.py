#!/usr/bin/env python3
"""Minimal local review UI for lead-enrichment-outreach."""

from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_PATH = ROOT / "examples" / "demo-review.json"
DEFAULT_HTML_PATH = ROOT / "ui" / "index.html"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8095"))
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(2 * 1024 * 1024)))
_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class ReviewStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        if not self.path.exists():
            raise ApiError(404, f"Review file not found: {self.path}")
        with self.path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        validate_review_payload(data)
        return data

    def save(self, data):
        validate_review_payload(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return data


def validate_review_payload(data):
    if not isinstance(data, dict):
        raise ApiError(400, "Review payload must be a JSON object")
    if "lead" not in data or not isinstance(data["lead"], dict):
        raise ApiError(400, "Review payload must include lead object")
    if "dossier" not in data or not isinstance(data["dossier"], dict):
        raise ApiError(400, "Review payload must include dossier object")
    if "draft" not in data or not isinstance(data["draft"], dict):
        raise ApiError(400, "Review payload must include draft object")
    if "review_decision" not in data or not isinstance(data["review_decision"], dict):
        raise ApiError(400, "Review payload must include review_decision object")

    draft = data["draft"]
    for field in ("subject", "body"):
        if not isinstance(draft.get(field), str) or not draft[field].strip():
            raise ApiError(400, f"Draft field '{field}' must be a non-empty string")

    decision = data["review_decision"]
    status = decision.get("status")
    if status not in {"approved", "rejected", "needs_review"}:
        raise ApiError(400, "review_decision.status must be approved, rejected, or needs_review")
    if not isinstance(decision.get("updated_at"), str) or not decision["updated_at"].strip():
        raise ApiError(400, "review_decision.updated_at must be a non-empty string")

    dossier = data["dossier"]
    review = dossier.get("review")
    if not isinstance(review, dict) or review.get("status") not in {"ready", "review_required", "blocked"}:
        raise ApiError(400, "dossier.review.status must be ready, review_required, or blocked")


class Handler(BaseHTTPRequestHandler):
    server_version = "LeadReviewUI/0.1"

    def log_message(self, fmt, *args):
        pass

    @property
    def store(self):
        return self.server.store

    @property
    def html_path(self):
        return self.server.html_path

    def _send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, code, text, content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "Invalid Content-Length header") from exc
        if length <= 0:
            raise ApiError(400, "Request body is empty")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, f"Request body exceeds limit of {MAX_BODY_BYTES} bytes")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ApiError(400, "Invalid JSON body") from exc

    def _handle_error(self, exc):
        if isinstance(exc, ApiError):
            self._send_json(exc.status, {"ok": False, "error": exc.message})
        else:
            self._send_json(500, {"ok": False, "error": str(exc)})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send_json(200, {"ok": True, "review_file": str(self.store.path)})
                return
            if parsed.path == "/api/review":
                with _LOCK:
                    data = self.store.load()
                self._send_json(200, data)
                return
            if parsed.path in {"/", "/index.html"}:
                self._send_text(200, self.html_path.read_text(encoding="utf-8"), "text/html; charset=utf-8")
                return
            self._send_json(404, {"ok": False, "error": "Not found"})
        except Exception as exc:
            self._handle_error(exc)

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/review":
                data = self._read_json()
                with _LOCK:
                    saved = self.store.save(data)
                self._send_json(200, {"ok": True, "review": saved})
                return
            self._send_json(404, {"ok": False, "error": "Not found"})
        except Exception as exc:
            self._handle_error(exc)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def build_demo_review(dossier_path: Path, draft_path: Path, output_path: Path):
    with dossier_path.open(encoding="utf-8") as fh:
        dossier = json.load(fh)
    with draft_path.open(encoding="utf-8") as fh:
        draft = json.load(fh)
    payload = {
        "lead": {
            "company": dossier.get("company"),
            "domain": dossier.get("primary_domain"),
            "offer": "AI-assisted lead enrichment and outreach",
        },
        "dossier": dossier,
        "draft": {
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "target_contact": draft.get("target_contact"),
        },
        "review_decision": {
            "status": "needs_review",
            "notes": "",
            "updated_at": "demo-seeded",
        },
    }
    ReviewStore(output_path).save(payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description="Run local review UI for lead-enrichment-outreach")
    parser.add_argument("--review-file", default=str(DEFAULT_REVIEW_PATH), help="Path to review JSON file")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--seed-demo", action="store_true", help="Seed demo review JSON before serving")
    args = parser.parse_args()

    review_path = Path(args.review_file).resolve()
    if args.seed_demo:
        build_demo_review(
            ROOT / "examples" / "demo" / "ready" / "deepl-dossier.json",
            ROOT / "examples" / "demo" / "ready" / "deepl-draft.json",
            review_path,
        )

    server = ThreadedHTTPServer((args.host, args.port), Handler)
    server.store = ReviewStore(review_path)
    server.html_path = DEFAULT_HTML_PATH
    print(f"Review UI running on http://{args.host}:{args.port} using {review_path}")
    server.serve_forever()


if __name__ == "__main__":
    main()
