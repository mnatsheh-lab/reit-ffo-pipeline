"""Build the dashboard: one self-contained HTML page with the pipeline's results embedded.

    python -m src.build_dashboard            # writes dashboard/index.html

The page does no math of its own; it shows the stored extraction and restatement records.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from . import config

TEMPLATE = config.ROOT / "dashboard" / "template.html"
OUT = config.ROOT / "dashboard" / "index.html"
NAMES = {t: v["name"] for t, v in config.REITS.items()}


def page_ref(x: dict) -> str:
    return x.get("page_printed") or (f"seq {x['page_seq']}" if x.get("page_seq") else "")


def record(d: dict) -> dict:
    e, r = d["extraction"], d["restated"]
    line = lambda x, **kw: {"label": x["label"], "amount": x["amount"], "page": page_ref(x), **kw}
    return {
        "ticker": d["ticker"], "name": NAMES.get(d["ticker"], d["ticker"]), "quarter": d["quarter"],
        "period_end": d["period_end"], "url": d["source"]["url"], "filename": d["source"]["filename"],
        "shares": e["diluted_shares"]["amount"], "shares_label": e["diluted_shares"]["label"],
        "shares_page": page_ref(e["diluted_shares"]),
        "start": line(e["starting_line"]),
        "ffo_lines": [line(x, category=x["category"]) for x in e["ffo_adjustments"] if x["amount"]],
        "ffo": line(e["ffo_total"]),
        "core_name": e.get("core_metric_name"), "core": e["core_total"] and line(e["core_total"]),
        "affo_name": e.get("affo_metric_name"), "affo": e["affo_total"] and line(e["affo_total"]),
        "steps": [line(s, category=s["category"], applied=s["applied"], reason=s["reason"], section=s["section"])
                  for s in r["steps"] if s["amount"]],
        "affo_unused": [line(x, category=x["category"]) for x in e["affo_adjustments"]
                        if x["amount"] and x["category"] not in ("recurring_capex",)
                        and not any(s["label"] == x["label"] and s["section"] == "affo" for s in r["steps"])],
        "capex": [line(x) for x in r["recurring_capex"]], "capex_source": r.get("recurring_capex_source"),
        "reported_ps": e["reported_per_share"],
        "nareit_ps": r["nareit_ffo_ps"], "company_core_ps": r["company_core_ps"], "company_affo_ps": r["company_affo_ps"],
        "cons_core": r["conservative_core_ffo"], "cons_core_ps": r["conservative_core_ffo_ps"],
        "cons_affo": r["conservative_affo"], "cons_affo_ps": r["conservative_affo_ps"],
        "ties": not e.get("validation_errors"), "flags": r["flags"],
    }


def build(extract_dir: Path, out: Path = OUT) -> Path:
    data = [record(json.loads(p.read_text())) for p in sorted(Path(extract_dir).glob("*.json"))]
    data.sort(key=lambda x: (x["ticker"], x["quarter"]))
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/[]", json.dumps(data, separators=(",", ":")))
    html = html.replace("__BUILT__", date.today().strftime("%B %d, %Y").replace(" 0", " "))
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    path = build(config.OUTPUT_DIR / "extractions")
    print(f"Dashboard written to {path}")
    sys.exit(0)
