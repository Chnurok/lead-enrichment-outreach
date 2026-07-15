#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

import enrich_lead
import generate_outreach

ARTIFACT_SCHEMA_VERSION = "v1"


def build_artifact(company=None, domain=None, offer=None, dossier=None, draft=None, allow_review_required=False):
    dossier = dossier or {}
    review = dossier.get("review") or {}
    status = review.get("status") or "blocked"
    artifact = {
        "artifact_type": "lead_enrichment_outreach_workflow",
        "artifact_version": ARTIFACT_SCHEMA_VERSION,
        "input": {
            "company": company or dossier.get("company"),
            "domain": domain or dossier.get("primary_domain"),
            "offer": offer,
            "fast_mode": bool((dossier.get("workflow_flags") or {}).get("fast_mode")),
        },
        "result": {
            "status": status,
            "ready_for_outreach": bool(review.get("ready_for_outreach")),
            "requires_review": status == "review_required",
            "draft_generated": bool(draft),
            "allow_review_required": bool(allow_review_required),
        },
        "artifacts": {
            "dossier": dossier,
            "review": review,
            "draft": draft,
        },
    }
    return artifact


def should_generate_fast_review_draft(dossier, fast_mode):
    if not fast_mode:
        return False
    review = dossier.get("review") or {}
    trust = dossier.get("trust_signals") or {}
    social = trust.get("social_identity") or {}
    best_contact = trust.get("best_contact") or {}
    contact_confidence = dossier.get("contact_confidence")
    if contact_confidence is None:
        contact_confidence = trust.get("contact_confidence") or 0
    identity_confidence = dossier.get("entity_confidence")
    if identity_confidence is None:
        identity_confidence = trust.get("identity_confidence") or 0
    has_proxy_contact = bool(dossier.get("best_contact_email")) or bool(dossier.get("contact_pages")) or bool(social.get("company_pages"))
    has_usable_direct_contact = bool(best_contact.get("official")) or (bool(best_contact.get("strong")) and not bool(best_contact.get("weak")))
    return (
        review.get("status") == "review_required"
        and identity_confidence >= 0.35
        and (contact_confidence >= 0.25 or has_usable_direct_contact)
        and has_proxy_contact
    )


def run_workflow(company, domain=None, offer=None, region=None, query_mode="smart", allow_review_required=False, fast_mode=False, preferred_language=None):
    dossier = enrich_lead.enrich(company, region=region, domain=domain, query_mode=query_mode, fast_mode=fast_mode, preferred_language=preferred_language)
    dossier["workflow_flags"] = {"fast_mode": bool(fast_mode)}
    draft = None
    if offer:
        if generate_outreach.dossier_is_ready(dossier) or allow_review_required or should_generate_fast_review_draft(dossier, fast_mode):
            draft = generate_outreach.draft(
                dossier,
                offer,
                "Would a 10-minute intro next week be useful?",
            )
    return build_artifact(
        company=company,
        domain=domain,
        offer=offer,
        dossier=dossier,
        draft=draft,
        allow_review_required=allow_review_required,
    )


def load_dossier(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    parser = argparse.ArgumentParser(description="Unified workflow: company/domain/offer -> dossier -> review -> optional draft")
    parser.add_argument("--company", help="Company name to enrich")
    parser.add_argument("--domain", help="Optional known company domain")
    parser.add_argument("--region", help="Optional region hint for enrichment")
    parser.add_argument("--offer", help="Optional offer to generate an outreach draft")
    parser.add_argument("--query-mode", choices=["basic", "smart"], default="smart")
    parser.add_argument("--allow-review-required", action="store_true", help="Generate a draft for review_required dossiers after manual review")
    parser.add_argument("--fast-mode", action="store_true", help="Use shallower enrichment and allow review-required drafts when identity is strong enough")
    parser.add_argument("--dossier-json", help="Existing dossier JSON to wrap and optionally draft from")
    args = parser.parse_args()

    if args.dossier_json:
        dossier = load_dossier(args.dossier_json)
        dossier["workflow_flags"] = {"fast_mode": bool(args.fast_mode)}
        draft = None
        if args.offer and (
            generate_outreach.dossier_is_ready(dossier)
            or args.allow_review_required
            or should_generate_fast_review_draft(dossier, args.fast_mode)
        ):
            draft = generate_outreach.draft(dossier, args.offer, "Would a 10-minute intro next week be useful?")
        artifact = build_artifact(
            company=args.company,
            domain=args.domain,
            offer=args.offer,
            dossier=dossier,
            draft=draft,
            allow_review_required=args.allow_review_required,
        )
    else:
        if not args.company:
            parser.error("--company is required unless --dossier-json is provided")
        artifact = run_workflow(
            args.company,
            domain=args.domain,
            offer=args.offer,
            region=args.region,
            query_mode=args.query_mode,
            allow_review_required=args.allow_review_required,
            fast_mode=args.fast_mode,
        )

    json.dump(artifact, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
