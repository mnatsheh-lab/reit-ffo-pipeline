"""Check the REIT list against EDGAR (no Claude calls, free).

    python -m src.universe

For each ticker, fetches EDGAR's record for its CIK and shows the registered name, so a wrong
CIK is caught before any paid run. Also shows how many quarters each REIT contributes.
"""
from __future__ import annotations

import re
import sys

from . import config
from .edgar import SUBMISSIONS_URL, EdgarClient
from .quarters import Quarter, quarter_range


def latest_quarter() -> str:
    from datetime import date, timedelta
    d = date.today() - timedelta(days=45)          # results come out 3-8 weeks after quarter end
    q = (d.month - 1) // 3                          # last fully reported quarter
    return f"{d.year}Q{q}" if q else f"{d.year - 1}Q4"


def quarters_for(ticker: str, end: str | None = None) -> list[Quarter]:
    info = config.REITS[ticker]
    first = max(Quarter.parse(info.get("start") or config.FIRST_QUARTER), Quarter.parse(config.FIRST_QUARTER))
    last = min(Quarter.parse(info.get("end") or latest_quarter()), Quarter.parse(end or latest_quarter()))
    return quarter_range(str(first), str(last)) if first <= last else []


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in {"inc", "trust", "the", "corp", "co", "of", "reit", "l", "p", "lp"}}


def main() -> int:
    edgar = EdgarClient(config.SEC_USER_AGENT, config.CACHE_DIR)
    total, bad = 0, 0
    print(f"{'Ticker':6} {'CIK':>8}  {'Quarters':>8}  EDGAR name (former names)                     Check")
    for t, info in config.REITS.items():
        data = edgar.get_json(SUBMISSIONS_URL.format(cik=info["cik"]))
        names = [data.get("name", "")] + [f.get("name", "") for f in data.get("formerNames", [])]
        ok = any(words(info["name"]) & words(n) for n in names)
        bad += not ok
        n = len(quarters_for(t))
        total += n
        shown = names[0] + (f" ({'; '.join(names[1:3])})" if len(names) > 1 else "")
        print(f"{t:6} {info['cik']:>8}  {n:>8}  {shown[:46]:46} {'OK' if ok else 'CHECK CIK'}")
    print(f"\n{len(config.REITS)} REITs, {total} company-quarters from {config.FIRST_QUARTER} to {latest_quarter()}.")
    if bad:
        print(f"{bad} CIK(s) need checking before a paid run.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
