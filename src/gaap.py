"""GAAP figures from SEC XBRL data (free, no Claude calls).

    python -m src.gaap                # all REITs -> output/gaap/<TICKER>.json
    python -m src.gaap MAA CPT        # just these

Every 10-Q and 10-K carries machine-readable (XBRL) facts. SEC publishes them per company at
data.sec.gov/api/xbrl/companyfacts. This module turns those facts into one value per metric per
calendar quarter, recording the XBRL concept, filing and form each value came from.

Quarterly values for flows (EPS, revenue, net income, dividends, interest) come from a three-month
fact when the filing has one. Otherwise the quarter is derived as year-to-date minus the previous
year-to-date (the usual case for Q4, which only appears in the 10-K as a full year). Derived values
are marked; for per-share figures the subtraction is approximate because share counts change.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime

from . import config
from .edgar import EdgarClient
from .quarters import Quarter, quarter_range
from .universe import latest_quarter

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
OUT_DIR = config.OUTPUT_DIR / "gaap"

# metric -> unit, kind (duration = over the quarter, instant = at quarter end), concepts in order of preference.
# A concept given as a tuple is the sum of its parts (all parts must be present). "fill_only" concepts
# never become a metric's main concept; they only fill quarters the others leave empty.
METRICS: dict[str, dict] = {
    "eps_diluted": {"label": "Diluted EPS", "unit": "USD/shares", "kind": "duration", "per_share": True,
                    "concepts": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted",
                                 "IncomeLossFromContinuingOperationsPerDilutedShare"]},
    "revenue": {"label": "Total revenue", "unit": "USD", "kind": "duration",
                "concepts": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                             "OperatingLeaseLeaseIncome", "RealEstateRevenueNet", "OperatingLeasesIncomeStatementLeaseRevenue"]},
    "net_income_common": {"label": "Net income to common shareholders", "unit": "USD", "kind": "duration",
                          "concepts": ["NetIncomeLossAvailableToCommonStockholdersDiluted",
                                       "NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLoss"]},
    "dividends_ps": {"label": "Dividends declared per share", "unit": "USD/shares", "kind": "duration", "per_share": True,
                     "concepts": ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"]},
    "interest_expense": {"label": "Interest expense", "unit": "USD", "kind": "duration",
                         "concepts": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt",
                                      "InterestExpenseOperating"]},
    "total_debt": {"label": "Total debt", "unit": "USD", "kind": "instant",
                   "concepts": ["LongTermDebt", "DebtInstrumentCarryingAmount", "DebtLongtermAndShorttermCombinedAmount",
                                ("SecuredDebt", "UnsecuredDebt"), "NotesPayable", "SecuredDebt"],
                   "fill_only": ["SecuredDebt"]},   # secured debt alone is total debt only for all-mortgage REITs
    "total_assets": {"label": "Total assets", "unit": "USD", "kind": "instant", "concepts": ["Assets"]},
}
FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A"}


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _near(a: date, b: date, days: int = 7) -> bool:
    return abs((a - b).days) <= days


def _facts(facts: dict, concept: str, unit: str) -> list[dict]:
    """Facts for one concept from 10-Qs/10-Ks; where the same period was filed more than once, the latest filing wins."""
    units = facts.get("facts", {}).get("us-gaap", {}).get(concept, {}).get("units", {})
    best: dict[tuple, dict] = {}
    for f in units.get(unit, []):
        if f.get("form") not in FORMS or f.get("val") is None:
            continue
        key = (f.get("start"), f["end"])
        if key not in best or f.get("filed", "") > best[key].get("filed", ""):
            best[key] = f
    return list(best.values())


def _src(f: dict, concept: str) -> dict:
    return {"concept": concept, "form": f.get("form"), "accn": f.get("accn"), "filed": f.get("filed")}


def _duration_value(rows: list[dict], q: Quarter) -> dict | None:
    end = q.period_end
    ending = [f for f in rows if f.get("start") and _near(_d(f["end"]), end)]
    for f in ending:                                   # a three-month fact
        if 80 <= (_d(f["end"]) - _d(f["start"])).days <= 100:
            return {"value": f["val"], "derived": False, "f": f}
    # year-to-date minus the previous year-to-date with the same start
    prev_end = Quarter(q.year, q.q - 1).period_end if q.q > 1 else None
    if not prev_end:
        return None
    for f in sorted(ending, key=lambda f: f["start"]):
        start = _d(f["start"])
        if (_d(f["end"]) - start).days <= 100:
            continue
        for g in rows:
            if g.get("start") and _near(_d(g["start"]), start, 3) and _near(_d(g["end"]), prev_end):
                return {"value": round(f["val"] - g["val"], 6), "derived": True, "f": f}
    return None


def _instant_value(rows: list[dict], q: Quarter) -> dict | None:
    for f in rows:
        if not f.get("start") and _near(_d(f["end"]), q.period_end, 3):
            return {"value": f["val"], "derived": False, "f": f}
    return None


def _concept_value(facts: dict, concept, spec: dict, q: Quarter, cache: dict) -> dict | None:
    parts = concept if isinstance(concept, tuple) else (concept,)
    vals = []
    for c in parts:
        if c not in cache:
            cache[c] = _facts(facts, c, spec["unit"])
        v = (_duration_value if spec["kind"] == "duration" else _instant_value)(cache[c], q)
        if v is None:
            return None
        vals.append(v)
    out = {"value": round(sum(v["value"] for v in vals), 6), "derived": any(v["derived"] for v in vals),
           **_src(vals[0]["f"], "+".join(parts))}
    return out


def metrics_for(facts: dict, quarters: list[Quarter]) -> dict[str, dict]:
    """{quarter: {metric: {value, concept, derived, form, accn, filed}}}.

    Per metric, the concept that covers the most quarters is used throughout; others only fill gaps,
    so a series doesn't silently switch definitions from quarter to quarter.
    """
    out: dict[str, dict] = {str(q): {} for q in quarters}
    for name, spec in METRICS.items():
        cache: dict = {}
        found = {c: {str(q): v for q in quarters if (v := _concept_value(facts, c, spec, q, cache))} for c in spec["concepts"]}
        main = [c for c in spec["concepts"] if c not in spec.get("fill_only", [])]
        order = sorted(main, key=lambda c: (-len(found[c]), spec["concepts"].index(c))) + spec.get("fill_only", [])
        for q in quarters:
            for c in order:
                v = found[c].get(str(q))
                if v:
                    if spec.get("per_share") and v["derived"]:
                        v["approx"] = True
                    out[str(q)][name] = v
                    break
    return out


def collect(tickers: list[str] | None = None, edgar: EdgarClient | None = None) -> dict[str, dict]:
    edgar = edgar or EdgarClient(config.SEC_USER_AGENT, config.CACHE_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    first = Quarter.parse(config.FIRST_QUARTER)
    for t in tickers or list(config.REITS):
        info = config.REITS[t]
        start = max(first, Quarter.parse(info.get("start") or config.FIRST_QUARTER))
        end = min(Quarter.parse(info.get("end") or latest_quarter()), Quarter.parse(latest_quarter()))
        if start > end:
            continue
        # one extra year before the first quarter so year-over-year growth works from the start
        quarters = quarter_range(str(Quarter(start.year - 1, start.q)), str(end))
        facts = edgar.get_json(FACTS_URL.format(cik=info["cik"]), fresh=True)
        data = {"ticker": t, "cik": info["cik"], "entity": facts.get("entityName"), "fetched": date.today().isoformat(),
                "first_quarter": str(start), "metrics": {k: v["label"] for k, v in METRICS.items()},
                "quarters": metrics_for(facts, quarters)}
        (OUT_DIR / f"{t}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        results[t] = data
        own = [q for q in data["quarters"] if q >= str(start)]
        have = {m: sum(1 for q in own if m in data["quarters"][q]) for m in METRICS}
        print(f"{t:5} {len(own):3} quarters  " + "  ".join(f"{m.split('_')[0][:7]} {n}" for m, n in have.items()))
    return results


if __name__ == "__main__":
    if not config.SEC_USER_AGENT:
        sys.exit("Set SEC_USER_AGENT in .env first (run setup.bat).")
    collect(sys.argv[1:] or None)
    print(f"\nSaved to {OUT_DIR}. Free: no Claude calls.")
