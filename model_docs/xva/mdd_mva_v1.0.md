# Model Development Document
# Margin Valuation Adjustment (MVA) — Version 1.0
# Apex Global Bank | Quantitative Research Division
# Classification: RESTRICTED — Model Risk Sensitive
# SR 11-7 Section Reference: Model Development

---

## 1. DOCUMENT METADATA

| Field | Value |
|---|---|
| **Model Name** | Margin Valuation Adjustment (MVA) |
| **Model ID** | APEX-MDL-0012 |
| **Version** | 1.0 |
| **Status** | In Validation |
| **Risk Tier** | Tier 1 |
| **Regulatory Framework** | BCBS-IOSCO Uncleared Margin Rules (UMR); ISDA SIMM v2.6; EMIR; Dodd-Frank |
| **Date of Development** | March 2026 |
| **Business Owner** | Head of Global Markets Trading (James Okafor) |
| **Model Developer** | Quantitative Research — XVA Team |
| **MRO Review** | Pending — Dr. Rebecca Chen |
| **CRO Approval** | Pending — Dr. Priya Nair |

### 1.1 Version History

| Version | Date | Change Summary |
|---|---|---|
| 0.1 | Nov 2025 | Initial framework — IM forecasting via regression |
| 0.5 | Jan 2026 | SIMM sensitivities methodology integrated |
| 1.0 | Mar 2026 | Production candidate; submitted for validation |

---

## 2. EXECUTIVE SUMMARY

### 2.1 Model Purpose

MVA is the present value of the expected future costs of posting Initial Margin (IM) on uncleared OTC derivatives over the life of a trade. It was introduced as a necessary valuation adjustment following the implementation of the BCBS-IOSCO Uncleared Margin Rules (UMR), which began phased implementation in 2016 and reached Phase 6 in September 2022 (capturing entities with AANA ≥ $8 billion).

Unlike Variation Margin (which is exchanged daily and represents current mark-to-market), Initial Margin is a forward-looking risk buffer held by a third-party custodian to cover potential exposure during the Margin Period of Risk if a counterparty defaults. It is not returned to the poster until the trade matures or is terminated. The cost of funding this IM — at Apex's unsecured borrowing spread — for potentially decades on a long-dated swap is the MVA.

MVA = Present Value of [ Expected Future IM(t) × Funding Spread(t) × Δt ]

### 2.2 Why MVA Matters Now

Before UMR Phase 6, only the largest dealers exchanged IM on bilateral OTC trades. Phase 6 extended the requirement to mid-size institutions. For Apex, this created an overnight obligation to post IM on approximately 47% of its bilateral OTC derivatives portfolio with Phase 6 counterparties. The aggregate IM obligation for Apex is currently approximately **$8.7 billion** across all bilateral relationships.

At an average funding spread of 55bp, the annual cost of carrying this IM is approximately **$48 million per year**. Over the average remaining life of the portfolio (approximately 6.2 years duration-weighted), the present value of these future funding costs is approximately **$240 million** — the current portfolio MVA.

This is no longer a rounding error. MVA must be priced into new trades.

### 2.3 Output Description

- **Trade MVA**: MVA charge per new trade — incorporated into front-office pricing
- **Portfolio MVA**: Daily P&L reported in income statement
- **IM forecast profile**: Expected IM at each future date (EPE of IM under SIMM)
- **MVA Greeks**: Sensitivities to rates and volatility for hedging
- **MVA by counterparty**: Attribution for collateral efficiency analysis
- **SIMM sensitivity report**: The underlying SIMM sensitivities driving IM calculations

### 2.4 Key Assumptions

- Initial Margin is calculated under ISDA SIMM v2.6 (the industry standard IM model for bilateral trades)
- Future IM is estimated by simulating future SIMM sensitivities (delta, vega, curvature) under the same Monte Carlo framework used for CVA/FVA
- Apex's funding spread for IM is the same as used in FVA (55bp over OIS for 1–5Y; curve used for longer tenors)
- The custodian is a qualifying third-party custodian (State Street); IM posted earns no return (or OIS − haircut)
- SIMM risk weights and correlations are fixed at current ISDA SIMM v2.6 calibration; no scenario for SIMM recalibration risk

