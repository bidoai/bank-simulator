# Model Development Document
# Funding Valuation Adjustment (FVA) — Version 1.0
# Apex Global Bank | Quantitative Research Division
# Classification: RESTRICTED — Model Risk Sensitive
# SR 11-7 Section Reference: Model Development

---

## 1. DOCUMENT METADATA

| Field | Value |
|---|---|
| **Model Name** | Funding Valuation Adjustment (FVA) |
| **Model ID** | APEX-MDL-0011 |
| **Version** | 1.0 |
| **Status** | In Validation |
| **Risk Tier** | Tier 1 |
| **Regulatory Framework** | IFRS 13 Fair Value; Internal FTP Policy; Basel III (informational) |
| **Date of Development** | March 2026 |
| **Business Owner** | Head of Global Markets Trading (James Okafor) |
| **Model Developer** | Quantitative Research — XVA Team |
| **MRO Review** | Pending — Dr. Rebecca Chen |
| **CRO Approval** | Pending — Dr. Priya Nair |

### 1.1 Version History

| Version | Date | Change Summary |
|---|---|---|
| 0.1 | Jan 2026 | Initial framework — funding cost only (FCA) |
| 0.8 | Feb 2026 | Added funding benefit (FBA); asymmetric treatment |
| 1.0 | Mar 2026 | Production candidate; submitted for validation |

---

## 2. EXECUTIVE SUMMARY

### 2.1 Model Purpose

FVA captures the cost (or benefit) of funding derivatives positions that are not fully collateralised under a CSA. When Apex enters an uncollateralised derivative with a client and hedges it in the interbank market under a collateralised CSA, the bank faces an asymmetric funding situation: variation margin must be posted to the hedge counterparty when the hedge is out-of-the-money, but no corresponding margin is received from the client. This funding gap must be financed at Apex's unsecured borrowing rate. FVA quantifies the present value of this cost over the life of the trade.

FVA = FCA (Funding Cost Adjustment) − FBA (Funding Benefit Adjustment)

FCA is the cost of funding receivables (when Apex is owed money but cannot receive collateral). FBA is the benefit when Apex owes money and can use its own funds rather than paying market rates.

### 2.2 The FVA Debate — Why This Model Is Controversial

FVA is the most debated valuation adjustment in derivatives pricing. Hull and White (2012) argued that FVA adjustments represent double-counting with DVA: a bank's funding costs are already reflected in its credit spread, and applying FVA separately misprices derivatives by incorporating an avoidable cost into an asset's fair value. The counterargument — adopted by most major dealers — is that FVA is real: it affects actual cash flows and trading decisions, regardless of theoretical arguments about perfect markets.

Apex's policy (approved by the CFO and CRO in 2024) is to **include FVA in derivatives fair value** for internal pricing and P&L purposes, consistent with industry practice. This document acknowledges the theoretical debate and documents the specific methodological choices made.

### 2.3 Output Description

- **FVA charge per new trade**: Used by front office to price uncollateralised client derivatives
- **Portfolio FVA**: Daily P&L impact reported in income statement
- **FVA Greeks**: Sensitivities to interest rates (DV01), FX, and credit spreads — used for hedging
- **FCA/FBA decomposition**: Separated for internal cost allocation between treasury (funding) and trading (derivative)
- **FVA by counterparty and desk**: Granular attribution for profitability analysis

### 2.4 Key Assumptions

- Apex's unsecured borrowing spread over OIS/SOFR is a reliable proxy for the marginal cost of funding derivatives positions
- The funding curve is flat across tenors within a 1-year horizon (curve shape used for longer tenors)
- The hedge for every uncollateralised client trade is assumed to be executed collateralised (full VM under ISDA SIMM)
- DVA and FVA are computed independently and do not overlap (separate model for DVA, embedded in bilateral CVA calculation)
- Funding costs are symmetric: the same spread applies to borrowing and investing (relaxed in the FCA/FBA asymmetric variant)

### 2.5 Known Limitations

- The assumption of a single funding curve ignores liquidity segmentation (different tenors trade at different spreads, especially in stress)
- FVA is sensitive to the assumed hedging strategy; actual hedging behaviour may differ from the "always hedge collateralised" assumption
- FBA (funding benefit) recognition is conservative — many practitioners argue FBA should not be recognised as it relies on Apex defaulting, which would extinguish the benefit
- The model does not capture dynamic funding strategies (e.g., using repo to fund derivatives positions more cheaply)

