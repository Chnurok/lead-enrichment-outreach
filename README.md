# Lead Enrichment Outreach

![Preview](assets/preview.svg)

Reviewable AI-assisted B2B outreach workflow:

**company/domain → dossier → trust review → draft → human decision**

This repo now includes the local review UI/HTTP layer inside the main product. No auth, no real sending, fail-closed by default.

## What v1 includes

- lead enrichment into dossier JSON
- trust gating with `ready` / `review_required` / `blocked`
- restrained draft generation
- local review UI for:
  - dossier summary
  - review status, reasons, warnings, sources
  - ranked contacts
  - draft subject/body editing
  - operator decision: `approved` / `rejected` / `needs_review`
- reproducible local demo

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -q
```

## Fast demo path

1. Inspect the existing demo artifacts:

```bash
make demo
```

2. Start the local review UI:

```bash
make demo-ui
```

3. Open:

```text
http://127.0.0.1:8095
```

This seeds `examples/demo-review.json` from the included dossier/draft example and opens a minimal operator workflow.

## Main entrypoints

### Enrichment

```bash
python3 skill/scripts/enrich_lead.py --company "DeepL"
```

### Draft generation

```bash
python3 skill/scripts/generate_outreach.py examples/demo/ready/deepl-dossier.json \
  --offer "AI-assisted lead enrichment and outreach"
```

Weak dossiers are blocked by default:

```bash
python3 skill/scripts/generate_outreach.py examples/demo/review_required/mistral-ai-dossier.json \
  --offer "AI-assisted lead enrichment and outreach"
```

Override only after explicit human review:

```bash
python3 skill/scripts/generate_outreach.py examples/demo/review_required/mistral-ai-dossier.json \
  --offer "AI-assisted lead enrichment and outreach" \
  --allow-review-required
```

### Unified workflow artifact

```bash
python3 skill/scripts/workflow.py \
  --company "DeepL" \
  --domain deepl.com \
  --offer "AI-assisted lead enrichment and outreach"
```

This emits one JSON artifact with:
- input
- dossier
- review verdict
- optional draft

### Review UI

```bash
python3 ui/review_server.py --review-file examples/demo-review.json
```

Optional demo seeding:

```bash
python3 ui/review_server.py --seed-demo --review-file examples/demo-review.json
```

## Review file format

The UI reads and writes one JSON document with:

- `lead`
- `dossier`
- `draft`
- `review_decision`

Example status flow:

- dossier `review.status` shows system trust verdict
- operator `review_decision.status` is one of:
  - `approved`
  - `rejected`
  - `needs_review`

This keeps trust verdict separate from human approval.

## Repo layout

- `skill/` — enrichment and draft scripts
- `examples/` — public demo dossiers/drafts/review JSON
- `tests/` — unit tests
- `ui/` — local review UI + HTTP server

## Safety stance

This is a **reviewable outreach system, not black-box lead gen magic**.

- weak dossier → not ready by default
- `review_required` is not treated as ready
- operator sees warnings, reasons, and sources before approving
- no real email send flow in v1

## Verification run

Relevant checks for this v1:

```bash
python3 -m unittest discover -s tests -q
python3 ui/review_server.py --seed-demo --review-file examples/demo-review.json --host 127.0.0.1 --port 8095
```

Use Ctrl+C to stop the local server.

## License

MIT
