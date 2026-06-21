# TZ — Public Demo Hardening Roadmap

Date: 2026-06-20

## Objective

Turn the public `lead-enrichment-outreach` demo from a "works on a VPS" surface into a demo box that is reasonably hardened for repeated remote use without carrying obvious security, UX, or deployment footguns.

## Context

The first hardening pass already closed the biggest holes:

- non-local API access now requires a shared token
- wildcard CORS was removed
- `HEAD` now works
- absolute server paths no longer leak in saved-review errors
- the demo process is now managed by `systemd`

That still leaves a second layer of work:

- token bootstrap and persistence are still awkward
- docs still need a single source of truth for the public demo path
- root page / API auth behavior should be cleaner and more intentional
- public demo traffic should get safer default headers
- regression tests should cover the public-demo auth UX, not just the API gate

## Scope

### Phase 1 — Auth bootstrap and session flow

Goal: make the first-open experience usable without leaving the token permanently visible in the browser address bar or requiring JS-visible token propagation forever.

Tasks:

1. Support bootstrap of an authenticated browser session from the initial shared token.
2. Prefer cookie-backed demo auth for same-origin browser use.
3. Keep explicit header auth working for curl/health/manual checks.
4. Stop treating query-string token auth as a general-purpose API mechanism.
5. Preserve a graceful root-page experience when the browser has no valid session yet.

Acceptance:

- `GET /?token=VALID` can establish a browser session.
- `GET /` works for HTML delivery even before API auth is established.
- `GET /api/review` still returns `401` without valid auth.
- Browser use no longer depends on continuously copying the token into frontend API headers.

### Phase 2 — HTTP hardening

Goal: add safer defaults to the demo surface without overcomplicating the simple Python server.

Tasks:

1. Add basic security headers suitable for a static HTML + JSON demo surface.
2. Set cookie attributes intentionally.
3. Avoid caching auth-sensitive responses too casually.
4. Keep behavior compatible with the existing local demo path.

Acceptance:

- responses include basic hardening headers where appropriate
- auth cookie is scoped and not exposed to JS
- no regression in local demo usage

### Phase 3 — Frontend unauthorized UX

Goal: make the operator experience explicit when the page is opened without a valid demo session.

Tasks:

1. Show a clean "token/session required" state.
2. Detect `401` from API calls and switch into that state cleanly.
3. Avoid a broken half-rendered UI when auth is missing or expired.

Acceptance:

- unauthorized page load is understandable
- expired/missing auth does not leave the UI in an inconsistent state

### Phase 4 — Docs and deploy truthfulness

Goal: make the repo’s docs match the actual behavior of the public demo.

Tasks:

1. Update README / README.ru wording about demo auth.
2. Update public demo docs to describe the current bootstrap flow.
3. Update deploy docs so the `systemd` path, token env file, and smoke checks stay aligned.
4. Keep the docs clear about what is still *not* production-grade.

Acceptance:

- no major public-demo doc still claims "no auth"
- first-open instructions match the real server behavior

### Phase 5 — Regression coverage and rollout

Goal: leave behind proof that the demo hardening path stays intact.

Tasks:

1. Add tests for root-page behavior under auth.
2. Add tests for bootstrap/session behavior.
3. Re-run the review server suite.
4. Restart the live `systemd` service and smoke-test the new behavior.

Acceptance:

- test suite passes
- live service still works after restart
- first-open, unauthorized API, and token-authenticated health checks are all verified

## Deliverables

- server code updates
- frontend code updates
- expanded tests
- updated docs
- live rollout on the current VPS demo instance

## Definition of Done

The work is done when:

1. the public demo can be opened cleanly from a tokenized first link,
2. the browser session no longer depends on exposing that token in the address bar after bootstrap,
3. unauthorized API access remains blocked,
4. docs reflect reality,
5. tests pass,
6. the `systemd` service is restarted and smoke-checked successfully.
