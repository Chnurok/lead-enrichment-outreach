#!/usr/bin/env python3
"""Minimal local review UI for lead-enrichment-outreach."""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "skill" / "scripts"
DEFAULT_REVIEW_PATH = ROOT / "examples" / "demo-review.json"
DEFAULT_HTML_PATH = ROOT / "ui" / "index.html"
DEFAULT_DEMO_DOSSIER_PATH = ROOT / "examples" / "demo" / "ready" / "deepl-dossier.json"
DEFAULT_DEMO_DRAFT_PATH = ROOT / "examples" / "demo" / "ready" / "deepl-draft.json"
DEFAULT_DEMO_LEADS_CSV_PATH = ROOT / "examples" / "demo-leads.csv"
DEFAULT_DEMO_BATCH_PATH = ROOT / "examples" / "demo-output.json"
DEFAULT_DEMO_OFFER = "AI-assisted lead enrichment and outreach"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8095"))
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(2 * 1024 * 1024)))
_LOCK = threading.Lock()

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import batch_workflow_csv
import export_ready_leads
import generate_outreach


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


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in (value or "").strip())
    compact = "-".join(part for part in cleaned.split("-") if part)
    return compact or "lead"


def build_saved_review_path(review_payload: dict) -> Path:
    lead = review_payload.get("lead") or {}
    company = slugify(lead.get("company") or "lead")
    return ROOT / "examples" / "saved-reviews" / f"{company}-review.json"


def list_saved_reviews():
    base = ROOT / "examples" / "saved-reviews"
    base.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(base.glob("*.json")):
        try:
            payload = ReviewStore(path).load()
        except ApiError:
            continue
        items.append({
            "filename": path.name,
            "path": str(path),
            "company": ((payload.get("lead") or {}).get("company")) or "Unknown company",
            "domain": ((payload.get("lead") or {}).get("domain")) or "n/a",
            "review_status": (((payload.get("dossier") or {}).get("review") or {}).get("status")) or "unknown",
            "decision_status": ((payload.get("review_decision") or {}).get("status")) or "unknown",
            "updated_at": ((payload.get("review_decision") or {}).get("updated_at")) or "unknown",
        })
    return items


def load_saved_review(filename: str):
    if not isinstance(filename, str) or not filename.strip():
        raise ApiError(400, "filename must be a non-empty string")
    if "/" in filename or "\\" in filename or not filename.endswith(".json"):
        raise ApiError(400, "invalid saved review filename")
    path = ROOT / "examples" / "saved-reviews" / filename
    return ReviewStore(path).load()


def save_review_payloads(review_payloads):
    if not isinstance(review_payloads, list) or not review_payloads:
        raise ApiError(400, "reviews must be a non-empty array")
    saved = []
    for payload in review_payloads:
        validate_review_payload(payload)
        output_path = build_saved_review_path(payload)
        ReviewStore(output_path).save(payload)
        saved.append({
            "company": ((payload.get("lead") or {}).get("company")) or "Unknown company",
            "path": str(output_path),
        })
    return saved


def approve_ready_saved_reviews(filenames):
    if not isinstance(filenames, list) or not filenames:
        raise ApiError(400, "filenames must be a non-empty array")
    approved = []
    for filename in filenames:
        payload = load_saved_review(filename)
        review = ((payload.get("dossier") or {}).get("review")) or {}
        if review.get("status") != "ready":
            continue
        payload["review_decision"] = {
            **(payload.get("review_decision") or {}),
            "status": "approved",
            "updated_at": "bulk-approved",
        }
        output_path = build_saved_review_path(payload)
        ReviewStore(output_path).save(payload)
        approved.append({
            "company": ((payload.get("lead") or {}).get("company")) or "Unknown company",
            "filename": output_path.name,
        })
    return approved


def build_approved_export(batch_artifact, saved_reviews=None):
    saved_reviews = saved_reviews if saved_reviews is not None else list_saved_reviews()
    approved_companies = {
        str(item.get("company") or "").lower()
        for item in saved_reviews
        if item.get("decision_status") == "approved" and item.get("review_status") == "ready"
    }
    ready_export = export_ready_batch(batch_artifact)
    items = [
        item for item in ready_export["items"]
        if str(item.get("company") or "").lower() in approved_companies
    ]
    return {
        "artifact_type": "lead_enrichment_outreach_approved_export",
        "artifact_version": ready_export.get("artifact_version", "v1"),
        "summary": {
            "approved_ready_count": len(items),
            "ready_count": ready_export["summary"]["ready_count"],
        },
        "items": items,
    }


