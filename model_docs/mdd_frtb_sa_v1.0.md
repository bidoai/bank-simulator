# Model Development Document: FRTB Standardised Approach
**Model ID:** APEX-MDL-0003
**Version:** 1.0
**Owner:** Dr. Priya Nair (CRO)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** Draft
**Last Review:** 2026-03-01 | **Next Review:** 2027-03-01
**Regulatory:** BCBS d352 (Jan 2016), CRR3 2024, SR 11-7

---

## 1. Model Overview

### Purpose
The FRTB Standardised Approach (SA) replaces the Basel 2.5 Standardised Approach with a sensitivity-based method (SBM) that better reflects risk. Under Basel IV / CRR3, all banks must report FRTB-SA capital; IMA banks use it as a floor. Apex uses FRTB-SA as the primary capital model pending IMA approval.

### Business Use
- **Regulatory capital (primary):** SA capital is the binding constraint until IMA approval
- **Internal limit calibration:** SA sensitivities inform risk appetite for delta, vega, curvature
- **Parallel run:** Compared against IMA output; material divergence triggers governance review

---

## 2. Theoretical Basis

### Three Capital Components

**1. Sensitivity-Based Method (SBM):**
Capital computed from risk factor sensitivities across 7 risk classes (GIRR, CSR non-sec, CSR sec, FX, EQ, Commodity, VEGA).

**Delta capital:**
```
K_delta = √( Σ_b Σ_{i,j ∈ b} ρ_{ij} WS_i WS_j )
```
where `WS_i = RW_i × s_i` (risk weight × net sensitivity), `ρ_{ij}` is the intra-bucket correlation, and `b` indexes buckets.

**Cross-bucket aggregation:**
```
K_SBM = √( Σ_b K_b² + Σ_{b≠c} γ_{bc} S_b S_c )
```
where `γ_{bc}` is the cross-bucket correlation and `S_b = Σ_i WS_i` within bucket.

**2. Residual Risk Add-On (RRAO):**
```
RRAO = 1.0% × notional_exotic + 0.1% × notional_other
```
Applies to instruments with path-dependent payoffs, correlation products, and non-linear exotic optionality.

**3. Default Risk Charge (DRC):**
```
DRC = max(0, Σ_i JTD_i × LGD_i × RW_i) × W_maturity
```
Jump-to-default exposure for non-securitisation credit positions.

### IR Tenor Buckets (GIRR):
0.25Y, 0.5Y, 1Y, 2Y, 3Y, 5Y, 10Y, 15Y, 20Y, 30Y (10 buckets per currency).

---

## 3. Mathematical Specification

**Equity Risk Weights by Bucket:**

| Bucket | Description | Delta RW |
|--------|-------------|----------|
| 1 | Large-cap EM | 55% |
| 8 | Large-cap DM | 25% |
| 11 | Small-cap | 70% |

**IR Risk Weights (GIRR):**
Tenor-dependent: 1.7% (3m) to 1.5% (10Y), prescribed by BCBS d352 §21.52.

**Correlation parameters:** Three scenarios (high/medium/low) for conservative capital: ρ = 1.0×, 0.75×, 0.5× of base correlations.

---

## 4. Implementation

**Code location:** `infrastructure/risk/regulatory_capital.py` — SA RWA calculator.

**Sensitivities source:** `GreeksCalculator` (APEX) provides delta and vega. Curvature computed as `CVR_i = -V(S_i + RW_i × S_i) + V(S_i - RW_i × S_i) - 2V(S_i)`.

**Capital aggregation:** Three correlation scenarios; capital = max across scenarios.

---

## 5. Validation

**Benchmark:** FRTB-SA capital benchmarked against ISDA SIMM for non-cleared derivatives. Material divergence (>20%) triggers a model review.

**Sensitivity validation:** Delta sensitivities validated against analytic Greeks for vanilla equity options.

---

## 6. Model Limitations

1. **Curvature proxy:** CVR computed analytically using bump-and-reprice; no full Monte Carlo revaluation.
2. **RRAO classification:** Exotic optionality identification is manual; no automated product classifier.
3. **DRC recovery assumptions:** Recovery rate 40% applied uniformly; actual recovery varies by seniority.

---

## 7. Use Authorization

### Authorized Uses
1. **Regulatory capital (binding floor):** FRTB-SA capital is the binding capital floor until IMA approval is obtained. Output is the primary market risk capital constraint under CRR3 2024.
2. **Internal limit calibration:** SA sensitivities inform risk appetite for delta, vega, and curvature across desks.
3. **Parallel run vs. IMA:** SA output compared against IMA (VaR/SVaR) output to monitor model divergence; divergence >20% triggers governance review.
4. **FRTB three-scenario capital:** High/medium/low correlation scenarios feed the conservative capital floor per BCBS d352.

### Prohibited Uses
- **Representing as validated to regulators:** FRTB-SA is in Draft status (FRTB-F1 and FRTB-F2 open Major). Must not be described as a "fully validated" model to examiners without noting open findings.
- **Exotic product capital:** RRAO classification is manual (FRTB-F2 open); exotic product capital charges must be reviewed by Quant before relying on SA output.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| CRO | Risk Management | Capital reporting; limit governance |
| Regulatory Reporting Team | Finance | Basel IV capital filings |
| Market Risk Managers | Risk Management | Sensitivity-based limit monitoring |
| Model Validation Officer | Model Risk | Benchmark validation, curvature review |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Priya Nair | CRO / Model Owner | 2026-03-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-03-01 (provisional — Draft status) |

### Use Conditions
- Until FRTB-F1 (curvature not vendor-benchmarked) is remediated, curvature capital must be floored at 110% of the RRAO output as a conservative buffer.
- Transition to "Validated" status requires independent vendor benchmark reconciliation for curvature and closure of FRTB-F2.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| FRTB-F1 | Major | Curvature risk aggregation not validated against independent vendor benchmark | Open |
| FRTB-F2 | Major | RRAO treatment for path-dependent exotics not documented; manual classification in use | Open |
| FRTB-F3 | Minor | DRC jump-to-default recovery rate uniformly 40%; seniority-specific recovery not modelled | Open |
