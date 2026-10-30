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

# SEC Central Index Keys. The universe step (Phase 8) will build this list automatically;
# for now it holds the five answer-key REITs.
REITS: dict[str, dict] = {
    "MAA": {"cik": 912595, "name": "Mid-America Apartment Communities"},
    "CPT": {"cik": 906345, "name": "Camden Property Trust"},
    "IRT": {"cik": 1466085, "name": "Independence Realty Trust"},
    "NXRT": {"cik": 1620393, "name": "NexPoint Residential Trust"},
    "BRT": {"cik": 14846, "name": "BRT Apartments Corp."},
}


def check_settings() -> list[str]:
    """Return a list of problems with the local setup (empty if all good)."""
    problems = []
    if not ANTHROPIC_API_KEY:
        problems.append("ANTHROPIC_API_KEY is missing from .env")
    if not SEC_USER_AGENT or "@" not in SEC_USER_AGENT:
        problems.append('SEC_USER_AGENT in .env must be "Your Name your@email.com"')
    return problems
