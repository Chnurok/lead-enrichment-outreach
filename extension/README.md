# Browser Extension

This directory is the canonical source of truth for the extension.

`extension.zip` is only a convenience artifact if you deliberately regenerate it later; do not treat the zip as the editable source.

## Load unpacked

Load unpacked from this directory in a Chromium-based browser:

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select the `extension/` directory

Default backend:

- `http://127.0.0.1:8095`

Recommended operator flow:

1. run `make demo-ui`
2. wait for `Review UI running on http://127.0.0.1:8095`
3. load `extension/` as unpacked
4. open a company site, map listing, directory page, Google result, or LinkedIn company page
5. click the extension and run `Recover contact`

Current popup behavior:

- detects current tab context
- normalizes page type into `company_website` / `map_listing` / `directory_listing` / `google_results` / `linkedin_company` / `unknown`
- sends one-click recovery request to `/api/extension/enrich`
- shows best contact, its verification state, review status, warnings, and summary
- shows next step, inferred domain, and review reasons
- shows outreach draft opener when the backend returns one
- keeps an always-visible short recent-recoveries list locally
- supports copy/open actions for the current result and recent primary sites
- keeps stale results hidden after a failed retry and preserves backend errors until the connection is healthy
- renders `ready`, `review_required`, and `blocked` as distinct operator states; it never auto-sends outreach

Options page:

- save backend URL
- save optional review token
- test backend health before returning to the popup
- show a short reminder of the recommended local setup
- request access only to a custom backend host that you explicitly save or test

Required local backend:

```bash
make demo-ui
```

If the review UI is protected with `REVIEW_UI_AUTH_TOKEN`, open the extension settings and paste the same token.

When the backend is started with `make demo-ui`, the popup exposes a `Demo-safe result` selector. Its `ready`, `review_required`, and `blocked` results come from the bundled demo batch, so the extension story is deterministic and does not depend on live enrichment. Run the server without `--demo` for a real current-page recovery.

## Ship-ready smoke check

Automated contract checks:

```bash
make extension-check
make extension-backend-smoke
```

The first command validates extension JavaScript, manifest wiring, DOM bindings, backend paths, permissions, page-type normalization, persistent offline errors, and the ready/demo popup flow. The second boots the same local handler used by `make demo-ui` and exercises all three demo-safe extension outcomes through `/healthz` and `/api/extension/enrich`. Both are included in `make verify`.

Manual unpacked-extension check before a demo:

1. `make demo-ui`
2. load unpacked `extension/`
3. confirm popup shows backend `ok`
4. keep the default `Demo-safe result` set to `Ready · DeepL` and run one recovery from any normal `http://` or `https://` page
5. confirm:
   - status changes from loading to a clear `ready`, `review_required`, `blocked`, or error state
   - best contact path is actionable
   - next step / warnings / reasons are visible
   - settings page can validate the backend
6. repeat with the other two demo-safe outcomes

For a hosted backend, enter its `http://` or `https://` base URL in Settings and accept the backend-host browser permission prompt. Do not put credentials in the URL; use the review-token field.

## Packaging

Ship or load the contents of `extension/`. If a zip is required, generate `extension.zip` from this directory only after verification and keep it out of Git. The root `.gitignore` already excludes `extension.zip`.
