#!/usr/bin/env python3
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "enrich_lead.py"
DEFAULT_LEADS = ROOT / "examples" / "ab-leads.csv"


def run(company, domain, mode):
    cmd = [sys.executable, str(SCRIPT), "--company", company, "--query-mode", mode]
    if domain:
        cmd += ["--domain", domain]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def score(item):
    s = item.get("confidence", 0)
    if item.get("emails"):
        s += 0.2
    if item.get("summary"):
        s += 0.1
    return round(s, 2)


def main():
    leads_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LEADS
    rows = [line.strip().split(",") for line in leads_path.read_text(encoding="utf-8").splitlines()[1:] if line.strip()]
    report = []
    for company, _region, domain in rows:
        a = run(company, domain, "basic")
        b = run(company, domain, "smart")
        report.append({
            "company": company,
            "basic": score(a),
            "smart": score(b),
            "winner": "smart" if score(b) >= score(a) else "basic"
        })
    summary = {
        "cases": report,
        "basic_avg": round(statistics.mean(x["basic"] for x in report), 3),
        "smart_avg": round(statistics.mean(x["smart"] for x in report), 3),
    }
    summary["recommended_mode"] = "smart" if summary["smart_avg"] >= summary["basic_avg"] else "basic"
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