def approved_export_csv_text(batch_artifact, saved_reviews=None):
    export = build_approved_export(batch_artifact, saved_reviews=saved_reviews)
    buffer = io.StringIO()
    fieldnames = [
        "company",
        "domain",
        "best_contact_email",
        "best_contact_source_url",
        "summary",
        "review_status",
        "next_step",
        "draft_subject",
        "draft_body",
        "draft_target_contact",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(export["items"])
    return buffer.getvalue()


def build_approved_bundle(batch_artifact, saved_reviews=None):
    saved_reviews = saved_reviews if saved_reviews is not None else list_saved_reviews()
    approved_export = build_approved_export(batch_artifact, saved_reviews=saved_reviews)
    approved_saved_reviews = [
        item for item in saved_reviews
        if item.get("decision_status") == "approved" and item.get("review_status") == "ready"
    ]
    return {
        "artifact_type": "lead_enrichment_outreach_approved_bundle",
        "artifact_version": approved_export.get("artifact_version", "v1"),
        "summary": {
            "approved_ready_count": approved_export["summary"]["approved_ready_count"],
            "saved_reviews_count": len(approved_saved_reviews),
        },
        "approved_export": approved_export,
        "saved_reviews": approved_saved_reviews,
    }


def build_approved_bundle_zip_base64(batch_artifact, saved_reviews=None):
    bundle = build_approved_bundle(batch_artifact, saved_reviews=saved_reviews)
    approved_csv = approved_export_csv_text(batch_artifact, saved_reviews=saved_reviews)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("approved-bundle-summary.json", json.dumps(bundle["summary"], ensure_ascii=False, indent=2) + "\n")
        zf.writestr("approved-ready-leads.json", json.dumps(bundle["approved_export"], ensure_ascii=False, indent=2) + "\n")
        zf.writestr("approved-ready-leads.csv", approved_csv)
        zf.writestr("approved-saved-reviews.json", json.dumps(bundle["saved_reviews"], ensure_ascii=False, indent=2) + "\n")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def load_approved_bundle_zip_base64(zip_base64: str):
    if not isinstance(zip_base64, str) or not zip_base64.strip():
        raise ApiError(400, "zip_base64 must be a non-empty string")
    try:
        archive_bytes = base64.b64decode(zip_base64.encode("ascii"))
    except Exception as exc:
        raise ApiError(400, "Invalid base64 zip payload") from exc

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
            approved_export = json.loads(zf.read("approved-ready-leads.json").decode("utf-8"))
            saved_reviews = json.loads(zf.read("approved-saved-reviews.json").decode("utf-8"))
            summary = json.loads(zf.read("approved-bundle-summary.json").decode("utf-8"))
    except KeyError as exc:
        raise ApiError(400, f"Approved bundle missing required file: {exc}") from exc
    except (OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise ApiError(400, "Invalid approved bundle zip") from exc

    batch_results = []
    for item in approved_export.get("items") or []:
        batch_results.append({
            "input": {
                "company": item.get("company"),
                "domain": item.get("domain"),
                "offer": None,
            },
            "result": {
                "status": item.get("review_status") or "ready",
                "draft_generated": bool(item.get("draft_subject") or item.get("draft_body")),
            },
            "artifacts": {
                "dossier": {
                    "company": item.get("company"),
                    "primary_domain": item.get("domain"),
                    "best_contact_email": item.get("best_contact_email"),
                    "summary": item.get("summary"),
                    "review": {
                        "status": item.get("review_status") or "ready",
                        "next_step": item.get("next_step"),
                        "reasons": [],
                        "top_contact_candidates": [],
                    },
                    "site_candidates": [],
                    "warnings": [],
                },
                "review": {
                    "status": item.get("review_status") or "ready",
                    "next_step": item.get("next_step"),
                    "reasons": [],
                    "top_contact_candidates": [],
                },
                "draft": {
                    "subject": item.get("draft_subject") or "",
                    "body": item.get("draft_body") or "",
                    "target_contact": item.get("draft_target_contact") or item.get("best_contact_email") or "",
                },
            },
        })

    batch = {
        "artifact_type": "lead_enrichment_outreach_batch_workflow",
        "artifact_version": approved_export.get("artifact_version", "v1"),
        "summary": {
            "ready": approved_export.get("summary", {}).get("approved_ready_count", len(batch_results)),
            "review_required": 0,
            "blocked": 0,
            "total": approved_export.get("summary", {}).get("approved_ready_count", len(batch_results)),
        },
        "results": batch_results,
    }
    return {
        "bundle_summary": summary,
        "batch": batch,
        "saved_reviews": saved_reviews,
    }


def run_batch_from_csv_text(csv_text: str, offer=None, query_mode="smart", allow_review_required=False):
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise ApiError(400, "csv_text must be a non-empty string")

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or "company" not in reader.fieldnames:
        raise ApiError(400, "CSV must include a company column")

    rows = list(reader)
    if not rows:
        raise ApiError(400, "CSV must include at least one data row")

    results = [
        batch_workflow_csv.workflow.run_workflow(
            (row.get("company") or "").strip(),
            domain=((row.get("domain") or "").strip() or None),
            offer=offer,
            region=((row.get("region") or "").strip() or None),
            query_mode=query_mode,
            allow_review_required=allow_review_required,
        )
        for row in rows
        if (row.get("company") or "").strip()
    ]
    if not results:
        raise ApiError(400, "CSV must include at least one non-empty company value")

    return batch_workflow_csv.build_batch_artifact(
        results,
        source_csv="ui-upload.csv",
        offer=offer,
        query_mode=query_mode,
        allow_review_required=allow_review_required,
    )


def export_ready_batch(batch_artifact):
    if not isinstance(batch_artifact, (dict, list)):
        raise ApiError(400, "batch artifact must be a JSON object or array")
    return export_ready_leads.build_ready_export(batch_artifact)


def export_ready_batch_csv_text(batch_artifact):
    export = export_ready_batch(batch_artifact)
    buffer = io.StringIO()
    fieldnames = [
        "company",
        "domain",
        "best_contact_email",
        "best_contact_source_url",
        "summary",
        "review_status",
        "next_step",
        "draft_subject",
        "draft_body",
        "draft_target_contact",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(export["items"])
    return buffer.getvalue()


def generate_missing_ready_drafts(batch_artifact, offer=None, cta="Would a 10-minute intro next week be useful?"):
    if not isinstance(batch_artifact, dict):
        raise ApiError(400, "batch artifact must be a JSON object")
    results = batch_artifact.get("results")
    if not isinstance(results, list):
        raise ApiError(400, "batch artifact must include results array")

    generated = 0
    for item in results:
        if ((item.get("result") or {}).get("status")) != "ready":
            continue
        artifacts = item.setdefault("artifacts", {})
        draft = artifacts.get("draft")
        if isinstance(draft, dict) and ((draft.get("subject") or "").strip() or (draft.get("body") or "").strip()):
            continue
        dossier = artifacts.get("dossier") or {}
        effective_offer = offer or ((item.get("input") or {}).get("offer"))
        if not effective_offer:
            continue
        artifacts["draft"] = generate_outreach.draft(dossier, effective_offer, cta)
        item.setdefault("input", {})["offer"] = effective_offer
        item.setdefault("result", {})["draft_generated"] = True
        generated += 1

    if "summary" in batch_artifact and isinstance(batch_artifact["summary"], dict):
        batch_artifact["summary"]["draft_generated"] = sum(
            1
            for item in results
            if ((item.get("artifacts") or {}).get("draft"))
        )
    return {
        "batch": batch_artifact,
        "generated_count": generated,
    }


def build_handoff_bundle(batch_artifact, saved_reviews=None):
    ready_export = export_ready_batch(batch_artifact)
    saved_reviews = saved_reviews if saved_reviews is not None else list_saved_reviews()
    return {
        "artifact_type": "lead_enrichment_outreach_handoff_bundle",
        "artifact_version": ready_export.get("artifact_version", "v1"),
        "summary": {
            "ready_count": ready_export["summary"]["ready_count"],
            "total_results": ready_export["summary"]["total_results"],
            "saved_reviews_count": len(saved_reviews),
        },
        "ready_export": ready_export,
        "saved_reviews": saved_reviews,
    }


def build_handoff_bundle_zip_base64(batch_artifact, saved_reviews=None):
    bundle = build_handoff_bundle(batch_artifact, saved_reviews=saved_reviews)
    ready_csv = export_ready_batch_csv_text(batch_artifact)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bundle-summary.json", json.dumps(bundle["summary"], ensure_ascii=False, indent=2) + "\n")
        zf.writestr("ready-leads.json", json.dumps(bundle["ready_export"], ensure_ascii=False, indent=2) + "\n")
        zf.writestr("ready-leads.csv", ready_csv)
        zf.writestr("saved-reviews.json", json.dumps(bundle["saved_reviews"], ensure_ascii=False, indent=2) + "\n")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def load_handoff_bundle_zip_base64(zip_base64: str):
    if not isinstance(zip_base64, str) or not zip_base64.strip():
        raise ApiError(400, "zip_base64 must be a non-empty string")
    try:
        archive_bytes = base64.b64decode(zip_base64.encode("ascii"))
    except Exception as exc:
        raise ApiError(400, "Invalid base64 zip payload") from exc

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
            ready_export = json.loads(zf.read("ready-leads.json").decode("utf-8"))
            saved_reviews = json.loads(zf.read("saved-reviews.json").decode("utf-8"))
            summary = json.loads(zf.read("bundle-summary.json").decode("utf-8"))
    except KeyError as exc:
        raise ApiError(400, f"Bundle missing required file: {exc}") from exc
    except (OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise ApiError(400, "Invalid handoff bundle zip") from exc

    batch_results = []
    for item in ready_export.get("items") or []:
        batch_results.append({
            "input": {
                "company": item.get("company"),
                "domain": item.get("domain"),
                "offer": None,
            },
            "result": {
                "status": item.get("review_status") or "ready",
                "draft_generated": bool(item.get("draft_subject") or item.get("draft_body")),
            },
            "artifacts": {
                "dossier": {
                    "company": item.get("company"),
                    "primary_domain": item.get("domain"),
                    "best_contact_email": item.get("best_contact_email"),
                    "summary": item.get("summary"),
                    "review": {
                        "status": item.get("review_status") or "ready",
                        "next_step": item.get("next_step"),
                        "reasons": [],
                        "top_contact_candidates": [],
                    },
                    "site_candidates": [],
                    "warnings": [],
                },
                "review": {
                    "status": item.get("review_status") or "ready",
                    "next_step": item.get("next_step"),
                    "reasons": [],
                    "top_contact_candidates": [],
                },
                "draft": {
                    "subject": item.get("draft_subject") or "",
                    "body": item.get("draft_body") or "",
                    "target_contact": item.get("draft_target_contact") or item.get("best_contact_email") or "",
                },
            },
        })

    batch = {
        "artifact_type": "lead_enrichment_outreach_batch_workflow",
        "artifact_version": ready_export.get("artifact_version", "v1"),
        "summary": {
            "ready": ready_export.get("summary", {}).get("ready_count", len(batch_results)),
            "review_required": 0,
            "blocked": 0,
            "total": ready_export.get("summary", {}).get("ready_count", len(batch_results)),
        },
        "results": batch_results,
    }
    return {
        "bundle_summary": summary,
        "batch": batch,
        "saved_reviews": saved_reviews,
    }


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

    dossier = data["dossier"]
    review = dossier.get("review")
    if not isinstance(review, dict) or review.get("status") not in {"ready", "review_required", "blocked"}:
        raise ApiError(400, "dossier.review.status must be ready, review_required, or blocked")

    decision = data["review_decision"]
    status = decision.get("status")
    if status not in {"approved", "rejected", "needs_review"}:
        raise ApiError(400, "review_decision.status must be approved, rejected, or needs_review")
    if not isinstance(decision.get("updated_at"), str) or not decision["updated_at"].strip():
        raise ApiError(400, "review_decision.updated_at must be a non-empty string")
    if status == "approved" and review.get("status") != "ready":
        raise ApiError(400, "Cannot mark review approved unless dossier.review.status is ready")


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

    @property
    def demo_batch_path(self):
        return getattr(self.server, "demo_batch_path", DEFAULT_DEMO_BATCH_PATH)

    def build_health_payload(self):
        demo_batch_path = self.demo_batch_path
        batch_exists = demo_batch_path.exists()
        batch_summary = None
        if batch_exists:
            try:
                with demo_batch_path.open(encoding="utf-8") as fh:
                    batch_payload = json.load(fh)
                batch_summary = batch_payload.get("summary")
            except (OSError, json.JSONDecodeError):
                batch_summary = {"error": "demo batch unreadable"}
        return {
            "ok": True,
            "review_file": str(self.store.path),
            "demo_batch_file": str(demo_batch_path),
            "demo_batch_exists": batch_exists,
            "demo_batch_summary": batch_summary,
            "saved_reviews_count": len(list_saved_reviews()),
        }

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
            if parsed.path in {"/health", "/healthz"}:
                self._send_json(200, self.build_health_payload())
                return
            if parsed.path == "/api/review":
                with _LOCK:
                    data = self.store.load()
                self._send_json(200, data)
                return
            if parsed.path == "/api/demo-batch":
                demo_batch_path = self.demo_batch_path
                if not demo_batch_path.exists():
                    raise ApiError(404, f"Demo batch file not found: {demo_batch_path}")
                with demo_batch_path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                self._send_json(200, data)
                return
            if parsed.path == "/api/saved-reviews":
                self._send_json(200, {"ok": True, "items": list_saved_reviews()})
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
            if parsed.path == "/api/review/save-as":
                data = self._read_json()
                validate_review_payload(data)
                output_path = build_saved_review_path(data)
                with _LOCK:
                    saved = ReviewStore(output_path).save(data)
                self._send_json(200, {"ok": True, "review": saved, "path": str(output_path)})
                return
            if parsed.path == "/api/batch/run":
                data = self._read_json()
                artifact = run_batch_from_csv_text(
                    data.get("csv_text", ""),
                    offer=data.get("offer"),
                    query_mode=data.get("query_mode") or "smart",
                    allow_review_required=bool(data.get("allow_review_required")),
                )
                self._send_json(200, {"ok": True, "batch": artifact})
                return
            if parsed.path == "/api/batch/export-ready":
                data = self._read_json()
                export = export_ready_batch(data.get("batch"))
                self._send_json(200, {"ok": True, "export": export})
                return
            if parsed.path == "/api/batch/generate-drafts":
                data = self._read_json()
                result = generate_missing_ready_drafts(
                    data.get("batch"),
                    offer=data.get("offer"),
                    cta=data.get("cta") or "Would a 10-minute intro next week be useful?",
                )
                self._send_json(200, {"ok": True, **result})
                return
            if parsed.path == "/api/batch/export-ready-csv":
                data = self._read_json()
                csv_text = export_ready_batch_csv_text(data.get("batch"))
                self._send_json(200, {"ok": True, "csv_text": csv_text})
                return
            if parsed.path == "/api/batch/export-approved":
                data = self._read_json()
                export = build_approved_export(data.get("batch"))
                self._send_json(200, {"ok": True, "export": export})
                return
            if parsed.path == "/api/batch/export-approved-csv":
                data = self._read_json()
                csv_text = approved_export_csv_text(data.get("batch"))
                self._send_json(200, {"ok": True, "csv_text": csv_text})
                return
            if parsed.path == "/api/batch/export-approved-bundle":
                data = self._read_json()
                bundle = build_approved_bundle(data.get("batch"))
                self._send_json(200, {"ok": True, "bundle": bundle})
                return
            if parsed.path == "/api/batch/export-approved-bundle-zip":
                data = self._read_json()
                zip_base64 = build_approved_bundle_zip_base64(data.get("batch"))
                self._send_json(200, {"ok": True, "filename": "approved-ready-bundle.zip", "zip_base64": zip_base64})
                return
            if parsed.path == "/api/batch/export-bundle":
                data = self._read_json()
                bundle = build_handoff_bundle(data.get("batch"))
                self._send_json(200, {"ok": True, "bundle": bundle})
                return
            if parsed.path == "/api/batch/export-bundle-zip":
                data = self._read_json()
                zip_base64 = build_handoff_bundle_zip_base64(data.get("batch"))
                self._send_json(200, {"ok": True, "filename": "lead-handoff-bundle.zip", "zip_base64": zip_base64})
                return
            if parsed.path == "/api/batch/import-bundle-zip":
                data = self._read_json()
                imported = load_handoff_bundle_zip_base64(data.get("zip_base64"))
                self._send_json(200, {"ok": True, "imported": imported})
                return
            if parsed.path == "/api/batch/import-approved-bundle-zip":
                data = self._read_json()
                imported = load_approved_bundle_zip_base64(data.get("zip_base64"))
                self._send_json(200, {"ok": True, "imported": imported})
                return
            if parsed.path == "/api/saved-reviews/open":
                data = self._read_json()
                review = load_saved_review(data.get("filename"))
                self._send_json(200, {"ok": True, "review": review})
                return
            if parsed.path == "/api/saved-reviews/save-many":
                data = self._read_json()
                with _LOCK:
                    saved = save_review_payloads(data.get("reviews"))
                self._send_json(200, {"ok": True, "saved": saved, "count": len(saved)})
                return
            if parsed.path == "/api/saved-reviews/approve-many":
                data = self._read_json()
                with _LOCK:
                    approved = approve_ready_saved_reviews(data.get("filenames"))
                self._send_json(200, {"ok": True, "approved": approved, "count": len(approved)})
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


def build_demo_batch(output_path: Path, offer=DEFAULT_DEMO_OFFER, query_mode="smart", allow_review_required=False):
    csv_text = DEFAULT_DEMO_LEADS_CSV_PATH.read_text(encoding="utf-8")
    artifact = run_batch_from_csv_text(
        csv_text,
        offer=offer,
        query_mode=query_mode,
        allow_review_required=allow_review_required,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


def bootstrap_demo_artifacts(review_path: Path, batch_path: Path, offer=DEFAULT_DEMO_OFFER, query_mode="smart"):
    build_demo_review(DEFAULT_DEMO_DOSSIER_PATH, DEFAULT_DEMO_DRAFT_PATH, review_path)
    return build_demo_batch(batch_path, offer=offer, query_mode=query_mode)


def main():
    parser = argparse.ArgumentParser(description="Run local review UI for lead-enrichment-outreach")
    parser.add_argument("--review-file", default=str(DEFAULT_REVIEW_PATH), help="Path to review JSON file")
    parser.add_argument("--demo-batch-file", default=str(DEFAULT_DEMO_BATCH_PATH), help="Path to demo batch JSON file")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--seed-demo", action="store_true", help="Seed demo review JSON before serving")
    parser.add_argument("--demo", action="store_true", help="Seed demo review JSON and rebuild the demo batch artifact before serving")
    parser.add_argument("--public", action="store_true", help="Bind to 0.0.0.0 for simple demo hosting")
    parser.add_argument("--demo-offer", default=DEFAULT_DEMO_OFFER, help="Offer used when rebuilding the demo batch artifact")
    parser.add_argument("--demo-query-mode", choices=("smart", "basic"), default="smart", help="Query mode used when rebuilding the demo batch artifact")
    args = parser.parse_args()

    review_path = Path(args.review_file).resolve()
    batch_path = Path(args.demo_batch_file).resolve()
    host = "0.0.0.0" if args.public else args.host
    if args.demo:
        bootstrap_demo_artifacts(
            review_path,
            batch_path,
            offer=args.demo_offer,
            query_mode=args.demo_query_mode,
        )
    elif args.seed_demo:
        build_demo_review(DEFAULT_DEMO_DOSSIER_PATH, DEFAULT_DEMO_DRAFT_PATH, review_path)

    server = ThreadedHTTPServer((host, args.port), Handler)
    server.store = ReviewStore(review_path)
    server.html_path = DEFAULT_HTML_PATH
    server.demo_batch_path = batch_path
    print(f"Review UI running on http://{host}:{args.port} using {review_path}")
    print(f"Demo batch path: {batch_path}")
    server.serve_forever()


if __name__ == "__main__":
    main()
