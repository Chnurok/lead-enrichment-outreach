# TZ — Demo Proxy Cleanup and Final Smoke Path

Date: 2026-06-20

## Goal

Finish the deploy surface so the public demo has a current nginx template, a repeatable smoke script, and one clear operator checklist for restart/pre-demo validation.

## Scope

1. Update nginx template to match the current systemd/auth model.
2. Add a reusable smoke script for the deployed demo instance.
3. Add a written smoke checklist for manual and scripted verification.
4. Wire the smoke path into docs/Makefile.

## Acceptance Criteria

- nginx template no longer reflects the old unauthenticated/public-health assumptions
- one command can smoke-check the current live demo
- deploy docs and public-demo docs both point to the same smoke path
