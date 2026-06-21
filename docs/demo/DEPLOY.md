# Deploy demo

Use this when the demo should stay up on a VPS without a manual shell session.

## Files

- `deploy/lead-enrichment-demo.service`
- `deploy/nginx-lead-enrichment-demo.conf`
- `deploy/smoke-demo.sh`
- `docs/demo/SMOKE_CHECKLIST.md`

## Assumed app path

The templates assume the repo lives at:

```text
/opt/lead-enrichment-outreach
```

If you deploy elsewhere, update the `WorkingDirectory` and `ExecStart` paths in the systemd unit.
The bundled unit also assumes the runtime user is `clawd`; change `User=` and `Group=` if your VPS uses a different app user.

## 1. Install the repo

```bash
sudo mkdir -p /opt/lead-enrichment-outreach
sudo chown -R $USER:$USER /opt/lead-enrichment-outreach
git clone <REPO_URL> /opt/lead-enrichment-outreach
cd /opt/lead-enrichment-outreach
pip install -r requirements.txt
python3 -m unittest discover -s tests -q
python3 ui/review_server.py --build-demo-batch-only --demo-batch-file examples/demo-output.json >/tmp/lead-enrichment-demo-batch.json
```

## 2. Create auth token env file

```bash
sudo tee /etc/lead-enrichment-demo.env >/dev/null <<'EOF'
REVIEW_UI_AUTH_TOKEN=replace-with-a-long-random-token
EOF
sudo chmod 600 /etc/lead-enrichment-demo.env
```

The public demo now requires that token. Open the UI with `?token=...`; the server upgrades it into an auth cookie and redirects the browser to a clean URL after the first hit.

## 3. Install systemd unit

```bash
sudo cp deploy/lead-enrichment-demo.service /etc/systemd/system/lead-enrichment-demo.service
sudo systemctl daemon-reload
sudo systemctl enable --now lead-enrichment-demo.service
```

Check:

```bash
systemctl status lead-enrichment-demo.service --no-pager
TOKEN=$(sudo sed -n 's/^REVIEW_UI_AUTH_TOKEN=//p' /etc/lead-enrichment-demo.env)
curl -fsS -H "X-Review-Token: $TOKEN" http://127.0.0.1:8095/healthz
```

Expected health signals:
- `demo_batch_exists` is `true`
- `demo_batch_summary.ready` is `1`
- `demo_batch_summary.review_required` is `1`
- `demo_batch_summary.blocked` is `1`

## 4. Put nginx in front

```bash
sudo cp deploy/nginx-lead-enrichment-demo.conf /etc/nginx/sites-available/lead-enrichment-demo.conf
sudo ln -sf /etc/nginx/sites-available/lead-enrichment-demo.conf /etc/nginx/sites-enabled/lead-enrichment-demo.conf
sudo nginx -t
sudo systemctl reload nginx
```

Before enabling it, update `server_name` in the nginx file so it does not collide with unrelated sites on the box.

Then open:

```text
http://YOUR_HOST/?token=YOUR_TOKEN
```

## 5. Update flow

```bash
cd /opt/lead-enrichment-outreach
git pull
python3 -m unittest discover -s tests -q
python3 ui/review_server.py --build-demo-batch-only --demo-batch-file examples/demo-output.json >/tmp/lead-enrichment-demo-batch.json
sudo systemctl restart lead-enrichment-demo.service
TOKEN=$(sudo sed -n 's/^REVIEW_UI_AUTH_TOKEN=//p' /etc/lead-enrichment-demo.env)
curl -fsS -H "X-Review-Token: $TOKEN" http://127.0.0.1:8095/healthz
./deploy/smoke-demo.sh http://127.0.0.1:18095
```

## Notes

- This is for a demo box, not a production multi-user deployment.
- The app now requires a shared auth token for non-local access.
- If you want TLS, terminate it at nginx or a higher-level proxy.
- The bundled systemd unit already starts the server with `--demo`, but rebuilding the demo batch explicitly during install/update gives you a simple preflight and a file you can inspect if health looks wrong.
- The smoke script assumes `/etc/lead-enrichment-demo.env` unless `REVIEW_UI_AUTH_TOKEN` or `TOKEN_FILE` is set explicitly.
