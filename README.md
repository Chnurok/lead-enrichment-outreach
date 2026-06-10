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

If tests pass, the repo is runnable locally.

## What to do in the first 3 minutes

### 1) See the product behavior without reading code

```bash
make demo
```

This prints all 3 trust outcomes:
- `ready` → safe to draft
- `review_required` → plausible lead, but human review required
- `blocked` → not trustworthy enough to continue

### 2) Open the operator UI

```bash
make demo-ui
```

Then open:

```text
http://127.0.0.1:8095
```

What you should see:
- a company dossier with source-backed summary
- trust verdict and reasons
- ranked contact candidates
- editable outreach draft
- explicit human decision controls (`approved` / `rejected` / `needs_review`)

This seeds `examples/demo-review.json` from the included ready-path example and opens a minimal local review workflow.

### 3) Inspect the example artifacts directly

- `examples/demo/index.json` — map of the demo scenarios
- `examples/demo/ready/` — happy path
- `examples/demo/review_required/` — weak-contact gated path
- `examples/demo/blocked/` — refusal path
- `examples/demo/refusal/` — draft refusal artifact

## Main entrypoints

### Enrichment

For reproducible local runs, pass a known domain (live search-only enrichment can be flaky depending on DuckDuckGo HTML output/network conditions):

```bash
python3 skill/scripts/enrich_lead.py --company "DeepL" --domain deepl.com
```

Output: a dossier JSON with summary, sources, candidate sites, contacts, confidence, warnings, and a review verdict.

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

Example artifacts live under `examples/demo/ready/`, `examples/demo/review_required/`, and `examples/demo/blocked/`.

### Unified workflow artifact

```bash
python3 skill/scripts/workflow.py \
  --company "DeepL" \
  --domain deepl.com \
  --offer "AI-assisted lead enrichment and outreach"
```

If you omit `--domain`, the workflow falls back to live web search and may be less reproducible.

This emits one JSON artifact with:
- input
- dossier
- review verdict
- optional draft

You can also wrap an existing dossier instead of re-running enrichment:

```bash
python3 skill/scripts/workflow.py \
  --dossier-json examples/demo/ready/deepl-dossier.json \
  --offer "AI-assisted lead enrichment and outreach"
```

### Review UI

```bash
python3 ui/review_server.py --review-file examples/demo-review.json
```

Optional demo seeding:

```bash
python3 ui/review_server.py --seed-demo --review-file examples/demo-review.json
```

Notes:
- this is a local-only UI served on `127.0.0.1` by default
- there is no auth because v1 is intentionally single-operator/local
- demo seeding currently uses the ready-path DeepL example, not the review-required Mistral example

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
- draft generation refuses weak dossiers unless explicitly overridden
- no real email send flow in v1
- local review server binds to `127.0.0.1` by default

In plain English: the product helps prepare outreach, but it does not silently scrape-and-spam.

## Verification run

Relevant checks for this v1:

```bash
python3 -m unittest discover -s tests -q
python3 ui/review_server.py --seed-demo --review-file examples/demo-review.json --host 127.0.0.1 --port 8095
```

Use Ctrl+C to stop the local server.

## License

MIT
