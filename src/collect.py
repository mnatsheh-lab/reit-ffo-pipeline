"""Run the collection agent across the universe.

    python -m src.collect                                # every REIT, every missing quarter since 2020
    python -m src.collect --tickers MAA                  # one REIT
    python -m src.collect --tickers MAA --start 2026Q2 --end 2026Q2
    python -m src.collect --yes                          # skip the confirmation prompt

Quarters already saved in the manifest are skipped, so a run can be stopped and resumed.
The agent works one year (4 quarters) at a time and the manifest is saved after each batch.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys

from . import config
from .agent import CollectionAgent
from .edgar import EdgarClient
from .quarters import Quarter
from .rules import pick, save
from .universe import quarters_for

MANIFEST_JSON = config.OUTPUT_DIR / "collection_manifest.json"
MANIFEST_CSV = config.OUTPUT_DIR / "collection_manifest.csv"
TOKENS_PER_QUARTER = 25_000   # rough, from the first live runs (input + output)


def load_manifest() -> dict[tuple[str, str], dict]:
    if not MANIFEST_JSON.exists():
        return {}
    return {(r["ticker"], r["quarter"]): r for r in json.loads(MANIFEST_JSON.read_text())}


def save_manifest(records: dict[tuple[str, str], dict]) -> None:
    rows = [records[k] for k in sorted(records)]
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    MANIFEST_JSON.write_text(json.dumps(rows, indent=2))
    with open(MANIFEST_CSV, "w", newline="", encoding="utf-8") as f:
        cols = ["ticker", "quarter", "status", "accession", "filename", "url", "path", "reason", "collected_on"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Collect FFO reconciliation documents from SEC EDGAR")
    parser.add_argument("--tickers", nargs="+", default=list(config.REITS))
    parser.add_argument("--start", help="first quarter, e.g. 2020Q1 (default: each REIT's own start)")
    parser.add_argument("--end", help="last quarter (default: latest reported)")
    parser.add_argument("--retry-missing", action="store_true", help="also retry quarters marked missing")
    parser.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    parser.add_argument("--no-rules", action="store_true", help="use the agent for every quarter")
    parser.add_argument("--check-rules", action="store_true",
                        help="free test: re-pick every saved quarter with the rules and compare with the manifest")
    args = parser.parse_args(argv)

    problems = config.check_settings()
    if problems:
        print("Setup problem:\n  - " + "\n  - ".join(problems))
        return 1
    tickers = [t.upper() for t in args.tickers]
    unknown = [t for t in tickers if t not in config.REITS]
    if unknown:
        print(f"Unknown tickers: {unknown}. Known: {list(config.REITS)}")
        return 1

    manifest = load_manifest()
    if args.check_rules:
        return check_rules(manifest, tickers)
    done = {k for k, r in manifest.items() if r["status"].startswith("saved") or (r["status"] == "missing" and not args.retry_missing)}
    plan = {}
    for t in tickers:
        qs = [q for q in quarters_for(t, args.end) if not args.start or q >= Quarter.parse(args.start)]
        todo = [q for q in qs if (t, str(q)) not in done]
        if todo:
            plan[t] = todo
    n = sum(len(v) for v in plan.values())
    if not n:
        print("Nothing to collect: every requested quarter is already in the manifest.")
        return 0
    print("Plan:")
    for t, qs in plan.items():
        print(f"  {t:5} {len(qs):3} quarters  ({qs[0]} to {qs[-1]})")
    print(f"Total: {n} company-quarters. Free rules are tried first; the agent (about "
          f"{TOKENS_PER_QUARTER // 1000}K Claude tokens a quarter) only handles quarters the rules can't settle.")
    if not args.yes and input("Start? Type y and press Enter: ").strip().lower() != "y":
        print("Cancelled.")
        return 0

    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    edgar = EdgarClient(config.SEC_USER_AGENT, config.CACHE_DIR)
    agent = CollectionAgent(client, config.MODEL, edgar, config.EDGAR_DIR)
    tin = tout = 0
    by_method = {"rules": 0, "agent": 0}
    for t, qs in plan.items():
        cik = config.REITS[t]["cik"]
        leftover = []
        if not args.no_rules:
            print(f"\n=== {t}: rules ===", flush=True)
            for q in qs:
                try:
                    choice, why = pick(edgar, cik, q)
                except Exception as exc:
                    choice, why = None, f"{type(exc).__name__}: {exc}"
                if choice:
                    rec = save(choice, t, cik, q, config.EDGAR_DIR, edgar, why)
                    manifest[(t, str(q))] = rec
                    by_method["rules"] += 1
                    print(f"  {q}: SAVED (rules)       {rec['filename']}")
                else:
                    leftover.append(q)
                    print(f"  {q}: to agent            {why}")
            save_manifest(manifest)
        else:
            leftover = qs
        for i in range(0, len(leftover), 4):
            batch = leftover[i:i + 4]
            print(f"\n=== {t}: agent for {', '.join(map(str, batch))} ===", flush=True)
            try:
                result = agent.run(t, cik, batch)
            except Exception as exc:          # keep going; the batch stays unresolved and can be retried
                print(f"  ERROR {type(exc).__name__}: {exc}")
                continue
            for r in result.records:
                r["method"] = "agent"
                by_method["agent"] += r["status"].startswith("saved")
                manifest[(r["ticker"], r["quarter"])] = r
                print(f"  {r['quarter']}: {r['status'].upper():17} {r['filename'] or r['reason'][:90]}")
            tin += result.input_tokens
            tout += result.output_tokens
            save_manifest(manifest)

    counts = {}
    for r in manifest.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n=== Manifest totals ===")
    for status, k in sorted(counts.items()):
        print(f"  {status}: {k}")
    print(f"  This run: {by_method['rules']} saved by rules (free), {by_method['agent']} by the agent")
    print(f"  Claude tokens this run: {tin:,} in / {tout:,} out")
    return 0


def check_rules(manifest: dict, tickers: list[str]) -> int:
    """Free: does the rule picker choose the same document the manifest already has?"""
    edgar = EdgarClient(config.SEC_USER_AGENT, config.CACHE_DIR)
    same = differ = deferred = 0
    for (t, qs), r in sorted(manifest.items()):
        if t not in tickers or not r["status"].startswith("saved"):
            continue
        choice, why = pick(edgar, config.REITS[t]["cik"], Quarter.parse(qs))
        if choice is None:
            deferred += 1
            print(f"  {t} {qs}: rules defer to the agent ({why})")
        elif choice["filing"]["accessionNumber"] == r["accession"] and choice["doc"]["name"] == r["filename"]:
            same += 1
            print(f"  {t} {qs}: same document ({r['filename']})")
        else:
            differ += 1
            print(f"  {t} {qs}: DIFFERENT - rules pick {choice['doc']['name']}, manifest has {r['filename']}")
    print(f"\nSame: {same}   Different: {differ}   Deferred to agent: {deferred}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
