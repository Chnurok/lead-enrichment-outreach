# TZ — Demo Auth Hardening and Public Demo Cleanup

Date: 2026-06-20

Note: this was the narrower first-pass auth-hardening TZ. The broader follow-up roadmap lives in `docs/demo/TZ-2026-06-20-demo-hardening-roadmap.md`.

## Goal

Finish the public demo hardening pass so the review UI is usable for demos without leaving stale security debt or misleading docs.

## Scope

1. Keep the API protected for non-local use.
2. Stop requiring the token to remain visible in the URL after the first page load.
3. Allow the HTML shell to load so the browser can bootstrap an authenticated session cleanly.
4. Show a clear UI state when a demo viewer opens the page without a token.
5. Update repo/docs language that still says the demo has no auth.
6. Cover the auth UX/server behavior with regression tests and rerun the review-server test suite.

## Acceptance Criteria

- `GET /` works even when server auth is configured.
- `GET /api/review` still returns `401` without a valid token.
- Opening `/?token=...` lets the frontend store the token client-side and continue API calls without keeping the token in the address bar.
- README/demo docs no longer claim that the public demo has no auth.
- `python3 -m unittest tests.test_review_server` passes.
