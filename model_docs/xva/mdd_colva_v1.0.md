# Model Development Document
# Collateral Valuation Adjustment (ColVA) — Version 1.0
# Apex Global Bank | Quantitative Research Division
# Classification: RESTRICTED — Model Risk Sensitive
# SR 11-7 Section Reference: Model Development

---

## 1. DOCUMENT METADATA

| Field | Value |
|---|---|
| **Model Name** | Collateral Valuation Adjustment (ColVA) |
| **Model ID** | APEX-MDL-0013 |
| **Version** | 1.0 |
| **Status** | In Validation |
| **Risk Tier** | Tier 2 |
| **Regulatory Framework** | IFRS 13 Fair Value; ISDA Master Agreement / CSA |
| **Date of Development** | March 2026 |
| **Business Owner** | Head of Global Markets Trading (James Okafor) |
| **Model Developer** | Quantitative Research — XVA Team |
| **MRO Review** | Pending — Dr. Rebecca Chen |
| **CRO Approval** | Pending — Dr. Priya Nair |

### 1.1 Version History

| Version | Date | Change Summary |
|---|---|---|
| 0.1 | Jan 2026 | Initial framework — CTD currency optionality only |
| 0.8 | Feb 2026 | Added rehypothecation value; multi-currency CSA |
| 1.0 | Mar 2026 | Production candidate; submitted for validation |

---

## 2. EXECUTIVE SUMMARY

### 2.1 Model Purpose

ColVA (Collateral Valuation Adjustment) captures the present value of optionality embedded in Credit Support Annexes (CSAs) governing collateral arrangements for OTC derivatives. The primary source of ColVA is the **cheapest-to-deliver (CTD) option**: when a CSA permits the collateral posting party to deliver collateral in any of several eligible currencies, that party will always choose the currency that is cheapest in terms of its own funding cost relative to the collateral rate paid. This embedded option has quantifiable economic value.

ColVA is classified as **Tier 2** within Apex's model inventory. While economically real, it is smaller in magnitude and less data-intensive than the Tier 1 XVA models (CVA, FVA, MVA). Nevertheless, for transactions where ColVA is material — large cross-currency interest rate swaps with multi-currency CSAs — it must be priced into client derivatives quotes and reflected in daily P&L.

### 2.2 Components of ColVA

ColVA has three primary components:

1. **CTD Currency Option (dominant)**: The value to the posting party of being able to switch the currency of posted collateral to whichever is cheapest at the time of posting. For a 10-year EUR/USD cross-currency swap with a multi-currency CSA, this option can be worth 3–8 basis points of notional.

2. **Substitution Option**: The right to substitute previously posted collateral (e.g., replace USD cash with EUR cash). This is only valuable when the relative cheapness of currencies changes after initial posting.

3. **Rehypothecation Value**: When a CSA permits the collateral receiver to re-use posted collateral (e.g., post it as margin to a third party), the receiver captures additional funding benefit. The value of this right depends on the receiver's cost of funding relative to the collateral rate.

### 2.3 Output Description

- **ColVA per new trade**: Priced into client derivatives quotes for transactions with multi-currency CSAs
- **Portfolio ColVA**: Daily P&L impact, reported in income statement under XVA line
- **CTD option decomposition**: By currency pair, to inform collateral optimisation decisions
- **ColVA by counterparty**: For counterparties with multi-currency CSA agreements

### 2.4 Key Assumptions

- The posting party will always exercise the CTD option optimally (rational collateral manager assumption)
- Currency basis swap spreads are the correct proxy for the cost differential between posting in different currencies
- The collateral rate paid on cash collateral is overnight index rate (SOFR, ESTR, SONIA) in the respective currency
- Substitution rights are exercised only when the CTD currency changes (no partial exercise)
- The collateral pool is not subject to haircuts for the base calculation (haircut variant available separately)

### 2.5 Known Limitations

- The model assumes the CSA counterparty does not strategically withhold consent to substitution — in practice, substitution may be delayed or refused
- Rehypothecation value is estimated using a simplified funding benefit; actual benefit depends on Apex's real-time collateral deployment strategy
- The model does not capture operational costs of currency switching (FX transaction costs, settlement risk)
- Correlation between the portfolio's mark-to-market value and currency basis spreads (a form of wrong-way risk) is modelled via historical correlation but not stress-tested independently

