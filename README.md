# Lead Enrichment Outreach

![Preview](assets/preview.svg)

Turn a company name into a reviewable outreach dossier and a usable first-draft email.

A lightweight Python toolkit first, with an optional OpenClaw skill for the same workflow.

## Who this is for

- Python users who want inspectable enrichment output
- OpenClaw users building research or outreach workflows
- technical operators who are fine reviewing JSON before acting on it

## 10-second example

```bash
python3 skill/scripts/enrich_lead.py --company "Mistral AI" --domain mistral.ai > dossier.json
python3 skill/scripts/generate_outreach.py dossier.json --offer "AI-assisted lead enrichment and outreach" > draft.json
```

What you get back:

- a likely official domain
- visible contact paths from public pages
- a best-contact guess
- source attribution and warnings
- an editable first-draft outreach email

Example dossier snippet:

```json
{
  "primary_domain": "mistral.ai",
  "best_contact_email": "press@mistral.ai",
  "site_verification": { "verified": true, "score": 3.25 },
  "trust_signals": {
    "site_verified": true,
    "best_contact": { "official": true, "weak": true, "tier": "official_weak" }
  },
  "warnings": ["Best available email looks weak for outreach: press@mistral.ai"]
}
```

## Quick start

```bash
git clone https://github.com/Chnurok/lead-enrichment-outreach.git
cd lead-enrichment-outreach
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -q
```

## Golden path

1. Start with a company name and, when available, a domain.
2. Generate one dossier.
3. Review the JSON for weak matches or bad contacts.
4. Generate one draft from the reviewed dossier.
5. Edit the final message like a human before using it.

## What to check in the dossier

- `primary_domain` looks plausible
- `site_verification.verified` is true or at least believable
- `best_contact_email` is not a weak target like `press@` or `privacy@`
- `summary_source`, `email_sources`, and `phone_sources` point to believable pages
- `trust_signals` and `warnings` match your own intuition

## Output shape

The enrichment output includes trust-oriented fields such as:

- `site_verification`
- `best_contact_email`
- `best_contact_source`
- `summary_source`
- `email_sources`
- `phone_sources`
- `trust_signals`
- `warnings`

The point is not just to return data, but to make the result reviewable.

## Examples

- `demo-leads.csv` — tiny batch input
- `demo-output.json` — trimmed dossier examples with trust-oriented fields visible
- `openai-dossier.json` — single credible dossier example
- `openai-draft.json` — restrained draft example
- `ab-report.json` — illustrative only, not benchmark evidence

## Repo layout

- `skill/` — installable OpenClaw skill
- `skill/scripts/` — enrichment and draft-generation scripts
- `tests/` — unit tests plus a lightweight query-mode harness
- `examples/` — curated public examples

## Reliability notes

This repo uses public web results and intentionally lightweight heuristics. Expect some failure modes:

- sites that block fetching
- noisy phones or emails from raw HTML
- directory pages outranking the likely official site
- weak but official contacts such as `press@` or `privacy@`
- summaries that still need human cleanup

If the dossier looks wrong, treat it as wrong.

## OpenClaw packaging

```bash
python3 /usr/lib/node_modules/openclaw/skills/skill-creator/scripts/package_skill.py skill dist
```

`dist/` is generated during packaging and is not meant to stay committed.

## License

MIT
