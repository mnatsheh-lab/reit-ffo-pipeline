"""Split filing documents into pages and find the pages holding the FFO reconciliation."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

PAGE_BREAK = re.compile(r"<[^>]+page-break-(?:before|after)\s*:\s*always[^>]*>", re.I)
NUM = re.compile(r"\(?\d{1,3}(?:,\d{3})+\)?")


@dataclass
class Page:
    seq: int            # position in the document (1 = first page)
    printed: str        # page number printed on the page, if any (e.g. "10")
    text: str


def _html_text(fragment: str) -> str:
    soup = BeautifulSoup(fragment, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tr in soup.find_all("tr"):
        tr.append("\n")
    for td in soup.find_all(["td", "th"]):
        td.append(" | ")
    text = soup.get_text(" ")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"( ?\| ?)+", " | ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _printed_number(text: str) -> str:
    tail = re.sub(r"[\s|]+$", "", text)[-80:]
    m = re.search(r"(?:page\s+)?(\d{1,3})$", tail, re.I)
    return m.group(1) if m else ""


def split_pages(raw: bytes, name: str) -> list[Page]:
    if name.lower().endswith(".pdf"):
        import pdfplumber

        pages = []
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for i, p in enumerate(pdf.pages, 1):
                t = p.extract_text() or ""
                pages.append(Page(i, _printed_number(t), t))
        return pages
    html = raw.decode("utf-8", errors="ignore")
    parts = PAGE_BREAK.split(html)
    pages = []
    for frag in parts:
        t = _html_text(frag)
        if t:
            pages.append(Page(len(pages) + 1, _printed_number(t), t))
    return pages


def reconciliation_score(text: str) -> float:
    """Higher = more likely to be a page of the net income -> FFO reconciliation."""
    low = text.lower()
    nums = len(NUM.findall(text))
    if nums < 10:
        return 0.0
    score = 0.0
    score += 4 * bool(re.search(r"reconciliation", low))
    score += 3 * min(len(re.findall(r"funds from operations|\bffo\b|\bcffo\b|\baffo\b", low)), 6)
    score += 4 * bool(re.search(r"depreciation", low))
    score += 4 * bool(re.search(r"net (\(loss\) )?income|net loss", low))
    score += 3 * bool(re.search(r"gain[s]? on (the )?sale|sale of (depreciable )?real estate", low))
    score += 3 * bool(re.search(r"noncontrolling|non-controlling", low))
    score += 2 * bool(re.search(r"core ffo|cffo|normalized ffo|ffo as adjusted|adjusted ffo|affo", low))
    score += 2 * bool(re.search(r"weighted average", low))
    score += min(nums, 120) / 20
    # Guidance pages reconcile projected figures; penalize them.
    score -= 8 * bool(re.search(r"guidance|outlook|forecast|projected|estimated", low))
    return score


def candidate_pages(pages: list[Page], top: int = 4) -> list[Page]:
    """Best-scoring pages plus the page after each (reconciliations often span two pages)."""
    ranked = sorted(pages, key=lambda p: reconciliation_score(p.text), reverse=True)
    chosen = {p.seq for p in ranked[:top] if reconciliation_score(p.text) > 0}
    for seq in list(chosen):
        if seq + 1 <= len(pages) and reconciliation_score(pages[seq].text) > 10:
            chosen.add(seq + 1)
    return [p for p in pages if p.seq in chosen]
