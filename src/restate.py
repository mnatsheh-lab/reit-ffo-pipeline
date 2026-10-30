"""Apply the Conservative Core FFO definition (docs/common_definition.md) to an extraction.

All arithmetic is here, in code. Each adjustment is either APPLIED (we make the same
adjustment the company made) or KEPT IN (we undo the company's adjustment, so the item
stays in earnings), with the reason recorded for the dashboard.
"""
from __future__ import annotations

# Remove both gains and losses (apply the company's adjustment whatever its sign).
REMOVE_BOTH = {"investment_gain_loss", "derivative_mtm"}
# Keep costs in earnings; remove gains/recoveries. A positive adjustment is an add-back of a cost
# (kept in, i.e. not applied); a negative adjustment removes a gain or recovery (applied).
KEEP_COSTS = {"legal", "casualty", "debt_extinguishment", "transaction_costs", "severance_restructuring", "stock_comp"}
CAPEX = {"recurring_capex"}
# AFFO-only items our definition does not use.
IGNORED_AFFO = {"straight_line_rent", "debt_cost_amortization"}

REASONS = {
    "legal": "Legal costs are a normal cost of operating; kept as a cost",
    "casualty": "Casualty losses are a recurring cost; only insurance recoveries are removed",
    "debt_extinguishment": "Refinancing is recurring; costs kept, gains removed",
    "transaction_costs": "Acquisition-driven growth has a real cost; kept as a cost",
    "severance_restructuring": "Reorganizations recur; kept as a cost",
    "stock_comp": "Stock compensation dilutes shareholders; kept as a cost",
    "investment_gain_loss": "Non-real-estate investment results removed (gains and losses)",
    "derivative_mtm": "Non-cash derivative revaluation removed (gains and losses)",
    "other": "Unlisted adjustment type: treated conservatively (costs kept, gains removed) and flagged for review",
}


# Types the definition does not list yet. Until reviewed they get the conservative default
# (costs kept, gains removed) and are flagged.
PROVISIONAL = {
    "debt_cost_amortization": "Financing-cost amortization is a real cost of debt; kept as a cost (provisional rule, review)",
    "other": REASONS["other"],
}
REVIEW_NEEDED = set(PROVISIONAL) | {"re_depreciation", "jv_depreciation", "property_sale_gain_loss", "re_impairment", "nareit_other", "straight_line_rent", "recurring_capex"}


def treat(line: dict) -> tuple[bool, str]:
    """Return (applied?, reason) for one company adjustment."""
    cat, amt = line["category"], line["amount"]
    if cat in REMOVE_BOTH:
        return True, REASONS[cat]
    if cat == "noncontrolling_interest":
        return True, "Noncontrolling interests' share of the adjustments; applied as the company did"
    reason = REASONS.get(cat) or PROVISIONAL.get(cat) or f"'{cat}' item in the company's adjusted section; costs kept, gains removed (provisional rule, review)"
    if amt == 0:
        return False, reason + " (zero this quarter)"
    return (amt < 0), reason + (" (gain/recovery removed)" if amt < 0 else " (company add-back reversed)")


def restate(ext: dict) -> dict:
    flags = list(ext.get("validation_errors") and ["Extraction did not tie to reported totals"] or [])
    ffo = ext["ffo_total"]["amount"]
    shares = ext["diluted_shares"]["amount"]
    steps = []

    # Company adjustments that our definition rules on: the core section, plus any
    # definition items a company places in its AFFO section.
    rule_lines = [("core", l) for l in ext.get("core_adjustments", [])]
    rule_lines += [("affo", l) for l in ext.get("affo_adjustments", []) if l["category"] in REMOVE_BOTH | KEEP_COSTS | {"other"} and l["category"] != "stock_comp"]
    cons_core = ffo
    for section, line in rule_lines:
        applied, reason = treat(line)
        if line["category"] in REVIEW_NEEDED and line["amount"] != 0:
            flags.append(f"Review: '{line['label']}' ({line['category']}) handled by a provisional rule")
        if applied:
            cons_core += line["amount"]
        steps.append({**line, "section": section, "applied": applied, "effect": line["amount"] if applied else 0.0, "reason": reason})

    capex_lines = [l for l in ext.get("affo_adjustments", []) if l["category"] in CAPEX]
    capex_source = "affo_reconciliation" if capex_lines else None
    disclosed = ext.get("recurring_capex_disclosed")
    if not capex_lines and disclosed and disclosed.get("basis") == "quarter" and disclosed.get("amount"):
        capex_lines = [{**disclosed, "amount": -abs(disclosed["amount"]), "category": "recurring_capex"}]
        capex_source = "capex_table"
        flags.append(f"Recurring capex taken from a separate table (page {disclosed.get('page_printed') or disclosed.get('page_seq')}): "
                     "the company's own AFFO does not deduct it")
    elif not capex_lines and disclosed:
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
