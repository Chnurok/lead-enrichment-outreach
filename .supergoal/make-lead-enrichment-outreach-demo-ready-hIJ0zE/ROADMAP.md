# Supergoal Roadmap

## Goal

Make `lead-enrichment-outreach` demo-ready, deployable, and polished as a product:
- deterministic demo story
- stable operator review workflow
- ready-only export/handoff that matches the product narrative
- deploy path that can be shown without babysitting

## Phases

### Phase 1
Stabilize the demo artifact path so `batch-demo`, `demo-ui`, and `ready-export-demo` are reproducible from repo fixtures instead of live enrichment variance.

Acceptance:
- `make batch-demo` produces `ready=1`, `review_required=1`, `blocked=1`
- `make ready-export-demo` exports exactly one ready lead from the demo artifact
- test suite stays green

### Phase 2
Exercise the review UI as an operator, identify UX or workflow friction in approve/save/export/import paths, and fix the highest-value issues.

Acceptance:
- core review actions work cleanly in the UI
- no broken demo affordances
- README/demo docs still match observed behavior

### Phase 3
Harden deploy/demo operations so a remote demo host can be brought up and updated with minimal surprises.

Acceptance:
- deploy docs match current commands and behavior
- health check and startup path are explicit and current
- obvious operator/deploy footguns are documented or removed

### Phase 4
Final polish and audit.

Acceptance:
- tests pass
- demo commands tell one coherent product story
- no mismatch between docs, artifacts, and actual outputs
