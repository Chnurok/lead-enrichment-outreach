# Lead Enrichment Outreach

Reusable OpenClaw skill + scripts for turning rough company inputs into outreach-ready dossiers.

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
- `tests/` — unit tests + A/B test harness
- `examples/` — demo input data

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

### Run tests
```bash
pytest -q
python3 tests/ab_test_query_modes.py
```

## A/B test

The repo compares two search strategies:
- `basic` — one simple query
- `smart` — multiple intent-specific queries

The current recommendation is based on average dossier score from the test harness.

## Packaging the skill

```bash
python3 /usr/lib/node_modules/openclaw/skills/skill-creator/scripts/package_skill.py skill dist
```

## Notes

This repo is intentionally lightweight and public-safe:
- no API keys
- no private lead lists
- no sending automation by default
- no hidden dependencies on local secrets
