#!/usr/bin/env python3
"""Minimal local review UI for lead-enrichment-outreach."""

from __future__ import annotations

import argparse
import base64
import csv
import io
import ipaddress
import json
import os
import sys
import threading
import zipfile
from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "skill" / "scripts"
DEFAULT_REVIEW_PATH = ROOT / "examples" / "demo-review.json"
DEFAULT_HTML_PATH = ROOT / "ui" / "index.html"
DEFAULT_DEMO_DOSSIER_PATH = ROOT / "examples" / "demo" / "ready" / "deepl-dossier.json"
DEFAULT_DEMO_DRAFT_PATH = ROOT / "examples" / "demo" / "ready" / "deepl-draft.json"
DEFAULT_DEMO_BATCH_PATH = ROOT / "examples" / "demo-output.json"
DEFAULT_DEMO_INDEX_PATH = ROOT / "examples" / "demo" / "index.json"
DEFAULT_DEMO_OFFER = "AI-assisted lead enrichment and outreach"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8095"))
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(2 * 1024 * 1024)))
AUTH_TOKEN = os.getenv("REVIEW_UI_AUTH_TOKEN", "").strip()
AUTH_COOKIE_NAME = "lead_review_demo_auth"
MAX_IMPORT_ARCHIVE_BYTES = int(os.getenv("MAX_IMPORT_ARCHIVE_BYTES", str(1024 * 1024)))
MAX_IMPORT_ARCHIVE_TOTAL_BYTES = int(os.getenv("MAX_IMPORT_ARCHIVE_TOTAL_BYTES", str(2 * 1024 * 1024)))
MAX_CSV_TEXT_BYTES = int(os.getenv("MAX_CSV_TEXT_BYTES", str(256 * 1024)))
MAX_BATCH_ROWS = int(os.getenv("MAX_BATCH_ROWS", "250"))
MAX_SUBJECT_CHARS = int(os.getenv("MAX_SUBJECT_CHARS", "200"))
MAX_BODY_CHARS = int(os.getenv("MAX_BODY_CHARS", "20000"))
MAX_NOTES_CHARS = int(os.getenv("MAX_NOTES_CHARS", "5000"))
MAX_CONTACT_CHARS = int(os.getenv("MAX_CONTACT_CHARS", "320"))
_LOCK = threading.Lock()

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import batch_workflow_csv
import export_ready_leads
import generate_outreach
import workflow


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def build_security_headers(content_type: str) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "X-Frame-Options": "DENY",
        "Cache-Control": "no-store",
    }
    if content_type.startswith("text/html"):
        headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
    return headers


def require_string(value, field_name: str, *, allow_empty: bool = False, max_chars: int | None = None) -> str:
    if not isinstance(value, str):
        raise ApiError(400, f"{field_name} must be a string")
    if not allow_empty and not value.strip():
        raise ApiError(400, f"{field_name} must be a non-empty string")
    if max_chars is not None and len(value) > max_chars:
        raise ApiError(400, f"{field_name} exceeds limit of {max_chars} characters")
    return value


def decode_base64_zip(zip_base64: str) -> bytes:
    require_string(zip_base64, "zip_base64")
    try:
        archive_bytes = base64.b64decode(zip_base64.encode("ascii"), validate=True)
    except Exception as exc:
        raise ApiError(400, "Invalid base64 zip payload") from exc
    if len(archive_bytes) > MAX_IMPORT_ARCHIVE_BYTES:
        raise ApiError(413, f"Zip payload exceeds limit of {MAX_IMPORT_ARCHIVE_BYTES} bytes")
    return archive_bytes


def read_json_entries_from_zip(archive_bytes: bytes, required_names: list[str]) -> dict[str, object]:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
            members = {info.filename: info for info in zf.infolist()}
            total_uncompressed = sum(info.file_size for info in members.values())
            if total_uncompressed > MAX_IMPORT_ARCHIVE_TOTAL_BYTES:
                raise ApiError(413, f"Zip contents exceed limit of {MAX_IMPORT_ARCHIVE_TOTAL_BYTES} bytes")
            loaded = {}
            for name in required_names:
                info = members.get(name)
                if info is None:
                    raise ApiError(400, f"Bundle missing required file: {name}")
                loaded[name] = json.loads(zf.read(name).decode("utf-8"))
            return loaded
    except ApiError:
        raise
    except (OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise ApiError(400, "Invalid bundle zip") from exc


def configured_saved_reviews_dir() -> Path:
    raw = os.getenv("SAVED_REVIEWS_DIR")
    if raw and raw.strip():
        return Path(raw).expanduser().resolve()
    return ROOT / "examples" / "saved-reviews"


def can_write_to_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK | os.X_OK)