### 2.5 Known Limitations

- Forecasting SIMM sensitivities under future market scenarios is computationally expensive and relies on linear approximation for efficiency; true future SIMM may differ by 5–15%
- SIMM recalibration risk: ISDA recalibrates SIMM risk weights annually; a recalibration that increases risk weights would increase IM requirements and thus MVA
- The model assumes continuous IM posting; in practice, minimum transfer amounts (MTAs) create discontinuities that are smoothed over in the simulation
- MVA is computed assuming the full UMR regime; any regulatory change (e.g., threshold increases) would require immediate model update

---

## 3. BUSINESS CONTEXT AND PURPOSE

### 3.1 The UMR Backstory

The Uncleared Margin Rules emerged from the G20's Pittsburgh Summit (2009) mandate to reform OTC derivatives markets following the 2008 crisis. The core insight: the daisy chain of uncollateralised bilateral OTC trades had created a web of hidden counterparty risk. AIG's near-failure was a direct result — AIG had written enormous quantities of credit default swaps with minimal collateral, and when the credit markets collapsed, the potential losses were so large that AIG would have defaulted on hundreds of counterparties simultaneously.

UMR forces dealers and large end-users to post two-way IM on bilateral trades — creating a genuine buffer that survives the default of either party. The cost of this buffer — MVA — is real and must be priced.

### 3.2 ISDA SIMM Overview

ISDA's Standard Initial Margin Model (SIMM) is the industry-standard methodology for calculating IM on bilateral uncleared OTC derivatives. It was developed collaboratively by major dealers and ISDA, approved by regulators, and adopted by essentially all Phase 1-6 participants.

SIMM computes IM as a risk-weighted sum of trade sensitivities:

**Delta sensitivity (IR example)**:
```
s_k = ΔV / Δr_k    [sensitivity of portfolio value to a 1bp move in rate tenor k]
```

**SIMM IM for a single risk class**:
```
IM = √[ Σᵢ Σⱼ ρᵢⱼ × WSᵢ × WSⱼ ]
```

Where `WSᵢ = RW_i × s_i` (risk-weighted sensitivity), `ρᵢⱼ` is the prescribed inter-bucket correlation, and `RW_i` is the SIMM risk weight for bucket i.

SIMM covers six risk classes: Interest Rate (IR), Credit Qualifying (CQ), Credit Non-Qualifying (CNQ), Equity (EQ), FX, and Commodity (CM). The aggregate IM is computed by combining across risk classes with prescribed cross-class correlations.

### 3.3 Why MVA Is Tier 1

MVA feeds directly into:
1. **Income statement**: Daily MVA P&L affects earnings
2. **New trade pricing**: Incorrect MVA pricing leads to systematic mis-pricing of bilateral derivatives
3. **Collateral optimisation decisions**: MVA drives decisions about which trades to clear (CCPs require IM too, but on different terms) vs. keep bilateral

---

## 4. THEORETICAL FOUNDATION

### 4.1 MVA Formula

```
MVA = − Σᵢ s_f(tᵢ) × E[IM_SIMM(tᵢ)] × D(0, tᵢ) × Δtᵢ
```

Where:
- `s_f(tᵢ)` = Apex's funding spread at time tᵢ (from the funding curve used in FVA)
- `E[IM_SIMM(tᵢ)]` = expected Initial Margin under SIMM at future time tᵢ
- `D(0, tᵢ)` = OIS discount factor
- The negative sign: IM is a cash outflow (cost to Apex)

The key challenge is computing `E[IM_SIMM(tᵢ)]` — forecasting future SIMM sensitivities and therefore future IM requirements.

### 4.2 Forecasting Future SIMM Sensitivities

