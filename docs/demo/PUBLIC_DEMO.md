# Public demo

Use this when the product needs to be reachable on a remote box instead of only on localhost.

## Fast path

Run:

```bash
make demo-launch-public
```

This does three things:
- seeds `examples/demo-review.json`
- rebuilds `examples/demo-output.json`
- binds the UI to `0.0.0.0:8095`

The rebuilt batch is deterministic: it comes from `examples/demo/index.json`, not live enrichment calls.

## Smoke check

On the server:

```bash
make demo-public-health
make batch-demo
```

Expected result:
- JSON from `/healthz`
- `demo_batch_exists: true`
- `demo_batch_summary` with `ready=1`, `review_required=1`, `blocked=1`

## What to expose

Minimum useful URL:

```text
http://YOUR_HOST:8095/
```

Health URL:

```text
http://YOUR_HOST:8095/healthz
```

## Minimal presenter flow

1. Open `/` and show the preloaded queue.
2. Open one `ready` lead and show the draft/edit/decision surface.
3. Show the coverage dashboard and approved export path.
4. If needed, open `/healthz` to prove the demo batch is live and loaded.

## Notes

- This is still a lightweight demo surface, not a hardened production deployment.
- The server is local Python HTTP, no auth, no rate limiting, no reverse proxy by default.
- Use only with sanitized demo artifacts.
- If `/healthz` is up but `demo_batch_summary` is empty or stale, rerun `make batch-demo` and refresh the page.

For a longer-lived VPS setup with `systemd` and `nginx`, use `docs/demo/DEPLOY.md`.
