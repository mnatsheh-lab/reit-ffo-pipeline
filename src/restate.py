"""Apply an FFO definition to an extraction.

The rules live in src/definition.json (shared with the dashboard, which runs the same logic in
the browser so users can pick their own rules). Each company adjustment gets one of three
treatments by category:

    apply       remove the item from earnings, as the company did (gains and losses)
    keep_costs  keep costs in earnings, remove gains and recoveries (the risk-averse default)
    keep_all    keep the item in earnings (the company's adjustment is reversed)

All arithmetic is here, in code; the AI only transcribes the reconciliation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFINITION = json.loads((Path(__file__).with_name("definition.json")).read_text(encoding="utf-8"))
CATEGORIES = DEFINITION["categories"]
LABEL_RULES = [(re.compile(p, re.I), cat) for p, cat in DEFINITION["label_rules"]]
AFFO_EXCLUDED = set(DEFINITION["affo_excluded"])


def default_rules() -> dict:
    return {"treatments": {c: v["default"] for c, v in CATEGORIES.items()}, "capex": dict(DEFINITION["capex"])}


def normalize(line: dict) -> dict:
    """Fix the category from the line's label where a label rule matches."""
    for pattern, cat in LABEL_RULES:
        if pattern.search(line.get("label", "")):
            return {**line, "category": cat}
    return line


def rule_lines(ext: dict) -> list[tuple[str, dict]]:
    """Company adjustments the definition rules on: the adjusted-FFO section, plus items a company
    lists in its AFFO section that are earnings items (not capex, stock comp, financing-cost
    amortization or straight-line rent, which this definition simply doesn't add back)."""
    lines = [("core", normalize(l)) for l in ext.get("core_adjustments", [])]
    lines += [("affo", l) for l in map(normalize, ext.get("affo_adjustments", [])) if l["category"] not in AFFO_EXCLUDED]
    return lines


def treat(line: dict, rules: dict) -> tuple[bool, str]:
    """Return (applied?, reason) for one company adjustment."""
    cat, amt = line["category"], line["amount"]
    if cat == "noncontrolling_interest":
        return True, "Noncontrolling interests' share of the adjustments; applied as the company did"
    info = CATEGORIES.get(cat, CATEGORIES["other"])
    t = rules["treatments"].get(cat, rules["treatments"].get("other", "keep_costs"))
    reason = DEFINITION["treatment_reasons"][t]
    if t == info["default"]:
        reason += f" ({info['why']})"
    if amt == 0:
        return False, reason + "; zero this quarter"
    if t == "apply":
        return True, reason
    if t == "keep_all":
        return False, reason
    return (amt < 0), reason + ("; gain/recovery removed" if amt < 0 else "; company add-back reversed")


def restate(ext: dict, rules: dict | None = None) -> dict:
    rules = rules or default_rules()
    flags = list(ext.get("validation_errors") and ["Extraction did not tie to reported totals"] or [])
    ffo = ext["ffo_total"]["amount"]
    shares = ext["diluted_shares"]["amount"]
    steps = []
    cons_core = ffo
    for section, line in rule_lines(ext):
        applied, reason = treat(line, rules)
        info = CATEGORIES.get(line["category"])
        if line["amount"] != 0 and line["category"] != "noncontrolling_interest" and (info is None or info.get("provisional")):
            flags.append(f"Review: '{line['label']}' ({line['category']}) handled by a provisional rule")
        if applied:
            cons_core += line["amount"]
        steps.append({**line, "section": section, "applied": applied, "effect": line["amount"] if applied else 0.0, "reason": reason})

    capex_lines, capex_source = [], None
    if rules["capex"].get("deduct", True):
        capex_lines = [l for l in ext.get("affo_adjustments", []) if l["category"] == "recurring_capex"]
        capex_source = "affo_reconciliation" if capex_lines else None
        disclosed = ext.get("recurring_capex_disclosed")
        if not capex_lines and disclosed and rules["capex"].get("use_capex_table", True) and disclosed.get("basis") == "quarter" and disclosed.get("amount"):
            capex_lines = [{**disclosed, "amount": -abs(disclosed["amount"]), "category": "recurring_capex"}]
            capex_source = "capex_table"
            flags.append(f"Recurring capex taken from a separate table (page {disclosed.get('page_printed') or disclosed.get('page_seq')}): "
                         "the company's own AFFO does not deduct it")
        elif not capex_lines and disclosed and disclosed.get("basis") != "quarter":
            flags.append(f"Recurring capex only disclosed on a '{disclosed.get('basis')}' basis; Conservative AFFO not computed")
        elif not capex_lines:
            flags.append("No recurring capex disclosed; Conservative AFFO not computed")
    cons_affo = cons_core + sum(l["amount"] for l in capex_lines) if capex_lines else None

    def ps(x):
        return round(x / shares, 4) if (x is not None and shares) else None

    core_reported = ext["core_total"]["amount"] if ext.get("core_total") else None
    affo_reported = ext["affo_total"]["amount"] if ext.get("affo_total") else None
    return {
        "nareit_ffo": ffo, "nareit_ffo_ps": ps(ffo),
        "company_core_name": ext.get("core_metric_name"), "company_core": core_reported, "company_core_ps": ps(core_reported),
        "company_affo_name": ext.get("affo_metric_name"), "company_affo": affo_reported, "company_affo_ps": ps(affo_reported),
        "conservative_core_ffo": cons_core, "conservative_core_ffo_ps": ps(cons_core),
        "conservative_affo": cons_affo, "conservative_affo_ps": ps(cons_affo),
        "recurring_capex": [{**l} for l in capex_lines], "recurring_capex_source": capex_source,
        "steps": steps, "flags": flags, "diluted_shares": shares,
    }
