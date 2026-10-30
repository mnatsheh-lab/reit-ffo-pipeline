"""Project settings: paths, API settings and the REITs to collect."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
EDGAR_DIR = DATA_DIR / "raw" / "edgar"      # documents downloaded by the agent
CACHE_DIR = DATA_DIR / "raw" / "_cache"     # raw EDGAR responses, to avoid re-downloading
OUTPUT_DIR = ROOT / "output"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "").strip().strip('"')
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
EXTRACT_MODEL = os.getenv("CLAUDE_EXTRACT_MODEL", MODEL)               # stage 2 / fallback
EXTRACT_FAST_MODEL = os.getenv("CLAUDE_FAST_MODEL", "claude-haiku-5-5")  # stage 1 ("none" to skip)

# The universe: every U.S.-listed multifamily REIT (75% rule, docs/multifamily_rule.md) since 2022 (post-pandemic).
# CIKs are verified against EDGAR with `python -m src.universe` before any paid run.
# start/end bound the quarters collected (inclusive); None = open. Notes explain each boundary.
REITS: dict[str, dict] = {
    # Current constituents (FTSE Nareit Apartments, Aug 2026)
    "MAA":  {"cik": 912595,  "name": "Mid-America Apartment Communities"},
    "CPT":  {"cik": 906345,  "name": "Camden Property Trust"},
    "IRT":  {"cik": 1466085, "name": "Independence Realty Trust"},
    "NXRT": {"cik": 1620393, "name": "NexPoint Residential Trust"},
    "BRT":  {"cik": 14846,   "name": "BRT Apartments Corp."},
    "ESS":  {"cik": 920522,  "name": "Essex Property Trust"},
    "UDR":  {"cik": 74208,   "name": "UDR, Inc."},
    "CSR":  {"cik": 798359,  "name": "Centerspace", "note": "Investors Real Estate Trust until 2020; being acquired by IRT"},
    "CLPR": {"cik": 1649096, "name": "Clipper Realty"},
    # Merged into Vivmark Residential (VMRK) on Aug 17, 2026; history kept as two companies.
    "AVB":  {"cik": 915912,  "name": "AvalonBay Communities", "end": "2026Q2"},
    "EQR":  {"cik": 906107,  "name": "Equity Residential", "end": "2026Q2"},
    # EQR was the legal survivor: its CIK is now registered as Vivmark Residential (VMRK).
    "VMRK": {"cik": 906107,  "name": "Vivmark Residential", "start": "2026Q3", "note": "AvalonBay + Equity Residential, merged Aug 17, 2026"},
    # Former REITs (kept to avoid survivorship bias). Boundaries are provisional until the
    # Phase 8 classifier checks the 75% rule year by year.
    "AIV":  {"cik": 922864,  "name": "Apartment Investment and Management (Aimco)", "end": "2020Q3", "note": "Pre-split Aimco; the post-2020 development company is excluded pending review"},
    "AIRC": {"cik": 1820877, "name": "Apartment Income REIT (AIR Communities)", "start": "2020Q4", "end": "2024Q1", "note": "Spun off from Aimco Dec 2020; taken private 2024"},
    "APTS": {"cik": 1481832, "name": "Preferred Apartment Communities", "end": "2022Q1", "note": "Acquired 2022"},
    "BRG":  {"cik": 1442626, "name": "Bluerock Residential Growth REIT", "end": "2022Q2", "note": "Acquired 2022"},
    "ELME": {"cik": 104894,  "name": "Elme Communities", "start": "2021Q3", "end": "2025Q2", "note": "WashREIT until 2022; multifamily after office/retail sales; liquidated 2025-26"},
    "VRE":  {"cik": 924901,  "name": "Veris Residential", "start": "2022Q1", "end": "2025Q4", "note": "Mack-Cali until 2021; multifamily after office exits; taken private 2026"},
}
FIRST_QUARTER = "2022Q1"


def check_settings() -> list[str]:
    """Return a list of problems with the local setup (empty if all good)."""
    problems = []
    if not ANTHROPIC_API_KEY:
        problems.append("ANTHROPIC_API_KEY is missing from .env")
    if not SEC_USER_AGENT or "@" not in SEC_USER_AGENT:
        problems.append('SEC_USER_AGENT in .env must be "Your Name your@email.com"')
    return problems
