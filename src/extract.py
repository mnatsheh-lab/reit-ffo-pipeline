"""Extraction: Claude reads the FFO reconciliation pages and fills a fixed form;
Python checks that every section adds up to the company's reported totals.

If the numbers don't tie, Claude gets the specific errors back and one chance to correct them.
"""
from __future__ import annotations

import json
from pathlib import Path

from .pages import Page, candidate_pages, split_pages

CATEGORIES = {
    # NAREIT FFO items
    "re_depreciation": "Depreciation and amortization of real estate (incl. discontinued ops)",
    "jv_depreciation": "Share of real estate depreciation of unconsolidated joint ventures",
    "property_sale_gain_loss": "Gains/losses on sale of depreciable real estate (incl. JV share)",
    "re_impairment": "Impairment of depreciable real estate",
    "noncontrolling_interest": "Net income attributable to noncontrolling interests / OP units",
    "nareit_other": "Any other item in the net income -> FFO section",
    # Company 'core' items
    "legal": "Legal costs, settlements, recoveries",
    "casualty": "Casualty / storm / weather losses, charges and insurance recoveries",
    "investment_gain_loss": "Gains/losses on non-real-estate investments (tech funds, securities)",
    "derivative_mtm": "Derivative / hedge / embedded derivative fair value changes",
    "debt_extinguishment": "Loss/gain on extinguishment or modification of debt, prepayment costs",
    "transaction_costs": "Transaction, merger, acquisition-pursuit, integration costs",
    "severance_restructuring": "Severance, restructuring, executive transition, software transition",
    "stock_comp": "Non-cash / stock-based compensation",
    "non_re_depreciation": "Depreciation/amortization of NON-real-estate assets (corporate offices, IT, 'other depreciation')",
    # AFFO items
    "recurring_capex": "Recurring / maintenance capital expenditures",
    "straight_line_rent": "Straight-line rent and similar non-cash revenue",
    "debt_cost_amortization": "Amortization of deferred financing costs, debt discounts/premiums",
    "other": "Anything that fits none of the above (describe it in the label)",
}

LINE = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "Line-item name exactly as printed"},
        "amount": {"type": "number", "description": "Current-quarter (three months) amount, signed as its effect on the next subtotal"},
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "page_seq": {"type": "integer", "description": "The seq number from the [[PAGE ...]] marker"},
        "page_printed": {"type": "string", "description": "The printed page number from the marker ('' if none)"},
    },
    "required": ["label", "amount", "category", "page_seq", "page_printed"],
}
TOTAL = {
    "type": "object",
    "properties": {
        "label": {"type": "string"}, "amount": {"type": "number"},
        "page_seq": {"type": "integer"}, "page_printed": {"type": "string"},
    },
    "required": ["label", "amount", "page_seq", "page_printed"],
}
NULLABLE_TOTAL = {"anyOf": [TOTAL, {"type": "null"}]}

EXTRACTION_VERSION = 2   # bump when the form or prompt changes; older results are re-extracted

CAPEX_DISCLOSED = {
    "anyOf": [{
        "type": "object",
        "properties": {
            "label": {"type": "string"}, "amount": {"type": "number", "description": "Positive amount spent, same unit as the totals"},
            "basis": {"type": "string", "enum": ["quarter", "year_to_date", "annual", "per_unit_only", "other"]},
            "scope": {"type": "string", "description": "e.g. 'company total', 'company share (excl. JV partners)'"},
            "page_seq": {"type": "integer"}, "page_printed": {"type": "string"},
        },
        "required": ["label", "amount", "basis", "scope", "page_seq", "page_printed"],
    }, {"type": "null"}],
}

