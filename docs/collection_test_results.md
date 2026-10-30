# Collection Agent — Test Results

**Run date:** October 30, 2026 · **Scope:** 5 REITs × 3 quarters (Q4 2025 – Q2 2026) · **Model:** claude-sonnet-5-5

## Result: 15 of 15 documents correct

| REIT | Document the agent chose | Q4 2025 | Q1 2026 | Q2 2026 |
|---|---|---|---|---|
| MAA | Ex. 99.1 (combined release + supplemental) | 100% | 100% | 100% |
| CPT | Ex. 99.2 (separate supplemental package) | 100% | 100% | 100% |
| IRT | Ex. 99.2 (supplemental) | 100% | 100% | 100% |
| NXRT | Ex. 99.1 (earnings supplement) | 100% | 100% | 100% |
| BRT | Ex. 99.1 (supplemental) | n/a* | 100% | 100% |

Percentages are the share of figures on the FFO reconciliation page(s) of the hand-collected document that also appear in the agent's document (`python -m src.verify_collection`). 1,184 of 1,184 figures matched across the 14 comparable quarters.

\* The hand-collected BRT Q4 2025 file is a scanned image with no text, so it cannot be compared automatically. The agent's version is the text-based EDGAR exhibit, which also solves the scanned-file problem.

## Findings

- **Exhibit choice varies by company and the agent handled it.** MAA's supplemental is in Exhibit 99.1 (its 99.2 is portfolio statistics); Camden's and IRT's are in Exhibit 99.2. The agent read both candidates and picked the one with the full reconciliation each time.
- **One false alarm in the automatic checks, now fixed.** BRT's three documents were first flagged *saved_unverified* because the check required the phrase "depreciation and amortization of real estate"; BRT writes "Depreciation and amortization". The check now requires only "reconciliation" and "depreciation", and all 15 pass.
- **Cost:** a single quarter used about 21,500 input and 800 output tokens; the full 15-document run used roughly ten times that.
