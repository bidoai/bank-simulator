# Model Development Document
# Credit Valuation Adjustment (CVA) — Version 1.0
# Apex Global Bank | Quantitative Research Division
# Classification: RESTRICTED — Model Risk Sensitive
# SR 11-7 Section Reference: Model Development

---

## 1. DOCUMENT METADATA

| Field | Value |
|---|---|
| **Model Name** | Credit Valuation Adjustment (CVA) |
| **Model ID** | APEX-MDL-0010 |
| **Version** | 1.0 |
| **Status** | In Validation |
| **Risk Tier** | Tier 1 |
| **Regulatory Framework** | Basel III SA-CVA / BA-CVA; IFRS 13 Fair Value; ISDA SIMM |
| **Date of Development** | March 2026 |
| **Business Owner** | Head of Global Markets Trading (James Okafor) |
| **Model Developer** | Quantitative Research — XVA Team |
| **MRO Review** | Pending — Dr. Rebecca Chen |
| **CRO Approval** | Pending — Dr. Priya Nair |

### 1.1 Version History

| Version | Date | Author | Change Summary |
|---|---|---|---|
| 0.1 | Jan 2026 | XVA Quant Team | Initial draft — bilateral framework |
| 0.9 | Feb 2026 | XVA Quant Team | Added WWR module; stress calibration |
| 1.0 | Mar 2026 | XVA Quant Team | Production candidate; submitted for validation |

---

## 2. EXECUTIVE SUMMARY

### 2.1 Model Purpose

CVA is the market value of counterparty credit risk embedded in a derivatives portfolio. It represents the expected loss arising from counterparty default, adjusted for the replacement cost of the derivative at the time of default. This model computes bilateral CVA (incorporating both counterparty and own-credit risk) for all over-the-counter (OTC) derivatives held by Apex Global Bank that are subject to counterparty credit risk.

CVA is subtracted from the risk-free value of the derivatives portfolio to arrive at the fair value of the portfolio under IFRS 13. It also feeds the regulatory CVA capital charge under Basel III.

### 2.2 Business Use Cases

1. **Fair Value Accounting (IFRS 13)**: Daily CVA P&L is reported in the income statement. CVA is a component of the derivatives fair value disclosed in financial statements.
2. **Regulatory Capital (Basel III SA-CVA)**: CVA feeds the Standardised Approach CVA capital charge, which is calibrated to the sensitivity of CVA to market risk factors.
3. **Derivatives Pricing**: Front-office traders add CVA as a charge when pricing new derivatives with counterparties who are uncollateralised or partially collateralised.
4. **Counterparty Limit Management**: CVA informs the Credit Risk Officer's assessment of counterparty exposure relative to credit limits.
5. **Hedging**: The CVA desk dynamically hedges CVA sensitivities (credit delta, IR delta) using CDS and interest rate instruments.

### 2.3 Output Description

The model produces:
- **Unilateral CVA**: Expected loss from counterparty default only
- **Bilateral CVA**: Net of CVA (counterparty risk) and DVA (own-credit risk), per IFRS 13
- **CVA Greeks**: Sensitivities to credit spread (CS01), interest rates (DV01), FX rates, and volatility — used for hedging and regulatory SA-CVA capital
- **CVA by counterparty**: Granular attribution for limit management
- **CVA P&L explain**: Daily change decomposed into market moves vs. credit spread changes vs. new trades

### 2.4 Key Assumptions

- Counterparty default times follow a Poisson process with intensity implied by CDS spreads or internal PD estimates
- Recovery rates are fixed (40% for senior unsecured; desk has override capability for specific counterparties)
- Market risk factors (interest rates, FX, equity prices) evolve independently of counterparty credit quality, except where wrong-way risk (WWR) is explicitly modelled
- Netting sets are legally enforceable — ISDA Master Agreement and Credit Support Annex (CSA) in place and legally reviewed for each counterparty
- Simulation horizon matches longest trade maturity (up to 30 years for long-dated swaps)

### 2.5 Known Limitations

- Wrong-way risk between FX and sovereign/bank counterparties is approximated; full correlation-based WWR simulation is computationally expensive
- Recovery rates are deterministic; stochastic recovery adds model complexity without materially changing the mean CVA estimate (though it matters for tail risk)
- The model does not capture re-rating dynamics (gradual credit deterioration before default)
- Gap risk (jump-to-default over a weekend or through a holiday) is not captured in the continuous-time framework
- Proxy CDS spreads (for counterparties without observable CDS) introduce basis risk

