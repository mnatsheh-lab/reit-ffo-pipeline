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


def _qualifying(edgar, cik, filing, q):
    out = []
    for doc in edgar.filing_documents(cik, filing["accessionNumber"]):
        if doc["size"] and doc["size"] < 5_000:
            continue
        raw = edgar.get_bytes(doc["url"])
        sc = score_document(raw, doc["name"], q)
        if sc["verified"] and sc["right_period"] and sc["recon"] >= MIN_RECON_SCORE:
            out.append({"filing": filing, "doc": doc, "raw": raw, **sc})
    return out


def pick(edgar: EdgarClient, cik: int, q: Quarter) -> tuple[dict | None, str]:
    """Return (choice, explanation). choice is None when the agent should decide.

    Earnings filings (Item 2.02) are checked first, earliest first; the first one with a qualifying
    exhibit wins. Investor-presentation filings (Item 7.01 only) often repeat the reconciliation, so
    they are used only when no earnings filing qualifies, and then only if exactly one does.
    """
    start, end = q.filing_window()
    filings = sorted(edgar.earnings_filings(cik, start, end), key=lambda f: f["filingDate"])
    if not filings:
        return None, "no earnings 8-K in the filing window"
    earnings = [f for f in filings if "2.02" in (f.get("items") or "")]
    others = [f for f in filings if f not in earnings]
    cands, source = [], ""
    for f in earnings:
        cands = _qualifying(edgar, cik, f, q)
        if cands:
            source = "earnings 8-K"
            break
    if not cands:
        found = [(f, _qualifying(edgar, cik, f, q)) for f in others]
        found = [(f, c) for f, c in found if c]
        if len(found) > 1:
            return None, f"no earnings 8-K qualifies and {len(found)} other filings contain a reconciliation"
        if found:
            cands, source = found[0][1], "Item 7.01 8-K"
    if not cands:
        return None, "no exhibit passed the checks"
    # Prefer the most complete document: reconciliation page strength, then share-count and
    # capex pages (supplementals have them; press releases often don't), then length.
    cands.sort(key=lambda c: (round(c["recon"]), c["extras"], c["size"]), reverse=True)
    best = cands[0]
    return best, (f"rules: {source} filed {best['filing']['filingDate']}, best of {len(cands)} qualifying "
                  f"exhibit(s) (reconciliation score {best['recon']:.0f})")


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
