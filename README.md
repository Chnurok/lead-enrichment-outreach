# Lead Enrichment Outreach

![Preview](assets/preview.svg)

A small, inspectable Python toolkit plus OpenClaw skill for one job: turn a rough company input into a grounded outreach dossier and a usable first-draft email.

## What this repo is good at

It helps with the messy middle of outbound research:

- identify the likely official website
- pull visible contact paths from public pages
- rank contacts by outreach usefulness
- attach provenance to extracted fields
- expose trust signals instead of hiding everything behind one score
- package that into a compact JSON dossier
- turn the dossier into a restrained outreach draft

It is intentionally narrow. It does not promise perfect scraping, verified deliverability, or automatic sending.

## Honest golden path

The strongest path in this repo is:

1. start with a company name and, when available, the domain
2. generate one dossier
3. review the JSON for garbage or weak signals
4. generate one draft from that reviewed dossier
5. edit the final message like a human before using it

That path keeps the tool useful without overselling reliability.

## Quick start

```bash
git clone https://github.com/Chnurok/lead-enrichment-outreach.git
cd lead-enrichment-outreach
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -q
```

## Golden-path commands

### 1) Enrich one lead

```bash
python3 skill/scripts/enrich_lead.py --company "Mistral AI" --domain mistral.ai > dossier.json
```

What to check in `dossier.json` before trusting it:

- `primary_domain` looks official
- `site_verification.verified` is true or at least plausible
- `summary` is coherent
- `best_contact_email` is not obviously a weak target like `press@` or `privacy@`
- `summary_source`, `email_sources`, and `phone_sources` point to believable pages
- `trust_signals` and `warnings` match your own intuition about the result

### 2) Generate one draft

```bash
python3 skill/scripts/generate_outreach.py dossier.json \
  --offer "AI-assisted lead enrichment and outreach" > draft.json
```

The output is a first draft, not send-ready copy.

## Output shape

The enrichment output now includes trust-oriented fields such as:

- `site_verification`
- `best_contact_email`
- `best_contact_source`
- `summary_source`
- `email_sources`
- `phone_sources`
- `trust_signals`
- `warnings`

This makes it easier to inspect not just *what* was found, but also *why it should or should not be trusted*.

## Examples

The `examples/` directory is curated to stay believable in public:

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

## Notes on reliability

This repo uses public web results and intentionally lightweight heuristics. Expect some failure modes:

- sites that block fetching
- noisy phones/emails from raw HTML
- directories outranking the official site
- weak but official contacts such as `press@` or `privacy@`
- summaries that still need human cleanup

If the dossier looks wrong, treat it as wrong.

## Packaging as an OpenClaw skill

```bash
python3 /usr/lib/node_modules/openclaw/skills/skill-creator/scripts/package_skill.py skill dist
```

`dist/` is generated during packaging and is not meant to stay committed.

## License

MIT