---

## 3. BUSINESS CONTEXT AND PURPOSE

### 3.1 The CSA Optionality Problem

A Credit Support Annex specifies the legal terms under which collateral is posted and received between counterparties. Many CSAs negotiated between Apex and its dealers specify that variation margin may be posted in any of several eligible currencies — typically USD, EUR, GBP, JPY, and CHF. The posting party (whichever counterparty has a net out-of-the-money position) always posts the currency that costs it the least.

The cost of posting collateral in currency X is:
```
Posting cost (X) = Funding cost of X − Collateral rate received on X
```

If Apex can fund USD at SOFR + 55bp but only receives SOFR on posted USD collateral, while it can fund EUR at ESTR + 40bp and receives ESTR on EUR collateral, the net cost differential is:
```
USD cost = 55bp;   EUR cost = 40bp → EUR is CTD by 15bp
```

Apex will post EUR, saving 15bp per annum on the collateral notional. Over the life of a 10-year swap, this saving — and the option to switch currencies if the differential changes — is the ColVA.

### 3.2 Market Context

Multi-currency CSAs became the industry standard in the 2010s as banks sought to optimise their collateral pools following the increased margin demands of the post-GFC regulatory environment. ISDA's 2016 Credit Support Annex for Variation Margin (VM-CSA) standardised the framework, but left currency eligibility as a negotiated term.

The theoretical framework for CTD option pricing was established by Fujii, Shimada, and Takahashi (2010) and subsequently refined by Piterbarg (2010) in the context of derivatives valuation under CSA. The practical implementation at major dealers — including Apex — followed shortly after.

### 3.3 Model Users

- **Front Office Pricing**: ColVA charge (or benefit, for the receiving party) included in price of derivatives with multi-currency CSAs
- **Collateral Management**: CTD decomposition informs which currency to post on a given day
- **Finance / P&L**: Daily ColVA P&L recognised in income statement under XVA line

---

## 4. THEORETICAL FOUNDATION

### 4.1 The CTD Option Value

The value of the CTD option for a single time step [t, t+Δt] in the risk-neutral measure is:

```
CTD_value(t) = E[max(c₁(t), c₂(t), ..., cₙ(t)) − c_base(t)] × Collateral(t) × Δt × D(0,t)
```

Where:
- `cᵢ(t)` = net funding benefit of posting in currency i at time t
- `c_base(t)` = net funding benefit of posting in the base currency (USD)
- `Collateral(t)` = expected collateral balance at time t (= expected absolute exposure, accounting for CSA terms)
- `D(0,t)` = OIS discount factor

The portfolio ColVA integrates over the life of all transactions:

```
ColVA = Σᵢ D(0,tᵢ) × E[max(c₁(tᵢ), c₂(tᵢ), ..., cₙ(tᵢ)) − c_USD(tᵢ)] × |V(tᵢ)| × Δtᵢ
```

Where `|V(t)|` is the absolute portfolio value (collateral balance under full collateralisation).

### 4.2 Currency Basis Swap Spread as CTD Proxy

The cost differential between posting in two currencies is proxied by the **cross-currency basis swap spread**. For EUR vs. USD:

```
CTD_spread_EUR_USD(t) = s_f_USD(t) − s_f_EUR(t) − xccy_basis_EUR_USD(t)
```

Where `xccy_basis` is the cross-currency basis (EUR/USD, EUR pays ESTR, USD receives SOFR + xccy basis; a negative basis means EUR is more expensive to source, reducing the CTD benefit of posting EUR).

In current market conditions (March 2026):
- EUR/USD xccy basis: −15bp (EUR at a premium to USD in cross-currency swaps)
- GBP/USD xccy basis: −8bp
- JPY/USD xccy basis: −45bp (JPY historically cheap to post, but Apex rarely holds JPY)

The CTD option is therefore currently dominated by the EUR vs. USD decision for most of Apex's derivatives book.

### 4.3 Stochastic Model for Basis Spreads

Cross-currency basis spreads are mean-reverting with stochastic volatility. Apex models them using an Ornstein-Uhlenbeck process:

