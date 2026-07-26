#!/usr/bin/env python3
"""Exercise the local demo server contract used by the unpacked extension."""

import json
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.review_server import Handler, ReviewStore, ThreadedHTTPServer, bootstrap_demo_artifacts


def request_json(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        review_path = Path(tmp) / "review.json"
        batch_path = Path(tmp) / "demo-output.json"
        bootstrap_demo_artifacts(review_path, batch_path)

        server = ThreadedHTTPServer(("127.0.0.1", 0), Handler)
        server.store = ReviewStore(review_path)
        server.html_path = ROOT / "ui" / "index.html"
        server.teaser_html_path = ROOT / "ui" / "teaser.html"
        server.demo_batch_path = batch_path
        server.auth_token = ""
        server.demo_mode = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            health = request_json(f"{base_url}/healthz")
            assert health["ok"] is True
            assert health["demo_mode"] is True
            assert health["demo_batch_summary"]["total"] == 3

            for scenario in ("ready", "review_required", "blocked"):
                response = request_json(f"{base_url}/api/extension/enrich", {
                    "demo_scenario": scenario,
                    "page_context": {
                        "url": "https://example.com/company",
                        "title": "Extension smoke page",
                        "page_type": "company_website",
                    },
                })
                result = response["result"]
                assert response["ok"] is True
                assert response["demo_safe"] is True
                assert result["review"]["status"] == scenario
                assert result["detected_context"]["page_type"] == "company_website"
                assert result["review"]["next_step"]
                assert isinstance(result["warnings"], list)
                if scenario == "ready":
                    assert result["best_contact"]["value"]
                    assert result["draft"]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    print("EXTENSION_BACKEND_SMOKE_OK")


if __name__ == "__main__":
    main()