---

## 3. BUSINESS CONTEXT AND PURPOSE

### 3.1 Business Problem

Prior to CVA, derivatives were marked to risk-free value (e.g., discounting at LIBOR/SOFR flat). This ignored the credit quality of the counterparty. A swap with an AAA-rated government counterparty and an identical swap with a CCC-rated corporate were marked at the same value — manifestly wrong and exposed during the 2008 financial crisis when Lehman Brothers defaulted with approximately $35 billion in outstanding OTC derivatives.

Post-crisis, IFRS 13 (2013) and the Basel III CVA capital charge (2019) mandated that banks explicitly value and capitalise counterparty credit risk.

### 3.2 Decision Processes Supported

- **New trade approval**: Pricing desks must include CVA in the initial pricing of any uncollateralised OTC derivative. A trader who prices a swap at SOFR + 45bp without CVA is undercharging by the cost of the credit risk being taken on.
- **Collateral negotiations**: CVA quantifies the value of a CSA — a counterparty willing to post daily variation margin significantly reduces CVA. This model provides the analytical basis for collateral negotiations.
- **Credit limit setting**: CVA by counterparty informs credit line utilisation reporting.

### 3.3 Regulatory Requirement

**Basel III SA-CVA capital charge** (CRR Article 383): Banks must hold capital against the risk that CVA itself moves due to market risk factors. The SA-CVA approach requires computing CVA sensitivities (delta and vega) to all market risk factors and aggregating them under a prescribed formula with regulatory correlations.

As Apex does not currently hold IMA-CVA approval, the Standardised Approach applies to all CVA capital.

### 3.4 Model Users

- **XVA Desk**: Daily CVA computation and P&L; hedging decision support
- **Credit Risk Officer**: Counterparty exposure monitoring
- **Finance / Accounting**: IFRS 13 fair value for financial statement disclosure
- **Regulatory Reporting**: Basel III CVA capital charge computation
- **Front Office Pricing Desks**: CVA charge added to client-facing derivatives prices

### 3.5 Materiality Assessment

CVA for Apex's derivatives portfolio is currently approximately **$2.1 billion** (gross, pre-netting and collateral). A 1% change in average counterparty credit spreads produces approximately **$85 million** in CVA P&L. This is a Tier 1 model: it feeds both the income statement and regulatory capital.

---

## 4. THEORETICAL FOUNDATION

### 4.1 Mathematical Framework

**Unilateral CVA** under risk-neutral measure Q:

```
CVA = (1 − R) × ∫₀ᵀ EE(t) × dPD(t)
```

Where:
- `R` = recovery rate (fraction of exposure recovered in default event)
- `EE(t)` = Expected Exposure at time t = E^Q[max(V(t), 0)]
- `V(t)` = mark-to-market value of the netting set at time t
- `PD(t)` = cumulative probability of default by time t, derived from CDS spread term structure
- `T` = maturity of longest trade in netting set

In discrete form over time steps t₁, t₂, ..., tₙ:

```
CVA ≈ (1 − R) × Σᵢ EE(tᵢ) × [PD(tᵢ₋₁, tᵢ)]
```

Where `PD(tᵢ₋₁, tᵢ)` is the marginal probability of default in interval [tᵢ₋₁, tᵢ].

**Bilateral CVA (BCVA)**:

```
BCVA = CVA − DVA
```

Where DVA (Debt Valuation Adjustment) replaces the counterparty's default probability and exposure profile with Apex's own default probability and the counterparty's exposure to Apex (the negative replacement cost):

```
DVA = (1 − R_Apex) × ∫₀ᵀ ENE(t) × dPD_Apex(t)
```

Where `ENE(t)` = Expected Negative Exposure = E^Q[min(V(t), 0)], i.e., the expected amount Apex owes to the counterparty.

### 4.2 Credit Curve Calibration

Counterparty default intensities λ(t) are bootstrapped from the CDS spread term structure:

```
s(T) ≈ (1 − R) × λ    [for flat hazard rate approximation]
```

For a flat hazard rate:
```
PD(0, T) = 1 − exp(−λT)    where  λ = s / (1 − R)
```

