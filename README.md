# Lead Enrichment Outreach

![Preview](assets/preview.svg)

Reviewable AI-assisted B2B outreach workflow:

**company/domain → dossier → trust review → draft → human decision**

This repo now includes the local review UI/HTTP layer inside the main product. No auth, no real sending, fail-closed by default.

## Demo first

If you want the shortest path to "show me the product", use this order:

```bash
make demo-quick
make demo
make demo-ui
make batch-demo
make ready-export-demo
```

What each step proves:
- `make demo` shows the three trust outcomes: `ready`, `review_required`, `blocked`
- `make demo-ui` opens the operator review surface on `http://127.0.0.1:8095` with the demo review file and demo batch preloaded
- `make batch-demo` and `make ready-export-demo` show the deterministic demo-batch-to-ops handoff story

Presenter docs:
- `docs/demo/README.md` — 2-minute walkthrough
- `docs/demo/SCRIPT.md` — literal talk track and command order
- `docs/demo/PUBLIC_DEMO.md` — fastest public-hosting path for a remote demo
- `docs/demo/DEPLOY.md` — systemd/nginx deploy path for a staying-up demo box

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

### 1) Frame the story

```bash
make demo-quick
make demo-story
```

This gives you the demo narrative in one line:

`company/domain -> dossier -> trust gate -> draft -> human decision -> ops-ready export`

### 2) See the product behavior without reading code

```bash
make demo
```

This prints all 3 trust outcomes:
- `ready` -> safe to draft
- `review_required` -> plausible lead, but human review required
- `blocked` -> not trustworthy enough to continue

### 3) Open the operator UI

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
- batch tools:
  - load demo batch JSON
  - upload batch JSON artifact
  - upload CSV and run enrichment from the UI
  - export ready-only leads as JSON or CSV from the current batch
  - browse saved review files and reopen them in the UI
  - export one handoff `.zip` bundle for ops
  - import a handoff `.zip` bundle back into the UI
  - inspect a compact ops dashboard for ready/draft/review coverage
  - bulk-save missing ready review files and jump to the next ready lead without a draft
  - bulk-generate drafts for ready leads that still have no draft
  - bulk-approve ready saved reviews and export approved-only handoff lists
  - export one-click final approved-only bundle for downstream ops
  - import the approved-only final bundle back into the UI

This seeds `examples/demo-review.json`, rebuilds `examples/demo-output.json`, and opens the local review workflow with the demo batch ready to inspect.

### 4) Show batch handoff

```bash
make batch-demo
make ready-export-demo
```

This closes the story:
- deterministic demo batch rebuilds from `examples/demo/index.json`
- the batch artifact still mirrors the same ready / review_required / blocked operator story
- ready-only export gives downstream ops a clean handoff

### 5) Inspect the example artifacts directly

```bash
make demo-artifacts
```

Or inspect:
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

### Batch workflow for a CSV

```bash
python3 skill/scripts/batch_workflow_csv.py \
  examples/demo-leads.csv \
  --offer "AI-assisted lead enrichment and outreach"
```

This emits one batch JSON artifact with:
- top-level summary counts for `ready`, `review_required`, `blocked`
- per-lead workflow artifacts
- clear visibility into how many drafts were actually generated

Optional output file:

```bash
python3 skill/scripts/batch_workflow_csv.py \
  examples/demo-leads.csv \
  --offer "AI-assisted lead enrichment and outreach" \
  --output examples/demo-output.json
```

The local review UI can now run the same flow directly from a CSV upload:
- choose a `.csv`
- optionally set an offer for ready leads
- choose `smart` or `basic` query mode
- optionally allow draft generation for `review_required` dossiers after human review
- export the current batch's ready-only leads as downloadable JSON or CSV

For the reproducible presenter path, rebuild the bundled demo batch instead of hitting live enrichment:

```bash
python3 ui/review_server.py \
  --build-demo-batch-only \
  --demo-batch-file examples/demo-output.json
```

This uses `examples/demo/index.json` and the curated demo dossiers/drafts, so the summary stays stable for demos and deploy smoke checks.

### Export ready-only leads for operations

Once you have a batch artifact, export only the leads that are actually ready:

```bash
python3 skill/scripts/export_ready_leads.py \
  examples/demo-output.json \
  --output-json examples/ready-leads.json \
  --output-csv examples/ready-leads.csv
```

This gives you:
- a clean `ready-only` JSON artifact
- a flat CSV for downstream ops or review
- draft subject/body bundled only for leads already marked `ready`

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
- `make batch-demo` is intentionally deterministic and rebuilds `examples/demo-output.json` from curated demo fixtures, not from live web enrichment
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

## Public demo on a server

For the shortest remote demo path on a VPS:

```bash
make demo-launch-public
```

Then verify from the host:

```bash
make demo-public-health
```

Health endpoint:

```text
/healthz
```

It returns:
- active review file path
- demo batch file path
- whether the demo batch exists
- batch summary counts when readable
- saved review file count

See `docs/demo/PUBLIC_DEMO.md` for the compact remote-demo checklist.

## Verification run

Relevant checks for this v1:

```bash
python3 -m unittest discover -s tests -q
python3 ui/review_server.py --demo --review-file examples/demo-review.json --demo-batch-file examples/demo-output.json --host 127.0.0.1 --port 8095
curl -fsS http://127.0.0.1:8095/healthz
```

Use Ctrl+C to stop the local server.

## License

MIT
