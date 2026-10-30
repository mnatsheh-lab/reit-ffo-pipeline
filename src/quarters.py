"""Helpers for fiscal quarters (all five answer-key REITs use calendar quarters)."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, order=True)
class Quarter:
    year: int
    q: int

    @classmethod
    def parse(cls, text: str) -> "Quarter":
        """Parse '2026Q2' or '2026-Q2'."""
        t = text.upper().replace("-", "")
        year, q = t.split("Q")
        quarter = cls(int(year), int(q))
        if quarter.q not in (1, 2, 3, 4):
            raise ValueError(f"Bad quarter: {text}")
        return quarter

    def __str__(self) -> str:
        return f"{self.year}Q{self.q}"

    @property
    def period_end(self) -> date:
        month = self.q * 3
        return date(self.year, month, calendar.monthrange(self.year, month)[1])

    @property
    def period_end_text(self) -> str:
        """e.g. 'June 30, 2026' - the phrase earnings documents use."""
        d = self.period_end
        return f"{calendar.month_name[d.month]} {d.day}, {d.year}"

    def next(self) -> "Quarter":
        return Quarter(self.year + (self.q == 4), 1 if self.q == 4 else self.q + 1)

    def filing_window(self) -> tuple[date, date]:
        """Dates within which the earnings release for this quarter is normally filed.

        Releases come out 3-10 weeks after quarter end (later for some small REITs),
        so search from the day after quarter end through about 120 days.
        """
        start = self.period_end + timedelta(days=1)
        return start, start + timedelta(days=120)


def quarter_range(start: str, end: str) -> list[Quarter]:
    first, last = Quarter.parse(start), Quarter.parse(end)
    if first > last:
        raise ValueError("start quarter is after end quarter")
    out, cur = [], first
    while cur <= last:
        out.append(cur)
        cur = cur.next()
    return out
