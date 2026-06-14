# Thinking

## Why this goal

The repo is already beyond prototype level: solid tests, local UI, deploy docs, and a coherent product story exist. The highest-value path to a "ready project" is not adding more surface area but making the demo/product path reliable, believable, and easy to show.

## Top risks

1. Demo drift: README/demo commands promise a ready-path handoff, but live enrichment variance can silently break that promise.
2. UI/operator gaps: review/export/import flows may technically exist but still feel fragile when driven end-to-end.
3. Deploy mismatch: docs may lag behind the actual command flow even if the code works locally.

## Non-obvious dependencies

1. The exported ready-only artifact has to match the same batch artifact loaded by the review UI.
2. Demo docs are only trustworthy if the generated `examples/demo-output.json` is deterministic.
3. Final deploy confidence depends on demo commands being stable first.

## Phase 1 verdict

The first real blocker was confirmed and fixed:
- before: `make batch-demo` returned `ready=0`, which undermined the product narrative
- after: deterministic example-backed demo batch returns `ready=1`, `review_required=1`, `blocked=1`

## Phase 2 verdict

The operator workflow itself is good enough to demo, but there was one credibility-killer:
- after bulk save/approve, the right-hand editor panel and queue metadata could still show stale `needs_review` / `decision pending` hints

That is now fixed:
- active lead state rehydrates from saved review files after bulk actions
- queue cards and next-step hint rerender from updated saved review state
- local demo console is cleaner by handling `/favicon.ico`
