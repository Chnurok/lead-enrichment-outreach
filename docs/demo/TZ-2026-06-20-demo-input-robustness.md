# TZ — Demo Input Robustness and Safer Imports

Date: 2026-06-20

## Goal

Harden the review demo against noisy or oversized operator inputs so a public demo box does not fall over on malformed CSV/JSON/ZIP imports or unbounded review text fields.

## Scope

1. Add server-side limits for CSV uploads, ZIP imports, and text fields in saved reviews.
2. Reject invalid base64 and oversized archives before parsing them deeply.
3. Keep import behavior fail-closed with explicit `4xx` errors.
4. Add client-side file-size prechecks for CSV/JSON/ZIP uploads.
5. Cover the new limits with regression tests.

## Acceptance Criteria

- oversized CSV upload is rejected
- invalid/oversized ZIP import is rejected
- oversized review notes/body/subject fields are rejected
- browser file inputs stop obviously too-large files before upload
- `python3 -m unittest tests.test_review_server` passes after the changes
