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

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then add your API key and SEC user agent
```

## Status

- [x] Scope defined: all U.S. listed multifamily REITs, Q1 2018 to present
- [x] Answer-key documents collected
- [x] MAA hand reconciliation (Q4 2025, Q1 2026, Q2 2026; all checks tie to reported figures)
- [ ] Common FFO definition and multifamily rule
- [ ] Collection agent (fixed list, current quarters)
- [ ] Extraction and restatement
- [ ] Accuracy testing
- [ ] Live universe tracking and daily updates
- [ ] Backfill to Q1 2018

## Author

Mohammad Natsheh — Master of Real Estate Development, Clemson University