For counterparties without observable CDS:
- **Proxy mapping**: assign counterparty to a peer group (sector × rating × geography); use average CDS spread of observable peers
- **Internal PD**: for loan counterparties with internal ratings, map PD to an implied spread using the relationship: `s ≈ PD × LGD / (1 − PD × LGD × tenor)`

### 4.3 Exposure Simulation

Expected Exposure is computed via Monte Carlo simulation:

1. **Simulate market risk factors** under risk-neutral measure: interest rates (multi-factor HJM or LMM), FX rates (GBM), equity prices (GBM with stochastic vol), commodity prices
2. **Re-price all trades** in each netting set on each simulation path at each time step
3. **Apply netting**: sum trades within each legally enforceable netting set
4. **Apply collateral**: subtract collateral balance (accounting for minimum transfer amounts, thresholds, and margin period of risk)
5. **Compute EE**: average of positive exposures across paths at each time step

**Simulation parameters**:
- Number of paths: 10,000 (production); 1,000 (intraday approximation)
- Time steps: monthly for first 2 years; quarterly thereafter; semi-annual beyond 10 years
- Interest rate model: 2-factor Hull-White (calibrated to swaption implied vols)
- FX model: GBM with local vol surface (calibrated to FX option market)
- Correlation structure: 47×47 correlation matrix estimated from 5-year historical data, stressed in adverse scenarios

### 4.4 Wrong-Way Risk (WWR)

Wrong-way risk arises when counterparty creditworthiness deteriorates precisely when exposure is highest — the worst possible combination.

**General WWR**: systematic correlation between market risk factors and credit spreads, captured in the simulation by correlating the counterparty's hazard rate process with relevant market factors.

