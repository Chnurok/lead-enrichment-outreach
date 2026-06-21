# TZ — Demo UX Polish and Bulk-Flow Edge Cases

Date: 2026-06-20

## Goal

Make the review demo feel less fragile for a human operator during the main browser walkthrough, especially around mass actions, empty states, and transitions between review, save, approve, and export.

## Scope

1. Reduce awkward dead-ends in the browser flow.
2. Make bulk actions visibly stateful while they run.
3. Improve post-action navigation so the operator lands on the next sensible item.
4. Make empty-state / fully-complete-state language more explicit.
5. Add regression coverage for bulk-flow helpers where practical.

## Acceptance Criteria

- bulk actions cannot be spam-clicked while already running
- the UI gives clearer operator feedback for “nothing left to do”
- after saving/approving in bulk, the UI moves toward the next useful lead instead of just silently refreshing
- test suite still passes after the changes
