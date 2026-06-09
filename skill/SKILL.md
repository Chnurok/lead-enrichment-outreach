---
name: lead-enrichment-outreach
description: Find likely company websites, extract visible public contact paths, build compact lead dossiers, and generate first-draft B2B outreach. Use when an OpenClaw bot needs to turn a company name, domain, or lead list into a reviewed outreach starting point.
---

# Lead Enrichment + Outreach

Use this skill to turn rough lead inputs into structured outreach dossiers.

## Workflow

1. Normalize the input.
   - Accept company name, region, domain, or CSV/JSON list.
   - Prefer `company + region` when the name is ambiguous.

2. Enrich the lead.
   - Run `scripts/enrich_lead.py` for single leads.
   - Run `scripts/batch_enrich_csv.py` for CSV batches.
   - Keep the raw JSON output.

3. Review the dossier.
   - Check `primary_domain`, `emails`, `phones`, `contact_pages`, and `summary`.
   - Reject obvious garbage: generic directories, social-only results, dead domains, or irrelevant regions.
   - If no usable website was found, retry with a tighter query before giving up.

4. Prepare outreach context.
   - Extract: what the company appears to do, the strongest visible contact path, and one plausible workflow pain.
   - Prefer explicit emails when present. Otherwise use a contact page or social link as fallback context.

5. Generate the draft.
   - Use the dossier plus the offer.
   - Keep claims grounded in the dossier.
   - Do not invent detailed facts that were not observed.

## Output rules

Produce a compact dossier with this shape:
- company
- region
- query
- primary_domain
- website_title
- summary
- emails
- phones
- contact_pages
- social_links
- snippets
- confidence
- warnings

When writing outreach:
- mention one concrete business clue from the dossier
- mention one likely operational risk or pain
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

Example:
```bash
python3 skill/scripts/generate_outreach.py dossier.json --offer "AI-assisted client outreach"
```

## References

- Read `references/lead-schema.md` when mapping data or validating outputs.
- Read `references/outreach-patterns.md` when drafting the email or follow-up.

## Heuristics

- Prefer the official website over directory listings.
- Prefer pages with `/contact`, `/about`, `/team`, or explicit email addresses.
- Score contacts higher when the domain email matches the company website.
- If only a contact form exists, keep it as a fallback channel.
- If multiple domains compete, favor the one whose title/snippets best match the company name and region.

## Guardrails

- Do not send automatically unless the user explicitly wants sending.
- Treat scraped personal data carefully.
- Keep public examples sanitized.
- When confidence is low, say why.
