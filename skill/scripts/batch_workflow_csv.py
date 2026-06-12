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
        "total": len(results),
    }
    for item in results:
        status = ((item.get("result") or {}).get("status")) or "blocked"
        counts[status] = counts.get(status, 0) + 1
        if (item.get("result") or {}).get("draft_generated"):
            counts["draft_generated"] += 1
    return counts


def build_batch_artifact(results, source_csv, offer=None, query_mode="smart", allow_review_required=False):
    return {
        "artifact_type": "lead_enrichment_outreach_batch_workflow",
        "artifact_version": workflow.ARTIFACT_SCHEMA_VERSION,
        "input": {
            "source_csv": str(source_csv),
            "offer": offer,
            "query_mode": query_mode,
            "allow_review_required": bool(allow_review_required),
        },
        "summary": summarize_results(results),
        "results": results,
    }


def run_batch(csv_path, offer=None, query_mode="smart", allow_review_required=False):
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
        )
        results.append(artifact)
    return build_batch_artifact(
        results,
        source_csv=csv_path,
        offer=offer,
        query_mode=query_mode,
        allow_review_required=allow_review_required,
    )


def main():
    parser = argparse.ArgumentParser(description="Run lead-enrichment-outreach workflow for a CSV of leads")
    parser.add_argument("csv_path", help="CSV with company, optional region, optional domain")
    parser.add_argument("--offer", help="Optional offer to draft against ready leads")
    parser.add_argument("--query-mode", choices=["basic", "smart"], default="smart")
    parser.add_argument("--allow-review-required", action="store_true", help="Generate drafts for review_required leads after manual review")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    artifact = run_batch(
        args.csv_path,
        offer=args.offer,
        query_mode=args.query_mode,
        allow_review_required=args.allow_review_required,
    )
    text = json.dumps(artifact, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