```
d(xccy_basis) = κ × (θ − xccy_basis) × dt + σ × dW
```

Parameters calibrated to 5-year historical data:
- EUR/USD: κ = 0.3, θ = −12bp (long-run mean), σ = 8bp/√year
- GBP/USD: κ = 0.4, θ = −7bp, σ = 6bp/√year
- JPY/USD: κ = 0.2, θ = −38bp, σ = 12bp/√year

The OU model is jointly simulated with the interest rate model (Hull-White, shared with CVA simulation infrastructure) to capture the correlation between interest rate movements and currency basis dynamics.

### 4.4 Rehypothecation Value

When Apex receives collateral under a CSA that permits rehypothecation, Apex can re-use that collateral — for example, posting it as margin at a CCP. The value of this right is:

```
Rehypo_value = Σᵢ D(0,tᵢ) × E[Collateral_received(tᵢ)] × (s_f − r_OIS) × Δtᵢ
```

Where `s_f − r_OIS` is Apex's benefit from using received collateral rather than borrowing in the unsecured market. At current funding spreads (55bp), the rehypothecation value is modest but non-zero.

**Rehypothecation is only relevant when Apex is the net receiver of collateral** (i.e., when the portfolio is in-the-money for Apex). For out-of-the-money positions, Apex is the poster, not the receiver.

### 4.5 Literature References

- Piterbarg, V. (2010). "Funding Beyond Discounting: Collateral Agreements and Derivatives Pricing." *Risk Magazine*, February 2010.
- Fujii, M., Shimada, Y., Takahashi, A. (2010). "A Note on Construction of Multiple Swap Curves with and without Collateral." *CARF Working Paper*.
- Antonov, A., Bianchetti, M. (2011). "Pricing Swaps and Options on Quadratic Gaussian Spreads." *SSRN Working Paper*.
- Kenyon, C., Stamm, R. (2012). *Discounting, LIBOR, CVA and Funding: Interest Rate and Credit Pricing*. Palgrave Macmillan.
- ISDA (2016). *2016 Credit Support Annex for Variation Margin (VM)*.

---

## 5. DATA REQUIREMENTS AND GOVERNANCE

### 5.1 Input Data Sources

| Data Item | Source | Frequency |
|---|---|---|
| Cross-currency basis swap spreads | Bloomberg / Markit | Daily |
| OIS rates (SOFR, ESTR, SONIA, TONAR) | Bloomberg / Internal | Daily |
| Apex funding curve (all currencies) | Treasury / Bloomberg | Daily |
| CSA terms database (eligible currencies, haircuts) | ISDA MA database | On amendment |
| Portfolio exposures / absolute MtM | CVA model Monte Carlo engine | Daily (shared run) |
| FX spot rates | Bloomberg | Real-time (EOD snapshot for ColVA) |

### 5.2 CSA Terms Database

The ColVA model is critically dependent on the accuracy of the CSA terms database, which records:
- Eligible currencies for VM posting (by counterparty)
- Haircuts by currency and asset class
- Rehypothecation rights (yes/no, by counterparty)
- Substitution notice periods (same-day, T+1, T+2)

The CSA terms database is maintained by the Legal/ISDA documentation team. Any change to a counterparty's CSA terms (amendment, new agreement) must be reflected in the database within one business day. The ColVA model validates against the database on each daily run and will flag missing or stale CSA records.

### 5.3 Data Governance

ColVA shares the CVA model's simulation infrastructure (same paths, same exposure profiles). The incremental computation is the CTD option value applied to those exposure profiles.

Cross-currency basis spreads are sourced from Bloomberg (primary) and Markit (secondary). Any day where the spread difference between sources exceeds 5bp triggers a data quality alert and defaults to the prior-day value with a staleness flag.

---

## 6. METHODOLOGY AND IMPLEMENTATION

### 6.1 Shared Simulation Infrastructure

ColVA runs as an extension of the CVA simulation:
1. CVA simulation produces `E[|V(t)|]` (expected absolute exposure) at each time step — this is the collateral balance
2. ColVA applies the CTD option value to this collateral profile
3. The CTD option value at each time step comes from the OU basis spread model (jointly simulated paths)