Three approaches, listed in increasing accuracy and computational cost:

**Approach 1 — Regression (current production approach)**

Train a regression model that maps current portfolio sensitivities and market state to future SIMM:
```
IM_SIMM(t) ≈ f(Sensitivities(0), Market_State(t))
```

Features: current DV01, vega, curvature; projected rate level and vol surface at t.
Model: gradient boosting regression trained on historical SIMM calculations for representative portfolios.
Accuracy: within 8% of full-calculation SIMM for 90% of scenarios.
Computation: ~2 seconds per counterparty netting set.

**Approach 2 — Approximate SIMM re-calculation**

At each Monte Carlo time step, re-compute approximate SIMM using perturbed sensitivities:
```
s_k(t) ≈ s_k(0) + (∂s_k/∂r) × Δr(t) + (∂s_k/∂σ) × Δσ(t)
```

Accuracy: within 5% of full SIMM for vanilla portfolios; larger errors for exotic products.
Computation: ~15 seconds per counterparty.

**Approach 3 — Full SIMM re-calculation (benchmark only)**

Re-run full SIMM calculation at each simulation node. Computationally prohibitive for production (days of computation for full portfolio). Used only for quarterly benchmark validation.

**Current production methodology**: Approach 1 (regression) for most counterparties; Approach 2 for the 20 largest counterparties by IM obligation (representing ~75% of total MVA).

### 4.3 SIMM Sensitivities Under Future Market Scenarios

For interest rate risk class (largest contributor at Apex — 62% of total IM):

Delta sensitivity evolution assumes that future DV01 scales with the duration of remaining trades and the simulated rate environment. Under a 2-factor Hull-White model:
```
DV01(t) ≈ DV01(0) × [Remaining Duration(t) / Duration(0)] × [Rate Level Adjustment(t)]
```

For vega (relevant for swaption portfolios): future vega is proportional to remaining time to expiry and the ratio of current vs. future implied vol. Vega collapses to zero at option expiry.

### 4.4 Marginal MVA (for New Trade Pricing)

When pricing a new trade, the relevant quantity is the **marginal MVA** — the change in portfolio MVA from adding the new trade:

```
Marginal_MVA = MVA(Portfolio + New Trade) − MVA(Portfolio)
```

Due to netting effects within a counterparty's netting set, marginal MVA can be significantly less than the standalone MVA of the new trade, or even negative (IM-reducing) if the new trade offsets existing sensitivities.

### 4.5 Literature References

- ISDA (2022). *SIMM Methodology, version 2.6*. ISDA.
- BCBS-IOSCO (2015). *Margin Requirements for Non-Centrally Cleared Derivatives*, rev. 2020.
- Green, A., Kenyon, C. (2014). "MVA: Initial Margin Valuation Adjustment by Replication and Regression." *Risk Magazine*, May 2014.
- Anfuso, F., Aziz, D., Giltinan, P., Loukopoulos, K. (2017). "A Sound Modelling and Backtesting Framework for Forecasting Initial Margin Requirements." SSRN Working Paper.
- Caspers, P., Giltinan, P., Lichters, R., Nowaczyk, N. (2017). "Forecasting Initial Margin Requirements: A Model Evaluation." *Journal of Risk*, Vol. 19.

---

## 5. DATA REQUIREMENTS AND GOVERNANCE

### 5.1 Input Data Sources

| Data Item | Source | Frequency |
|---|---|---|
| SIMM risk weights and correlations | ISDA SIMM documentation (annual release) | Annual; immediate update on release |
| Trade sensitivities (delta, vega, curvature) | Risk systems (Murex) | Daily |
| CSA terms (IM threshold, MTA, eligible collateral) | ISDA SIMM Custodial Agreement database | On amendment |
| Funding curve | Treasury (same as FVA) | Daily |
| Historical SIMM calculations (for regression training) | Risk data warehouse | Monthly re-training |
| Actual IM calls received/posted | Collateral management system | Daily |

