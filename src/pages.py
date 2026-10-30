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


def compress(text: str) -> str:
    """Remove the empty-cell filler HTML tables leave behind ('| | | |'); keeps every number and word."""
    t = re.sub(r"\$\s*\|\s*", "$", text)          # "$ | 1,234"  -> "$1,234"
    t = re.sub(r"\s*\|\s*%", "%", t)               # "12.3 | %"   -> "12.3%"
    t = re.sub(r"\s*\|\s*\)", ")", t)             # "(1,234 | )" -> "(1,234)"
    t = re.sub(r"(\s*\|\s*)+", " | ", t)           # runs of empty cells -> one separator
    t = re.sub(r"^\s*\|\s*", "", t, flags=re.M)
    t = re.sub(r"\s*\|\s*$", "", t, flags=re.M)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


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
        t = compress(_html_text(frag))
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


GUIDANCE = re.compile(r"guidance|outlook|full year 20\d\d estimate", re.I)


def shares_score(text: str) -> float:
    low = text.lower()
    score = 0.0
    if re.search(r"(diluted )?shares (and units )?outstanding for (ffo|funds from operations)", low):
        score += 6
    if re.search(r"weighted average[^\n]{0,80}(diluted|op units|units)", low):
        score += 2
    if re.search(r"\bffo\b|funds from operations", low):
        score += 1
    return score - 4 * bool(GUIDANCE.search(low)) if score else 0.0


def capex_score(text: str) -> float:
    low = text.lower()
    score = 0.0
    if re.search(r"recurring capital expenditure|recurring capex|maintenance capital", low):
        score += 5
    if re.search(r"historical capital expenditures|capital expenditures summary", low):
        score += 4
    if re.search(r"capital expenditure", low):
        score += 1
    return score - 4 * bool(GUIDANCE.search(low)) if score else 0.0


def candidate_pages(pages: list[Page], small: bool = False) -> list[Page]:
    """Best-scoring reconciliation pages plus the page after each (reconciliations often span
    two pages), plus the best pages for the FFO share count and for recurring capex.

    small=True sends the 2 best reconciliation pages and 1 page each for shares and capex: it covered
    every page actually used in the 15 answer-key quarters at about a quarter of the text."""
    top, extra = (2, 1) if small else (4, 2)
    ranked = sorted(pages, key=lambda p: reconciliation_score(p.text), reverse=True)
    chosen = {p.seq for p in ranked[:top] if reconciliation_score(p.text) > 0}
    for seq in list(chosen):
        if seq + 1 <= len(pages) and reconciliation_score(pages[seq].text) > 10:
            chosen.add(seq + 1)
    for scorer in (shares_score, capex_score):
        best = sorted((p for p in pages if scorer(p.text) > 0), key=lambda p: scorer(p.text), reverse=True)[:extra]
        chosen |= {p.seq for p in best}
    return [p for p in pages if p.seq in chosen]
