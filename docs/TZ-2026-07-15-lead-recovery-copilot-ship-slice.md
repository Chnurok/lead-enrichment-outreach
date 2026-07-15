# TZ — Lead Recovery Copilot Ship Slice

Date: 2026-07-15

## Goal

Ship the current `lead-enrichment-outreach` product as a credible extension-first operator MVP for messy local/regional B2B lead recovery.

The shipped surface should make this product easy to demo, easy to verify, and honest about what it is good at.

## Product Position

This slice is not trying to become:

- a giant verified contact database
- a CRM
- a mass outreach engine
- a generic "AI SDR platform"

This slice is trying to become:

- a browser-native lead recovery copilot
- a trust-first review workflow
- a batch-to-handoff operator tool

## Scope

### 1. Extension-first operator surface

The browser extension should remain the fastest way to recover the best available contact path from the current page.

Requirements:

- extension popup shows page context and recovery result clearly
- extension options allow backend configuration and health testing
- extension result model supports verified, unverified, and rejected contact evidence
- extension talks to the review server through `/api/extension/enrich`

### 2. Staged lead evidence

The dossier should support staged evidence instead of pretending everything depends on a clean official website.

Requirements:

- preserve backward-compatible dossier fields used by UI and exports
- add staged evidence structures for entity, contact, and official-site confidence
- allow `review_required` for plausible business-linked contact paths even when official-site proof is incomplete
- keep `blocked` for truly weak or noisy leads

### 3. Operator review and export

The hosted/local review UI should keep human review primary.

Requirements:

- show trust verdict, evidence, warnings, and next steps
- keep draft editing and approval flow
- preserve batch run, ready-only export, and approved handoff story
- keep demo artifacts reproducible

### 4. Verification loop

This slice must be easy to re-check before every push.

Requirements:

- one repo command runs the core verification loop
- verification covers Python tests, extension JavaScript syntax, demo workflow, UI boot, and ready-only export
- temporary local artifacts stay out of git by default

## Non-goals

Do not add in this slice:

- outbound sending
- CRM sync
- billing
- multitenant roles/permissions
- iOS companion app

## Acceptance Criteria

This slice is complete when all of the following hold:

1. `make verify` passes on a clean environment with dependencies installed.
2. `python3 -m unittest discover -s tests -q` passes.
3. extension scripts pass `node --check`.
4. demo flow still proves `ready`, `review_required`, and `blocked`.
5. demo UI boots and responds on `/healthz`.
6. ready-only export still succeeds from the demo batch.
7. current docs explain the product position and verification loop without pretending the product is something broader.

## Push Discipline

For each cycle:

1. change code/docs
2. run `make verify`
3. inspect git diff for noise
4. commit only intentional artifacts
5. push to GitHub

## Next Likely Cycle After This Slice

- improve RU/CIS entity retrieval quality
- add stronger business-linked contact ranking
- capture batch quality metrics on rough local leads
- add hosted auth/usage layer for pilot users
