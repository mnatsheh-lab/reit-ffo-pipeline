"""Collection accuracy test: compare the agent's documents with the hand-collected answer key.

For each company-quarter, finds the FFO reconciliation page(s) in the hand-collected PDF
(data/raw/<TICKER>/<TICKER>_<YYYYQn>_supplemental.pdf) and checks what share of their figures
appear in the document the agent saved. 100% means the agent found a document containing the
same reconciliation.

    python -m src.verify_collection
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

from . import config
from .edgar import document_text

NUM = re.compile(r"\(?\d{1,3}(?:,\d{3})+\)?")


def figures(text: str) -> set[str]:
    return {n.strip("()") for n in NUM.findall(text)}


def reconciliation_pages(pdf_path: Path) -> list[str]:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(pdf_path.read_bytes())) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            low = t.lower()
            if (("funds from operations" in low or re.search(r"\bffo\b", low)) and "depreciation" in low
                    and re.search(r"net (\(loss\) )?income|net loss", low) and len(NUM.findall(t)) >= 10):
                pages.append(t)
    return pages


def main() -> int:
    records = json.loads((config.OUTPUT_DIR / "collection_manifest.json").read_text())
    results = []
    for r in records:
        hand = config.DATA_DIR / "raw" / r["ticker"] / f"{r['ticker']}_{r['quarter']}_supplemental.pdf"
        label = f"{r['ticker']} {r['quarter']}"
        if not r.get("path") or not Path(r["path"]).exists():
            results.append((label, "agent saved nothing")); continue
        if not hand.exists():
            results.append((label, "no hand-collected file to compare")); continue
        pages = reconciliation_pages(hand)
        expected = set().union(*(figures(p) for p in pages)) if pages else set()
        if not expected:
            results.append((label, "hand-collected file has no readable reconciliation (scanned?)")); continue
        found = figures(document_text(Path(r["path"]).read_bytes(), r["path"]))
        share = len(expected & found) / len(expected)
        results.append((label, f"{len(expected & found)}/{len(expected)} figures match ({share:.0%})"))
    for label, msg in results:
        print(f"{label}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
