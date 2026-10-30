"""Offline tests for the free rule-based picker, using real EDGAR documents where available."""
import unittest
from datetime import date
from pathlib import Path

from src.quarters import Quarter
from src.rules import pick

DOCS = Path("/mnt/user-data/uploads/reit-ffo-pipeline/data/raw/edgar")
STATS = b"<html><body><p>Portfolio statistics. Units 104,000. Occupancy 95.5% as of June 30, 2026.</p>" + b"<p>x</p>" * 2000 + b"</body></html>"


class FakeEdgar:
    def __init__(self, filings, items=None):
        self.filings = filings      # list of (accession, filed_date, {name: bytes})
        self.items = items or {}    # accession -> 8-K item list (default "2.02,9.01")

    def earnings_filings(self, cik, start, end):
        return [{"accessionNumber": a, "filingDate": d, "form": "8-K", "items": self.items.get(a, "2.02,9.01")}
                for a, d, _ in self.filings if start <= date.fromisoformat(d) <= end]

    def filing_documents(self, cik, acc):
        docs = next(x for a, _, x in self.filings if a == acc)
        return [{"name": n, "size": len(b), "url": f"{acc}/{n}"} for n, b in docs.items()]

    def get_bytes(self, url):
        acc, name = url.split("/")
        return next(x for a, _, x in self.filings if a == acc)[name]

    def document_url(self, cik, acc, name):
        return f"{acc}/{name}"


def need(*paths):
    for p in paths:
        if not p.exists():
            raise unittest.SkipTest("EDGAR documents not available")
    return [p.read_bytes() for p in paths]


class RulesTests(unittest.TestCase):
    def test_picks_reconciliation_exhibit_over_stats(self):
        (maa,) = need(DOCS / "MAA/MAA_2026Q2_earnings.htm")
        edgar = FakeEdgar([("A1", "2026-07-29", {"maa-ex99_1.htm": maa, "maa-ex99_2.htm": STATS})])
        choice, why = pick(edgar, 1, Quarter.parse("2026Q2"))
        self.assertIsNotNone(choice, why)
        self.assertEqual(choice["doc"]["name"], "maa-ex99_1.htm")

    def test_rejects_next_quarters_release(self):
        q1, q2 = need(DOCS / "MAA/MAA_2026Q1_earnings.htm", DOCS / "MAA/MAA_2026Q2_earnings.htm")
        # Both releases fall inside Q1's 120-day window; only the Q1 one is right.
        edgar = FakeEdgar([("A1", "2026-04-29", {"q1.htm": q1}), ("A2", "2026-07-29", {"q2.htm": q2})])
        choice, why = pick(edgar, 1, Quarter.parse("2026Q1"))
        self.assertIsNotNone(choice, why)
        self.assertEqual(choice["doc"]["name"], "q1.htm")

    def test_supplemental_preferred_over_release(self):
        (cpt,) = need(DOCS / "CPT/CPT_2026Q2_earnings.htm")
        release = cpt[: len(cpt) // 3]   # a shorter document with less of the package
        edgar = FakeEdgar([("A1", "2026-07-30", {"ex99-1.htm": release, "exhibit992supplement2q26.htm": cpt})])
        choice, _ = pick(edgar, 1, Quarter.parse("2026Q2"))
        self.assertEqual(choice["doc"]["name"], "exhibit992supplement2q26.htm")

    def test_defers_when_nothing_qualifies_or_ambiguous(self):
        edgar = FakeEdgar([("A1", "2026-07-29", {"stats.htm": STATS})])
        self.assertIsNone(pick(edgar, 1, Quarter.parse("2026Q2"))[0])
        self.assertIsNone(pick(FakeEdgar([]), 1, Quarter.parse("2026Q2"))[0])
        (maa,) = need(DOCS / "MAA/MAA_2026Q2_earnings.htm")
        # two investor-presentation filings, no earnings 8-K: ambiguous, defer
        two = FakeEdgar([("A1", "2026-07-29", {"a.htm": maa}), ("A2", "2026-08-05", {"b.htm": maa})],
                        items={"A1": "7.01,9.01", "A2": "7.01,9.01"})
        choice, why = pick(two, 1, Quarter.parse("2026Q2"))
        self.assertIsNone(choice)
        self.assertIn("2 other filings", why)

    def test_earnings_8k_beats_investor_presentation(self):
        """MAA's real pattern: Item 7.01 presentation 8-Ks around the earnings 8-K."""
        (maa,) = need(DOCS / "MAA/MAA_2026Q2_earnings.htm")
        edgar = FakeEdgar([("P1", "2026-06-02", {"presentation.htm": maa}),   # REITweek deck, before release
                           ("E1", "2026-07-29", {"maa-ex99_1.htm": maa, "maa-ex99_2.htm": STATS}),
                           ("P2", "2026-09-10", {"deck.htm": maa})],
                          items={"P1": "7.01,9.01", "E1": "2.02,9.01", "P2": "7.01,9.01"})
        choice, why = pick(edgar, 1, Quarter.parse("2026Q2"))
        self.assertIsNotNone(choice, why)
        self.assertEqual((choice["filing"]["accessionNumber"], choice["doc"]["name"]), ("E1", "maa-ex99_1.htm"))
        self.assertIn("earnings 8-K", why)

    def test_single_presentation_used_when_no_earnings_8k(self):
        (maa,) = need(DOCS / "MAA/MAA_2026Q2_earnings.htm")
        edgar = FakeEdgar([("P1", "2026-07-29", {"supp.htm": maa})], items={"P1": "7.01,9.01"})
        choice, why = pick(edgar, 1, Quarter.parse("2026Q2"))
        self.assertIsNotNone(choice, why)
        self.assertIn("7.01", why)


if __name__ == "__main__":
    unittest.main()
