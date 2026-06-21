# Demo Operator Workflow Hardening

## Goal

Turn the browser review UI into a safer operator surface: prevent accidental loss of manual edits, make queue navigation faster, and keep the demo usable under real presenter/operator behavior.

## Problems

- Draft edits can be lost when the operator switches leads, opens another saved review, or loads a different batch.
- The UI still assumes mouse-heavy navigation and does not support quick queue movement during a demo.
- Small presenter actions like language switching should not clobber in-progress operator text.
- The queue filter is not sticky across reloads, which makes repeated demo runs more annoying than they need to be.

## Scope

- Add unsaved-change detection for draft/body/contact/notes/decision fields.
- Warn before destructive navigation inside the browser UI.
- Add keyboard shortcuts for common operator actions.
- Preserve queue filter preference locally.
- Keep unsaved edits intact during language switches.

## Acceptance Criteria

- Switching leads or importing/loading another artifact prompts before discarding dirty edits.
- Browser refresh/close warns when the draft is dirty.
- `Ctrl/Cmd+S` saves the active review.
- `Ctrl/Cmd+Shift+S` saves the active review file.
- `J/K` navigates visible queue items.
- `1/2/3` set decision outside text-entry mode.
- The active queue filter persists across reloads.
- Language switching does not wipe unsaved operator edits.

## Files

- `ui/index.html`

## Verification

- Manual browser check for dirty-state prompts and keyboard shortcuts.
- Existing server regression suite still passes unchanged.
