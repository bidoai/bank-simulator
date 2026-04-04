# Model Development Document: DFAST / Stress Testing Engine
**Model ID:** APEX-MDL-0015
**Version:** 1.0
**Owner:** Dr. Priya Nair (CRO)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** In Validation
**Last Review:** 2026-04-01 | **Next Review:** 2027-04-01
**Regulatory:** 12 CFR 252 (Regulation YY), Dodd-Frank Act §165(i), SR 12-7, SR 11-7

---

## 1. Model Overview

### Purpose
The DFAST/Stress Testing Engine projects Apex Global Bank's CET1 capital ratio over a 9-quarter forward horizon under three macroeconomic scenarios prescribed by the Federal Reserve (baseline, adverse, severely adverse). The model generates income statement and balance sheet projections quarter by quarter, accumulating losses through credit, market, and operational risk channels.

### Business Use
- **Regulatory submission:** Annual DFAST results submitted to the Federal Reserve under 12 CFR 252.
- **Capital planning:** CET1 ratio projections under stress inform the annual capital plan, dividend policy, and buyback approval.
- **Board and Audit Committee reporting:** Severely adverse scenario CET1 floor used to set management capital buffers.
- **ICAAP / Pillar 2:** Internal stressed capital assessment; stressed CET1 floor used to size the capital conservation buffer above the 4.5% regulatory minimum.
- **Risk appetite setting:** Stress test results anchor the quantitative risk appetite statement (minimum CET1 ≥ 8.0% under adverse; ≥ 6.5% under severely adverse).

### Scope
All material risk types: credit loss (loan portfolio), market risk (trading book P&L), operational loss, PPNR (pre-provision net revenue) haircut, and capital deductions.

---

## 2. Theoretical Basis

### 9-Quarter CET1 Projection

The model projects end-of-quarter CET1 capital:

```
CET1(t) = CET1(t-1) + PPNR(t) - Credit_Loss(t) - Market_Loss(t) - OpRisk_Loss(t)
          - Tax_Effect(t) - Dividend(t) - OCI_Change(t)
```

All quantities are quarterly. Dividends are zeroed in stress (conservative assumption). OCI changes reflect mark-to-market moves on AFS securities.

CET1 ratio at each quarter:
```
CET1_ratio(t) = CET1(t) / RWA(t)
```

RWA evolves with the balance sheet; credit RWA grows as loans migrate to higher-risk stages.

### Macroeconomic Scenario Drivers

The Federal Reserve publishes three scenarios annually. Apex uses five macro variables as primary drivers:

| Variable | Baseline | Adverse | Severely Adverse |
|----------|----------|---------|-----------------|
| Real GDP growth (annual) | +2.1% | -1.5% | -4.8% |
| Unemployment rate (peak) | 4.2% | 6.5% | 10.0% |
| US10Y yield (bps change) | +25bps | -75bps | -100bps |
| Equity market decline (S&P 500) | +5% | -25% | -55% |
| CRE price decline | -2% | -20% | -40% |

### Credit Loss Channel

Per-obligor probability of default is conditioned on macroeconomic variables via the IFRS 9 macro satellite (APEX-MDL-0007):

```
PD_PIT(t) = PD_TTC × exp(β_GDP × ΔGDP(t) + β_UR × ΔUR(t))
```

Quarterly credit loss:
```
CreditLoss(t) = Σ_i PD_PIT_i(t) × LGD_i × EAD_i(t)
```

Stage migration accelerates in severe stress: 30% of Stage 1 loans migrate to Stage 2 in adverse; 50% in severely adverse by Q4.

### Market Risk Channel

Trading book loss under equity shock:

```
MarketLoss_equity(t) = Δ_portfolio × ΔS(t) + ½Γ_portfolio × ΔS(t)²
```

VaR-scaled market loss (adverse/severely adverse quarterly):
```
MarketLoss_VaR(t) = SVaR_baseline × scenario_multiplier(t)
```