The joint simulation ensures that the correlation between market movements (which drive portfolio MtM) and currency basis dynamics (which drive CTD optionality) is captured.

### 6.2 Multi-Currency CSA Classification

Counterparties are classified into three tiers for ColVA purposes:

| Tier | CSA Type | Treatment |
|---|---|---|
| A | USD-only CSA (no currency optionality) | ColVA = 0 |
| B | Bilateral multi-currency CSA (2-3 eligible currencies) | Full CTD model |
| C | ISDA Standard multi-currency (5+ eligible currencies) | Full CTD model with all pairs |

Approximately 35% of Apex's derivatives notional is with Tier B or C counterparties. These counterparties generate essentially all of Apex's ColVA.

### 6.3 Collateral Optimisation vs. Valuation

ColVA is a **valuation** model, not a **collateral optimisation** model. It answers the question: "What is the fair value of the CTD option?" It assumes optimal future exercise but does not instruct the collateral management team which currency to post today.

The Collateral Management team (under Treasury) runs a separate optimisation model to determine the daily posting currency. ColVA and the optimisation model share data inputs but are governed separately.

### 6.4 Dealing with Haircuts

When a CSA specifies haircuts (e.g., non-cash collateral such as government bonds receives a 2% haircut), the effective collateral balance is:

```
Effective_Collateral = MtM_exposure × (1 / (1 − haircut))
```

For example, posting a bond with a 2% haircut requires posting 102% of the cash equivalent exposure. This increases the cost of posting and must be factored into the CTD calculation. In practice, cash collateral (with no haircut) dominates Apex's VM posting and the haircut adjustment is small.

---

## 7. MODEL TESTING AND BACKTESTING

### 7.1 CTD Option Sensitivity

The ColVA CTD option is most sensitive to:
1. **Basis spread level**: ±10bp shift in EUR/USD xccy basis changes portfolio ColVA by ~$4M
2. **Basis spread volatility**: Higher volatility increases the option value (convexity effect)
3. **Portfolio duration**: Longer-dated trades have more CTD optionality

Sensitivity analysis conducted quarterly and reported to MRO.

### 7.2 Benchmark Comparison

A simplified closed-form approximation for the CTD option value uses the Margrabe (1978) exchange option formula:

```
CTD_approx = Collateral_avg × Margrabe(s₁, s₂, σ_basis, T)
```

Where `σ_basis` is the volatility of the basis spread differential. Agreement threshold: within 15% of full simulation result. (Wider tolerance than CVA given the simpler nature of the instrument being modelled.)

### 7.3 P&L Attribution

Daily ColVA P&L is attributed to:
- Change in basis spreads (delta)
- Change in portfolio exposure (new trades, maturities, market moves)
- Passage of time (theta)

P&L explain > 75% of total ColVA daily change. Lower threshold than CVA/FVA because basis spread moves can be idiosyncratic and difficult to predict intraday.

---

## 8. PERFORMANCE METRICS AND CALIBRATION STANDARDS

| Metric | Acceptable Range | Action if Breached |
|---|---|---|
| ColVA P&L Explain | > 75% | Investigate within 3 business days |
| Benchmark deviation (Margrabe) | < 15% relative | Review within 30 days |
| Basis spread staleness | No spread > 3 business days old | Data quality alert |
| CSA database completeness | > 98% of active counterparties | Legal/documentation escalation |

### 8.1 Recalibration Schedule

- **Basis spread OU parameters**: Annual recalibration using rolling 5-year data
- **Correlation (portfolio MtM vs. basis)**: Annual recalibration
- **Simulation paths (shared with CVA)**: No independent recalibration; reviewed annually

---

## 9. LIMITATIONS, ASSUMPTIONS, AND KNOWN WEAKNESSES

### 9.1 Optimal Exercise Assumption

ColVA assumes the posting party always exercises the CTD option optimally. In practice:
- Collateral operations teams may not switch currencies daily due to operational friction
- Currency substitution requires counterparty consent and may face delays
- FX transaction costs eat into the basis spread advantage for small moves