---

## 3. BUSINESS CONTEXT AND PURPOSE

### 3.1 The Funding Gap Problem

Consider a simple example:

1. Apex writes a 5-year interest rate swap to a corporate client (uncollateralised — no CSA in place)
2. Apex hedges by entering the opposite swap with a dealer (collateralised — daily VM under ISDA SIMM)
3. If rates move so that the dealer hedge is out-of-the-money for Apex, Apex must post variation margin to the dealer immediately
4. But Apex cannot call margin from the corporate client
5. Apex must borrow funds to post that margin — at its unsecured borrowing spread over OIS

This is the funding gap. Over a 5-year swap, the expected cumulative cost of this funding gap — the FVA — can represent a significant fraction of the swap's gross profit.

### 3.2 Market Practice

Following the 2013 disclosures by Citigroup ($1.5B FVA loss) and JPMorgan ($1.5B FVA charge), virtually all major dealers began reporting FVA. The ISDA produced a paper in 2014 documenting the range of industry approaches. The consensus methodology — symmetric funding curve applied to expected future funding gaps — is what this model implements.

### 3.3 Model Users

- **Front Office Pricing**: FVA charge added to price of uncollateralised client derivatives
- **Finance / P&L**: Daily FVA P&L recognised in income statement
- **Treasury**: FVA informs funding cost allocation — trading desks are charged for the funding they consume
- **Collateral Negotiators**: FVA quantifies the value of upgrading a no-CSA relationship to a full CSA

---

## 4. THEORETICAL FOUNDATION

### 4.1 FVA Formula

The symmetric FVA formula under risk-neutral measure:

```
FVA = −∫₀ᵀ s_f(t) × E[V⁺(t)] × D(0,t) dt  +  ∫₀ᵀ s_f(t) × E[V⁻(t)] × D(0,t) dt
```

Simplified to:

```
FVA = FCA − FBA
FCA = −Σᵢ s_f × ENE_collateralised(tᵢ) × Δtᵢ × D(0, tᵢ)    [cost of funding gap when in-the-money]
FBA =  Σᵢ s_f × EPE_collateralised(tᵢ) × Δtᵢ × D(0, tᵢ)    [benefit of funding surplus when out-of-the-money]
```

Where:
- `s_f` = Apex's funding spread over OIS (current: 55bp for 1–5 year tenors)
- `EPE_collateralised(t)` = expected positive exposure of the **collateralised hedge** at time t (the collateral Apex receives from dealer hedge)
- `ENE_collateralised(t)` = expected negative exposure of the collateralised hedge (the collateral Apex must post)
- `D(0, t)` = OIS discount factor

**Intuition**: FCA is paid when Apex receives money from the client trade but must fund the hedge (borrowing cost). FBA is earned when Apex owes money on the client trade but can use that receipt to fund itself more cheaply.

### 4.2 Relationship to CVA

CVA and FVA share the same simulation infrastructure (EPE/ENE profiles from Monte Carlo) but differ in what drives the cost:

- **CVA**: the counterparty might *default* (credit loss) — proportional to default probability
- **FVA**: Apex must *fund* the position regardless of whether anyone defaults — proportional to exposure profile × funding spread

They are conceptually independent. Both are priced into client derivatives quotes.

### 4.3 The Asymmetric Variant (FCA Only)

Some practitioners argue FBA should not be recognised because:
1. It requires Apex to be in a net payable position to a collateralised counterparty
2. The "benefit" of holding their cash cheaply is already priced in the OIS rate
3. Recognising FBA inflates P&L on day 1 against a future cash flow that may not materialise

Apex's policy recognises symmetric FVA (FCA − FBA) but requires the FBA component to be separately disclosed in risk reports with a sensitivity showing the P&L impact of removing FBA.

### 4.4 Funding Curve Construction

Apex's unsecured funding curve is constructed from:
1. **Short end (0-1Y)**: SOFR + Apex CP (commercial paper) spread from recent issuance
2. **Medium term (1-5Y)**: SOFR + Apex senior unsecured bond spread (from Bloomberg/Markit secondary trading)
3. **Long end (5-30Y)**: SOFR + Apex CDS spread + liquidity premium (estimated from basis between bond spread and CDS)

