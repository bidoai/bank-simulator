# Apex Product Expansion Plan

## Objective

Close the biggest realism gap between Apex's current "markets + control plane" simulation and a true large global dealer bank.

## Recommended Build Order

1. Securities Finance
2. Securitized Products
3. Prime Brokerage
4. Transaction Banking
5. DCM / ECM / Underwriting

## Why Start Here

### Securities Finance

- Connects treasury, collateral, markets, and client financing
- Makes balance-sheet usage visible
- Creates realistic repo, stock-loan, and margin dynamics

### Securitized Products

- Adds MBS / ABS / CMBS / CLO product depth
- Introduces OAS, convexity, spread carry, and funding drag
- Naturally builds on Apex's existing treasury, collateral, and risk stack

## Phase 1 Build Scope

This implementation adds:

- `Securities Finance` dashboard + APIs
- `Securitized Products` dashboard + APIs
- seeded operating views for repo, stock loan, prime financing, and securitized inventory
- navigation and landing-page integration

## Planned Next Iterations

### Securities Finance

- repo ladder and maturity wall
- client-level margin call lifecycle
- stock-borrow availability and specials time series
- collateral optimization against treasury funding curves

### Securitized Products

- agency MBS OAS engine
- specified-pool collateral segmentation
- non-agency loss timing and waterfall engine
- securitized-product stress decomposition by sleeve

## Governance Requirement

These businesses should only scale after:

- clear ownership between desk, treasury, risk, and compliance
- explicit funding and liquidity limits
- model validation for prepayment / OAS analytics
- auditable daily reconciliation for desk metrics
