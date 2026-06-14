# Demo walkthrough

Use this doc when you need to show the product fast without narrating the whole repo.

## What to prove

In one sentence:

`company/domain -> dossier -> trust gate -> draft -> human decision -> ops-ready export`

The product is compelling only if both of these are visible:
- it can create a usable outreach draft for a good lead
- it refuses or gates weak leads instead of pretending everything is ready

## 2-minute script

### 1. Show the story

```bash
make demo-quick
make demo-story
```

This frames the flow before you open any files or UI.

### 2. Show the trust outcomes

```bash
make demo
```

Say:
- `ready` means the dossier is strong enough to draft
- `review_required` means the company may be real, but contact evidence is weak
- `blocked` means the workflow stops before outreach

### 3. Open the operator UI

```bash
make demo-ui
```

Open `http://127.0.0.1:8095` and point at:
- dossier summary and source-backed evidence
- trust verdict and warnings
- ranked contacts
- editable draft
- explicit operator decision controls

The demo review file and demo batch are already loaded, so you can start in the queue immediately.

### 4. Close with batch handoff

```bash
make batch-demo
make ready-export-demo
```

This is the payoff for ops:
- rebuild the bundled demo batch from curated fixtures
- export only `ready` leads for downstream work

## Demo artifacts

```bash
make demo-artifacts
```

Key files:
- `examples/demo/ready/deepl-dossier.json`
- `examples/demo/ready/deepl-draft.json`
- `examples/demo/review_required/mistral-ai-dossier.json`
- `examples/demo/blocked/unknown-co-dossier.json`
- `examples/demo/refusal/review-required-draft-refusal.json`
- `examples/demo-review.json`

## If you have 30 extra seconds

Use the unified artifact:

```bash
python3 skill/scripts/workflow.py \
  --dossier-json examples/demo/ready/deepl-dossier.json \
  --offer "AI-assisted lead enrichment and outreach"
```

This shows that one run can bundle:
- input
- dossier
- review verdict
- optional draft

## Presenter note

Do not lead with scraping or implementation details. Lead with the operator promise:

`We do not just generate outreach. We show evidence, gate weak leads, and hand off only the leads that are actually ready.`
