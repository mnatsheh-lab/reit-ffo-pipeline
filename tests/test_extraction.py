"""Offline tests for extraction checks, the restatement rules and the answer-key comparison."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from src.extract import extract_document, validate
from src.restate import restate
from src.verify_extraction import compare_maa

ROOT = Path(__file__).resolve().parent.parent


def L(label, amount, category, page=10):
    return {"label": label, "amount": amount, "category": category, "page_seq": page, "page_printed": str(page)}


def T(label, amount, page=10):
    return {"label": label, "amount": amount, "page_seq": page, "page_printed": str(page)}


# MAA, from page 10 of each supplemental (the same numbers as the hand-built answer key).
MAA = {
    "2025Q4": dict(start=56649, ffo_adj=[158367, -224, 168, 0, -330], ffo=214630,
                   core_adj=[(2181, "derivative_mtm"), (-1336, "investment_gain_loss"), (-903, "casualty"), (53000, "legal")],
                   core=267572, capex=-38260, affo=229312, shares=119987, ps=(1.79, 2.23, 1.91)),
    "2026Q1": dict(start=123437, ffo_adj=[160493, -20164, 170, 0, 2252], ffo=266188,
                   core_adj=[(1574, "derivative_mtm"), (-17237, "investment_gain_loss"), (4519, "casualty")],
                   core=255044, capex=-18748, affo=236296, shares=119629, ps=(2.23, 2.13, 1.98)),
    "2026Q2": dict(start=120828, ffo_adj=[161037, -35255, 168, 0, 3068], ffo=249846,
                   core_adj=[(-1091, "derivative_mtm"), (1068, "investment_gain_loss"), (-2299, "casualty")],
                   core=247524, capex=-37242, affo=210282, shares=119094, ps=(2.10, 2.08, 1.77)),
}
FFO_CATS = ["re_depreciation", "property_sale_gain_loss", "jv_depreciation", "nareit_other", "noncontrolling_interest"]


def maa_extraction(q):
    d = MAA[q]
    return {
        "amount_unit": "thousands", "core_metric_name": "Core FFO", "affo_metric_name": "Core AFFO", "affo_starts_from": "core",
        "starting_line": T("Net income available for MAA common shareholders", d["start"]),
        "ffo_adjustments": [L(f"line {i}", a, c) for i, (a, c) in enumerate(zip(d["ffo_adj"], FFO_CATS)) if a],
        "ffo_total": T("FFO attributable to common shareholders and unitholders", d["ffo"]),
        "core_adjustments": [L(c, a, c) for a, c in d["core_adj"]],
        "core_total": T("Core FFO attributable to common shareholders and unitholders", d["core"]),
        "affo_adjustments": [L("Recurring capital expenditures", d["capex"], "recurring_capex")],
        "affo_total": T("Core AFFO attributable to common shareholders and unitholders", d["affo"]),
        "diluted_shares": T("FFO weighted average common shares and units - diluted", d["shares"]),
        "reported_per_share": dict(zip(("ffo", "core", "affo"), d["ps"])), "notes": "",
    }


class ValidateTests(unittest.TestCase):
    def test_maa_ties(self):
        for q in MAA:
            self.assertEqual(validate(maa_extraction(q)), [], q)

    def test_missing_line_caught(self):
        e = maa_extraction("2025Q4")
        e["core_adjustments"] = e["core_adjustments"][:-1]   # drop the $53M legal line
        errs = validate(e)
        self.assertTrue(any("core_total" in x for x in errs))


class RestateTests(unittest.TestCase):
    def test_conservative_definition_on_maa(self):
        expected = {"2025Q4": (1.7883, 1.4694), "2026Q1": (2.0942, 1.9375), "2026Q2": (2.0784, 1.7657)}
        for q, (core_ps, affo_ps) in expected.items():
            r = restate(maa_extraction(q))
            self.assertAlmostEqual(r["conservative_core_ffo_ps"], core_ps, places=4, msg=q)
            self.assertAlmostEqual(r["conservative_affo_ps"], affo_ps, places=4, msg=q)
            self.assertEqual(r["flags"], [], q)

    def test_rules(self):
        r = restate(maa_extraction("2025Q4"))
        by_cat = {s["category"]: s for s in r["steps"]}
        self.assertFalse(by_cat["legal"]["applied"])          # $53M add-back reversed
        self.assertTrue(by_cat["casualty"]["applied"])        # net recovery removed
        self.assertTrue(by_cat["derivative_mtm"]["applied"])  # removed either way
        r1 = restate(maa_extraction("2026Q1"))
        self.assertFalse({s["category"]: s for s in r1["steps"]}["casualty"]["applied"])  # net charge kept

    def test_no_capex_and_other_flagged(self):
        e = maa_extraction("2026Q2")
        e["affo_adjustments"], e["affo_total"] = [], None
        e["core_adjustments"].append(L("Mystery item", 500, "other"))
        r = restate(e)
        self.assertIsNone(r["conservative_affo"])
        self.assertTrue(any("Review: 'Mystery item'" in f for f in r["flags"]))
        self.assertTrue(any("No recurring capex" in f for f in r["flags"]))

    def test_nxrt_style_rules(self):
        """NXRT Q4 2025 core section as extracted on the first live run."""
        e = {
            "core_metric_name": "Core FFO", "affo_metric_name": "AFFO", "affo_starts_from": "core",
            "ffo_total": T("FFO attributable to common stockholders", 13160, 19),
            "core_adjustments": [
                L("Loss on extinguishment of debt and modification costs", 0, "debt_extinguishment", 19),
                L("Casualty-related expenses/(recoveries)", 1700, "casualty", 19),
                L("Casualty loss", 4, "casualty", 19),
                L("Amortization of deferred financing costs", 1656, "debt_cost_amortization", 19),
                L("Mark-to-market adjustments of interest rate caps", 26, "derivative_mtm", 19),
                L("Adjustment for noncontrolling interests", -13, "noncontrolling_interest", 19),
            ],
            "core_total": T("Core FFO attributable to common stockholders", 16533, 19),
            "affo_adjustments": [L("Equity-based compensation expense", 2546, "stock_comp", 19),
                                 L("Adjustment for noncontrolling interests", -10, "noncontrolling_interest", 19)],
            "affo_total": T("AFFO attributable to common stockholders", 19069, 19),
            "recurring_capex_disclosed": {"label": "Capital expenditures - recurring", "amount": 2000, "basis": "quarter",
                                          "scope": "company total", "page_seq": 22, "page_printed": "20"},
            "diluted_shares": T("Weighted average diluted shares", 25411, 19),
        }
        r = restate(e)
        # Kept: casualty (1,700 + 4) and financing-cost amortization (1,656). Applied: derivative (+26), NCI (-13).
        self.assertEqual(r["conservative_core_ffo"], 13160 + 26 - 13)
        self.assertAlmostEqual(r["conservative_core_ffo_ps"], 0.5184, places=4)
        # Stock comp add-back in AFFO is not applied; capex comes from the separate table.
        self.assertEqual(r["conservative_affo"], 13173 - 2000)
        self.assertEqual(r["recurring_capex_source"], "capex_table")
        self.assertTrue(any("separate table" in f for f in r["flags"]))
        self.assertFalse(any("Amortization of deferred financing costs" in f for f in r["flags"]))  # now a firm rule
        amort = next(x for x in r["steps"] if x["category"] == "debt_cost_amortization")
        self.assertFalse(amort["applied"])

    def test_annual_capex_not_used(self):
        e = maa_extraction("2026Q2")
        e["affo_adjustments"], e["affo_total"] = [], None
        e["recurring_capex_disclosed"] = {"label": "Estimated recurring capex", "amount": 5278, "basis": "annual",
                                          "scope": "BRT share", "page_seq": 16, "page_printed": "12"}
        r = restate(e)
        self.assertIsNone(r["conservative_affo"])
        self.assertTrue(any("'annual' basis" in f for f in r["flags"]))


class ScriptedClaude:
    def __init__(self, inputs):
        self.inputs, self.messages, self.calls = list(inputs), self, []

    def create(self, **kw):
        self.calls.append(kw)
        assert kw["tool_choice"] == {"type": "auto"}
        nxt = self.inputs.pop(0)
        if isinstance(nxt, str):   # Claude replies in text instead of calling the tool
            return NS(content=[NS(type="text", text=nxt)], stop_reason="end_turn", usage=NS(input_tokens=500, output_tokens=50))
        return NS(content=[NS(type="tool_use", id=f"t{len(self.calls)}", name="record_reconciliation", input=nxt)],
                  stop_reason="tool_use", usage=NS(input_tokens=1000, output_tokens=300))


class ExtractLoopTests(unittest.TestCase):
    def test_retry_fixes_errors_on_real_document(self):
        doc = Path("/mnt/user-data/uploads/reit-ffo-pipeline/data/raw/edgar/MAA/MAA_2026Q2_earnings.htm")
        if not doc.exists():
            self.skipTest("EDGAR document not available")
        good = maa_extraction("2026Q2")
        bad = copy.deepcopy(good)
        bad["ffo_adjustments"] = bad["ffo_adjustments"][1:]          # forgot depreciation
        claude = ScriptedClaude([bad, good])
        ext = extract_document(claude, "m", doc.read_bytes(), doc.name, "MAA", "2026Q2", "June 30, 2026")
        self.assertEqual(ext["attempts"], 2)
        self.assertEqual(ext["validation_errors"], [])
        first_prompt = claude.calls[0]["messages"][0]["content"]
        self.assertIn("[[PAGE seq=10 printed=10]]", first_prompt)    # reconciliation page was sent
        self.assertIn("161,037", first_prompt)
        retry_msg = claude.calls[1]["messages"][2]["content"][0]["content"]  # user turn after the first attempt
        self.assertIn("ffo_total", retry_msg)


    def test_text_reply_gets_reminder(self):
        doc = Path("/mnt/user-data/uploads/reit-ffo-pipeline/data/raw/edgar/MAA/MAA_2026Q2_earnings.htm")
        if not doc.exists():
            self.skipTest("EDGAR document not available")
        claude = ScriptedClaude(["Here is the reconciliation...", maa_extraction("2026Q2")])
        ext = extract_document(claude, "m", doc.read_bytes(), doc.name, "MAA", "2026Q2", "June 30, 2026")
        self.assertEqual(ext["validation_errors"], [])
        self.assertEqual(len(claude.calls), 2)
        self.assertIn("record_reconciliation", claude.calls[1]["messages"][2]["content"])  # reminder turn


class AnswerKeyTests(unittest.TestCase):
    def test_compare_with_workbook(self):
        wb = ROOT / "data" / "answer_key" / "MAA_FFO_Reconciliation.xlsx"
        with tempfile.TemporaryDirectory() as d:
            for q in MAA:
                Path(d, f"MAA_{q}.json").write_text(json.dumps({"extraction": maa_extraction(q)}))
            self.assertEqual(compare_maa(wb, Path(d)), 0)
            e = maa_extraction("2025Q4"); e["core_total"]["amount"] = 1
            Path(d, "MAA_2025Q4.json").write_text(json.dumps({"extraction": e}))
            self.assertEqual(compare_maa(wb, Path(d)), 1)


if __name__ == "__main__":
    unittest.main()
