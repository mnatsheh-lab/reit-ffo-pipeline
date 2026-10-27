# REIT FFO Comparability Pipeline

An AI pipeline that collects quarterly earnings documents for Sunbelt multifamily REITs from SEC EDGAR, extracts every line of each company's FFO reconciliation, and restates all companies to one common FFO definition so they can be compared fairly.

## The problem

Funds from operations (FFO) is the main earnings measure for REITs. NAREIT defines a standard FFO, but most REITs also report their own versions (Core FFO, CFFO, Core AFFO, AFFO), and each company adds back different items. Comparing these figures across peers means reading footnotes in quarterly PDF supplementals and rebuilding the numbers by hand in Excel.

## What the pipeline does

```
Collect  →  Extract  →  Restate  →  Explain and report
```

1. **Collect.** An AI agent uses the free EDGAR API to find each REIT's quarterly earnings filing and downloads the exhibit that contains the FFO reconciliation.
2. **Extract.** Claude reads each reconciliation and returns every adjustment line as structured data, with the source page.
3. **Restate.** Python applies one common definition to every company. All arithmetic runs in code, not in the AI, and extracted lines are checked against each company's reported totals.
4. **Explain and report.** Claude writes a plain-language note on how each REIT's definitions differ, and results are written to an Excel comparison workbook.

## Scope

| Ticker | Company | "Core" metric reported |
|---|---|---|
| MAA | Mid-America Apartment Communities | Core FFO, Core AFFO |
| CPT | Camden Property Trust | Core FFO, Core AFFO |
| IRT | Independence Realty Trust | CFFO |
| NXRT | NexPoint Residential Trust | Core FFO |
| BRT | BRT Apartments Corp. | None (FFO and AFFO only) |

Period: Q4 2025, Q1 2026 and Q2 2026 (15 company-quarters).

## Accuracy testing

The documents were also collected by hand, and each reconciliation is rebuilt manually in Excel (`data/answer_key/`). The pipeline is graded against this answer key on:

- **Collection:** did it fetch the correct filing and exhibit for every company-quarter?
- **Extraction:** do extracted figures match to $0.01 per share?

Errors are logged by type: wrong document, wrong number, misclassified adjustment, wrong page cited, missed item.

## Repository layout

```
src/               pipeline code (collect, extract, restate, report)
data/raw/          downloaded PDFs (not committed)
data/answer_key/   hand-built reconciliations used for testing
output/            comparison tables
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then add your API key and SEC user agent
```

## Status

- [x] Peer set and period defined
- [x] Documents collected by hand (answer key)
- [ ] MAA hand reconciliation (Q2 2026 done; Q4 2025 and Q1 2026 in progress)
- [ ] Common FFO definition
- [ ] Collection agent
- [ ] Extraction and restatement
- [ ] Accuracy testing

## Author

Mohammad Natsheh — Master of Real Estate Development, Clemson University
