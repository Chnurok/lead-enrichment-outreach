---
name: lead-enrichment-outreach
description: Turn a company name, domain, or lead list into a reviewable outreach dossier and a first-draft B2B email. Use when an OpenClaw bot needs public-web enrichment with visible trust signals, source attribution, and human review before sending.
---

# Lead Enrichment + Outreach

Use this skill to turn rough lead inputs into structured, reviewable outreach dossiers.

## Workflow

1. Normalize the input.
   - Accept company name, region, domain, or CSV/JSON list.
   - Prefer `company + region` when the name is ambiguous.

2. Enrich the lead.
   - Run `skill/scripts/enrich_lead.py` for single leads.
   - Run `skill/scripts/batch_enrich_csv.py` for CSV batches.
   - Keep the raw JSON output.
   - For a single workflow artifact that bundles dossier + review + optional draft, use `skill/scripts/workflow.py`.

3. Review the dossier.
   - Check `primary_domain`, `site_verification`, `best_contact_email`, `summary`, `trust_signals`, and `warnings`.
   - Use `summary_source`, `email_sources`, and `phone_sources` to verify where important fields came from.
   - Reject obvious garbage: directory-only results, dead domains, irrelevant regions, or weak contacts presented as strong.

4. Prepare outreach context.
   - Extract what the company appears to do, the strongest visible contact path, and one plausible workflow pain.
   - Prefer explicit domain-matching emails when present. Otherwise use a contact page as fallback context.

5. Generate the draft.
   - Use the reviewed dossier plus the offer.
   - Keep claims grounded in the dossier.
   - Do not invent detailed facts that were not observed.

## Output rules

Produce a compact dossier with this shape:
- company
- region
- query
- primary_domain
- website_title
- site_verification
- summary
- summary_source
- emails
- email_sources
- best_contact_email
- best_contact_source
- phones
- phone_sources
- contact_pages
- social_links
- snippets
- trust_signals
- confidence
- warnings

When writing outreach:
- mention one concrete business clue from the dossier
- mention one likely operational pain
- connect the offer to that pain
- end with one clear CTA

## Scripts

### `skill/scripts/enrich_lead.py`
Use for one company.

Examples:
```bash
python3 skill/scripts/enrich_lead.py --company "Northwind Logistics" --region "Volgograd"
python3 skill/scripts/enrich_lead.py --company "Acme" --domain acme.example
```

### `skill/scripts/batch_enrich_csv.py`
Use for CSV batches. Requires a `company` column. Optional: `region`, `domain`.

Example:
```bash
python3 skill/scripts/batch_enrich_csv.py leads.csv --output enriched.json
```

### `skill/scripts/generate_outreach.py`
Use after enrichment to turn a dossier into a first email draft.
By default it refuses dossiers that are not `review.status == "ready"`; use `--allow-review-required` only after human review.

Example:
```bash
python3 skill/scripts/generate_outreach.py dossier.json --offer "AI-assisted client outreach"
```

## References

- Read `references/lead-schema.md` when mapping data or validating outputs.
- Read `references/outreach-patterns.md` when drafting the email or follow-up.

## Guardrails

- Do not send automatically unless the user explicitly wants sending.
- Treat `review_required` as gated, not ready.
- Treat scraped personal data carefully.
- Keep public examples sanitized.
- When confidence is low, say why.