### 5.2 SIMM Version Governance

ISDA releases updated SIMM calibrations annually (typically September). Each new version changes risk weights and correlations, which changes IM requirements across the portfolio. Apex's process:

1. ISDA releases SIMM vX.Y (typically 60 days notice)
2. XVA team recalibrates MVA model to new SIMM weights
3. Model Risk Officer expedited review (15 business days for SIMM version updates)
4. Production deployment by SIMM effective date
5. Parallel run for 5 business days pre-cutover

**SIMM version currently in production**: v2.6 (effective September 2024)

### 5.3 BCBS 239 Data Lineage

Every MVA figure is traceable to: (a) trade data from Murex, (b) SIMM sensitivity calculation (timestamped), (c) SIMM version tag, (d) funding curve snapshot, (e) MVA model version.

---

## 6. METHODOLOGY AND IMPLEMENTATION

### 6.1 Production Run Architecture

MVA shares the simulation infrastructure with CVA and FVA. The additional computation is:
1. At each Monte Carlo time step, compute approximate future SIMM for each netting set
2. Multiply by funding spread at that tenor
3. Discount back to today

**Run frequency**: Daily EOD (10,000 paths, same as CVA). Intraday indicative runs every 4 hours (1,000 paths).

**Computation time**: Approximately 18 minutes incremental on top of CVA run (regression approach). Total XVA suite (CVA + FVA + MVA) target: ≤ 70 minutes.

### 6.2 IM Portfolio Optimisation (Collateral Efficiency)

MVA is used in the collateral optimisation engine to evaluate whether bilateral trades should be:
1. Kept bilateral (pay MVA and FVA; retain flexibility)
2. Cleared at CCP (pay CCP IM and CCP default fund contribution; standardised but efficient for plain vanilla)
3. Compressed/terminated (reduce gross notional; reduce IM obligation)

The optimisation runs weekly and generates recommendations for the Head of Operations and trading desk heads.

### 6.3 Actual IM vs. Model Validation

Daily comparison of model-predicted SIMM against actual IM calls received from counterparties:
- Tolerance: ≤ 5% difference for 95% of daily IM calls
- Systematic bias (model consistently under- or over-predicting): investigate within 3 business days

This is both a data quality check (are counterparties calculating SIMM correctly?) and a model accuracy check.

---

## 7. MODEL TESTING AND BACKTESTING

### 7.1 Actual vs. Predicted IM

Primary backtesting: compare model-generated expected IM at horizon T against actual IM posted at time T.

Sample size: 24 months of daily IM calls across 130+ active counterparties.

**Results (as of model submission)**:
- Mean absolute error: 4.2% of actual IM (within 5% threshold)
- 95th percentile error: 11.8% (some large outliers from SIMM recalibration events)
- Directional accuracy (model correctly predicted IM would increase/decrease): 87%

### 7.2 Full-Calculation Benchmark

Quarterly comparison of regression-based SIMM forecast (production) against Approach 3 (full SIMM re-calculation) for a representative sub-portfolio:
- Target: regression within 8% of full calculation
- Last benchmark result (Q4 2025): 6.3% mean deviation — pass

### 7.3 SIMM Sensitivity Stress Test

Simulate a 50% increase in all SIMM risk weights (analogous to a severe SIMM recalibration):
- Portfolio IM increase: $4.3B (from $8.7B to ~$13B)
- MVA increase: ~$120M
- Funding requirement increase: ~$4.3B — reviewed against liquidity buffer
- Tested against LCR impact: LCR remains above 100% minimum; buffer sufficient

---

## 8. PERFORMANCE METRICS AND CALIBRATION STANDARDS

| Metric | Acceptable Range | Action if Breached |
|---|---|---|
| IM prediction error vs. actual calls | < 5% mean absolute | Investigate within 3 days |
| IM prediction error vs. full SIMM | < 8% mean deviation | Review regression model |
| SIMM version deployment lag | ≤ 0 days vs. ISDA effective date | Emergency deployment process |
| Actual IM call reconciliation | < 3 unreconciled calls > $10M | Collateral ops escalation |
| MVA P&L explain | > 75% | Investigate within 2 days |

