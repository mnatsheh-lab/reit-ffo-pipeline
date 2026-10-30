# Multifamily Rule

Decides which REITs belong in the universe. Applied to every REIT (SIC code 6798) with an exchange ticker, for every year from 2022 onward, and re-checked in each daily run.

## The rule

A REIT qualifies when **at least 75% of its gross invested book assets are in conventional apartments**.

This follows the FTSE Nareit property-sector methodology, which assigns a REIT to a sector or subsector when at least 75% of its gross invested book assets are in that property type.

## What counts as conventional apartments

| Included | Excluded |
|---|---|
| Market-rate apartment communities (garden, mid-rise, high-rise) | Student housing |
| Apartments held in consolidated joint ventures | Single-family rentals |
| | Senior housing |
| | Manufactured homes |
| | Commercial space (retail, office) inside mixed-use buildings |

## How it is applied

1. **AI classification.** For each candidate, Claude reads the latest 10-K (and the relevant 10-K for each historical year), finds the asset breakdown by property type, and computes the apartment share. It records the figure, the page and the filing it relied on.
2. **Cross-check.** The result is compared with the Apartments subsector in the FTSE Nareit All REITs constituent list. Any disagreement is flagged.
3. **Human approval.** New entries and borderline cases (apartment share between 65% and 85%, or any disagreement in step 2) are proposed for review and join the universe only after approval.
4. **Year by year.** Membership is decided per fiscal year, so a REIT that crosses the threshold enters or leaves the history in the right period.
5. **Exits.** A REIT leaves the active universe on a Form 25 (delisting) or Form 15 (deregistration); its history is kept.

## Universe as of October 2026

Matches the FTSE Nareit Apartments subsector (August 2026): VMRK, ESS, MAA, UDR, CPT, IRT, CSR, NXRT, BRT, CLPR.

Sources: FTSE Nareit All REITs constituents by sector, August 2026 (reit.com); FTSE Nareit US Real Estate Index Series consultation (classification methodology).