RECORD_TOOL = {
    "name": "record_reconciliation",
    "description": "Record the company's net income -> FFO -> adjusted FFO -> AFFO reconciliation for the target quarter.",
    "input_schema": {
        "type": "object",
        "properties": {
            "amount_unit": {"type": "string", "enum": ["thousands", "dollars"]},
            "core_metric_name": {"type": ["string", "null"], "description": "Company's adjusted FFO name (Core FFO, CFFO, Normalized FFO, FFO as Adjusted) or null"},
            "affo_metric_name": {"type": ["string", "null"], "description": "Company's AFFO name (AFFO, Core AFFO) or null"},
            "affo_starts_from": {"type": ["string", "null"], "enum": ["ffo", "core", None]},
            "starting_line": TOTAL,
            "ffo_adjustments": {"type": "array", "items": LINE},
            "ffo_total": TOTAL,
            "core_adjustments": {"type": "array", "items": LINE},
            "core_total": NULLABLE_TOTAL,
            "affo_adjustments": {"type": "array", "items": LINE},
            "affo_total": NULLABLE_TOTAL,
            "diluted_shares": {**TOTAL, "description": "The share count the company divides by for FFO per share (shares + units if FFO includes units)"},
            "recurring_capex_disclosed": {**CAPEX_DISCLOSED, "description": "Only if the AFFO section has NO recurring capex line: the recurring/maintenance capex for the quarter from another table; else null"},
            "reported_per_share": {
                "type": "object",
                "properties": {"ffo": {"type": ["number", "null"]}, "core": {"type": ["number", "null"]}, "affo": {"type": ["number", "null"]}},
                "required": ["ffo", "core", "affo"],
            },
            "notes": {"type": "string", "description": "Anything unusual or uncertain"},
        },
        "required": ["amount_unit", "core_metric_name", "affo_metric_name", "affo_starts_from", "starting_line",
                     "ffo_adjustments", "ffo_total", "core_adjustments", "core_total", "affo_adjustments",
                     "affo_total", "diluted_shares", "recurring_capex_disclosed", "reported_per_share", "notes"],
    },
}

SYSTEM_PROMPT = f"""You extract REIT FFO reconciliations from SEC filings into a fixed form, exactly as printed.

Rules:
- Use ONLY the current quarter's three-month column (e.g. "Three months ended June 30, 2026", first column).
  Ignore prior-year, year-to-date, full-year and guidance columns or tables.
- starting_line is the first line of the reconciliation (net income or net loss line it starts from).
- Every line between two subtotals goes in the matching adjustments list, in printed order:
  starting_line + ffo_adjustments = ffo_total; ffo_total + core_adjustments = core_total;
  (core_total or ffo_total, per affo_starts_from) + affo_adjustments = affo_total.
- Sign each amount as its effect on reaching the next subtotal: printed in parentheses or subtracted -> negative.
- If a company has no adjusted FFO metric, set core_total null and core_adjustments []. Same for AFFO.
- diluted_shares: the share count the company actually uses for FFO per share. It may be on a different page
  (e.g. "Diluted shares outstanding for FFO and AFFO" or "weighted average common shares and units"). Use the
  current-quarter figure, in the same unit as the dollar totals (if totals are in thousands and the count is
  printed in full, divide it by 1,000). Check it reproduces the reported per-share figures.
- recurring_capex_disclosed: if the company's AFFO does not subtract recurring (maintenance) capital expenditures,
  look for the current quarter's recurring capex in another table on these pages (e.g. a capital expenditures
  table or a sentence in the highlights). Prefer the company's own share and the quarterly figure; record the
  basis honestly (quarter, year_to_date, annual, per_unit_only). Use null if it is not disclosed.
- Copy labels exactly as printed. Give the page_seq and page_printed from the [[PAGE ...]] marker where each line appears.
- Categories: {json.dumps(CATEGORIES)}
- Use 'other' only when nothing else fits. Never invent or estimate numbers; if something is unclear, say so in notes.
- Always respond by calling the record_reconciliation tool."""


def pages_prompt(pages: list[Page]) -> str:
    return "\n\n".join(f"[[PAGE seq={p.seq} printed={p.printed or ''}]]\n{p.text}" for p in pages)


def _sum(xs) -> float:
    return sum(x["amount"] for x in xs)


