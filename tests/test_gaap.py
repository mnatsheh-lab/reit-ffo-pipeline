"""GAAP quarter derivation from XBRL company facts (no network).

The EPS facts below are MAA's real XBRL facts for 2025 (data.sec.gov companyconcept,
EarningsPerShareDiluted); the rest are made up to exercise the fallbacks.
"""
import unittest

from src.gaap import metrics_for
from src.quarters import Quarter, quarter_range


def fact(start, end, val, form="10-Q", filed="2025-01-01", accn="x"):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed, "accn": accn}


def inst(end, val, form="10-Q", filed="2025-01-01"):
    return {"end": end, "val": val, "form": form, "filed": filed, "accn": "y"}


FACTS = {"entityName": "MID AMERICA APARTMENT COMMUNITIES INC.", "facts": {"us-gaap": {
    "EarningsPerShareDiluted": {"units": {"USD/shares": [
        fact("2025-01-01", "2025-03-31", 1.54, filed="2025-04-30"),
        fact("2025-01-01", "2025-06-30", 2.46, filed="2025-07-31"),
        fact("2025-04-01", "2025-06-30", 0.92, filed="2025-07-31"),
        fact("2025-01-01", "2025-09-30", 3.30, filed="2025-10-30"),
        fact("2025-07-01", "2025-09-30", 0.84, filed="2025-10-30"),
        fact("2025-01-01", "2025-12-31", 3.78, form="10-K", filed="2026-02-06"),
        fact("2026-01-01", "2026-03-31", 1.06, filed="2026-04-30"),
        fact("2025-01-01", "2025-03-31", 9.99, form="8-K", filed="2026-05-01"),   # not a 10-Q/10-K: ignored
    ]}},
    # revenue: only year-to-date in Q2 (forces derivation), plus a later restatement of Q1
    "Revenues": {"units": {"USD": [
        fact("2025-01-01", "2025-03-31", 100.0, filed="2025-04-30"),
        fact("2025-01-01", "2025-03-31", 101.0, filed="2026-04-30"),   # restated in a later filing: wins
        fact("2025-01-01", "2025-06-30", 210.0, filed="2025-07-31"),
    ]}},
    # Q3 only under a second concept: fills the gap without replacing the main concept
    "OperatingLeaseLeaseIncome": {"units": {"USD": [fact("2025-07-01", "2025-09-30", 95.0)]}},
    "SecuredDebt": {"units": {"USD": [inst("2025-03-31", 40.0), inst("2025-06-30", 41.0)]}},
    "UnsecuredDebt": {"units": {"USD": [inst("2025-03-31", 60.0)]}},
    "Assets": {"units": {"USD": [inst("2025-03-31", 500.0), inst("2024-12-31", 480.0, form="10-K")]}},
}}}

Q = quarter_range("2025Q1", "2026Q1")
M = metrics_for(FACTS, Q)


class GaapQuarters(unittest.TestCase):
    def test_three_month_fact_used_directly(self):
        assert M["2025Q2"]["eps_diluted"]["value"] == 0.92 and not M["2025Q2"]["eps_diluted"]["derived"]
        assert M["2026Q1"]["eps_diluted"]["value"] == 1.06


    def test_q4_is_full_year_minus_nine_months(self):
        v = M["2025Q4"]["eps_diluted"]
        assert round(v["value"], 2) == 0.48 and v["derived"] and v["approx"] and v["form"] == "10-K"


    def test_non_periodic_forms_ignored(self):
        assert M["2025Q1"]["eps_diluted"]["value"] == 1.54


    def test_latest_filing_wins_and_ytd_derivation(self):
        assert M["2025Q1"]["revenue"]["value"] == 101.0
        assert M["2025Q2"]["revenue"]["value"] == 109.0 and M["2025Q2"]["revenue"]["derived"]
        assert "approx" not in M["2025Q2"]["revenue"]          # dollar amounts subtract exactly


    def test_fallback_concept_fills_gaps_only(self):
        assert M["2025Q1"]["revenue"]["concept"] == "Revenues"
        assert M["2025Q3"]["revenue"] == {**M["2025Q3"]["revenue"], "value": 95.0, "concept": "OperatingLeaseLeaseIncome"}


    def test_instants_and_summed_concepts(self):
        assert M["2025Q1"]["total_debt"]["value"] == 100.0 and M["2025Q1"]["total_debt"]["concept"] == "SecuredDebt+UnsecuredDebt"
        assert M["2025Q2"]["total_debt"]["value"] == 41.0 and M["2025Q2"]["total_debt"]["concept"] == "SecuredDebt"
        assert M["2025Q1"]["total_assets"]["value"] == 500.0
        assert "total_assets" not in M["2025Q2"]


    def test_missing_metrics_are_absent_not_zero(self):
        assert "dividends_ps" not in M["2025Q1"] and "interest_expense" not in M["2025Q1"]
