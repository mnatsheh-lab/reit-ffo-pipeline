"""Extract and restate every saved document in the collection manifest.

    python -m src.run_extract                 # everything in the manifest
    python -m src.run_extract --tickers MAA   # one company

Writes output/extractions/<TICKER>_<QUARTER>.json (every line with label, amount, page and
EDGAR link: what the dashboard shows) and output/restated_ffo.csv / .json (summary table).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import config
from .extract import extract_document
from .quarters import Quarter
from .restate import restate

EXTRACT_DIR = config.OUTPUT_DIR / "extractions"
ANSWER_KEY = config.DATA_DIR / "answer_key" / "MAA_FFO_Reconciliation.xlsx"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+")
    parser.add_argument("--redo", action="store_true", help="re-extract even if a result already exists")
    args = parser.parse_args(argv)

    problems = config.check_settings()
    if problems:
        print("Setup problem:\n  - " + "\n  - ".join(problems))
        return 1
    manifest = json.loads((config.OUTPUT_DIR / "collection_manifest.json").read_text())
    todo = [r for r in manifest if r["status"].startswith("saved") and (not args.tickers or r["ticker"] in [t.upper() for t in args.tickers])]

    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    model = config.EXTRACT_MODEL
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    rows, tin, tout = [], 0, 0

    for r in todo:
        out_path = EXTRACT_DIR / f"{r['ticker']}_{r['quarter']}.json"
        q = Quarter.parse(r["quarter"])
        if out_path.exists() and not args.redo:
            result = json.loads(out_path.read_text())
            print(f"{r['ticker']} {r['quarter']}: already extracted (use --redo to repeat)")
        else:
            print(f"{r['ticker']} {r['quarter']}: extracting {r['filename']} ...", flush=True)
            ext = extract_document(client, model, Path(r["path"]).read_bytes(), r["filename"],
                                   r["ticker"], str(q), q.period_end_text)
            tin += ext["usage"]["input_tokens"]
            tout += ext["usage"]["output_tokens"]
            result = {
                "ticker": r["ticker"], "quarter": r["quarter"], "period_end": q.period_end.isoformat(),
                "source": {"accession": r["accession"], "filename": r["filename"], "url": r["url"]},
                "extraction": ext, "restated": restate(ext),
            }
            out_path.write_text(json.dumps(result, indent=2))
            status = "TIES" if not ext["validation_errors"] else "DOES NOT TIE: " + "; ".join(ext["validation_errors"])
            print(f"    {status} (attempts: {ext['attempts']})")
        res = result["restated"]
        rows.append({
            "ticker": r["ticker"], "quarter": r["quarter"],
            "nareit_ffo_ps": res["nareit_ffo_ps"],
            "company_core_name": res["company_core_name"], "company_core_ps": res["company_core_ps"],
            "conservative_core_ffo_ps": res["conservative_core_ffo_ps"],
            "company_affo_name": res["company_affo_name"], "company_affo_ps": res["company_affo_ps"],
            "conservative_affo_ps": res["conservative_affo_ps"],
            "ties": not result["extraction"]["validation_errors"],
            "flags": " | ".join(res["flags"]), "source_url": result["source"]["url"],
        })

    with open(config.OUTPUT_DIR / "restated_ffo.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["ticker"])
        w.writeheader()
        w.writerows(rows)
    (config.OUTPUT_DIR / "restated_ffo.json").write_text(json.dumps(rows, indent=2))

    print("\n=== Restated FFO per share ===")
    print(f"{'REIT':5} {'Qtr':7} {'NAREIT':>7} {'Co. core':>9} {'Cons. core':>10} {'Co. AFFO':>9} {'Cons. AFFO':>10}  Ties")
    fmt = lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else "-"
    for row in rows:
        print(f"{row['ticker']:5} {row['quarter']:7} {fmt(row['nareit_ffo_ps']):>7} {fmt(row['company_core_ps']):>9} "
              f"{fmt(row['conservative_core_ffo_ps']):>10} {fmt(row['company_affo_ps']):>9} {fmt(row['conservative_affo_ps']):>10}  {'yes' if row['ties'] else 'NO'}")
    if tin:
        print(f"\nClaude tokens used: {tin:,} in / {tout:,} out")

    if ANSWER_KEY.exists():
        from .verify_extraction import compare_maa
        print("\n=== MAA vs your hand-built answer key ===")
        compare_maa(ANSWER_KEY, EXTRACT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
