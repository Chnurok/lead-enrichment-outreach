# Changelog

## v0.2.0

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
