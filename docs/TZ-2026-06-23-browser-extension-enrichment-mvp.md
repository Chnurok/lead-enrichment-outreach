# Browser Extension MVP — Local Business Contact Recovery

Date: 2026-06-23

## Goal

Build a `Chrome MV3 extension` that helps an operator recover the best available contact path for hard-to-enrich local businesses directly from the current browser tab.

This is not meant to be a generic Apollo/Hunter clone.

The extension should be the main operator surface, while the backend remains the product engine.

## Product thesis

Global enrichment tools are strongest when:

- the company already has a clean website
- the company is visible in major databases
- email verification is the main job

This product should be strongest where those tools are weak:

- local businesses
- regional B2B companies
- weak web presence
- map/directory-driven discovery
- public contact recovery from partial signals

Core promise:

`Open a weak local business page or listing -> recover the best usable contact path -> get a confidence-backed short summary -> move to outreach faster`

## What this product is

This is a:

- browser-native operator tool
- backend-powered enrichment workflow
- human-in-the-loop contact recovery assistant

This is not:

- a giant proprietary contact database
- a fully automated mass outreach machine
- a CRM replacement

## Target wedge

Primary early ICP:

- leadgen agencies
- manual prospecting teams
- SDR/outbound operators working with local or regional B2B companies
- agencies or operators selling into RU/CIS-style messy-web business environments

Secondary ICP later:

- regional service aggregators
- industrial/distributor outreach teams
- local-market recruitment or partner-sourcing teams

Avoid broad initial ICP such as:

- all founders
- all recruiters
- all freelancers
- all SDRs globally

## Primary MVP use case

`Open a company website, map listing, directory page, Google result, or LinkedIn/company-like page -> click extension -> recover the best contactable path and a short company summary`

In MVP, the main value is:

- single lead
- fast operator decision
- contact recovery from noisy public web signals

Not:

- CRM sync
- multi-step campaign management
- batch scraping
- list automation

## Core user value

The user should get, in one extension session:

- detected company or entity name
- detected domain if one exists
- best contact path
- all found contact paths
- short summary
- confidence-backed warnings
- copy actions
- optional short outreach opener

The important distinction is:

- not only “best email”
- but “best reachable contact path”

That can be:

- official-domain email
- public business-linked email
- phone
- contact page
- social/business page fallback

## Product positioning

Suggested positioning lines:

- `Recover contactable leads from weak business web presence`
- `Find the best reachable contact path for local businesses`
- `Turn messy public web signals into outreach-ready leads`
- `Map and directory pages into confidence-backed contact recovery`

Avoid generic lines like:

- `Get contacts from any page`
- `Prospecting enrichment inside your browser`

Those are too broad and commoditized.

## Monetization strategy

### Initial go-to-market

Start service-first or pilot-first.

Use the extension as the operator-facing shell on top of the backend workflow.

Sell first to teams that already do manual prospecting and currently waste time on:

- dead websites
- unclear contact ownership
- local company listings with weak official presence

### Commercial model after validation

Best likely model:

- seat + usage hybrid

Example shape:

- platform access per operator seat
- monthly usage bucket for enrichments/contact recoveries
- optional higher-cost plan for batch/export/team workflows

Indicative pricing direction once value is proven:

- `$39-99+/seat/month` for operator-facing usage
- or lower seat + usage credits
- or agency/internal pilot pricing first

Do not anchor MVP around ultra-cheap prosumer pricing like `$9/mo` unless the product becomes much more self-serve than it is today.

### What to sell

Sell outcomes like:

- `% blocked -> review_required recovered`
- `% leads with usable contact path`
- `time saved per operator`
- `cost per outreach-ready lead`

Do not sell:

- “biggest database”
- “verified emails at scale”

## Product architecture

### 1. Content script

Responsibilities:

- inspect the current page
- extract:
  - current URL
  - page title
  - visible text excerpt
  - selected text if available
  - visible emails/phones on page
  - page type hints
  - likely entity clues

### 2. Popup UI

Responsibilities:

- show detected entity/page context
- show one main `Recover contact` action
- show loading/progress state
- show structured result
- expose copy/open actions
- expose warnings/confidence
- expose usage left and upgrade CTA

### 3. Background service worker

Responsibilities:

- manage auth/session
- send recovery/enrichment requests to backend
- cache recent results
- persist minimal local history

### 4. Backend API

Responsibilities:

- accept page context
- run the enrichment/contact-recovery pipeline
- return normalized result
- enforce auth, quotas, and billing
- count recoveries/usage