**Specific WWR**: direct relationship between exposure and credit quality of a specific counterparty (e.g., a swap referencing the counterparty's own stock, or an FX forward with a sovereign where the FX rate and sovereign credit are highly correlated).

For specific WWR, exposure and default probability are jointly simulated using a bivariate diffusion:

```
dλ(t) = κ(θ − λ(t))dt + σ_λ dW_λ(t)
dV(t) = μ_V dt + σ_V dW_V(t)

dW_λ · dW_V = ρ_WWR dt
```

Where `ρ_WWR` is estimated from historical correlation between CDS spreads and derivative value for that counterparty.

### 4.5 Literature References

- Gregory, J. (2012). *Counterparty Credit Risk and Credit Value Adjustment*. Wiley Finance.
- Pykhtin, M., Zhu, S. (2007). "A Guide to Modelling Counterparty Credit Risk." *GARP Risk Review*, July/August 2007.
- BCBS (2015). *Review of the Credit Valuation Adjustment Risk Framework*. Basel Committee on Banking Supervision.
- Brigo, D., Capponi, A. (2010). "Bilateral Counterparty Risk with Application to CDSs." *Risk Magazine*, March 2010.
- Hull, J., White, A. (2012). "The FVA Debate." *Risk Magazine*, July 2012 (for context on DVA controversy).

---

## 5. DATA REQUIREMENTS AND GOVERNANCE

### 5.1 Input Data Sources

| Data Item | Source | Frequency | Fallback |
|---|---|---|---|
| CDS spread term structures | Bloomberg CDSW / Markit | Daily EOD | Prior day + spread adjustment |
| Interest rate curves (SOFR, EURIBOR, etc.) | Bloomberg / Internal treasury curves | Intraday | Prior EOD curve |
| FX spot and forward rates | WM/Reuters 4pm fix | Daily | Bloomberg BGN |
| Equity prices | Exchange feeds | Real-time | Prior close |
| Implied volatility surfaces | Bloomberg OVDV | Daily | Prior day + ATM adjustment |
| Trade/netting set data | Front office systems (Murex) | Real-time | Last confirmed booking |
| CSA / collateral terms | ISDA Master Agreement database | On CSA amendment | Legal review required |
| Recovery rate assumptions | Credit risk database | Quarterly review | 40% senior unsecured default |
| Historical correlations | Risk data warehouse | Monthly recalibration | 3-year lookback minimum |

### 5.2 Data Quality Requirements

- CDS spread completeness: ≥ 95% of counterparty PDs must come from observable CDS or proxy; ≤ 5% from internal PD mapping
- Proxy mapping staleness: proxy assignments reviewed quarterly; any peer group with average CDS age > 5 business days triggers alert
- Trade completeness: 100% of trades in scope must be loaded to CVA system within T+1 of execution; same-day for trades > $100M notional
- CSA terms: any CSA amendment must be reflected in CVA system within 2 business days of legal execution

### 5.3 BCBS 239 Data Lineage

Every CVA output must be traceable to:
1. Underlying trade data (trade ID, booking system record)
2. Market data snapshot (time-stamped Bloomberg/Markit pull)
3. Model version (CVA model version tag applied at run time)
4. Netting set assignment (legal review date of ISDA MA)

Lineage is captured in the risk data warehouse with immutable audit log. Regulators (ECB / Fed) can request full lineage for any CVA figure within 4 hours.

### 5.4 Lookback Period

- Correlation estimation: 5-year rolling window (approximately 1,250 business days), with exponential weighting (half-life 500 days) to weight recent data more heavily without fully discarding the 2020 COVID episode
- Stressed correlation (used in adverse scenario): 2008 GFC window (January 2007 – December 2009)

---

## 6. METHODOLOGY AND IMPLEMENTATION

### 6.1 Production Run Schedule

| Run Type | Timing | Paths | Purpose |
|---|---|---|---|
| Intraday indicative | Every 2 hours | 1,000 | Trader pricing / limit monitoring |
| EOD official | 18:00 EST | 10,000 | IFRS 13 P&L, regulatory reporting |
| Weekly stressed | Saturday | 20,000 | Stressed CVA for ICAAP |
| Scenario | On demand | 5,000 | New trade pre-approval |

### 6.2 Computational Architecture

CVA computation is computationally intensive: 10,000 paths × 30 time steps × ~15,000 active trades × re-pricing = approximately 4.5 billion pricing evaluations per EOD run.

Implementation uses:
- **GPU acceleration** (NVIDIA A100) for Monte Carlo path generation and trade repricing
- **Vectorised numpy/cupy** for exposure aggregation
- **Parallelisation** by netting set (embarrassingly parallel)
- **Approximation**: linear exposure approximation (first-order Taylor expansion around current market) for small trades below $5M notional

EOD runtime target: ≤ 45 minutes. Breach of this target triggers automatic alert to technology team.

### 6.3 Netting and Collateral Logic

```
Exposure(t, path) = max( Σ_trades V_i(t, path) − Collateral(t, path), 0 )
```

Collateral balance at time t is computed as:
```
Collateral(t) = Collateral(0) + Σ margin calls settled up to (t − MPoR)
```

Where MPoR = Margin Period of Risk = 10 business days (regulatory minimum for daily margined counterparties; 20 days for weekly margined).

Minimum Transfer Amount (MTA) and thresholds are applied per CSA terms. For uncollateralised counterparties, Collateral(t) = 0 throughout.

### 6.4 SA-CVA Capital Calculation

Under Basel III SA-CVA, the capital charge is computed from CVA sensitivities:

```
K_SA-CVA = m_CVA × √[ Σ_b [ ρ × Σ_k WS_k,b ]² + (1-ρ²) × Σ_k WS²_k,b ]
```

Where:
- `m_CVA` = 1.25 (supervisory scalar)
- `ρ` = prescribed intra-bucket correlation
- `WS_k,b` = weighted sensitivity of CVA to risk factor k in bucket b
- Sensitivities computed by bumping each risk factor ±1bp and recomputing CVA

---

## 7. MODEL TESTING AND BACKTESTING

### 7.1 Backtesting Methodology

CVA cannot be directly backtested against realized losses (default events are rare). Instead, the model is validated through:

**Proxy backtesting**: Compare CVA P&L (the daily change in CVA) against what would be predicted by CVA Greeks × observed market moves (P&L explain). Unexplained CVA P&L > 10% of total on more than 5 days in a quarter triggers model review.

**EE Profile validation**: Compare model-generated Expected Exposure profile for a representative vanilla IRS portfolio against:
1. Independent analytical solution (known closed-form for simple cases)
2. Industry benchmark calculation (ORE — Open Source Risk Engine)
3. Regulatory benchmark exercises when published by ECB/SSM

**Credit spread sensitivity (CS01) validation**: Bump each counterparty's CDS spread by 1bp and compare model CS01 against analytical approximation:

```
CS01 ≈ ΔCVAₚₑᵣ₁ₚ₊ / 0.01% ≈ (1 − R) × Duration_weighted_EE × PD_density
```

Agreement threshold: model CS01 within 5% of analytical estimate for 95% of counterparties.

### 7.2 Comparison Against Benchmark

The ORE (Open Source Risk Engine, QuantLib-based) is maintained as an independent benchmark. Quarterly full-portfolio comparison:
- EE profiles: ≤ 3% mean absolute deviation
- CVA point estimate: ≤ 5% relative deviation
- CS01: ≤ 5% relative deviation

### 7.3 Stress Testing

**Stress scenarios applied to CVA model itself:**

| Scenario | CDS Spread Shock | IR Shock | CVA Impact (estimated) |
|---|---|---|---|
| IG counterparties widen 100bp | +100bp | 0 | +$420M |
| HY counterparties widen 500bp | +500bp | 0 | +$180M |
| Correlation breakdown (all correlations → 1.0) | 0 | 0 | +$340M |
| WWR activation (top 10 counterparties) | +200bp | 0 | +$290M |
| Combined stress (GFC analog) | +300bp IG / +800bp HY | +200bp | +$1.1B |

---

## 8. PERFORMANCE METRICS AND CALIBRATION STANDARDS

### 8.1 Primary Performance Metrics

| Metric | Definition | Acceptable Range | Action if Breached |
|---|---|---|---|
| CVA P&L Explain | (Greeks × moves) / Total CVA P&L change | > 85% | Investigate within 2 business days |
| EE Benchmark Deviation | Model EE vs. ORE benchmark | < 5% relative | Formal model review within 30 days |
| CS01 Accuracy | Model vs. analytical approximation | < 5% relative | Desk notification; review within 15 days |
| Computation Time (EOD) | Wall clock time for 10K path run | < 45 minutes | Technology escalation |
| CDS Data Completeness | % counterparty PDs from observable CDS | > 95% | Data quality alert; proxy review |

### 8.2 Recalibration Schedule

- **Correlation matrix**: Monthly recalibration using rolling 5-year window
- **Credit curves**: Daily (automatic, from Bloomberg/Markit feeds)
- **Volatility surfaces**: Daily (automatic)
- **Recovery rate assumptions**: Quarterly review by Credit Risk Officer
- **WWR parameters**: Semi-annual, or immediately following a significant counterparty credit event

### 8.3 Failure Criteria

The model is considered to have failed if any of the following occur:
1. CVA P&L explain < 70% for three consecutive business days
2. EE benchmark deviation > 15% on a full portfolio comparison
3. EOD run fails to complete within 2 hours (SLA breach)
4. Data completeness drops below 90% for more than 2 consecutive days
5. Model produces negative CVA for a counterparty without a contractual explanation (indicates sign error)

---

## 9. LIMITATIONS, ASSUMPTIONS, AND KNOWN WEAKNESSES

### 9.1 Assumption: Fixed Recovery Rate

**The assumption**: Recovery is fixed at 40% for senior unsecured counterparties.

**Why it may fail**: Recovery rates are highly variable in practice. Average recovery on senior unsecured bonds varies from 20% to 70% depending on industry, jurisdiction, and economic cycle. In a systemic crisis, recoveries fall materially below historical averages (average recovery during 2008-2009 was approximately 28%).

**Compensating control**: Conservative floor: recovery is floored at 35% in stressed scenario runs. Desk has override capability for specific counterparties with collateral or structural seniority considerations.

### 9.2 Assumption: Independent Defaults (No Contagion)

**The assumption**: Counterparty default events are driven by idiosyncratic factors only, captured by individual CDS spreads. The model does not explicitly simulate contagion — where one counterparty's default increases the probability of another's.

**Why it may fail**: In systemic events, financial institution counterparties tend to become highly correlated. A bank counterparty network where each institution holds significant exposure to the others creates potential for cascade. Lehman's default in 2008 nearly triggered cascade failures.

**Compensating control**: The "Correlation Breakdown" stress scenario (correlations set to 1.0 across all counterparties) serves as a bound on this risk. In addition, portfolio concentration limits (single-counterparty PFE limit) reduce tail contagion exposure.

### 9.3 Assumption: Static Netting Set

**The assumption**: The composition of the netting set (which trades are included) is fixed at valuation date. In reality, new trades are added and existing trades mature continuously.

**Why it may fail**: A large new trade added after valuation date could materially change the exposure profile. The 2-day settlement lag for trade booking means there is always a small window of exposure not captured.

**Compensating control**: Same-day booking requirement for trades > $100M notional, with manual CVA adjustment same day.

### 9.4 Numerical Approximation: Linear Exposure for Small Trades

For trades below $5M notional, the model uses a first-order Taylor approximation to EE rather than full repricing. This is computationally necessary (approximately 40% of trades by count but only 2% of gross notional).

**Error bound**: Analysis on representative sample shows approximation error < 1% of CVA contribution for this segment. Acceptable for the computational saving.

### 9.5 Model Risk from Proxy CDS Spreads

Approximately 8% of counterparties (by count; 3% by CVA contribution) lack observable CDS and rely on proxy spreads from peer groups. Proxy basis risk — the divergence between the proxy and the actual counterparty's creditworthiness — is unobservable and therefore unquantifiable by construction.

**Compensating control**: 25% add-on to CVA for all proxy-mapped counterparties. Proxy mapping reviewed quarterly.

---

## 10. COMPENSATING CONTROLS AND RISK MITIGANTS

| Risk | Control | Owner |
|---|---|---|
| Wrong-way risk underestimation | WWR module with explicit correlation; stress scenarios | XVA Quant Team |
| Recovery rate error | Conservative floor (35%); quarterly review | Credit Risk Officer |
| Proxy CDS spread error | 25% CVA add-on for proxy counterparties | XVA Quant Team |
| Model correlation instability | Stressed correlation scenario (all correlations = 1) | Market Risk Officer |
| Booking lag (new trades) | Mandatory same-day booking for trades > $100M | Operations |
| Computation failure | Manual backup using prior-day CVA + Greeks × moves | XVA Technology |
| Contagion/cascade risk | Counterparty concentration limits; stress testing | Credit Risk Officer |

### 10.1 CVA Hedging

The CVA desk actively hedges CVA sensitivities:
- **Credit delta (CS01)**: hedged via single-name CDS or CDS indices (CDX IG, iTraxx Main)
- **Interest rate delta (DV01)**: hedged via interest rate swaps
- **FX delta**: hedged via FX forwards

Hedging effectiveness is monitored daily via the P&L explain framework. Residual unhedged CVA (primarily illiquid counterparties without liquid CDS instruments) is disclosed separately in risk reports.

### 10.2 Model Reserve

A model reserve of **$45 million** is held against CVA model uncertainty, covering:
- Proxy spread basis risk ($15M)
- Wrong-way risk model simplification ($20M)
- Recovery rate uncertainty ($10M)

---

## 11. CHANGE MANAGEMENT

### 11.1 Material Change Definition

A material change to the CVA model is defined as any of the following:
- Change in simulation methodology (e.g., number of risk factors, correlation structure)
- Change in collateral treatment or MPoR assumption
- Change in WWR model specification
- Recalibration that changes the portfolio CVA by more than 5%
- Change in scope (adding new product types to CVA computation)

Material changes require full re-validation by the Model Risk Officer before production deployment.

### 11.2 Minor Change Definition

Non-material changes (new counterparty added, CDS proxy group reassignment, computational optimisation with no methodology change) may be deployed via an expedited review process with MRO notification within 5 business days.

### 11.3 Emergency Patch Procedure

In the event of a production failure or material data error:
1. Interim CVA estimate produced using prior-day CVA + Greeks × observed moves (manual calculation)
2. Root cause identified within 4 hours
3. Patch deployed and validated by XVA team lead
4. MRO notified same day
5. Full incident report filed within 5 business days

---

## 12. APPROVALS AND SIGN-OFF

| Role | Name | Status | Date |
|---|---|---|---|
| Model Developer | XVA Quant Team | ✓ Submitted | March 2026 |
| Model Risk Officer | Dr. Rebecca Chen | ⏳ Pending Validation | — |
| Chief Risk Officer | Dr. Priya Nair | ⏳ Pending MRO Approval | — |
| Business Owner | James Okafor | ⏳ Pending CRO Approval | — |
| Regulatory Capital | Finance / Reg Reporting | ⏳ Pending | — |

**Business Owner Acknowledgment of Limitations (to be completed upon approval):**
> "I acknowledge the limitations described in Section 9, including the fixed recovery rate assumption, the proxy CDS spread add-on for approximately 8% of counterparties, and the absence of explicit contagion modelling. I accept the compensating controls described in Section 10 as adequate mitigants for current business use."

---

*Document Classification: RESTRICTED — Model Risk Sensitive*
*Apex Global Bank | Quantitative Research Division | XVA Team*
*Next scheduled review: March 2027 (or upon material model change)*