The curve is rebuilt daily. Any point where Apex has not issued bonds in the past 12 months uses a linear interpolation between bracketing tenors.

### 4.5 Literature References

- Burgard, C., Kjaer, M. (2011). "Partial Differential Equation Representations of Derivatives with Bilateral Counterparty Risk and Funding Costs." *Journal of Credit Risk*, Vol. 7.
- Hull, J., White, A. (2012). "The FVA Debate." *Risk Magazine*, July 2012.
- Hull, J., White, A. (2014). "Valuing Derivatives: Funding Value Adjustments and Fair Value." *Financial Analysts Journal*, Vol. 70.
- Andersen, L., Duffie, D., Song, Y. (2019). "Funding Value Adjustments." *Journal of Finance*, Vol. 74.
- ISDA (2014). *FVA: The ISDA Guidance*.

---

## 5. DATA REQUIREMENTS AND GOVERNANCE

### 5.1 Input Data Sources

| Data Item | Source | Frequency |
|---|---|---|
| Apex funding curve (CP, bond spreads) | Treasury / Bloomberg | Daily |
| OIS discount curves (SOFR, ESTR, SONIA) | Bloomberg / Internal | Daily |
| EPE/ENE profiles | CVA model Monte Carlo engine | Daily (shared run) |
| Trade/netting set data | Front office systems | Real-time |
| CSA terms (VM threshold, MTA) | ISDA MA database | On amendment |

### 5.2 Data Governance

FVA shares the CVA model's simulation infrastructure. Any change to the simulation parameters (number of paths, time grid, market factor models) requires simultaneous review of both CVA and FVA outputs to confirm consistency.

The funding curve construction is owned jointly by the XVA team and Treasury. Disputes about the appropriate funding spread are escalated to the CFO / Head of Treasury.

---

## 6. METHODOLOGY AND IMPLEMENTATION

### 6.1 Shared Simulation with CVA

FVA reuses the Monte Carlo simulation generated for CVA (same paths, same time steps, same market factor evolution). The incremental computation is:
1. Apply netting set aggregation (same as CVA)
2. Apply CSA collateral offset (same as CVA)
3. Apply funding spread to EPE/ENE profiles

This integration reduces computational cost but creates a dependency: FVA results cannot be produced without a successful CVA run.

### 6.2 FVA for Partially Collateralised Trades

Many CSAs have a threshold (e.g., Apex posts margin only when net MtM exceeds $10M) or minimum transfer amount. These create a "funding gap" even for nominally collateralised relationships:

```
Funding_Gap(t) = max(V(t) − Threshold − MTA, 0) − posted_collateral(t)
```

The FVA for partially collateralised trades is computed using this adjusted exposure rather than the full EPE/ENE.

### 6.3 Desk-Level FVA Allocation

FVA is allocated to individual trading desks based on their contribution to the firm's aggregate funding need. The allocation methodology:
1. Compute firm-level FVA
2. Decompose by netting set
3. Allocate netting set FVA to originating desk using trade-level sensitivities
4. Charge desk P&L; credit is passed to Treasury (which provides the actual funding)

This creates the correct incentive: traders who write large uncollateralised trades face explicit P&L charges for the funding they consume.

---

## 7. MODEL TESTING AND BACKTESTING

### 7.1 Proxy Backtesting

Daily FVA P&L is compared against Greeks-predicted P&L:
```
Predicted ΔFVA = DV01_FVA × ΔIR + ΔFunding_Spread × Duration × Exposure
```

Tolerance: P&L explain > 80% of total FVA daily change. Lower threshold than CVA given the additional uncertainty from funding spread moves.

### 7.2 Benchmark Comparison

Quarterly comparison against an independently computed FVA using:
- Simplified closed-form for a representative vanilla IRS: `FVA ≈ s_f × EPE_avg × T` (annuity formula)
- Agreement threshold: within 8% of full simulation result

### 7.3 Sensitivity to Funding Curve

