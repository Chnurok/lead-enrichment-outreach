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
2. wait for `Listening on http://127.0.0.1:8095`
3. load `extension/` as unpacked
4. open a company site, map listing, directory page, Google result, or LinkedIn company page
5. click the extension and run `Recover contact`

Current popup behavior:

- detects current tab context
- normalizes page type into `company_website` / `map_listing` / `directory_listing` / `google_results` / `linkedin_company` / `unknown`
- sends one-click recovery request to `/api/extension/enrich`
- shows best contact, review status, warnings, and summary
- shows next step, inferred domain, and review reasons
- shows outreach draft opener when the backend returns one
- keeps a short recent-recoveries list locally
- supports copy/open actions for best contact and primary site

Options page:

- save backend URL
- save optional review token
- test backend health before returning to the popup
- show a short reminder of the recommended local setup

Required local backend:

```bash
make demo-ui
```

If the review UI is protected with `REVIEW_UI_AUTH_TOKEN`, open the extension settings and paste the same token.

## Ship-ready smoke check

Minimum local check before calling the extension ready:

1. `make demo-ui`
2. load unpacked `extension/`
3. confirm popup shows backend `ok`
4. run one recovery from a normal company page or a demo-safe public page
5. confirm:
   - status changes from loading to success or a clear error
   - best contact path is actionable
   - next step / warnings / reasons are visible
   - settings page can validate the backend