### 5. Optional web dashboard

Support layer only:

- login
- account
- billing
- usage
- maybe recent history

It is not the primary product surface.

## Supported inputs in MVP

Priority v1 page types:

- company websites
- map/listing pages
- directory pages
- Google result pages

Optional but not core in v1:

- LinkedIn company pages
- LinkedIn person pages

Reason:

LinkedIn makes the product look generic.
Weak-web local business contact recovery is the sharper wedge.

## Main user flow

1. User opens a business page, listing, map card, or result page.
2. User clicks the extension.
3. Extension shows detected entity clues and a `Recover contact` action.
4. User clicks the main action.
5. Backend runs enrichment/contact recovery.
6. Extension shows:
   - entity name
   - best contact path
   - alternative contact paths
   - short summary
   - confidence/warnings
7. User copies the result or opens the discovered contact page.

## Functional requirements

### 1. Page detection

The extension must detect:

- current URL
- likely company/entity/domain
- page type:
  - `company_website`
  - `map_listing`
  - `directory_listing`
  - `google_results`
  - `linkedin_company`
  - `unknown`

### 2. Recovery trigger

When the user clicks the main action, the extension sends:

- `url`
- `title`
- `page_text_excerpt`
- optional `selected_text`
- detected `company`
- detected `domain`
- detected `page_type`
- visible `emails`
- visible `phones`

### 3. Result schema

The backend must return at minimum:

- `company`
- `primary_domain`
- `summary`
- `best_contact_email`
- `emails`
- `phones`
- `contact_pages`
- `social_links`
- `confidence`
- `warnings`

Recommended staged fields should also be available to the extension:

- `entity_candidates`
- `contact_candidates`
- `entity_confidence`
- `contact_confidence`
- `official_site_confidence`
- `evidence_summary`

Optional:

- `outreach_opener`

### 4. Popup result UI

The popup must display:

- entity/company
- domain if present
- best contact path
- alternative contact paths
- summary
- confidence
- warnings
- copy/open actions

### 5. Usage gating

The user must see:

- usage left
- locked state after quota exhaustion
- upgrade CTA

### 6. Auth

MVP auth can stay simple:

- email magic link
- or token-based login tied to a minimal dashboard

### 7. Minimal history

Keep recent history of:

- last `10-20` recoveries

Stored:

- locally
- or account-linked if already easy

## UX screens

### 1. Not logged in

Show:

- short wedge-specific value proposition
- login/signup
- usage teaser

### 2. Ready

Show:

- detected entity/page info
- `Recover contact` button

### 3. Loading

Show:

- progress state
- short expectation text

Example:

- `Checking page context`
- `Looking for public contact paths`
- `Scoring best contact option`

### 4. Result

Show:

- best contact path
- summary
- confidence
- alternative contacts
- warnings
- copy/open actions
- usage left

### 5. Upgrade

Show:

- quota exhausted state
- concise B2B upgrade CTA

## What not to build in MVP

Do not build yet:

- CRM sync
- auto-scraping large lists
- bulk enrichment inside extension
- auto-sending outreach
- team workspaces
- complex billing stack
- multi-browser support beyond Chrome

## MVP scope

### P0

- Chrome extension shell
- popup UI
- content script page detection
- backend recover/enrich endpoint
- single-lead contact recovery result
- login
- usage limits
- copy/open actions

### P1

- LinkedIn-specific parsing improvements
- outreach opener generation
- saved history
- better paywall UX
- better error states

### P2

- CRM integrations
- saved lists
- export flows
- team plans
- batch assist modes

## Reuse from existing project

Can be reused:

- enrichment backend logic
- staged evidence model
- contact extraction
- confidence and warning logic
- reviewable contact recovery semantics

Should not be reused as main product shape:

- operator review web UI as the primary surface
- CSV-first framing
- internal batch/export demo framing

Right split:

- backend reuse: `yes`
- browser UX reuse: `build new`
- operator semantics reuse: `yes`

## Definition of done

The MVP is complete when:

- the extension installs and opens correctly
- on a weak business page/listing the user can click one action
- backend returns a useful contact recovery result
- popup shows best contact path + summary + warnings
- login works
- usage quota works
- upgrade path exists
- a user gets useful value within `10-20` seconds

## Strategic note

If this product starts to feel like:

- `Apollo-lite`
- `Hunter in a popup`
- `generic prospecting helper`

then the positioning has drifted.

If it feels like:

- `this rescues hard local leads other tools leave behind`

then the product is on the right track.
