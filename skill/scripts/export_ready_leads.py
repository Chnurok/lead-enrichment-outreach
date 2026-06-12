#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


def load_batch_artifact(path):
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def extract_results(batch_artifact):
    if isinstance(batch_artifact, list):
        return batch_artifact
    if isinstance(batch_artifact, dict):
        return batch_artifact.get("results") or []
    return []


def ready_results(batch_artifact):
    results = extract_results(batch_artifact)
    return [
        item for item in results
        if (
            ((item.get("result") or {}).get("status") == "ready")
            or ((item.get("review") or {}).get("status") == "ready")
        )
    ]


def build_ready_export(batch_artifact):
    ready = ready_results(batch_artifact)
    items = []
    for item in ready:
        dossier = ((item.get("artifacts") or {}).get("dossier")) or item
        draft = ((item.get("artifacts") or {}).get("draft")) or {}
        review = ((item.get("artifacts") or {}).get("review")) or (item.get("review") or {})
        items.append({
            "company": (item.get("input") or {}).get("company") or dossier.get("company"),
            "domain": (item.get("input") or {}).get("domain") or dossier.get("primary_domain"),
            "best_contact_email": dossier.get("best_contact_email"),
            "best_contact_source_url": ((dossier.get("best_contact_source") or {}).get("source_url")),
            "summary": dossier.get("summary"),
            "review_status": review.get("status"),
            "next_step": review.get("next_step"),
            "draft_subject": draft.get("subject"),
            "draft_body": draft.get("body"),
            "draft_target_contact": draft.get("target_contact"),
        })
    return {
        "artifact_type": "lead_enrichment_outreach_ready_export",
        "artifact_version": batch_artifact.get("artifact_version", "v1") if isinstance(batch_artifact, dict) else "v1",
        "source_artifact_type": batch_artifact.get("artifact_type") if isinstance(batch_artifact, dict) else "legacy_ready_list",
        "summary": {
            "ready_count": len(items),
            "total_results": len(extract_results(batch_artifact)),
        },
        "items": items,
    }


def write_csv(path, items):
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
    with Path(path).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(items)


def main():
    parser = argparse.ArgumentParser(description="Export ready-only leads and drafts from a batch workflow artifact")
    parser.add_argument("batch_artifact_json", help="Path to batch workflow JSON artifact")
    parser.add_argument("--output-json", help="Optional path for ready-only JSON export")
    parser.add_argument("--output-csv", help="Optional path for ready-only CSV export")
    args = parser.parse_args()

    batch_artifact = load_batch_artifact(args.batch_artifact_json)
    export = build_ready_export(batch_artifact)

    text = json.dumps(export, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    if args.output_csv:
        write_csv(args.output_csv, export["items"])


if __name__ == "__main__":
    main()
