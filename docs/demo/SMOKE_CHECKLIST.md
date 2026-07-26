# Demo Smoke Checklist

Use this after deploy, after restart, and before an important remote demo.

## Fast path

```bash
./deploy/smoke-demo.sh http://127.0.0.1:18095
```

Expected final line:

```text
SMOKE_OK
```

## What it verifies

1. root HTML responds
2. `/?token=...` returns `303`
3. bootstrap response sets `lead_review_demo_auth`
4. unauthenticated API access is blocked with `401`
5. token-authenticated `/healthz` works
6. cookie-authenticated `/api/review` works

## Manual browser pass

1. Open the first-link URL with `?token=...`
2. Confirm the URL becomes clean after load
3. Confirm the demo batch opens
4. Confirm a ready lead can be opened
5. Confirm save / save-as / bulk actions are clickable and recover cleanly

## Extension pass

1. Run `make extension-check` and `make extension-backend-smoke`.
2. Start `make demo-ui` and confirm `http://127.0.0.1:8095/healthz` reports `demo_mode: true`.
3. Load unpacked `extension/`; do not load or edit `extension.zip`.
4. Confirm the popup shows backend `ok`, normalized current-page context, and local recent recoveries.
5. Exercise all three `Demo-safe result` values and confirm distinct `ready`, `review_required`, and `blocked` states.
6. Confirm best contact, warnings, reasons, next step, opener (ready only), and copy/open actions match the state.
7. Stop the backend and reopen the popup: it must show a persistent connection error while keeping recent recoveries visible.

## If something fails

Check in this order:

1. `systemctl status lead-enrichment-demo.service --no-pager`
2. `journalctl -u lead-enrichment-demo.service -n 100 --no-pager`
3. `TOKEN=$(sudo sed -n 's/^REVIEW_UI_AUTH_TOKEN=//p' /etc/lead-enrichment-demo.env)`
4. `curl -i -H "X-Review-Token: $TOKEN" http://127.0.0.1:18095/healthz`
