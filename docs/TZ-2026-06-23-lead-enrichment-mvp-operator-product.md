# Lead Enrichment MVP: operator-first product

## Goal

Turn the existing `lead-enrichment-outreach` repo into a simple operator-facing MVP that can be sold as a narrow paid service:

- input: `CSV` with companies and/or domains
- processing: enrichment -> trust review -> optional draft generation
- output: reviewed/exportable leads for manual outreach or client handoff

This MVP is based on the existing codebase and should reuse the current enrichment, review, and export pipeline instead of introducing a new product from scratch.

## Existing project base

The current repo already includes:

- lead enrichment into dossier JSON
- trust gating with `ready`, `review_required`, `blocked`
- outreach draft generation
- batch workflow for CSV
- local review UI / HTTP layer
- ready-only export in JSON/CSV
- demo/deploy path

Key files:

- `README.md`
- `skill/scripts/enrich_lead.py`
- `skill/scripts/workflow.py`
- `skill/scripts/batch_workflow_csv.py`
- `skill/scripts/export_ready_leads.py`
- `ui/review_server.py`
- `skill/references/lead-schema.md`

## Product framing

The MVP is not a self-serve SaaS. It is an operator tool for producing lead batches with human review.

Initial sellable offer:

- `100 enriched leads in 24h`
- or `company/domain list -> best contacts + short personalization`

Primary use case:

- `company/domain -> website -> best contact -> summary -> short outreach line`

## What the MVP must do

### Input

Accept a CSV with:

- `company` — required
- `domain` — optional
- `region` — optional

The input format should remain compatible with the current batch workflow.

### Processing

For each lead:

1. run enrichment
2. build dossier
3. assign trust status
4. generate draft when allowed
5. expose result in review UI

### Output

Export reviewed leads in `CSV` and `JSON`.

Main output should be a client/operator-ready CSV containing at minimum:

- `company`
- `domain`
- `primary_domain` or `primary_site_url`
- `website_title`
- `summary`
- `best_contact_email`
- `best_contact_source_url`
- `emails`
- `phones`
- `contact_pages`
- `review_status`
- `next_step`
- `draft_subject`
- `draft_body`
- `draft_target_contact`
- `confidence`
- `warnings`

## Non-goals

Do not build in this MVP:

- billing
- mass sending
- CRM
- public multitenant SaaS
- complex auth/roles
- “AI SDR platform”

## Functional requirements

### 1. CSV upload

The UI must allow the operator to:

- upload a CSV file
- validate that the `company` column exists
- choose processing options before run:
  - `query_mode`: `basic` or `smart`
  - `fast_mode`
  - `allow_review_required`
  - optional offer text for draft generation

Limits should continue to use the current server-side caps where possible.

### 2. Batch enrichment

The system must reuse `skill/scripts/batch_workflow_csv.py`.

Requirements:

- each row with a valid company runs independently
- one failed lead must not crash the whole batch
- a batch artifact JSON is produced and stored
- batch summary must include:
  - total
  - ready
  - review_required
  - blocked
  - draft_generated

### 3. Lead dossier view

Each lead must expose the current dossier fields from `lead-schema.md`, including:

- `company`
- `region`
- `query`
- `primary_domain`
- `website_title`
- `summary`
- `emails`
- `phones`
- `contact_pages`
- `social_links`
- `snippets`
- `trust_signals`
- `confidence`
- `warnings`

The UI should make evidence readable rather than hide it in raw JSON.

### 4. Trust review

Use the current trust statuses:

- `ready`
- `review_required`
- `blocked`

Rules:

- `ready` can be drafted and exported
- `review_required` requires human review before downstream use
- `blocked` is excluded from handoff/export by default

### 5. Draft generation

Reuse `skill/scripts/workflow.py` and the existing draft generator.

Requirements:

- drafts are auto-generated for `ready`
- drafts for `review_required` are only generated when explicitly allowed
- operator can edit draft subject/body
- no automatic sending

### 6. Operator review UI

Reuse `ui/review_server.py` as the base.

Must preserve:

- dossier summary view
- trust verdict, reasons, warnings
- contact/evidence review
- draft editing
- operator decision:
  - `approved`
  - `rejected`
  - `needs_review`
- saved review payloads
- bulk actions for ready leads

Must simplify:

- reduce demo/presenter-first UX
- make operator workflow primary

### 7. Export

Support:

- ready-only export
- approved-only export
- JSON export
- CSV export
- optional handoff bundle export if already supported cleanly

CSV is the primary deliverable.

### 8. Saved reviews and reopen flow

The system must support:

- reopening saved review files
- reopening batch results
- bulk-approving ready leads
- exporting only approved leads

## UX structure

### Screen 1. Upload

Elements:

- CSV file picker
- offer input
- query mode selector
- fast mode toggle
- allow review-required drafts toggle
- run button

### Screen 2. Batch results

Show:

- total
- ready
- review_required
- blocked
- drafts generated

Actions:

- open review queue
- export ready
- export approved

### Screen 3. Review queue

Layout:

- left: lead list
- top: filters
- right: selected lead detail

Filters:

- all
- ready
- review_required
- blocked
- approved
- rejected
- needs_review

### Screen 4. Lead detail

Show:

- company / domain
- summary
- trust verdict
- warnings
- source-backed contacts
- snippets / evidence
- draft editor
- approve / reject / needs_review controls

### Screen 5. Export

Actions:

- export JSON
- export CSV
- export approved-only
- export handoff bundle

## Reuse without rewrite

Keep and reuse directly:

- enrichment engine in `skill/scripts/enrich_lead.py`
- workflow wrapper in `skill/scripts/workflow.py`
- batch CSV runner in `skill/scripts/batch_workflow_csv.py`
- export base in `skill/scripts/export_ready_leads.py`
- review backend in `ui/review_server.py`

## Required changes

### P0

- remove demo-first emphasis from UI copy/layout
- keep upload -> review -> export as primary path
- support approved-only CSV export
- expand export fields so output is useful for real ops

### P1

- save and reopen batch runs
- improved queue filters
- simplified operator dashboard
- bulk approve for ready leads

### P2

- better handoff bundle UX
- reusable offer templates
- cleaner batch history UX

## Definition of done

The MVP is complete when:

- a CSV with `50-100` leads can be uploaded
- batch workflow runs successfully
- batch artifact is saved
- operator can review each lead in the UI
- each lead shows trust status and evidence
- drafts exist for `ready` leads
- operator can approve/reject leads
- approved leads can be exported to CSV
- exported CSV is usable for manual outreach or client handoff

## Delivery scope

### Scope for one evening

- de-emphasize demo UX
- keep a stable upload -> review -> export flow
- improve CSV export schema
- ensure one happy-path operator flow works cleanly

### Scope for three days

- proper operator-first UI
- batch history / reopen flow
- approved-only export flow
- cleaned-up review states
- minimal landing/offer framing for selling the service
