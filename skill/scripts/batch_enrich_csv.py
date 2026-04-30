#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--output")
    ap.add_argument("--query-mode", choices=["basic", "smart"], default="smart")
    args = ap.parse_args()

    rows = list(csv.DictReader(Path(args.csv_path).open(encoding="utf-8")))
    results = []
    script = Path(__file__).with_name("enrich_lead.py")

    for row in rows:
        company = (row.get("company") or "").strip()
        if not company:
            continue
        cmd = [sys.executable, str(script), "--company", company, "--query-mode", args.query_mode]
        if row.get("region"):
            cmd += ["--region", row["region"].strip()]
        if row.get("domain"):
            cmd += ["--domain", row["domain"].strip()]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            results.append({"company": company, "error": proc.stderr.strip() or "enrichment failed"})
            continue
        try:
            results.append(json.loads(proc.stdout))
        except json.JSONDecodeError:
            results.append({"company": company, "error": "invalid json", "raw": proc.stdout[:500]})

    text = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
