# Extraction & Restatement — Test Results

**Run date:** October 30, 2026 (extraction v2) · **Scope:** 5 REITs × 3 quarters · **Model:** claude-sonnet-5-5 · **Tokens:** 283,269 in / 20,600 out

## Accuracy

- **MAA vs hand-built answer key:** 42 / 42 figures match (net income, FFO, Core FFO, Core AFFO, share count and 9 adjustment categories, for each of 3 quarters).
- **Arithmetic ties:** 15 / 15 company-quarters. For every quarter, the extracted lines add up to the company's reported FFO, adjusted FFO and AFFO totals, and reproduce the reported per-share figures.
- **First run (v1)** tied 13 / 15: BRT Q4 2025 and Q1 2026 failed the per-share check because BRT prints its FFO share count on a separate page. v2 sends that page to Claude; both now tie.
- **Recurring capex from capex tables** (used where the company's own AFFO does not deduct capex) was checked against the source documents for NXRT, BRT and IRT.

## Results (per diluted share)

| REIT | Quarter | NAREIT FFO | Company core | **Conservative Core FFO** | Company AFFO | **Conservative AFFO** |
|---|---|---|---|---|---|---|
| MAA | Q4 2025 | 1.79 | 2.23 | **1.79** | 1.91 | **1.47** |
| MAA | Q1 2026 | 2.23 | 2.13 | **2.09** | 1.98 | **1.94** |
| MAA | Q2 2026 | 2.10 | 2.08 | **2.08** | 1.77 | **1.77** |
| CPT | Q4 2025 | 1.73 | 1.76 | **1.73** | 1.46 | **1.43** |
| CPT | Q1 2026 | 1.15 | 1.70 | **1.20** | 1.55 | **1.05** |
| CPT | Q2 2026 | 1.68 | 1.68 | **1.64** | 1.39 | **1.35** |
| IRT | Q4 2025 | 0.33 | 0.32 (CFFO) | **0.32** | – | **0.29** |
| IRT | Q1 2026 | 0.27 | 0.26 | **0.26** | – | **0.23** |
| IRT | Q2 2026 | 0.28 | 0.28 | **0.27** | – | **0.22** |
| NXRT | Q4 2025 | 0.52 | 0.65 | **0.52** | 0.75 | **0.37** |
| NXRT | Q1 2026 | 0.69 | 0.68 | **0.61** | 0.77 | **0.48** |
| NXRT | Q2 2026 | 0.60 | 0.66 | **0.59** | 0.77 | **0.41** |
| BRT | Q4 2025 | 0.26 | – | **0.26** | 0.34 | **n/a*** |
| BRT | Q1 2026 | 0.33 | – | **0.33** | 0.39 | **0.24** |
| BRT | Q2 2026 | 0.29 | – | **0.29** | 0.36 | **0.20** |

\* BRT discloses recurring capex for Q4 2025 only on a full-year basis, so Conservative AFFO is not computed for that quarter rather than estimated.

## Low-cost configuration (Oct 30, 2026)

The same 15 quarters were re-extracted with the low-cost setup (Claude Haiku 5.5 on a small page set, Sonnet only as fallback):

- **15 / 15** handled by Haiku alone; the Sonnet fallback was never needed.
- **15 / 15** tie to reported totals; **MAA 42 / 42** vs the answer key.
- **Every per-share result identical** to the Sonnet run above (NAREIT FFO, Conservative Core FFO, Conservative AFFO).
- **Tokens:** 134,270 in / 43,514 out, about $0.035 for all 15 (≈ $0.002 per quarter, ~22× cheaper than Sonnet).

## Findings

- **Camden Q1 2026:** Core FFO $1.70 vs Conservative $1.20. Camden added back $51.2M of legal costs and settlements, $1.8M of pursuit costs and a casualty charge; the definition keeps them as costs.
- **MAA Q4 2025:** $2.23 vs $1.79 from a $53.0M legal settlement add-back.
- **NXRT:** reported AFFO ($0.75–0.77) is *above* its Core FFO because it adds back stock compensation and deducts no recurring capex. With recurring capex from its own capex table ($3.4–4.6M a quarter) and costs kept in, Conservative AFFO is $0.37–0.48, roughly half the reported figure.
- **IRT and BRT** do not deduct recurring capex in their adjusted metrics either; Conservative AFFO uses the capex they disclose elsewhere (IRT: $5.8–12.4M a quarter; BRT share: $1.6–1.8M).
- **New adjustment types found** and added to the definition: financing-cost amortization (NXRT) and non-real-estate depreciation (IRT). Remaining items under review: IRT "Other loss" and Camden "Other miscellaneous items" (small).
