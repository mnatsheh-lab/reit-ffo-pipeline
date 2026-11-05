"""Build the dashboard: one self-contained HTML page with the pipeline's results embedded.

    python -m src.build_dashboard            # writes dashboard/index.html

The page embeds the extraction records, the rules definition, restate.js (so readers can change the
rules) and the GAAP figures from output/gaap (python -m src.gaap).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from . import config
from .restate import DEFINITION, default_rules, restate, rule_lines

TEMPLATE = config.ROOT / "dashboard" / "template.html"
OUT = config.ROOT / "dashboard" / "index.html"
NAMES = {t: v["name"] for t, v in config.REITS.items()}


def page_ref(x: dict) -> str:
    return x.get("page_printed") or (f"seq {x['page_seq']}" if x.get("page_seq") else "")


def record(d: dict) -> dict:
    e = d["extraction"]
    r = restate(e)          # always recomputed from the stored extraction with the current rules
    line = lambda x, **kw: {"label": x["label"], "amount": x["amount"], "page": page_ref(x), **kw}
    return {
        "ticker": d["ticker"], "name": NAMES.get(d["ticker"], d["ticker"]), "quarter": d["quarter"],
        "period_end": d["period_end"], "url": d["source"]["url"], "filename": d["source"]["filename"],
        "shares": e["diluted_shares"]["amount"], "shares_label": e["diluted_shares"]["label"],
        "shares_page": page_ref(e["diluted_shares"]),
        "start": line(e["starting_line"]),
        "ffo_lines": [line(x, category=x["category"]) for x in e.get("ffo_adjustments", []) if x["amount"]],
        "ffo": line(e["ffo_total"]),
        "core_name": e.get("core_metric_name"), "core": e.get("core_total") and line(e["core_total"]),
        "affo_name": e.get("affo_metric_name"), "affo": e.get("affo_total") and line(e["affo_total"]),
        "steps": [line(s, category=s["category"], applied=s["applied"], reason=s["reason"], section=s["section"])
                  for s in r["steps"] if s["amount"]],
        # raw inputs for the in-browser rules engine (dashboard/restate.js)
        "rule_lines": [line(l, category=l["category"], section=sec) for sec, l in rule_lines(e)],
        "capex_recon": [line(x) for x in e.get("affo_adjustments", []) if x["category"] == "recurring_capex"],
        "capex_disclosed": e.get("recurring_capex_disclosed") and {
            "label": e["recurring_capex_disclosed"]["label"], "amount": e["recurring_capex_disclosed"]["amount"],
            "basis": e["recurring_capex_disclosed"].get("basis"), "page": page_ref(e["recurring_capex_disclosed"])},
        "validation_failed": bool(e.get("validation_errors")),
        "affo_unused": [line(x, category=x["category"]) for x in e.get("affo_adjustments", [])
                        if x["amount"] and x["category"] not in ("recurring_capex",)
                        and not any(s["label"] == x["label"] and s["section"] == "affo" for s in r["steps"])],
        "capex": [line(x) for x in r["recurring_capex"]], "capex_source": r.get("recurring_capex_source"),
        "reported_ps": e["reported_per_share"],
        "nareit_ps": r["nareit_ffo_ps"], "company_core_ps": r["company_core_ps"], "company_affo_ps": r["company_affo_ps"],
        "cons_core": r["conservative_core_ffo"], "cons_core_ps": r["conservative_core_ffo_ps"],
        "cons_affo": r["conservative_affo"], "cons_affo_ps": r["conservative_affo_ps"],
        "ties": not e.get("validation_errors"), "flags": r["flags"],
    }


def gaap_table(gaap_dir: Path) -> dict:
    """{ticker: {quarter: {metric: {v, c, f, d, a}}}} from output/gaap. Dollar amounts are converted to
    $ thousands to match the extractions; per-share amounts stay in dollars."""
    from .gaap import METRICS
    out = {}
    for p in sorted(Path(gaap_dir).glob("*.json")):
        g = json.loads(p.read_text(encoding="utf-8"))
        out[g["ticker"]] = {q: {m: {"v": round(x["value"] if METRICS[m]["unit"] == "USD/shares" else x["value"] / 1000, 4),
                                     "c": x["concept"], "f": x["form"], **({"d": 1} if x["derived"] else {}),
                                     **({"a": 1} if x.get("approx") else {})}
                                 for m, x in ms.items() if m in METRICS}
                            for q, ms in g["quarters"].items()}
    return out


def build(extract_dir: Path, out: Path = OUT, gaap_dir: Path | None = None) -> Path:
    data = [record(json.loads(p.read_text())) for p in sorted(Path(extract_dir).glob("*.json"))]
    data.sort(key=lambda x: (x["ticker"], x["quarter"]))
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/[]", json.dumps(data, separators=(",", ":")))
    gaap = gaap_table(gaap_dir or config.OUTPUT_DIR / "gaap")
    html = html.replace("/*__GAAP__*/{}", json.dumps(gaap, separators=(",", ":")))
    html = html.replace("/*__DEFINITION__*/{}", json.dumps(DEFINITION, separators=(",", ":")))
    html = html.replace("/*__RESTATE_JS__*/", (config.ROOT / "dashboard" / "restate.js").read_text(encoding="utf-8"))
    tick = sorted({d["ticker"] for d in data}); qs = sorted({d["quarter"] for d in data})
    q = lambda x: f"Q{x[5]} {x[:4]}"
    coverage = f"{len(tick)} REITs, {len(data)} company-quarters ({q(qs[0])}–{q(qs[-1])})" if data else "no data yet"
    html = html.replace("__COVERAGE__", coverage)
    html = html.replace("__BUILT__", date.today().strftime("%B %d, %Y").replace(" 0", " "))
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    path = build(config.OUTPUT_DIR / "extractions")
    print(f"Dashboard written to {path}")
    sys.exit(0)
