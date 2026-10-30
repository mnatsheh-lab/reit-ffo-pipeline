"""Run the collection agent.

    python -m src.collect                                  # answer-key REITs, Q4 2025 - Q2 2026
    python -m src.collect --tickers MAA --start 2026Q2 --end 2026Q2
"""
from __future__ import annotations

import argparse
import csv
import json
import sys

from . import config
from .agent import CollectionAgent
from .edgar import EdgarClient
from .quarters import quarter_range


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Collect FFO reconciliation documents from SEC EDGAR")
    parser.add_argument("--tickers", nargs="+", default=list(config.REITS))
    parser.add_argument("--start", default="2025Q4")
    parser.add_argument("--end", default="2026Q2")
    args = parser.parse_args(argv)

    problems = config.check_settings()
    if problems:
        print("Setup problem:\n  - " + "\n  - ".join(problems))
        return 1
    unknown = [t for t in args.tickers if t.upper() not in config.REITS]
    if unknown:
        print(f"Unknown tickers: {unknown}. Known: {list(config.REITS)}")
        return 1

    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    edgar = EdgarClient(config.SEC_USER_AGENT, config.CACHE_DIR)
    agent = CollectionAgent(client, config.MODEL, edgar, config.EDGAR_DIR)
    quarters = quarter_range(args.start, args.end)

    all_records, tokens_in, tokens_out = [], 0, 0
    for ticker in (t.upper() for t in args.tickers):
        print(f"\n=== {ticker}: {', '.join(map(str, quarters))} ===")
        result = agent.run(ticker, config.REITS[ticker]["cik"], quarters)
        for line in result.log:
            print("  " + line[:200])
        for r in result.records:
            print(f"  {r['quarter']}: {r['status'].upper():17} {r['filename'] or r['reason']}")
        all_records += result.records
        tokens_in += result.input_tokens
        tokens_out += result.output_tokens

    config.OUTPUT_DIR.mkdir(exist_ok=True)
    (config.OUTPUT_DIR / "collection_manifest.json").write_text(json.dumps(all_records, indent=2))
    with open(config.OUTPUT_DIR / "collection_manifest.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["ticker", "quarter", "status", "accession", "filename", "url", "path", "reason", "collected_on"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_records)

    counts = {}
    for r in all_records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n=== Summary ===")
    for status, n in sorted(counts.items()):
        print(f"  {status}: {n}")
    print(f"  Claude tokens used: {tokens_in:,} in / {tokens_out:,} out")
    print(f"  Manifest: {config.OUTPUT_DIR / 'collection_manifest.csv'}")
    return 0 if counts.get("missing", 0) == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
