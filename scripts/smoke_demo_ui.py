#!/usr/bin/env python3
"""Boot the demo CLI on its documented URL and verify its public local surface."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8095"


def read_url(path: str) -> bytes:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=3) as response:
        return response.read()


def main() -> None:
    command = [
        sys.executable,
        "ui/review_server.py",
        "--demo",
        "--review-file",
        "examples/demo-review.json",
        "--demo-batch-file",
        "examples/demo-output.json",
        "--host",
        "127.0.0.1",
        "--port",
        "8095",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        health = None
        for _ in range(30):
            if process.poll() is not None:
                raise RuntimeError(f"demo UI exited early with code {process.returncode}")
            try:
                health = json.loads(read_url("/healthz").decode("utf-8"))
                break
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                time.sleep(0.2)
        if health is None:
            raise RuntimeError("demo UI did not become healthy on http://127.0.0.1:8095")
        assert health["ok"] is True
        assert health["demo_mode"] is True
        assert health["demo_batch_summary"]["total"] == 3
        page = read_url("/").decode("utf-8")
        assert "Start 90-second demo" in page
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    print("DEMO_UI_SMOKE_OK")


if __name__ == "__main__":
    main()
