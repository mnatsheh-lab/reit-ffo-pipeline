"""Free, rule-based document picker. Tried before the (paid) collection agent.

For a quarter it scores every exhibit of the earnings 8-Ks filed in the normal window and accepts
the best one only when the choice is clear; otherwise it returns None and the agent decides.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .edgar import EdgarClient, document_text, reconciliation_signals
from .pages import capex_score, reconciliation_score, shares_score, split_pages
from .quarters import Quarter

MIN_RECON_SCORE = 25     # the true reconciliation page scored 27-43 in all 15 answer-key quarters


def score_document(raw: bytes, name: str, q: Quarter) -> dict:
    text = document_text(raw, name)
    low = text.lower()
    checks = reconciliation_signals(text, q.period_end_text)
    pages = split_pages(raw, name)
    nxt = q.next().period_end_text.lower()
    return {
        "checks": checks,
        "verified": checks["mentions_ffo"] and checks["has_reconciliation_words"] and checks["mentions_period_end"],
        # a later quarter's release also mentions this quarter's date in comparisons; reject it
        "right_period": low.count(q.period_end_text.lower()) >= low.count(nxt),
        "recon": max((reconciliation_score(p.text) for p in pages), default=0),
        "extras": max((shares_score(p.text) for p in pages), default=0) + max((capex_score(p.text) for p in pages), default=0),
        "size": len(text),
    }


def pick(edgar: EdgarClient, cik: int, q: Quarter) -> tuple[dict | None, str]:
    """Return (choice, explanation). choice is None when the agent should decide."""
    start, end = q.filing_window()
    filings = edgar.earnings_filings(cik, start, end)
    if not filings:
        return None, "no earnings 8-K in the filing window"
    cands = []
    for f in filings:
        for doc in edgar.filing_documents(cik, f["accessionNumber"]):
            if doc["size"] and doc["size"] < 5_000:
                continue
            raw = edgar.get_bytes(doc["url"])
            sc = score_document(raw, doc["name"], q)
            if sc["verified"] and sc["right_period"] and sc["recon"] >= MIN_RECON_SCORE:
                cands.append({"filing": f, "doc": doc, "raw": raw, **sc})
    if not cands:
        return None, "no exhibit passed the checks"
    filings_with_cands = {c["filing"]["accessionNumber"] for c in cands}
    if len(filings_with_cands) > 1:
        # e.g. an amended 8-K or a separate supplemental filing: let the agent judge
        return None, f"{len(filings_with_cands)} filings contain a reconciliation"
    # Prefer the most complete document: reconciliation page strength, then share-count and
    # capex pages (supplementals have them; press releases often don't), then length.
    cands.sort(key=lambda c: (round(c["recon"]), c["extras"], c["size"]), reverse=True)
    best = cands[0]
    return best, f"rules: best of {len(cands)} qualifying exhibit(s) (reconciliation score {best['recon']:.0f})"


def save(choice: dict, ticker: str, cik: int, q: Quarter, out_dir: Path, edgar: EdgarClient, reason: str) -> dict:
    ext = Path(choice["doc"]["name"]).suffix.lower() or ".htm"
    dest = Path(out_dir) / ticker / f"{ticker}_{q}_earnings{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(choice["raw"])
    acc = choice["filing"]["accessionNumber"]
    return {
        "ticker": ticker, "cik": cik, "quarter": str(q), "status": "saved", "method": "rules",
        "accession": acc, "filename": choice["doc"]["name"], "url": edgar.document_url(cik, acc, choice["doc"]["name"]),
        "path": str(dest), "reason": reason, "checks": choice["checks"], "collected_on": date.today().isoformat(),
    }