---

## 9. LIMITATIONS, ASSUMPTIONS, AND KNOWN WEAKNESSES

### 9.1 SIMM Recalibration Risk

ISDA recalibrates SIMM annually. A significant recalibration (risk weights increased substantially) would:
1. Increase actual IM requirements immediately
2. Require MVA model update within 60 days
3. Affect profitability of all existing bilateral derivatives — a retroactive cost that cannot be hedged

**No model-based compensation is possible for this risk.** The compensating control is operational: ISDA recalibration schedule is tracked; pre-implementation analysis of the impact of proposed changes is prepared quarterly.

### 9.2 Basis Between SIMM and Actual IM

Different counterparties calculate SIMM slightly differently (different curve construction, different aggregation methods). These differences create a basis between Apex's SIMM calculation and the counterparty's — resulting in disputes and IM calls that differ from model predictions.

**Compensating control**: Dispute resolution process (ISDA SIMM reconciliation guidance); daily IM call reconciliation with automatic escalation for > $5M discrepancy.

### 9.3 Regression Model Staleness

The regression model for future SIMM is retrained monthly on historical data. In a regime change (e.g., a rapid large move in rates or a significant restructuring of the derivatives portfolio), the regression may become unrepresentative until the next retraining cycle.

**Compensating control**: Anomaly detection on regression outputs — if predicted IM deviates from actual by > 15% on three consecutive days, emergency retraining is triggered.

### 9.4 Eligible Collateral Uncertainty

SIMM IM must be posted in eligible collateral (typically cash or high-quality government bonds). If eligible collateral is scarce (a real stress scenario in which everyone is simultaneously posting IM), the cost of sourcing eligible collateral may exceed the funding spread assumed in the model.

**Compensating control**: Collateral availability stress test run quarterly; minimum eligible collateral buffer maintained by Treasury.

---

## 10. COMPENSATING CONTROLS

| Risk | Control | Owner |
|---|---|---|
| SIMM recalibration | Pre-implementation impact analysis; operational monitoring | XVA Quant + Reg Affairs |
| IM calculation disputes | Daily IM reconciliation; dispute resolution protocol | Collateral Ops |
| Regression staleness | Monthly retraining; anomaly detection | XVA Quant Team |
| Eligible collateral scarcity | Collateral availability stress test; buffer maintained | Treasury |
| SIMM version deployment lag | Change management process; 60-day advance preparation | Technology / XVA |

### 10.1 Model Reserve

A model reserve of **$18 million** is held against MVA model uncertainty:
- Regression approximation error: $8M
- SIMM recalibration risk: $7M
- Collateral cost uncertainty: $3M

---

## 11. CHANGE MANAGEMENT

### 11.1 SIMM Version Updates

SIMM annual recalibration is classified as a material model change requiring expedited MRO review (15 business days). No delay to production deployment is permitted — ISDA effective dates are regulatory compliance deadlines.

### 11.2 All Other Material Changes

Full re-validation process applies (definition same as CVA MDD Section 11).

---

## 12. APPROVALS AND SIGN-OFF

| Role | Name | Status | Date |
|---|---|---|---|
| Model Developer | XVA Quant Team | ✓ Submitted | March 2026 |
| Model Risk Officer | Dr. Rebecca Chen | ⏳ Pending | — |
| Chief Risk Officer | Dr. Priya Nair | ⏳ Pending | — |
| Head of Treasury (UMR Compliance) | Amara Diallo | ⏳ Pending | — |
| Business Owner | James Okafor | ⏳ Pending | — |

---

*Document Classification: RESTRICTED — Model Risk Sensitive*
*Apex Global Bank | Quantitative Research Division | XVA Team*
*Next scheduled review: March 2027 (or upon SIMM version update / material model change)*
