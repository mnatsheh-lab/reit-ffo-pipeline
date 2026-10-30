"""Small, polite client for SEC EDGAR.

SEC fair-access rules: identify yourself with a User-Agent containing a name and email,
and stay under 10 requests per second.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"


class EdgarClient:
    def __init__(self, user_agent: str, cache_dir: Path, min_interval: float = 0.15):
        if not user_agent:
            raise ValueError("A SEC user agent (name and email) is required")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self._last = 0.0

    # ---------- low-level ----------
    def _get(self, url: str) -> bytes:
        key = hashlib.sha1(url.encode()).hexdigest()
        cached = self.cache_dir / key
        if cached.exists():
            return cached.read_bytes()
        for attempt in range(5):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            resp = self.session.get(url, timeout=60)
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            cached.write_bytes(resp.content)
            return resp.content
        raise RuntimeError(f"EDGAR kept refusing {url}")

    def get_json(self, url: str) -> dict:
        return json.loads(self._get(url))

    def get_bytes(self, url: str) -> bytes:
        return self._get(url)

    # ---------- filings ----------
    def filings(self, cik: int) -> list[dict]:
        """All filings for a company, newest first, as dicts."""
        data = self.get_json(SUBMISSIONS_URL.format(cik=cik))
        rows = _rows(data["filings"]["recent"])
        for page in data["filings"].get("files", []):
            rows += _rows(self.get_json(SUBMISSIONS_PAGE_URL.format(name=page["name"])))
        return rows

    def earnings_filings(self, cik: int, start: date, end: date) -> list[dict]:
        """8-K filings with Item 2.02 (Results of Operations) or 7.01 filed between start and end."""
        out = []
        for f in self.filings(cik):
            if f["form"] not in ("8-K", "8-K/A"):
                continue
            items = f.get("items") or ""
            # Item 2.02 = results of operations. Some REITs file the supplemental separately
            # under Item 7.01 (Regulation FD), so include those too.
            if "2.02" not in items and "7.01" not in items:
                continue
            filed = date.fromisoformat(f["filingDate"])
            if start <= filed <= end:
                out.append(f)
        return sorted(out, key=lambda f: f["filingDate"])

    def filing_documents(self, cik: int, accession: str) -> list[dict]:
        """Files inside one filing (name, size)."""
        base = ARCHIVE_URL.format(cik=cik, acc=accession.replace("-", ""))
        index = self.get_json(base + "index.json")
        docs = []
        for item in index["directory"]["item"]:
            name = item["name"]
            if name.lower().endswith((".htm", ".html", ".pdf", ".txt")) and "index" not in name.lower():
                docs.append({"name": name, "size": int(item.get("size") or 0), "url": base + name})
        return docs

    def document_url(self, cik: int, accession: str, name: str) -> str:
        return ARCHIVE_URL.format(cik=cik, acc=accession.replace("-", "")) + name


def _rows(block: dict) -> list[dict]:
    keys = list(block.keys())
    n = len(block[keys[0]]) if keys else 0
    return [{k: block[k][i] for k in keys} for i in range(n)]


# ---------- text extraction ----------
def document_text(raw: bytes, name: str) -> str:
    """Plain text from an HTML or PDF document. PDF pages are marked '[[PAGE n]]'."""
    if name.lower().endswith(".pdf"):
        import pdfplumber

        parts = []
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                parts.append(f"[[PAGE {i}]]\n{page.extract_text() or ''}")
        return "\n".join(parts)
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    # Keep table rows on their own lines so reconciliations stay readable.
    for tr in soup.find_all("tr"):
        tr.append("\n")
    for td in soup.find_all(["td", "th"]):
        td.append(" | ")
    text = soup.get_text(" ")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"( \| )+", " | ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


FFO_PATTERNS = [r"funds\s+from\s+operations", r"\bFFO\b"]
# Companies word the depreciation line differently ("Depreciation and amortization of real estate
# assets", "Real estate depreciation", or just "Depreciation and amortization" at BRT), so only
# require the word "depreciation" alongside "reconciliation".
RECON_PATTERNS = [r"reconciliation", r"depreciation"]


def reconciliation_signals(text: str, period_end_text: str) -> dict:
    """Cheap checks that a document holds an FFO reconciliation for the right period."""
    low = text.lower()
    return {
        "mentions_ffo": any(re.search(p, text, re.I) for p in FFO_PATTERNS),
        "has_reconciliation_words": all(re.search(p, low) for p in RECON_PATTERNS),
        "mentions_period_end": period_end_text.lower() in low,
        "ffo_mentions": len(re.findall(FFO_PATTERNS[0], low)),
    }


def excerpts(text: str, pattern: str, width: int = 600, limit: int = 4) -> list[str]:
    """Short windows of text around matches of a regex."""
    out = []
    for m in re.finditer(pattern, text, re.I):
        lo, hi = max(0, m.start() - width // 3), min(len(text), m.end() + width)
        out.append(text[lo:hi])
        if len(out) >= limit:
            break
    return out