Multiplier: 1.5× (adverse), 3.5× (severely adverse).

### PPNR Model

Pre-provision net revenue is modelled as a function of rate environment and economic activity:

```
PPNR(t) = NII(t) + NonInterestIncome(t) - NonInterestExpense(t)
```

NII is projected using the ALM engine (APEX-MDL-0017) repricing gap schedule:
```
NII(t) = Σ_bucket (Asset_yield(bucket,t) - Liability_cost(bucket,t)) × Balance(bucket)
```

In adverse scenarios, fee income is haircut by 20%; in severely adverse by 40%.

### Operational Risk Loss

Operational risk loss applied as a flat quarterly charge calibrated to AMA historical loss data:
```
OpRisk(t) = OpRisk_baseline × (1 + 0.5 × Scenario_severity_index)
```

where severity_index = 0 (baseline), 1 (adverse), 2 (severely adverse).

---

## 3. Mathematical Specification

| Parameter | Value | Source |
|-----------|-------|--------|
| Projection horizon | 9 quarters | 12 CFR 252 |
| Scenarios | 3 (baseline/adverse/severely adverse) | Federal Reserve annual publication |
| Starting CET1 capital | $45.0B | Balance sheet |
| Starting RWA | $346.0B | Regulatory Capital Engine |
| Starting CET1 ratio | 13.0% | |
| Quarterly PPNR (baseline) | $1.2B | ALM / NII model |
| Annual credit loss (severely adverse) | $8.5B | ECL satellite |
| Annual market loss (severely adverse) | $6.0B | SVaR × 3.5× |
| Minimum CET1 floor (regulatory) | 4.5% | 12 CFR 3 |
| Internal risk appetite floor (adverse) | 8.0% | Board risk appetite |
| Internal risk appetite floor (severely adverse) | 6.5% | Board risk appetite |

### Illustrative 9-Quarter CET1 Trajectory (Severely Adverse)

| Quarter | CET1 ($B) | RWA ($B) | CET1 Ratio |
|---------|-----------|----------|------------|
| Q0 (start) | 45.0 | 346.0 | 13.0% |
| Q1 | 42.3 | 352.0 | 12.0% |
| Q2 | 39.1 | 362.0 | 10.8% |
| Q3 | 36.4 | 371.0 | 9.8% |
| Q4 | 34.2 | 378.0 | 9.0% |
| Q5 | 33.0 | 380.0 | 8.7% |
| Q6 | 32.8 | 379.0 | 8.7% |
| Q7 | 33.2 | 376.0 | 8.8% |
| Q8 | 34.1 | 374.0 | 9.1% |
| Q9 | 35.2 | 372.0 | 9.5% |

Trough CET1 ratio: 8.7% (Q5/Q6) — above the 6.5% internal floor. Capital plan adjustment required if trough falls below 8.0%.

---

## 4. Implementation

**Code location:** `infrastructure/stress/dfast_engine.py`
**Class:** `DFASTEngine`
**Key methods:**
- `run_scenario(scenario: str)` → quarterly CET1 trajectory
- `run_all_scenarios()` → all three scenarios
- `get_trough_cet1(scenario)` → minimum CET1 ratio over horizon
- `get_capital_actions_needed(scenario, floor)` → capital shortfall relative to floor

**Integration:**
- Credit losses sourced from `IFRS9ECLEngine.run_scenario(macro_params)`
- Market losses sourced from `VaRCalculator` SVaR × multiplier
- PPNR from `ALMEngine.get_nii_sensitivity()` + static fee/expense model
- Starting capital from `RegulatoryCapitalEngine.get_snapshot()`

**Dashboard:** DFAST CET1 panel in `dashboard/scenarios.html` with Plotly chart; Basel 4.5% minimum line and internal 8% floor line rendered as reference bands.

---

## 5. Validation

