# Demo path

This repo now ships a simple, reproducible demo story:

1. **ready** — `examples/demo/ready/deepl-dossier.json`
   - official site verified
   - official contact available
   - outreach draft can be generated automatically
2. **review_required** — `examples/demo/review_required/mistral-ai-dossier.json`
   - company looks real
   - only weak contacts were found
   - draft is blocked by default and only appears in the explicit override artifact
3. **blocked** — `examples/demo/blocked/unknown-co-dossier.json`
   - no trustworthy official site/contact
   - workflow stops before drafting
4. **refusal** — `examples/demo/refusal/review-required-draft-refusal.json`
   - captures the fail-closed CLI refusal for a weak dossier

## Fast walkthrough

```bash
make demo-ready
make demo-refusal
make demo
```

`make demo` prints the status, confidence, best contact, and next step for all bundled scenarios.

## End-to-end local run

```bash
python3 skill/scripts/workflow.py \
  --company "DeepL" \
  --domain deepl.com \
  --offer "AI-assisted lead enrichment and outreach"
```

For a gated case:

```bash
python3 skill/scripts/generate_outreach.py \
  examples/demo/review_required/mistral-ai-dossier.json \
  --offer "AI-assisted lead enrichment and outreach"
```

Expected outcome: refusal with exit code `2`.

## Packaging notes

- `examples/demo/index.json` is the manifest for demo scenarios.
- Existing top-level example files remain for compatibility.
- The new demo tree is organized by review outcome so operators can quickly show the happy path and the safety rails.
