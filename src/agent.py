"""Collection agent: Claude uses EDGAR tools to find, check and save the document
holding each quarter's FFO reconciliation.

Claude decides which filing and which exhibit to use; Python does every download,
every check and every file write, and records all of it in a manifest.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .edgar import EdgarClient, document_text, excerpts, reconciliation_signals
from .quarters import Quarter

MAX_TURNS = 40

SYSTEM_PROMPT = """You are a research assistant collecting REIT earnings documents from SEC EDGAR.

Goal: for each target quarter, save the ONE document that contains the company's full
reconciliation of net income to Funds From Operations (FFO) for that quarter, including the
company's own adjusted metric (Core FFO, CFFO, Normalized FFO, FFO as Adjusted, AFFO) if it reports one.

How to work:
1. Call list_earnings_filings for a quarter. Earnings 8-Ks (Item 2.02) are usually filed 3-10 weeks
   after quarter end. Ignore filings for other quarters (e.g. preliminary or guidance-only releases).
2. Call list_filing_documents and look at the exhibits. Exhibit 99.1 is usually the press release;
   some companies put a fuller supplemental package in Exhibit 99.2.
3. Call read_document on the candidates. Prefer the document whose reconciliation is the most
   complete (every line from net income to FFO and to the company's adjusted FFO). If both the
   release and the supplemental contain it, prefer the supplemental.
4. Confirm the document covers the target quarter (three months ended on the period end date).
5. Call save_document exactly once per quarter. If nothing suitable exists, call report_missing.

Rules: never guess. Base every decision on what the tools return. Be efficient: read only the
documents you need. When all target quarters are saved or reported missing, reply with a one-line summary."""

TOOLS = [
    {
        "name": "list_earnings_filings",
        "description": "List the company's 8-K filings with Item 2.02 (Results of Operations) filed in the normal window after a quarter ends.",
        "input_schema": {
            "type": "object",
            "properties": {"quarter": {"type": "string", "description": "Target quarter, e.g. 2026Q2"}},
            "required": ["quarter"],
        },
    },
    {
        "name": "list_filing_documents",
        "description": "List the documents (main 8-K and exhibits) inside one filing.",
        "input_schema": {
            "type": "object",
            "properties": {"accession": {"type": "string", "description": "Accession number, e.g. 0000912595-26-000045"}},
            "required": ["accession"],
        },
    },
    {
        "name": "read_document",
        "description": (
            "Read a document from a filing. Returns its length, automatic checks (mentions FFO, has "
            "reconciliation wording, mentions the target period end), the opening text, and excerpts around "
            "'funds from operations'. Optionally pass a regex in 'search' for more excerpts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "accession": {"type": "string"},
                "filename": {"type": "string"},
                "quarter": {"type": "string", "description": "Target quarter, used for the period-end check"},
                "search": {"type": "string", "description": "Optional regex to find more excerpts"},
            },
            "required": ["accession", "filename", "quarter"],
        },
    },
    {
        "name": "save_document",
        "description": "Save the chosen document as the source for a quarter. Call once per quarter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quarter": {"type": "string"},
                "accession": {"type": "string"},
                "filename": {"type": "string"},
                "reason": {"type": "string", "description": "One sentence: why this document is the right one"},
            },
            "required": ["quarter", "accession", "filename", "reason"],
        },
    },
    {
        "name": "report_missing",
        "description": "Record that no suitable document could be found for a quarter.",
        "input_schema": {
            "type": "object",
            "properties": {"quarter": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["quarter", "reason"],
        },
    },
]


@dataclass
class CollectionResult:
    ticker: str
    records: list[dict] = field(default_factory=list)
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    log: list[str] = field(default_factory=list)


class CollectionAgent:
    def __init__(self, client, model: str, edgar: EdgarClient, out_dir: Path):
        self.client = client          # an anthropic.Anthropic() instance (or a test double)
        self.model = model
        self.edgar = edgar
        self.out_dir = Path(out_dir)

    # ---------- public ----------
    def run(self, ticker: str, cik: int, quarters: list[Quarter]) -> CollectionResult:
        result = CollectionResult(ticker)
        state = {"ticker": ticker, "cik": cik, "targets": {str(q): q for q in quarters}, "done": {}}
        messages = [{
            "role": "user",
            "content": f"Company: {ticker} (CIK {cik}). Target quarters: {', '.join(str(q) for q in quarters)}.",
        }]

        for _ in range(MAX_TURNS):
            result.turns += 1
            resp = self.client.messages.create(
                model=self.model, max_tokens=2000, system=SYSTEM_PROMPT, tools=TOOLS, messages=messages
            )
            usage = getattr(resp, "usage", None)
            if usage is not None:
                result.input_tokens += getattr(usage, "input_tokens", 0) or 0
                result.output_tokens += getattr(usage, "output_tokens", 0) or 0

            assistant_content, tool_calls = [], []
            for block in resp.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                    if block.text.strip():
                        result.log.append(f"Claude: {block.text.strip()}")
                elif block.type == "tool_use":
                    assistant_content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
                    tool_calls.append(block)
            messages.append({"role": "assistant", "content": assistant_content})

            if resp.stop_reason != "tool_use" or not tool_calls:
                break

            tool_results = []
            for call in tool_calls:
                try:
                    output = self._dispatch(call.name, call.input, state)
                    is_error = False
                except Exception as exc:  # report tool errors back to Claude
                    output, is_error = {"error": f"{type(exc).__name__}: {exc}"}, True
                result.log.append(f"tool {call.name}({json.dumps(call.input)}) -> {'ERROR' if is_error else 'ok'}")
                tool_results.append({
                    "type": "tool_result", "tool_use_id": call.id,
                    "content": json.dumps(output, default=str)[:12000], "is_error": is_error,
                })
            messages.append({"role": "user", "content": tool_results})

            if set(state["done"]) >= set(state["targets"]):
                break

        # Anything Claude never resolved is recorded as missing.
        for qs in state["targets"]:
            if qs not in state["done"]:
                state["done"][qs] = self._record(state, qs, status="missing", reason="Agent stopped before resolving this quarter")
        result.records = [state["done"][qs] for qs in sorted(state["done"])]
        return result

    # ---------- tools ----------
    def _dispatch(self, name: str, args: dict, state: dict):
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            raise ValueError(f"Unknown tool {name}")
        return handler(args, state)

    def _quarter(self, state: dict, text: str) -> Quarter:
        q = Quarter.parse(text)
        if str(q) not in state["targets"]:
            raise ValueError(f"{q} is not a target quarter")
        return q

    def _tool_list_earnings_filings(self, args, state):
        q = self._quarter(state, args["quarter"])
        start, end = q.filing_window()
        rows = self.edgar.earnings_filings(state["cik"], start, end)
        return {
            "quarter": str(q), "period_end": q.period_end_text,
            "search_window": [start.isoformat(), end.isoformat()],
            "filings": [{"accession": r["accessionNumber"], "form": r["form"], "filed": r["filingDate"],
                         "items": r.get("items"), "primary_document": r.get("primaryDocument")} for r in rows],
        }

    def _tool_list_filing_documents(self, args, state):
        docs = self.edgar.filing_documents(state["cik"], args["accession"])
        return {"accession": args["accession"], "documents": [{"name": d["name"], "size": d["size"]} for d in docs]}

    def _load_text(self, state, accession, filename):
        raw = self.edgar.get_bytes(self.edgar.document_url(state["cik"], accession, filename))
        return raw, document_text(raw, filename)

    def _tool_read_document(self, args, state):
        q = self._quarter(state, args["quarter"])
        _, text = self._load_text(state, args["accession"], args["filename"])
        out = {
            "filename": args["filename"], "characters": len(text),
            "checks": reconciliation_signals(text, q.period_end_text),
            "opening": text[:1500],
            "ffo_excerpts": excerpts(text, r"reconciliation[^\n]{0,120}funds\s+from\s+operations|funds\s+from\s+operations", limit=3),
        }
        if args.get("search"):
            out["search_excerpts"] = excerpts(text, args["search"], limit=4)
        return out

    def _tool_save_document(self, args, state):
        q = self._quarter(state, args["quarter"])
        if str(q) in state["done"]:
            raise ValueError(f"{q} was already resolved")
        raw, text = self._load_text(state, args["accession"], args["filename"])
        checks = reconciliation_signals(text, q.period_end_text)
        ext = Path(args["filename"]).suffix.lower() or ".htm"
        dest = self.out_dir / state["ticker"] / f"{state['ticker']}_{q}_earnings{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        verified = checks["mentions_ffo"] and checks["has_reconciliation_words"] and checks["mentions_period_end"]
        state["done"][str(q)] = self._record(
            state, str(q), status="saved" if verified else "saved_unverified",
            accession=args["accession"], filename=args["filename"], path=str(dest), reason=args["reason"], checks=checks,
        )
        return {"saved_to": dest.name, "checks": checks, "verified": verified}

    def _tool_report_missing(self, args, state):
        q = self._quarter(state, args["quarter"])
        state["done"][str(q)] = self._record(state, str(q), status="missing", reason=args["reason"])
        return {"recorded": True}

    def _record(self, state, quarter, status, accession="", filename="", path="", reason="", checks=None):
        url = self.edgar.document_url(state["cik"], accession, filename) if accession and filename else ""
        return {
            "ticker": state["ticker"], "cik": state["cik"], "quarter": quarter, "status": status,
            "accession": accession, "filename": filename, "url": url, "path": path,
            "reason": reason, "checks": checks or {}, "collected_on": date.today().isoformat(),
        }
