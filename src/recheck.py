"""Re-run the automatic checks on documents already saved, and update the manifest.

    python -m src.recheck
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from . import config
from .edgar import document_text, reconciliation_signals
from .quarters import Quarter


def main() -> int:
    path = config.OUTPUT_DIR / "collection_manifest.json"
    records = json.loads(path.read_text())
    changed = 0
    for r in records:
        if not r.get("path") or not Path(r["path"]).exists():
            continue
        text = document_text(Path(r["path"]).read_bytes(), r["path"])
        checks = reconciliation_signals(text, Quarter.parse(r["quarter"]).period_end_text)
        status = "saved" if (checks["mentions_ffo"] and checks["has_reconciliation_words"] and checks["mentions_period_end"]) else "saved_unverified"
        if status != r["status"]:
            print(f"{r['ticker']} {r['quarter']}: {r['status']} -> {status}")
            changed += 1
        r["status"], r["checks"] = status, checks
    path.write_text(json.dumps(records, indent=2))
    with open(config.OUTPUT_DIR / "collection_manifest.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["ticker", "quarter", "status", "accession", "filename", "url", "path", "reason", "collected_on"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)
    print(f"Rechecked {len(records)} records, {changed} status change(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
