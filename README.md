# Lead Enrichment Outreach

![Preview](assets/preview.svg)

Reusable OpenClaw skill + Python scripts for turning rough company inputs into outreach-ready dossiers.

## Why this exists

A lot of outreach work breaks on the boring middle: finding the right site, locating real contact paths, extracting enough context to say something relevant, and packaging that into a usable first draft. This repo focuses on that middle layer.

## What it does

- finds likely official websites
- extracts emails, phones, contact pages, and social links
- builds a short factual company summary
- produces a structured lead dossier
- generates a first outreach draft from that dossier
- supports CSV batch enrichment
- includes A/B testing for query strategies

## Repo layout

- `skill/` — installable OpenClaw skill
- `skill/scripts/` — CLI scripts for enrichment and draft generation
- `tests/` — unit tests + A/B harness
- `examples/` — sanitized demo inputs and outputs

## Quick start

```bash
git clone https://github.com/Chnurok/lead-enrichment-outreach.git
cd lead-enrichment-outreach
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Core commands

### Single lead enrichment
```bash
python3 skill/scripts/enrich_lead.py --company "Stripe" --domain stripe.com
```

### Batch enrichment
```bash
python3 skill/scripts/batch_enrich_csv.py examples/demo-leads.csv --output enriched.json
```

### Generate outreach draft
```bash
python3 skill/scripts/enrich_lead.py --company "Stripe" --domain stripe.com > dossier.json
python3 skill/scripts/generate_outreach.py dossier.json --offer "AI-assisted lead enrichment and outreach" > draft.json
```

## Example dossier fields

The enrichment step outputs structured JSON with fields like:

- `company`
- `primary_domain`
- `summary`
- `emails`
- `phones`
- `contact_pages`
- `social_links`
- `confidence`
- `warnings`

## A/B test mode

The repo compares two search strategies:

- `basic` — one simple query
- `smart` — multiple intent-specific queries

The current recommendation is based on average dossier score from the bundled test harness.

## Packaging as an OpenClaw skill

```bash
python3 /usr/lib/node_modules/openclaw/skills/skill-creator/scripts/package_skill.py skill dist
```

## Design choices

This repo is intentionally lightweight and public-safe:

- no API keys
- no private lead lists
- no auto-sending by default
- no hidden dependencies on local secrets

## License

MIT
