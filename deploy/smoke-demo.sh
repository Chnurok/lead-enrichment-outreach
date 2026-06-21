#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:18095}"
TOKEN="${REVIEW_UI_AUTH_TOKEN:-}"
TOKEN_FILE="${TOKEN_FILE:-/etc/lead-enrichment-demo.env}"

if [[ -z "$TOKEN" && -f "$TOKEN_FILE" ]]; then
  if [[ -r "$TOKEN_FILE" ]]; then
    TOKEN="$(sed -n 's/^REVIEW_UI_AUTH_TOKEN=//p' "$TOKEN_FILE")"
  elif command -v sudo >/dev/null 2>&1; then
    TOKEN="$(sudo sed -n 's/^REVIEW_UI_AUTH_TOKEN=//p' "$TOKEN_FILE")"
  fi
fi

if [[ -z "$TOKEN" ]]; then
  echo "Missing REVIEW_UI_AUTH_TOKEN or readable TOKEN_FILE" >&2
  exit 1
fi

echo "1. root html"
curl -fsS -o /dev/null "$BASE_URL/"

echo "2. bootstrap redirect"
bootstrap_headers="$(mktemp)"
curl -sS -D "$bootstrap_headers" -o /dev/null "$BASE_URL/?token=$TOKEN"
grep -q '^HTTP/.* 303' "$bootstrap_headers"
grep -qi '^set-cookie: lead_review_demo_auth=' "$bootstrap_headers"
rm -f "$bootstrap_headers"

echo "3. unauthorized api blocked"
unauth_code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/api/review")"
test "$unauth_code" = "401"

echo "4. token-auth health"
curl -fsS -H "X-Review-Token: $TOKEN" "$BASE_URL/healthz" >/dev/null

echo "5. cookie-auth api"
curl -fsS --cookie "lead_review_demo_auth=$TOKEN" "$BASE_URL/api/review" >/dev/null

echo "SMOKE_OK"
