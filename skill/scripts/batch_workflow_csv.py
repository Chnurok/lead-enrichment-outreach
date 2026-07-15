#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path

import workflow


def load_rows(csv_path):
    with Path(csv_path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def summarize_results(results):
    counts = {
        "ready": 0,
        "review_required": 0,
        "blocked": 0,
        "draft_generated": 0,
        "verified_contact_leads": 0,
        "official_email_leads": 0,
        "memory_reused_leads": 0,
        "source_backed_summary_leads": 0,
        "useful_contact_leads": 0,
        "high_usability_contact_leads": 0,
        "low_usability_primary_contact_leads": 0,
        "average_confidence": 0,
        "average_entity_confidence": 0,
        "average_contact_confidence": 0,
        "total": len(results),
    }
    confidence_total = 0.0
    entity_total = 0.0
    contact_total = 0.0
    for item in results:
        status = ((item.get("result") or {}).get("status")) or "blocked"
        counts[status] = counts.get(status, 0) + 1
        if (item.get("result") or {}).get("draft_generated"):
            counts["draft_generated"] += 1
        dossier = ((item.get("artifacts") or {}).get("dossier")) or {}
        evidence_summary = dossier.get("evidence_summary") or {}
        if evidence_summary.get("verified_contact_count", 0) > 0:
            counts["verified_contact_leads"] += 1
        if dossier.get("best_contact_email") and any(
            candidate.get("contact_type") == "email" and candidate.get("official")
            for candidate in (dossier.get("contact_candidates") or [])
        ):
            counts["official_email_leads"] += 1
        if evidence_summary.get("memory_reused_contact_count", 0) > 0:
            counts["memory_reused_leads"] += 1
        if (dossier.get("summary_source") or {}).get("source_type") in {"page", "serp", "memory"}:
            counts["source_backed_summary_leads"] += 1
        if evidence_summary.get("useful_contact_count", 0) > 0:
            counts["useful_contact_leads"] += 1
        if evidence_summary.get("high_usability_contact_count", 0) > 0:
            counts["high_usability_contact_leads"] += 1
        primary_contact = next((candidate for candidate in (dossier.get("contact_candidates") or []) if candidate.get("is_primary")), None)
        if primary_contact and primary_contact.get("outreach_usability") == "low":
            counts["low_usability_primary_contact_leads"] += 1
        confidence_total += float(dossier.get("confidence") or 0.0)
        entity_total += float(dossier.get("entity_confidence") or 0.0)
        contact_total += float(dossier.get("contact_confidence") or 0.0)
    if results:
        counts["average_confidence"] = round(confidence_total / len(results), 2)
        counts["average_entity_confidence"] = round(entity_total / len(results), 2)
        counts["average_contact_confidence"] = round(contact_total / len(results), 2)
    return counts


def build_batch_artifact(results, source_csv, offer=None, query_mode="smart", allow_review_required=False, fast_mode=False):
    return {
        "artifact_type": "lead_enrichment_outreach_batch_workflow",
        "artifact_version": workflow.ARTIFACT_SCHEMA_VERSION,
        "input": {
            "source_csv": str(source_csv),
            "offer": offer,
            "query_mode": query_mode,
            "allow_review_required": bool(allow_review_required),
            "fast_mode": bool(fast_mode),
        },
        "summary": summarize_results(results),
        "results": results,
    }


def run_batch(csv_path, offer=None, query_mode="smart", allow_review_required=False, fast_mode=False):
    results = []
    for row in load_rows(csv_path):
        company = (row.get("company") or "").strip()
        if not company:
            continue
        domain = (row.get("domain") or "").strip() or None
        region = (row.get("region") or "").strip() or None
        artifact = workflow.run_workflow(
            company,
            domain=domain,
            offer=offer,
            region=region,
            query_mode=query_mode,
            allow_review_required=allow_review_required,
            fast_mode=fast_mode,
        )
        results.append(artifact)
    return build_batch_artifact(
        results,
        source_csv=csv_path,
        offer=offer,
        query_mode=query_mode,
        allow_review_required=allow_review_required,
        fast_mode=fast_mode,
    )


def main():
    parser = argparse.ArgumentParser(description="Run lead-enrichment-outreach workflow for a CSV of leads")
    parser.add_argument("csv_path", help="CSV with company, optional region, optional domain")
    parser.add_argument("--offer", help="Optional offer to draft against ready leads")
    parser.add_argument("--query-mode", choices=["basic", "smart"], default="smart")
    parser.add_argument("--allow-review-required", action="store_true", help="Generate drafts for review_required leads after manual review")
    parser.add_argument("--fast-mode", action="store_true", help="Use shallower enrichment and allow review-required drafts when identity is strong enough")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    artifact = run_batch(
        args.csv_path,
        offer=args.offer,
        query_mode=args.query_mode,
        allow_review_required=args.allow_review_required,
        fast_mode=args.fast_mode,
    )
    text = json.dumps(artifact, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