def saved_reviews_dir() -> Path:
    preferred = configured_saved_reviews_dir()
    if can_write_to_dir(preferred):
        return preferred
    fallback = ROOT / ".local-state" / "saved-reviews"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class ReviewStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        if not self.path.exists():
            raise ApiError(404, f"Review file not found: {display_path(self.path)}")
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
    return saved_reviews_dir() / f"{company}-review.json"


def list_saved_reviews():
    base = saved_reviews_dir()
    items = []
    for path in sorted(base.glob("*.json")):
        try:
            payload = ReviewStore(path).load()
        except ApiError:
            continue
        items.append({
            "filename": path.name,
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
    path = saved_reviews_dir() / filename
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
            "filename": output_path.name,
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
    if not approved:
        raise ApiError(400, "No ready saved reviews were eligible for approval")
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
    archive_bytes = decode_base64_zip(zip_base64)
    loaded = read_json_entries_from_zip(
        archive_bytes,
        ["approved-ready-leads.json", "approved-saved-reviews.json", "approved-bundle-summary.json"],
    )
    approved_export = loaded["approved-ready-leads.json"]
    saved_reviews = loaded["approved-saved-reviews.json"]
    summary = loaded["approved-bundle-summary.json"]

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
    require_string(csv_text, "csv_text")
    if len(csv_text.encode("utf-8")) > MAX_CSV_TEXT_BYTES:
        raise ApiError(413, f"csv_text exceeds limit of {MAX_CSV_TEXT_BYTES} bytes")

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or "company" not in reader.fieldnames:
        raise ApiError(400, "CSV must include a company column")

    rows = list(reader)
    if not rows:
        raise ApiError(400, "CSV must include at least one data row")
    if len(rows) > MAX_BATCH_ROWS:
        raise ApiError(400, f"CSV exceeds row limit of {MAX_BATCH_ROWS}")

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
    archive_bytes = decode_base64_zip(zip_base64)
    loaded = read_json_entries_from_zip(
        archive_bytes,
        ["ready-leads.json", "saved-reviews.json", "bundle-summary.json"],
    )
    ready_export = loaded["ready-leads.json"]
    saved_reviews = loaded["saved-reviews.json"]
    summary = loaded["bundle-summary.json"]

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
    require_string(draft.get("subject"), "draft.subject", max_chars=MAX_SUBJECT_CHARS)
    require_string(draft.get("body"), "draft.body", max_chars=MAX_BODY_CHARS)
    if "target_contact" in draft and draft.get("target_contact") is not None:
        require_string(draft.get("target_contact"), "draft.target_contact", allow_empty=True, max_chars=MAX_CONTACT_CHARS)

    dossier = data["dossier"]
    review = dossier.get("review")
    if not isinstance(review, dict) or review.get("status") not in {"ready", "review_required", "blocked"}:
        raise ApiError(400, "dossier.review.status must be ready, review_required, or blocked")

    decision = data["review_decision"]
    status = decision.get("status")
    if status not in {"approved", "rejected", "needs_review"}:
        raise ApiError(400, "review_decision.status must be approved, rejected, or needs_review")
    require_string(decision.get("updated_at"), "review_decision.updated_at")
    if "notes" in decision and decision.get("notes") is not None:
        require_string(decision.get("notes"), "review_decision.notes", allow_empty=True, max_chars=MAX_NOTES_CHARS)
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
            "review_file": display_path(self.store.path),
            "demo_batch_file": display_path(demo_batch_path),
            "demo_batch_exists": batch_exists,
            "demo_batch_summary": batch_summary,
            "saved_reviews_dir": display_path(saved_reviews_dir()),
            "saved_reviews_count": len(list_saved_reviews()),
        }

    def _is_local_request(self) -> bool:
        host = self.client_address[0]
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return host in {"localhost"}

    def _auth_required(self) -> bool:
        return bool(getattr(self.server, "auth_token", "")) or not self._is_local_request()

    def _query_params(self):
        return parse_qs(urlparse(self.path).query or "", keep_blank_values=False)

    def _cookies(self):
        raw = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        if raw:
            jar.load(raw)
        return jar

    def _cookie_token(self) -> str:
        morsel = self._cookies().get(AUTH_COOKIE_NAME)
        return morsel.value.strip() if morsel else ""

    def _request_token(self) -> str:
        header_token = self.headers.get("X-Review-Token", "").strip()
        if header_token:
            return header_token
        auth_header = self.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        cookie_token = self._cookie_token()
        if cookie_token:
            return cookie_token
        return ""

    def _ensure_authorized(self):
        if not self._auth_required():
            return
        expected = getattr(self.server, "auth_token", "")
        if not expected:
            raise ApiError(503, "Server auth token is not configured")
        provided = self._request_token()
        if provided != expected:
            raise ApiError(401, "Unauthorized")

    def _send_json(self, code, payload, head_only=False, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        content_type = "application/json; charset=utf-8"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in build_security_headers(content_type).items():
            self.send_header(key, value)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _send_text(self, code, text, content_type="text/plain; charset=utf-8", head_only=False, extra_headers=None):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in build_security_headers(content_type).items():
            self.send_header(key, value)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _send_redirect(self, location: str, extra_headers=None):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for key, value in build_security_headers("text/html; charset=utf-8").items():
            self.send_header(key, value)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _build_auth_cookie(self, token: str) -> str:
        cookie = cookies.SimpleCookie()
        cookie[AUTH_COOKIE_NAME] = token
        cookie[AUTH_COOKIE_NAME]["path"] = "/"
        cookie[AUTH_COOKIE_NAME]["httponly"] = True
        cookie[AUTH_COOKIE_NAME]["samesite"] = "Strict"
        if not self._is_local_request():
            cookie[AUTH_COOKIE_NAME]["secure"] = True
        return cookie.output(header="").strip()

    def _maybe_bootstrap_browser_session(self, parsed) -> bool:
        if parsed.path not in {"/", "/index.html"}:
            return False
        expected = getattr(self.server, "auth_token", "")
        if not expected:
            return False
        query_token = (self._query_params().get("token") or [""])[0].strip()
        header_token = self.headers.get("X-Review-Token", "").strip()
        bootstrap_token = query_token or header_token
        if bootstrap_token and bootstrap_token == expected:
            self._send_redirect("/", extra_headers={"Set-Cookie": self._build_auth_cookie(expected)})
            return True
        return False

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
        self.send_response(204)
        self.send_header("Allow", "GET, POST, HEAD, OPTIONS")
        self.send_header("Content-Length", "0")
        for key, value in build_security_headers("text/plain; charset=utf-8").items():
            self.send_header(key, value)
        self.end_headers()

    def _handle_get(self, *, head_only=False):
        try:
            parsed = urlparse(self.path)
            if self._maybe_bootstrap_browser_session(parsed):
                return
            if parsed.path == "/favicon.ico":
                self._send_text(204, "", "image/x-icon", head_only=head_only)
                return
            if parsed.path in {"/", "/index.html"}:
                self._send_text(200, self.html_path.read_text(encoding="utf-8"), "text/html; charset=utf-8", head_only=head_only)
                return
            self._ensure_authorized()
            if parsed.path in {"/health", "/healthz"}:
                self._send_json(200, self.build_health_payload(), head_only=head_only)
                return
            if parsed.path == "/api/review":
                with _LOCK:
                    data = self.store.load()
                self._send_json(200, data, head_only=head_only)
                return
            if parsed.path == "/api/demo-batch":
                demo_batch_path = self.demo_batch_path
                if not demo_batch_path.exists():
                    raise ApiError(404, f"Demo batch file not found: {display_path(demo_batch_path)}")
                with demo_batch_path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                self._send_json(200, data, head_only=head_only)
                return
            if parsed.path == "/api/saved-reviews":
                self._send_json(200, {"ok": True, "items": list_saved_reviews()}, head_only=head_only)
                return
            self._send_json(404, {"ok": False, "error": "Not found"}, head_only=head_only)
        except Exception as exc:
            self._handle_error(exc)

    def do_GET(self):
        self._handle_get(head_only=False)

    def do_HEAD(self):
        self._handle_get(head_only=True)

    def do_POST(self):
        try:
            self._ensure_authorized()
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
                self._send_json(200, {"ok": True, "review": saved, "filename": output_path.name})
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


def load_demo_scenarios(index_path: Path | None = None):
    index_path = index_path or DEFAULT_DEMO_INDEX_PATH
    with index_path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    scenarios = payload.get("demo_scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ApiError(400, f"Demo index has no scenarios: {index_path}")
    return scenarios


def build_demo_batch_artifact(scenarios, offer=DEFAULT_DEMO_OFFER, allow_review_required=False):
    results = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        status = scenario.get("status")
        if status == "refusal":
            continue

        dossier_path = ROOT / str(scenario.get("path") or "")
        if not dossier_path.exists():
            raise ApiError(404, f"Demo dossier not found: {dossier_path}")
        with dossier_path.open(encoding="utf-8") as fh:
            dossier = json.load(fh)

        draft = None
        draft_path_value = scenario.get("draft")
        draft_override_value = scenario.get("draft_override")
        draft_path = ROOT / str(draft_path_value) if draft_path_value else None
        draft_override_path = ROOT / str(draft_override_value) if draft_override_value else None

        if draft_path and draft_path.exists():
            with draft_path.open(encoding="utf-8") as fh:
                draft = json.load(fh)
        elif allow_review_required and draft_override_path and draft_override_path.exists():
            with draft_override_path.open(encoding="utf-8") as fh:
                draft = json.load(fh)

        review = dossier.get("review") or {}
        company = dossier.get("company") or scenario.get("company")
        domain = dossier.get("primary_domain")
        scenario_status = review.get("status") or status or "blocked"

        results.append(
            workflow.build_artifact(
                company=company,
                domain=domain,
                offer=offer,
                dossier=dossier,
                draft=draft,
                allow_review_required=allow_review_required,
            )
        )
        results[-1]["result"]["status"] = scenario_status
        results[-1]["result"]["ready_for_outreach"] = bool(review.get("ready_for_outreach"))
        results[-1]["result"]["requires_review"] = scenario_status == "review_required"
        results[-1]["result"]["draft_generated"] = bool(draft)

    return batch_workflow_csv.build_batch_artifact(
        results,
        source_csv="examples/demo/index.json",
        offer=offer,
        query_mode="demo",
        allow_review_required=allow_review_required,
    )


def build_demo_batch(output_path: Path, offer=DEFAULT_DEMO_OFFER, allow_review_required=False):
    artifact = build_demo_batch_artifact(
        load_demo_scenarios(),
        offer=offer,
        allow_review_required=allow_review_required,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


def bootstrap_demo_artifacts(review_path: Path, batch_path: Path, offer=DEFAULT_DEMO_OFFER):
    build_demo_review(DEFAULT_DEMO_DOSSIER_PATH, DEFAULT_DEMO_DRAFT_PATH, review_path)
    return build_demo_batch(batch_path, offer=offer)


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
    parser.add_argument("--build-demo-batch-only", action="store_true", help="Build the deterministic demo batch artifact, print it, and exit")
    parser.add_argument("--auth-token", default=AUTH_TOKEN, help="Shared token required for non-local access")
    args = parser.parse_args()

    review_path = Path(args.review_file).resolve()
    batch_path = Path(args.demo_batch_file).resolve()
    host = "0.0.0.0" if args.public else args.host
    auth_token = (args.auth_token or "").strip()
    if host not in {"127.0.0.1", "::1", "localhost"} and not auth_token:
        parser.error("--auth-token or REVIEW_UI_AUTH_TOKEN is required for non-local binding")
    if args.build_demo_batch_only:
        artifact = build_demo_batch(
            batch_path,
            offer=args.demo_offer,
        )
        print(json.dumps(artifact, ensure_ascii=False, indent=2))
        return
    if args.demo:
        bootstrap_demo_artifacts(
            review_path,
            batch_path,
            offer=args.demo_offer,
        )
    elif args.seed_demo:
        build_demo_review(DEFAULT_DEMO_DOSSIER_PATH, DEFAULT_DEMO_DRAFT_PATH, review_path)

    server = ThreadedHTTPServer((host, args.port), Handler)
    server.store = ReviewStore(review_path)
    server.html_path = DEFAULT_HTML_PATH
    server.demo_batch_path = batch_path
    server.auth_token = auth_token
    print(f"Review UI running on http://{host}:{args.port} using {review_path}")
    print(f"Demo batch path: {batch_path}")
    if auth_token:
        print("Review UI auth: token required via ?token=... or X-Review-Token header")
    server.serve_forever()


if __name__ == "__main__":
    main()
