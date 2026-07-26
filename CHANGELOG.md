# Changelog

## v0.2.0

### Extension-first ship surface

- hardened the MV3 popup and settings flow around backend health, token storage, hosted-backend permissions, and stale error states
- normalized current-page context into the six documented page types
- added actionable recovery evidence, recent recoveries, opener rendering, and distinct `ready` / `review_required` / `blocked` operator states
- added deterministic demo-safe extension scenarios plus static, popup-state, backend-contract, and local UI smoke checks
- kept `extension/` canonical and `extension.zip` ignored as a derived artifact

### Stronger core behavior

- added explainable `site_candidates` output instead of only returning one chosen domain
- added `review` verdicts (`ready`, `review_required`, `blocked`) to make human review explicit
- added ranked `top_contact_candidates` with reasons and source attribution
- kept confidence scoring, but turned it into a clearer decision surface

### Fewer embarrassing failures

- `generate_outreach.py` now refuses to draft by default when the dossier is not ready
- added `--allow-review-required` override for conscious manual use
- preserved support for weak-but-official examples while making the risk visible

### Proof

- expanded tests to cover review verdicts, contact explanations, and CLI refusal/override behavior
- refreshed examples to show both a weak-contact review case and a ready-to-draft case