**Historical back-testing:** 2020 COVID-19 shock used as ex-post validation: actual CET1 trough (Q2 2020) compared against model projection under severely adverse. Model overstated loss by 8% (conservative).

**Sensitivity analysis:** CET1 trough sensitivity to ±50bps in GDP coefficient and ±1pp in peak unemployment verified to produce monotonic response consistent with economic intuition.

**Benchmarking:** PPNR model benchmarked against Fed-published DFAST results for peer Category III banks; NII sensitivity within ±12% of peer median.

**Regulatory review:** DFAST results subject to Federal Reserve horizontal review; any supervisory adjustment to loss rates is incorporated in the final submission.

---

## 6. Model Limitations

1. **Macro satellite calibration (inherited from APEX-MDL-0007):** β_GDP and β_UR coefficients not post-COVID recalibrated; pandemic non-linearity may understate credit losses in tail scenarios.
2. **Static PPNR model:** Fee income and expense do not dynamically respond to customer behaviour under stress; balance sheet run-off not modelled.
3. **No second-round effects:** Feedback loops (e.g., capital depletion → deleveraging → further credit losses) are not modelled.
4. **Operational risk flat charge:** Does not reflect scenario-specific operational risk drivers (e.g., litigation spike in adverse).
5. **Single macro satellite:** PPNR and credit loss both depend on the same GDP/unemployment satellite; model correlation between loss channels is implicit and may be understated.

---

## 7. Use Authorization

### Authorized Uses
1. **Federal Reserve DFAST submission:** Annual regulatory submission of 9-quarter CET1 projections under 12 CFR 252.
2. **Annual capital plan:** CET1 trough under adverse/severely adverse determines dividend and buyback capacity for Board approval.
3. **Board Risk Committee reporting:** Quarterly stress update against the prior annual submission; deviation > 50bps trough triggers re-run.
4. **ICAAP Pillar 2 capital buffer:** Stressed CET1 floor (severely adverse trough) used to size management capital buffer above regulatory minimum.
5. **Risk appetite statement:** Quantitative floors (CET1 ≥ 8.0% adverse, ≥ 6.5% severely adverse) anchored to DFAST output.

### Prohibited Uses
- **Intraday or tactical risk decisions:** DFAST is a quarterly/annual strategic planning tool; it must not be used for intraday trading limits or desk-level capital allocation.
- **Marketing or investor communications without CFO approval:** DFAST results are supervisory information; disclosure in investor materials requires CFO and Legal review.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| CRO | Risk Management | Model output; capital planning |
| CFO | Finance | Capital plan; DFAST submission |
| Regulatory Reporting Team | Finance | Federal Reserve submission |
| Board Risk Committee | Board | Capital adequacy review |
| Internal Audit | Audit | DFAST methodology audit |
| Model Validation Officer | Model Risk | Validation; sensitivity testing |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Priya Nair | CRO / Model Owner | 2026-04-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-04-01 (provisional) |
| CFO | Chief Financial Officer | 2026-04-01 |
| Board Risk Committee | Board | 2026-04-01 |

### Use Conditions
- DFAST results must be reviewed by the CRO and CFO before submission to the Federal Reserve. No submission without dual sign-off.
- Any scenario trough below the 8.0% internal floor triggers mandatory Board Risk Committee notification within 5 business days.
- Macro scenario inputs must be updated within 10 business days of Federal Reserve scenario publication each year.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| DFAST-F1 | Major | Macro satellite coefficients (β_GDP, β_UR) inherited from APEX-MDL-0007 and not independently calibrated for DFAST; COVID non-linearity may understate severely adverse credit losses | Open |
| DFAST-F2 | Major | PPNR model uses static fee income and expense projections; no dynamic balance sheet run-off model for deposit attrition under stress | Open |
| DFAST-F3 | Minor | Operational risk loss modelled as a flat charge; no scenario-specific OpRisk drivers (litigation, conduct risk) incorporated | Open |