def validate(ext: dict) -> list[str]:
    """Return a list of arithmetic problems (empty = everything ties)."""
    tol = 1.5 if ext.get("amount_unit") == "thousands" else 1500
    errors = []
    ffo_calc = ext["starting_line"]["amount"] + _sum(ext["ffo_adjustments"])
    if abs(ffo_calc - ext["ffo_total"]["amount"]) > tol:
        errors.append(f"starting_line + ffo_adjustments = {ffo_calc:,.0f} but ffo_total = {ext['ffo_total']['amount']:,.0f}")
    if ext.get("core_total"):
        core_calc = ext["ffo_total"]["amount"] + _sum(ext["core_adjustments"])
        if abs(core_calc - ext["core_total"]["amount"]) > tol:
            errors.append(f"ffo_total + core_adjustments = {core_calc:,.0f} but core_total = {ext['core_total']['amount']:,.0f}")
    elif ext["core_adjustments"]:
        errors.append("core_adjustments given but core_total is null")
    if ext.get("affo_total"):
        base = ext["core_total"] if ext.get("affo_starts_from") == "core" and ext.get("core_total") else ext["ffo_total"]
        affo_calc = base["amount"] + _sum(ext["affo_adjustments"])
        if abs(affo_calc - ext["affo_total"]["amount"]) > tol:
            errors.append(f"{ext.get('affo_starts_from')} total + affo_adjustments = {affo_calc:,.0f} but affo_total = {ext['affo_total']['amount']:,.0f}")
    shares = ext["diluted_shares"]["amount"]
    rps = ext["reported_per_share"]
    for key, total in (("ffo", ext["ffo_total"]), ("core", ext.get("core_total")), ("affo", ext.get("affo_total"))):
        if total and rps.get(key) is not None and shares:
            calc = round(total["amount"] / shares, 2)
            if abs(calc - rps[key]) > 0.011:
                errors.append(f"{key}: total / diluted_shares = {calc:.2f} but reported per share = {rps[key]:.2f}")
    return errors


def extract_document(client, model: str, raw: bytes, filename: str, ticker: str, quarter_label: str,
                     period_end_text: str) -> dict:
    pages = split_pages(raw, filename)
    cands = candidate_pages(pages)
    user = (f"Company: {ticker}. Target quarter: {quarter_label} (three months ended {period_end_text}).\n"
            f"Pages likely to contain the reconciliation:\n\n{pages_prompt(cands)}")
    messages = [{"role": "user", "content": user}]
    usage = {"input_tokens": 0, "output_tokens": 0}
    ext, errors, attempts, calls = None, ["no extraction returned"], 0, 0
    # Up to 2 extraction attempts (the second after a failed arithmetic check), plus at most
    # 2 reminders if Claude answers in text instead of calling the tool.
    while attempts < 2 and calls < 4:
        calls += 1
        resp = client.messages.create(
            model=model, max_tokens=8000, system=SYSTEM_PROMPT, tools=[RECORD_TOOL],
            tool_choice={"type": "auto"}, messages=messages,
        )
        u = getattr(resp, "usage", None)
        if u is not None:
            usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
        content = []
        for b in resp.content:
            if b.type == "text":
                content.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                content.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        block = next((b for b in resp.content if b.type == "tool_use" and b.name == RECORD_TOOL["name"]), None)
        messages.append({"role": "assistant", "content": content or [{"type": "text", "text": "(no content)"}]})
        if block is None:
            messages.append({"role": "user", "content": "Please record the reconciliation now by calling the record_reconciliation tool."})
            continue
        attempts += 1
        ext = dict(block.input)
        errors = validate(ext)
        if not errors:
            break
        messages.append({"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": block.id, "is_error": True,
            "content": "These checks failed:\n- " + "\n- ".join(errors) +
                       "\nRe-read the pages, fix missing or mis-signed lines, and call record_reconciliation again.",
        }]})
    if ext is None:
        raise RuntimeError("Claude did not return an extraction")
    ext["version"] = EXTRACTION_VERSION
    ext["validation_errors"] = errors
    ext["attempts"] = attempts
    ext["usage"] = usage
    ext["candidate_pages"] = [{"seq": p.seq, "printed": p.printed} for p in cands]
    return ext
