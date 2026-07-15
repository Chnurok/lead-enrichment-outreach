# TZ — RU Local Lead Retrieval Rebuild

Date: 2026-06-23

## Goal

Turn enrichment for raw Russian local-business leads from a fragile SERP-dependent heuristic into a staged discovery pipeline that can still produce a reviewable dossier when no clean official website is immediately found.

## What Is Actually Wrong

The current system is not mainly failing because of thresholds.

It is failing because the architecture assumes this path:

`company name -> web search -> official website -> contacts -> draft`

That path works for globally visible companies and known domains, but it breaks on raw K+ style leads because:

- the input entity is weak and often ambiguous
- DuckDuckGo/Bing HTML search is unstable for RU local businesses
- official sites are often missing, weak, dead, hidden, or not well indexed
- map/directory pages may contain the only real public signal, but the current system treats them mostly as search noise
- the workflow expects official-site discovery too early, before entity discovery is stable

So the current bottleneck is not trust scoring. It is that retrieval and entity resolution are collapsed into one brittle step.

## Product Reframe

For RU local-business leads, the product should not think:

`find official site first`

It should think:

`identify entity first, then collect public contact paths, then try to upgrade to official site if possible`

That means the workflow must support a legitimate intermediate state:

- entity identified with medium confidence
- public contact path exists
- official website absent or unverified
- dossier still becomes `review_required` instead of `blocked`

## Required Architecture Change

Split enrichment into explicit stages.

### Stage 1 — Entity Discovery

Goal: answer “does this company likely exist as a coherent business entity in the expected region?”

Allowed evidence:

- directory/registry cards
- map cards
- classifieds/catalog cards
- repeated search-result mentions
- company name + region/address/phone consistency

Output:

- `entity_candidates`
- normalized company title variants
- region/address hints
- phone hints
- source diversity
- `entity_confidence`

This stage must not require an official domain.

### Stage 2 — Contact Path Discovery

Goal: find any usable public contact path for the entity, not only official-domain email.

Allowed outputs:

- official-domain email
- generic mailbox from public listing
- phone
- contact form page
- WhatsApp / Telegram / VK contact page if publicly business-linked
- map/directory contact details with source attribution

Output:

- `contact_candidates`
- per-contact trust class
- `contact_confidence`

This stage must distinguish:

- `official`
- `business-linked but non-official`
- `weak/untrusted`

### Stage 3 — Official Site Upgrade

Goal: try to promote the lead from “entity known” to “official web presence confirmed”.

Output:

- `primary_domain` if proven
- `official_site_confidence`
- explicit failure reason if not proven

This stage is valuable, but it must become optional for `review_required`.

### Stage 4 — Review Verdict

The verdict should be based on staged evidence, not only website success.

Desired behavior:

- `ready`
  when entity is strong and direct outreach path is strong
- `review_required`
  when entity is plausible and at least one business-linked contact path exists, even without confirmed official site
- `blocked`
  only when entity itself is too weak or every contact path is too weak/noisy

## Non-Goals

Do not try to “fix” this mainly by:

- tweaking confidence thresholds again
- adding more search query variants only
- letting directories become official sites
- auto-drafting from low-identity garbage

Those can improve edges, but they do not solve the core failure mode.

## Implementation Scope

### Phase 1 — Internal Data Model

Add explicit structures for:

- `entity_candidates`
- `contact_candidates`
- `evidence_sources`
- staged confidence fields:
  - `entity_confidence`
  - `contact_confidence`
  - `official_site_confidence`

Acceptance:

- dossier can explain why a lead is reviewable even without `primary_domain`
- current result format remains backward-compatible enough for UI/tests

### Phase 2 — Entity Discovery Fallback

Implement a dedicated fallback path for RU local leads that collects and scores public entity hints from map/directory/registry-style sources.

Requirements:

1. Treat these sources as entity evidence, not official-site evidence.
2. Extract at least:
   - displayed company name
   - address/region hints
   - phones/emails if present
   - source URL
3. Merge multiple weak hints into one stronger entity candidate when they cohere.

Acceptance:

- a raw RU local lead can become `review_required` from coherent public hints alone
- sources are preserved in the dossier

### Phase 3 — Business-Linked Contact Classification

Add a contact classifier that can rank:

- official-domain contact
- public business listing contact
- social/business page contact
- generic weak mailbox
- likely junk

Acceptance:

- review output clearly says whether contact is direct, indirect, or weak
- batch stats can later measure how many leads reached “contactable but not official-site-backed”

### Phase 4 — Verdict Logic Rewrite

Rewrite `build_review_result` around staged evidence.

Acceptance:

- no-official-site should no longer imply `blocked`
- `blocked` should mean true insufficiency, not just “official site missing”
- reasons should explain which stage failed

### Phase 5 — Batch Evaluation Harness

Add a repeatable evaluation pass for 20-50 raw RU leads.

Track at minimum:

- `ready`
- `review_required`
- `blocked`
- `official_site_found`
- `business_linked_contact_found`
- `draft_generated`

Acceptance:

- progress is measured by batch outcome changes, not anecdotes from 1-3 leads

## Definition Of Done

This work is done when all of the following are true:

1. raw RU local leads no longer depend on official-site discovery as the only path out of `blocked`
2. the dossier can carry coherent entity evidence from map/directory/registry sources without falsely calling them official
3. `review_required` becomes the normal output for “real business, weak web presence, still contactable”
4. batch evaluation on raw RU leads shows a clear increase in useful non-blocked outcomes
5. tests cover the staged evidence model and the new review semantics

## First Concrete Build Order

1. Introduce `entity_candidates` and `contact_candidates` into the dossier model.
2. Implement RU entity-discovery fallback extraction from public listing-style pages.
3. Add business-linked contact ranking.
4. Rewrite verdict logic around staged evidence.
5. Run a 20-50 lead batch and compare before/after metrics.