Funding curve sensitivity analysis — parallel shift of +100bp in Apex's funding spread:
- Expected FVA increase: proportional to portfolio duration × exposure
- Monitored quarterly; material sensitivity triggers review of hedging strategy

---

## 8. PERFORMANCE METRICS AND CALIBRATION STANDARDS

| Metric | Acceptable Range | Action if Breached |
|---|---|---|
| FVA P&L Explain | > 80% | Investigate within 2 business days |
| Benchmark deviation | < 8% relative | Review within 30 days |
| Funding curve staleness | No tenor > 5 business days old | Data quality alert |
| FBA as % of FCA | Disclosed separately; no threshold | Quarterly disclosure to MRO |

### 8.1 Recalibration Schedule

- **Funding curve**: Daily (automated from bond/CDS feed)
- **Simulation paths (shared with CVA)**: No recalibration; path count reviewed annually
- **FCA/FBA policy (asymmetric vs. symmetric)**: Annual review by CFO / CRO

---

## 9. LIMITATIONS, ASSUMPTIONS, AND KNOWN WEAKNESSES

### 9.1 Theoretical Controversy

The fundamental limitation of FVA is theoretical: the academic literature has not reached consensus on whether FVA is a legitimate fair value adjustment or a distortion of asset pricing principles. Hull and White's critique — that FVA leads to negative NPV trades being accepted when they shouldn't be — is mathematically valid in a frictionless market. In practice, market frictions (unsecured funding is genuinely more expensive than collateralised) make FVA operationally real regardless of its theoretical status.

**Compensating control**: FVA is disclosed separately from CVA and DVA in financial statements. The sensitivity of P&L to the FVA methodology (symmetric vs. FCA-only) is disclosed in the quarterly risk report.

### 9.2 Funding Spread Instability in Stress

In a stress event affecting Apex's credit, the funding spread may widen dramatically and non-linearly. The current model uses a flat funding spread calibrated to current market conditions. A 100bp widening in Apex's credit spread would increase FCA by approximately $180M.

**Compensating control**: Stressed FVA computed using funding spread at 75th percentile of historical 6-month widening.

### 9.3 Wrong-Way Funding Risk

For some counterparties, the scenarios where Apex's funding costs are highest (stress events) coincide with scenarios where those counterparties are most likely to increase their derivatives exposure. This "wrong-way funding risk" is not explicitly modelled.

**Compensating control**: Concentration limits on uncollateralised exposure by desk ensure no single counterparty drives excessive FVA.

---

## 10. COMPENSATING CONTROLS

| Risk | Control | Owner |
|---|---|---|
| Theoretical controversy | Separate disclosure; FCA-only sensitivity | Finance / CFO |
| Funding spread instability | Stressed FVA at 75th percentile spread | XVA Quant Team |
| Funding curve staleness | Daily rebuild; 5-day staleness alert | Market Data |
| FBA overstatement | FBA disclosed separately; policy review annually | CFO / CRO |
| Shared simulation failure | FVA unavailable if CVA run fails; fallback using prior-day + Greeks | XVA Technology |

### 10.1 Model Reserve

A model reserve of **$25 million** is held against FVA model uncertainty:
- Theoretical methodology uncertainty (FCA vs. FCA-FBA): $12M
- Funding curve construction uncertainty: $8M
- Wrong-way funding risk: $5M

---

## 11. CHANGE MANAGEMENT

Material changes (funding curve methodology, FCA/FBA policy, integration with new simulation infrastructure) require full MRO re-validation. Non-material changes (new tenor point added to funding curve, computational optimisation) via expedited review with 5-business-day notification.

---

## 12. APPROVALS AND SIGN-OFF

| Role | Name | Status | Date |
|---|---|---|---|
| Model Developer | XVA Quant Team | ✓ Submitted | March 2026 |
| Model Risk Officer | Dr. Rebecca Chen | ⏳ Pending | — |
| Chief Risk Officer | Dr. Priya Nair | ⏳ Pending | — |
| CFO (FVA Policy Owner) | Diana Osei | ⏳ Pending | — |
| Business Owner | James Okafor | ⏳ Pending | — |

---

*Document Classification: RESTRICTED — Model Risk Sensitive*
*Apex Global Bank | Quantitative Research Division | XVA Team*
*Next scheduled review: March 2027 (or upon material model change)*
