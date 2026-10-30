# REIT FFO Comparability Pipeline

An AI pipeline that tracks every U.S. publicly traded multifamily REIT, collects each quarterly earnings filing from SEC EDGAR since 2018, extracts every line of each FFO reconciliation, and restates all companies to one common FFO definition, so they can be compared fairly across companies and over time. It updates itself daily.

> Helps REIT equity analysts and real estate investors make apples-to-apples valuation and peer-comparison decisions across all U.S. listed multifamily REITs, by using an AI agent that monitors SEC EDGAR daily to produce a continuously updated, restated FFO history with source-page citations.

## The problem

Funds from operations (FFO) is the main earnings measure for REITs. NAREIT defines a standard FFO, but most REITs also report their own versions (Core FFO, Normalized FFO, CFFO, FFO as Adjusted, AFFO), each company adds back different items, and companies change their own definitions over time. Comparing them means reading footnotes in quarterly filings and rebuilding the numbers by hand in Excel.

## What the pipeline does

```
Track universe → Collect → Extract → Restate → Explain and report
                     (runs daily on a schedule)
```

1. **Track the universe.** Finds every REIT (SIC 6798) with a ticker in the SEC company list; Claude classifies each against a written multifamily rule, citing its 10-K. Exits are detected from Form 25 (delisting) and Form 15 (deregistration). Former REITs stay in the history to avoid survivorship bias.
2. **Collect.** Uses the free EDGAR API to find each quarterly earnings filing and download the exhibit with the FFO reconciliation.
3. **Extract.** Claude returns every reconciliation line as structured data, with the source page.
4. **Restate.** Python applies one fixed common definition (today's) to every company-quarter, retroactively. All arithmetic runs in code, and extracted lines are checked against reported totals. Where an older filing combines or omits an item, the pipeline searches the 10-Q notes and otherwise flags the quarter as *restated with limits* instead of guessing.
5. **Explain and report.** Claude writes a plain-language note on how each REIT's reported metrics differ; results go to Excel and data files.

## Scope

- **Companies:** every U.S. exchange-listed multifamily REIT at any point since 2018.
- **Period:** Q1 2018 to the latest quarter, then each new quarter as it is filed.

Current universe (October 2026):

| Ticker | Company | Markets | "Core" metric |
|---|---|---|---|
| VMRK | Vivmark Residential (AvalonBay + Equity Residential, merged Aug. 2026) | Coastal | Core FFO / Normalized FFO before merger |
| ESS | Essex Property Trust | West Coast | Core FFO |
| UDR | UDR | Mixed | FFO as Adjusted |
| MAA | Mid-America Apartment Communities | Sunbelt | Core FFO, Core AFFO |
| CPT | Camden Property Trust | Sunbelt | Core FFO, Core AFFO |
| IRT | Independence Realty Trust | Sunbelt/Midwest | CFFO |
| NXRT | NexPoint Residential Trust | Sunbelt | Core FFO |
| BRT | BRT Apartments | Sunbelt | None (FFO and AFFO only) |
| CSR | Centerspace (being acquired by IRT) | Midwest/Mountain | Core FFO |
| CLPR | Clipper Realty | New York City | AFFO (subject to multifamily rule) |

Former REITs in the history include Veris Residential, Elme Communities, Aimco, AIR Communities, Preferred Apartment Communities and Bluerock Residential.

## Final product: FFO dashboard

A web dashboard, rebuilt after each daily pipeline run:

1. **REIT selector:** drop-down of every REIT in the universe (current and former), plus a quarter selector.
2. **Restated FFO:** the headline figure on this project's common definition, beside the company's own reported FFO and "core" metric.
3. **The formula:** the calculation written out step by step, with the REIT's actual numbers in each term:
   `FFO = Net income + RE depreciation − Gains on sale + JV depreciation + NCI`, then `Common FFO = FFO ± adjustments under the common definition`.
4. **Line-item references:** every term shows its amount, the line-item name exactly as printed in the filing, and its page, e.g. *"Legal costs, settlements and (recoveries), net" — $53,000K — page 10*, linked to the source filing on SEC EDGAR.
5. **Flags:** quarters restated with limits are marked, with the item that could not be separated.

The dashboard only displays stored pipeline records and does no calculation of its own, so every figure traces back to a page in a filing.

## Accuracy testing

An answer key was built by hand: 15 supplementals (MAA, CPT, IRT, NXRT, BRT for Q4 2025–Q2 2026), a full manual reconciliation of MAA (`data/answer_key/`), and spot checks of other REITs and pre-2020 quarters. The pipeline is graded on:

- **Collection:** correct filing and exhibit for every company-quarter.
- **Extraction:** figures match to $0.01 per share.

Errors are logged by type: wrong document, wrong number, misclassified adjustment, wrong page cited, missed item.

## Repository layout

```
src/               pipeline code (universe, collect, extract, restate, report)
data/raw/          downloaded filings (not committed)
data/answer_key/   hand-built reconciliations used for testing
output/            restated FFO tables
```

## Setup (Windows)

1. Install Python 3.11+.
2. Double-click `setup.bat`: installs the libraries and creates `.env`.
3. Paste your Claude API key into `.env` after `ANTHROPIC_API_KEY=`.

## Running

| Command | What it does |
|---|---|
| `run_check_universe.bat` | Free: checks every REIT's SEC ID against EDGAR before any paid run. |
| `run_pilot_MAA.bat` | Pilot: MAA from 2018 to today (~34 quarters), then rebuilds the dashboard. Asks before spending. |
| `run_all.bat` | Every REIT, every missing quarter since 2018. Asks before each paid step; safe to stop and restart. |
| `run_test_MAA.bat` | Collects one quarter (MAA Q2 2026). Use first to check everything works. |
| `run_collect.bat` | Collects all five answer-key REITs, Q4 2025 to Q2 2026. |
| `python -m src.collect --tickers MAA CPT --start 2025Q4 --end 2026Q2` | Custom run. |
| `run_extract.bat` | Extracts every saved reconciliation, applies the Conservative Core FFO definition, and checks MAA against the answer key. Results in `output/restated_ffo.csv` and `output/extractions/`. |
| `run_dashboard.bat` | Rebuilds `dashboard/index.html` from the latest results and opens it in your browser. |
| `run_verify.bat` | Re-checks saved documents and compares them with the hand-collected answer key. |
| `python -m unittest discover tests` | Offline tests (no API key or internet needed). |

Downloaded documents go to `data/raw/edgar/<TICKER>/`, and every decision is logged in `output/collection_manifest.csv` (filing, exhibit, EDGAR link, the agent's reason, and automatic checks).

## Status

- [x] Scope defined: all U.S. listed multifamily REITs, Q1 2018 to present
- [x] Answer-key documents collected
- [x] MAA hand reconciliation (Q4 2025, Q1 2026, Q2 2026; all checks tie to reported figures)
- [x] Common FFO definition (`docs/common_definition.md`)
- [x] Multifamily rule (`docs/multifamily_rule.md`)
- [x] Collection agent — 15/15 documents correct against the answer key ([results](docs/collection_test_results.md))
- [x] Extraction and restatement — 15/15 quarters tie; MAA 42/42 vs answer key ([results](docs/extraction_test_results.md))
- [ ] Accuracy testing
- [ ] Live universe tracking and daily updates
- [ ] Backfill to Q1 2018 — universe of 17 REITs / 466 company-quarters configured; resumable yearly batches; pilot pending
- [x] FFO dashboard demo (`dashboard/index.html`, built by `python -m src.build_dashboard`)

## Author

Mohammad Natsheh — Master of Real Estate Development, Clemson University
