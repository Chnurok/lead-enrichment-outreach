# Deploy demo

Use this when the demo should stay up on a VPS without a manual shell session.

## Files

- `deploy/lead-enrichment-demo.service`
- `deploy/nginx-lead-enrichment-demo.conf`

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
```

## 2. Install systemd unit

```bash
sudo cp deploy/lead-enrichment-demo.service /etc/systemd/system/lead-enrichment-demo.service
sudo systemctl daemon-reload
sudo systemctl enable --now lead-enrichment-demo.service
```

Check:

```bash
systemctl status lead-enrichment-demo.service --no-pager
curl -fsS http://127.0.0.1:8095/healthz
```

## 3. Put nginx in front

```bash
sudo cp deploy/nginx-lead-enrichment-demo.conf /etc/nginx/sites-available/lead-enrichment-demo.conf
sudo ln -sf /etc/nginx/sites-available/lead-enrichment-demo.conf /etc/nginx/sites-enabled/lead-enrichment-demo.conf
sudo nginx -t
sudo systemctl reload nginx
```

Then open:

```text
http://YOUR_HOST/
```

## 4. Update flow

```bash
cd /opt/lead-enrichment-outreach
git pull
python3 -m unittest discover -s tests -q
sudo systemctl restart lead-enrichment-demo.service
curl -fsS http://127.0.0.1:8095/healthz
```

## Notes

- This is for a demo box, not a production multi-user deployment.
- The app still has no auth and should only expose sanitized demo data.
- If you want TLS, terminate it at nginx or a higher-level proxy.
