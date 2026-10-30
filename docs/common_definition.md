# Common FFO Definition

This project restates every REIT, every quarter since Q1 2020, to one fixed definition, applied retroactively regardless of the definition the company used at the time. The outlook is deliberately **risk-averse**: where a judgment is needed, costs are treated as recurring parts of running the business.

Two metrics are reported:

- **Conservative Core FFO** — the headline figure.
- **Conservative AFFO** — Conservative Core FFO minus recurring capital expenditures, shown alongside.

## Starting point: NAREIT FFO

Net income to common shareholders, adjusted per the Nareit FFO White Paper (2018 restatement):

| Item | Treatment |
|---|---|
| Depreciation and amortization of real estate | Add back |
| Gains/losses on sale of depreciable real estate | Remove |
| Impairments of depreciable real estate | Add back (follows Nareit) |
| Share of unconsolidated JV real estate depreciation | Add back |
| Net income attributable to noncontrolling OP unitholders | Add back; per-share figures use shares + units |

## From NAREIT FFO to Conservative Core FFO

| # | Adjustment type | Treatment | Rationale |
|---|---|---|---|
| 1 | Legal costs and settlements | **Keep as a cost** (do not add back) | Lawsuits are a normal cost of operating large apartment portfolios. |
| 2 | Casualty losses (storms, fires, freezes) | **Keep losses as a cost; remove insurance recoveries** | Weather is a recurring cost of owning in exposed markets; insurance windfalls should not lift earnings. |
| 3 | Gains/losses on non-real-estate investments | **Remove both** | Measures the apartment business only; avoids a built-in bias. |
| 4 | Derivative and hedge mark-to-market changes | **Remove both** | Non-cash and reverse over time. Cash swap settlements always stay in FFO. |
| 5 | Debt extinguishment | **Keep costs; remove gains** | Refinancing is a recurring part of running a leveraged REIT. |
| 6 | Transaction, merger and acquisition-pursuit costs | **Keep as a cost** | Growth through acquisitions has a real price. |
| 7 | Severance and restructuring | **Keep as a cost** | Reorganizations recur at large companies. |
| 8 | Non-cash stock compensation | **Keep as a cost** | Dilutes shareholders, so it is a real cost. |
| 9 | Amortization of deferred financing costs (and debt discounts/premiums) | **Keep as a cost; remove benefits** | Loan fees are a real cost of borrowing, just spread over the loan's life. *Added Oct 30, 2026 after NXRT's add-back of ~$0.065/share.* |
| 10 | Depreciation of non-real-estate assets ("other depreciation") | **Keep as a cost** | Nareit adds back only real estate depreciation; offices and IT wear out and are replaced. *Added Oct 30, 2026 after IRT's add-back.* |

## From Conservative Core FFO to Conservative AFFO

| Item | Treatment |
|---|---|
| Recurring capital expenditures | Deduct |

## Rules for applying the definition

- **Net lines.** Where a company reports a single net line (e.g. "casualty related charges and (recoveries), net"), the sign of the net amount decides the treatment: a net charge is kept as a cost; a net recovery is removed.
- **Combined or missing items.** If a filing combines items that this definition treats differently, or omits an item, the pipeline searches the 10-Q notes. If the item still cannot be separated, the quarter is flagged **restated with limits**, naming the item. The pipeline never guesses.
- **Unlisted adjustment types.** Any company adjustment not covered above gets the conservative default (costs kept in earnings, gains removed) and is flagged on the dashboard as pending review until a rule is added here.
- **Recurring capex not in the company's AFFO.** If a company's own AFFO does not deduct recurring capex (e.g. NXRT, BRT), Conservative AFFO uses the quarterly recurring capex from the company's capex table and says so. If only an annual or per-unit figure is disclosed, Conservative AFFO is not computed for that quarter.
- **One-sided treatments** (items 2 and 5) mean Conservative Core FFO will usually be at or below each company's own Core FFO. This is intentional.

## Worked example: MAA

| | Q4 2025 | Q1 2026 | Q2 2026 |
|---|---|---|---|
| NAREIT FFO per share | $1.79 | $2.23 | $2.10 |
| MAA reported Core FFO | $2.23 | $2.13 | $2.08 |
| **Conservative Core FFO** | **$1.79** | **$2.09** | **$2.08** |
| MAA reported Core AFFO | $1.91 | $1.98 | $1.77 |
| **Conservative AFFO** | **$1.47** | **$1.94** | **$1.77** |

- **Q4 2025:** the $53.0M legal settlement stays as a cost (MAA added it back): −$0.44 per share.
- **Q1 2026:** the $4.5M net casualty charge stays as a cost (MAA added it back): −$0.04 per share.
- **Q2 2026:** MAA's adjustments (derivative, investments, net casualty recovery) all match this definition, so the figures are identical.

Source: MAA Earnings Release and Supplemental Data, page 10, for each quarter.
