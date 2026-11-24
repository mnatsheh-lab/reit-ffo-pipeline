"""Rank REITs on their key metrics over the trailing four quarters (no Claude calls).

    python -m src.scorecard              # REITs still reporting, as of the latest quarter
    python -m src.scorecard --as-of 2025Q4

Every metric uses the latest four quarters that have it (ending at --as-of), so a company whose
newest filing isn't in the data yet is measured on its latest available year, and the table says so.
Scores are relative to the peer set: 100 = best of the group on that metric, 0 = worst.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from . import config
from .quarters import Quarter

EXTRACT_DIR = config.OUTPUT_DIR / "extractions"
GAAP_DIR = config.OUTPUT_DIR / "gaap"

# metric: (label, pillar, higher_is_better)
METRICS = {
    "ffo_growth": ("Conservative Core FFO/share growth (median year-over-year)", "Growth", True),
    "revenue_growth": ("Revenue growth", "Growth", True),
    "interest_coverage": ("Interest coverage (FFO + interest) / interest", "Balance sheet", True),
    "debt_to_assets": ("Debt to assets", "Balance sheet", False),
    "payout": ("Dividend / Conservative Core FFO", "Dividend safety", False),
    "definition_gap": ("Definition gap (company headline vs conservative)", "Earnings quality", False),
}
PILLARS = ["Growth", "Balance sheet", "Dividend safety", "Earnings quality"]


def _q(s: str) -> Quarter:
    return Quarter.parse(s)


def _back(q: Quarter, n: int) -> Quarter:
    i = q.year * 4 + q.q - 1 - n
    return Quarter(i // 4, i % 4 + 1)


def load():
    ffo = {}
    for p in EXTRACT_DIR.glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        ffo.setdefault(d["ticker"], {})[d["quarter"]] = d["restated"]
    gaap = {}
    for p in GAAP_DIR.glob("*.json"):
        g = json.loads(p.read_text(encoding="utf-8"))
        gaap[g["ticker"]] = {q: {m: v["value"] for m, v in ms.items()} for q, ms in g["quarters"].items()}
    return ffo, gaap


def _window(have, end: Quarter, n=4, look=4):
    """Latest n consecutive quarters ending at or before `end` (searching back `look` quarters) for
    which have(q) is true. Returns the list of quarter strings, newest last, or None."""
    for shift in range(look + 1):
        last = _back(end, shift)
        qs = [str(_back(last, i)) for i in reversed(range(n))]
        if all(have(q) for q in qs):
            return qs
    return None


def metrics_for(t: str, ffo: dict, gaap: dict, end: Quarter) -> tuple[dict, dict]:
    f, g = ffo.get(t, {}), gaap.get(t, {})
    m, asof = {}, {}
    ps = lambda q: f.get(q, {}).get("conservative_core_ffo_ps")
    gv = lambda q, k: g.get(q, {}).get(k)

    # growth: trailing four quarters vs the four before
    w = _window(lambda q: ps(q) is not None and ps(str(_back(_q(q), 4))) is not None, end)
    if w:
        # median of the four year-over-year quarterly changes: one-off charges the conservative definition
        # keeps in earnings would otherwise swing a trailing-sum growth rate (a bad year-ago quarter looks like growth)
        ch = sorted((ps(q) - ps(str(_back(_q(q), 4)))) / ps(str(_back(_q(q), 4))) for q in w if ps(str(_back(_q(q), 4))) > 0)
        m["ffo_growth"] = (ch[len(ch) // 2] if len(ch) % 2 else (ch[len(ch) // 2 - 1] + ch[len(ch) // 2]) / 2) if len(ch) >= 3 else None
        asof["ffo_growth"] = w[-1]
    w = _window(lambda q: gv(q, "revenue") and gv(str(_back(_q(q), 4)), "revenue"), end)
    if w:
        now, then = sum(gv(q, "revenue") for q in w), sum(gv(str(_back(_q(q), 4)), "revenue") for q in w)
        m["revenue_growth"] = (now - then) / abs(then)
        asof["revenue_growth"] = w[-1]
    # interest coverage: (conservative core FFO + interest) / interest, trailing four quarters
    w = _window(lambda q: f.get(q, {}).get("conservative_core_ffo") is not None and gv(q, "interest_expense"), end)
    if w:
        interest = sum(abs(gv(q, "interest_expense")) for q in w) / 1000          # $ -> $ thousands
        core = sum(f[q]["conservative_core_ffo"] for q in w)
        m["interest_coverage"] = (core + interest) / interest if interest else None
        asof["interest_coverage"] = w[-1]
    # leverage: latest quarter-end
    w = _window(lambda q: gv(q, "total_debt") and gv(q, "total_assets"), end, n=1)
    if w:
        m["debt_to_assets"] = gv(w[0], "total_debt") / gv(w[0], "total_assets")
        asof["debt_to_assets"] = w[0]
    # payout: dividends per share / conservative core FFO per share, trailing four quarters
    # (quarters where either is missing, e.g. a Q4 the 10-K doesn't tag, are left out of both sums; needs 3 of 4)
    last4 = [str(_back(end, i)) for i in reversed(range(4))]
    both = [q for q in last4 if gv(q, "dividends_ps") is not None and ps(q) is not None]
    if len(both) >= 3:
        core = sum(ps(q) for q in both)
        m["payout"] = sum(gv(q, "dividends_ps") for q in both) / core if core > 0 else None
        asof["payout"] = both[-1]
    # definition gap: the company's own adjusted FFO vs the restated figure
    def headline(q):
        r = f.get(q, {})
        return r.get("company_core_ps")          # companies with no adjusted FFO aren't scored on this
    w = _window(lambda q: headline(q) is not None and ps(q) is not None, end)
    if w:
        cons = sum(ps(q) for q in w)
        m["definition_gap"] = (sum(headline(q) for q in w) - cons) / cons if cons > 0 else None
        asof["definition_gap"] = w[-1]
    return {k: v for k, v in m.items() if v is not None}, asof


def score(rows: dict[str, dict]) -> dict[str, dict]:
    """0-100 per metric by rank within the group (ties share the score), pillar = mean of its metrics,
    overall = mean of the pillars the REIT has."""
    out = {t: {"metrics": {}, "pillars": {}} for t in rows}
    for k, (_, _, hib) in METRICS.items():
        have = {t: r[k] for t, r in rows.items() if k in r}
        if len(have) < 2:
            continue
        vals = sorted(set(have.values()), reverse=hib)
        if len(vals) < 2:          # no spread across the group: the metric carries no information
            continue
        for t, v in have.items():
            out[t]["metrics"][k] = 100 * (1 - vals.index(v) / (len(vals) - 1)) if len(vals) > 1 else 50
    for t, o in out.items():
        for p in PILLARS:
            s = [o["metrics"][k] for k, (_, pil, _) in METRICS.items() if pil == p and k in o["metrics"]]
            if s:
                o["pillars"][p] = sum(s) / len(s)
        o["overall"] = sum(o["pillars"].values()) / len(o["pillars"]) if o["pillars"] else None
    return out


def active(as_of: Quarter, ffo: dict) -> list[str]:
    """REITs with an extracted quarter at as_of and at least five quarters of history."""
    return sorted(t for t, qs in ffo.items() if str(as_of) in qs and len(qs) >= 5)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", help="last quarter, e.g. 2026Q3 (default: latest in the data)")
    args = ap.parse_args(argv)
    ffo, gaap = load()
    end = _q(args.as_of) if args.as_of else max(_q(q) for qs in ffo.values() for q in qs)
    tickers = active(end, ffo)
    raw, asof = {}, {}
    for t in tickers:
        raw[t], asof[t] = metrics_for(t, ffo, gaap, end)
    sc = score(raw)
    order = sorted(tickers, key=lambda t: -(sc[t]["overall"] or 0))
    result = [{"rank": i + 1, "ticker": t, "overall": sc[t]["overall"], **{f"pillar_{p}": sc[t]["pillars"].get(p) for p in PILLARS},
               **{k: raw[t].get(k) for k in METRICS}, **{f"asof_{k}": asof[t].get(k) for k in METRICS}} for i, t in enumerate(order)]
    out = config.OUTPUT_DIR / "scorecard.json"
    out.write_text(json.dumps({"as_of": str(end), "metrics": {k: v[0] for k, v in METRICS.items()}, "rows": result}, indent=1))
    with open(config.OUTPUT_DIR / "scorecard.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(result[0]))
        w.writeheader()
        w.writerows(result)
    pct = lambda v: "   –  " if v is None else f"{v * 100:+6.1f}%"
    print(f"Scorecard as of {end}: {len(order)} REITs still reporting with 5+ quarters\n")
    print(f"{'#':>2} {'REIT':5} {'Score':>5}  {'Growth':>6} {'Balance':>7} {'Divid.':>6} {'Quality':>7}   "
          f"{'FFO gr':>7} {'Rev gr':>7} {'IntCov':>6} {'D/A':>6} {'Payout':>7} {'Gap':>7}")
    for r in result:
        p = lambda k: "   –" if r[f"pillar_{k}"] is None else f"{r[f'pillar_{k}']:6.0f}"
        cov = "    –" if r["interest_coverage"] is None else f"{r['interest_coverage']:5.1f}x"
        print(f"{r['rank']:>2} {r['ticker']:5} {r['overall']:5.0f}  {p('Growth')} {p('Balance sheet'):>7} {p('Dividend safety')} {p('Earnings quality'):>7}   "
              f"{pct(r['ffo_growth'])} {pct(r['revenue_growth'])} {cov} {pct(r['debt_to_assets'])} {pct(r['payout'])} {pct(r['definition_gap'])}")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
