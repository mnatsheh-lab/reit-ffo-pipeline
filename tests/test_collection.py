"""Offline tests: simulated EDGAR + scripted Claude. Run with:  python -m unittest discover tests"""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

from src.agent import CollectionAgent
from src.edgar import document_text, reconciliation_signals
from src.quarters import Quarter, quarter_range

RELEASE = b"""<html><body><p>MAA REPORTS SECOND QUARTER 2026 RESULTS</p>
<p>Three months ended June 30, 2026</p></body></html>"""
SUPPLEMENT = b"""<html><body><h2>Reconciliation of net income to Funds From Operations</h2>
<table><tr><td>Net income</td><td>120,828</td></tr>
<tr><td>Depreciation and amortization of real estate assets</td><td>161,037</td></tr>
<tr><td>FFO</td><td>249,846</td></tr></table>
<p>Three months ended June 30, 2026</p></body></html>"""


class FakeEdgar:
    def __init__(self):
        self.docs = {"ex99-1.htm": RELEASE, "ex99-2.htm": SUPPLEMENT}

    def earnings_filings(self, cik, start, end):
        rows = [{"accessionNumber": "0000912595-26-000045", "form": "8-K", "filingDate": "2026-07-29",
                 "items": "2.02,9.01", "primaryDocument": "maa-8k.htm"}]
        return [r for r in rows if start <= date.fromisoformat(r["filingDate"]) <= end]

    def filing_documents(self, cik, accession):
        return [{"name": n, "size": len(b), "url": n} for n, b in self.docs.items()]

    def document_url(self, cik, accession, name):
        return f"https://example/{accession}/{name}"

    def get_bytes(self, url):
        return self.docs[url.rsplit("/", 1)[1]]


def tool(i, name, **inp):
    return NS(type="tool_use", id=f"t{i}", name=name, input=inp)


class ScriptedClaude:
    """Returns pre-written responses in order, like a very predictable Claude."""
    def __init__(self, steps):
        self.steps = list(steps)
        self.messages = self
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        blocks = self.steps.pop(0)
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        return NS(content=blocks, stop_reason=stop, usage=NS(input_tokens=100, output_tokens=20))


class QuarterTests(unittest.TestCase):
    def test_parse_and_range(self):
        self.assertEqual([str(q) for q in quarter_range("2025Q4", "2026Q2")], ["2025Q4", "2026Q1", "2026Q2"])
        self.assertEqual(Quarter.parse("2025Q4").period_end_text, "December 31, 2025")
        self.assertEqual(Quarter.parse("2026Q1").period_end, date(2026, 3, 31))

    def test_filing_window_covers_release(self):
        start, end = Quarter.parse("2026Q2").filing_window()
        self.assertTrue(start <= date(2026, 7, 29) <= end)


class TextTests(unittest.TestCase):
    def test_signals(self):
        text = document_text(SUPPLEMENT, "x.htm")
        s = reconciliation_signals(text, "June 30, 2026")
        self.assertTrue(s["mentions_ffo"] and s["has_reconciliation_words"] and s["mentions_period_end"])
        s2 = reconciliation_signals(document_text(RELEASE, "x.htm"), "June 30, 2026")
        self.assertFalse(s2["has_reconciliation_words"])

    def test_generic_depreciation_wording_passes(self):
        brt_style = b"""<p>The tables below provide a reconciliation of net loss to FFO and AFFO.</p>
        <table><tr><td>Net loss</td><td>(3,405)</td></tr><tr><td>Depreciation and amortization</td><td>6,710</td></tr>
        <tr><td>Funds from operations</td><td>5,505</td></tr></table><p>Three months ended June 30, 2026</p>"""
        s = reconciliation_signals(document_text(brt_style, "x.htm"), "June 30, 2026")
        self.assertTrue(s["has_reconciliation_words"])

    def test_real_maa_pdf(self):
        pdf = Path("/home/claude/REIT_Supplementals/MAA/MAA_2026Q2_supplemental.pdf")
        if not pdf.exists():
            self.skipTest("answer-key PDF not available")
        text = document_text(pdf.read_bytes(), pdf.name)
        self.assertIn("[[PAGE 10]]", text)
        s = reconciliation_signals(text, "June 30, 2026")
        self.assertTrue(all([s["mentions_ffo"], s["has_reconciliation_words"], s["mentions_period_end"]]))


class AgentTests(unittest.TestCase):
    def test_full_loop_saves_supplement(self):
        acc = "0000912595-26-000045"
        claude = ScriptedClaude([
            [tool(1, "list_earnings_filings", quarter="2026Q2")],
            [tool(2, "list_filing_documents", accession=acc)],
            [tool(3, "read_document", accession=acc, filename="ex99-1.htm", quarter="2026Q2"),
             tool(4, "read_document", accession=acc, filename="ex99-2.htm", quarter="2026Q2")],
            [tool(5, "save_document", quarter="2026Q2", accession=acc, filename="ex99-2.htm",
                  reason="Exhibit 99.2 has the full net income to FFO reconciliation")],
        ])
        with tempfile.TemporaryDirectory() as d:
            agent = CollectionAgent(claude, "test-model", FakeEdgar(), Path(d))
            res = agent.run("MAA", 912595, [Quarter.parse("2026Q2")])
            self.assertEqual(len(res.records), 1)
            rec = res.records[0]
            self.assertEqual(rec["status"], "saved")
            self.assertEqual(rec["filename"], "ex99-2.htm")
            self.assertTrue(Path(rec["path"]).exists())
            self.assertTrue(Path(rec["path"]).name == "MAA_2026Q2_earnings.htm")
            self.assertEqual(res.turns, 4)  # stops once every quarter is resolved
            # Every tool_use is answered by a tool_result with the same id, in the next message
            msgs = claude.calls[-1]["messages"]
            for i, m in enumerate(msgs):
                if m["role"] == "assistant":
                    use_ids = [b["id"] for b in m["content"] if b["type"] == "tool_use"]
                    if use_ids:
                        result_ids = [b["tool_use_id"] for b in msgs[i + 1]["content"]]
                        self.assertEqual(use_ids, result_ids)

    def test_unresolved_quarter_marked_missing_and_bad_quarter_rejected(self):
        claude = ScriptedClaude([
            [tool(1, "list_earnings_filings", quarter="2019Q1")],   # not a target -> tool error
            [NS(type="text", text="I could not find it.")],
        ])
        with tempfile.TemporaryDirectory() as d:
            res = CollectionAgent(claude, "m", FakeEdgar(), Path(d)).run("MAA", 912595, [Quarter.parse("2026Q2")])
        self.assertEqual(res.records[0]["status"], "missing")
        self.assertTrue(any("ERROR" in line for line in res.log))
        results = [b for m in claude.calls[-1]["messages"] if m["role"] == "user" and isinstance(m["content"], list)
                   for b in m["content"]]
        self.assertTrue(results[0]["is_error"])

    def test_wrong_period_is_saved_unverified(self):
        acc = "0000912595-26-000045"
        claude = ScriptedClaude([
            [tool(1, "save_document", quarter="2026Q1", accession=acc, filename="ex99-2.htm", reason="test")],
            [NS(type="text", text="done")],
        ])
        with tempfile.TemporaryDirectory() as d:
            res = CollectionAgent(claude, "m", FakeEdgar(), Path(d)).run("MAA", 912595, [Quarter.parse("2026Q1")])
        self.assertEqual(res.records[0]["status"], "saved_unverified")


if __name__ == "__main__":
    unittest.main()