**Compensating control**: The model applies an operational discount factor of 85% to the theoretical CTD value, estimated from historical analysis of Apex's actual posting behaviour vs. the optimal theoretical posting. This discount is reviewed annually.

### 9.2 Rehypothecation Risk

The rehypothecation value assumes Apex can always deploy received collateral at its full funding benefit. In a stress scenario:
- Received collateral may be legally encumbered and unavailable for rehypothecation
- The collateral receiver's funding benefit may differ from Apex's unsecured spread

**Compensating control**: Rehypothecation value (currently ~$8M of total ColVA) is disclosed separately and conservatively estimated.

### 9.3 CSA Amendment Risk

If a counterparty amends its CSA to remove multi-currency optionality (e.g., mandating USD-only posting), the ColVA for that counterparty drops to zero immediately. A large counterparty switching to a USD-only CSA could reduce portfolio ColVA by $5–15M.

**Compensating control**: Legal team notifies the XVA desk within one business day of any CSA amendment. Day-1 recalculation triggered automatically.

### 9.4 Basis Spread Jump Risk

The OU model captures mean-reversion but not jumps in currency basis spreads. During the COVID-19 stress event (March 2020), EUR/USD xccy basis widened by 45bp in a single day — well outside the model's diffusive dynamics. This would cause ColVA to be underestimated during stress events.

**Compensating control**: Stressed ColVA is computed using basis spreads at their 95th percentile of historical 1-month widening. Disclosed in quarterly risk report.

---

## 10. COMPENSATING CONTROLS

| Risk | Control | Owner |
|---|---|---|
| Suboptimal exercise | 85% operational discount factor; annual review | XVA Quant Team |
| Basis spread staleness | 3-day staleness alert; prior-day fallback | Market Data |
| CSA database gaps | 98% completeness threshold; legal escalation | Legal / Documentation |
| Basis jump risk | Stressed ColVA at 95th percentile spread widening | XVA Quant Team |
| Rehypothecation overstatement | Separate disclosure; conservative estimate | XVA Quant Team / Treasury |
| Shared simulation failure | ColVA unavailable if CVA run fails; fallback using prior-day + basis delta | XVA Technology |

### 10.1 Model Reserve

A model reserve of **$6 million** is held against ColVA model uncertainty:
- Optimal exercise discount factor uncertainty: $3M
- Basis spread model mis-specification: $2M
- CSA database completeness: $1M

The ColVA reserve is small relative to CVA ($45M) and FVA ($25M), reflecting the Tier 2 classification of the model.

---

## 11. RELATIONSHIP TO OTHER XVA MODELS

ColVA interacts with the other XVA models in the following ways:

| XVA | Interaction with ColVA |
|---|---|
| **CVA** | Shares Monte Carlo simulation paths and EPE/ENE profiles |
| **FVA** | FVA and ColVA both depend on the funding spread; if Apex's funding spread changes, both are affected. No double-counting: FVA applies to uncollateralised positions; ColVA applies to the optionality within collateralised positions |
| **MVA** | MVA applies to initial margin (for uncleared derivatives); ColVA applies to variation margin optionality. Separate models |
| **DVA** | No direct interaction; ColVA does not depend on Apex's own default probability |

The XVA aggregation report (produced daily) shows CVA + DVA + FVA + MVA + ColVA as a single XVA total, with individual components disclosed separately for risk management purposes.

---

## 12. CHANGE MANAGEMENT

Material changes (new CSA currency types, change to OU model specification, integration with new simulation infrastructure) require full MRO re-validation. Non-material changes (calibration updates, new counterparty CSA loaded into database) via expedited review with 3-business-day notification.

---

## 13. APPROVALS AND SIGN-OFF

| Role | Name | Status | Date |
|---|---|---|---|
| Model Developer | XVA Quant Team | ✓ Submitted | March 2026 |
| Model Risk Officer | Dr. Rebecca Chen | ⏳ Pending | — |
| Chief Risk Officer | Dr. Priya Nair | ⏳ Pending | — |
| Business Owner | James Okafor | ⏳ Pending | — |

---

*Document Classification: RESTRICTED — Model Risk Sensitive*
*Apex Global Bank | Quantitative Research Division | XVA Team*
*Next scheduled review: March 2027 (or upon material model change)*
