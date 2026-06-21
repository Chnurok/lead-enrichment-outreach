# Demo Storytelling And Saved-Review Triage

## Goal

Improve the browser demo so it explains itself better during a live walkthrough and makes saved-review state easier to reason about without extra narration.

## Problems

- The UI has strong data, but the presenter still has to mentally summarize what matters most right now.
- Saved review files are listed flat, which makes it harder to see approval bottlenecks at a glance.
- The hero story and operator panel do not adapt enough to the current batch state.

## Scope

- Add a dynamic “what matters now” overview.
- Add a dynamic demo-story block tied to current batch/review state.
- Add triage buckets for saved review files.
- Keep the changes frontend-only and compatible with the current API.

## Acceptance Criteria

- The UI highlights the current bottleneck or next best operator step automatically.
- The hero/presenter story updates when batch state changes.
- Saved reviews are grouped into:
  - pending approval
  - already approved
  - not ready upstream
- The active company is visually recognizable inside saved-review triage.
- Existing server tests and smoke checks remain green.

## Files

- `ui/index.html`

## Verification

- JS parses successfully.
- Existing unit tests pass.
- Local smoke check passes.
