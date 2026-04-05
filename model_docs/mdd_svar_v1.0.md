# Model Development Document: Stressed Value-at-Risk
**Model ID:** APEX-MDL-0002
**Version:** 1.0
**Owner:** Dr. Priya Nair (CRO)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** In Validation
**Last Review:** 2026-03-01 | **Next Review:** 2027-03-01
**Regulatory:** Basel 2.5 MRA (BCBS Jul 2009), SR 11-7

---

## 1. Model Overview

### Purpose
Stressed VaR (SVaR) supplements the standard VaR model by re-running it on a historical window calibrated to a period of significant financial stress. SVaR addresses the criticism that VaR calibrated to a calm period dramatically understates tail risk.

### Business Use
- **Regulatory capital (IMA banks):** `Capital = max(VaR_t, 3×avg60_VaR) + max(SVaR_t, 3×avg60_SVaR)`, per Basel 2.5
- **Stress testing:** SVaR provides the stressed losses component in DFAST severely adverse
- **Model governance:** SVaR independently challenges standard VaR — divergence triggers review

### Scope
Same instrument universe as APEX-MDL-0001. The stressed window uses 2007-07-01 to 2009-06-30 (GFC) as the primary calibration period.

---

## 2. Theoretical Basis

### Stressed Period Selection
The BCBS requires the stressed period to capture "a period of significant financial stress relevant to the firm's portfolio." Apex uses the 2007–2009 GFC period as the primary window, satisfying:
- Equity markets: S&P 500 peak-to-trough -57%
- Credit spreads: IG CDS spread +450bps
- FX volatility: EUR/USD realised vol +18 p.a.
- Rates: US10Y 2-year range >200bps

### Methodology
SVaR uses the same Monte Carlo Cholesky method as APEX-MDL-0001, but with:
1. **Shocked return series:** Factor shocks derived from GFC 250-day window
2. **Stressed covariance matrix:** Calibrated to 2007-2009 realized correlations and volatilities
3. **Static stressed correlation:** Independent of CorrelationRegimeModel (STRESS matrix applied unconditionally)

```
SVaR = -Percentile(P&L | Σ_stressed, μ_stressed, 2000 paths, 99%)
```

### Basel 2.5 Capital Formula
```
IMA_capital = max(VaR_t, k_1 × VaR_avg60) × √10
            + max(SVaR_t, k_2 × SVaR_avg60) × √10
```
where k_1 and k_2 are the respective backtesting multipliers (minimum 3.0 each).

---

## 3. Mathematical Specification

| Parameter | GFC Stressed Value |
|-----------|-------------------|
| Equity return shock (daily σ) | 3.2% (vs 1.2% normal) |
| FX return shock | 0.9% |
| Rates return shock (bps/day) | 8.5bps |
| Equity-equity correlation | 0.87 |
| Equity-credit correlation | -0.72 |
| SVaR / VaR ratio (typical) | 2.5–4.0× |

---

## 4. Implementation

**Code location:** `infrastructure/risk/var_calculator.py` — uses `correlation_regime.STRESS` matrix with GFC-calibrated volatilities.

**Stressed period re-identification:** Must occur at minimum annually. Re-identification tests 3 alternative 250-day windows; selects the window producing the highest portfolio SVaR. Approved by CRO and Model Validation.

**Runtime:** Same as standard VaR MC (~50ms). Typically run daily post-close.

---

## 5. Validation

**Backtesting:** SVaR does not have a backtesting requirement under Basel 2.5 (only VaR is backfitted). However, Validator independently verified that GFC window reproduces reported SVaR within ±5%.

**SVaR/VaR ratio monitoring:** Internal guideline: SVaR/VaR ratio should be ≥2× in normal conditions. Ratio below 1.5× triggers re-identification review.

---

## 6. Model Limitations

1. **Static stressed period:** GFC 2007-2009 may not be representative for an equity-heavy book in a tech-sector stress; COVID-2020 window produces higher equity SVaR.
2. **Annual re-identification frequency:** Period between re-identifications may allow stale period to persist through an emerging stress.
3. **No account of correlation breakdown:** SVaR correlation matrix is static; in reality, correlations during stress are dynamic.

---

## 7. Use Authorization

### Authorized Uses
1. **Basel 2.5 IMA capital (SVaR add-on):** Mandatory SVaR component of IMA capital; regulatory capital = VaR capital + SVaR capital under Basel 2.5 MRA.
2. **DFAST adverse and severely adverse P&L:** SVaR provides the stressed loss distribution for DFAST quarterly projections.
3. **Independent VaR challenge:** CRO uses SVaR/VaR ratio as a diagnostic; ratio < 1.5× triggers standard VaR recalibration review.
4. **ICAAP buffer sizing:** Finance uses SVaR-implied stressed losses in internal capital adequacy assessment (ICAAP) Pillar 2 buffers.

### Prohibited Uses
- **Capital reporting with stale stressed period:** SVaR must not be used for regulatory capital if the stressed period has not been re-identified within 12 months. SVAR-F1 (open) requires CRO written certification as compensating control until remediated.
- **Backtesting exceptions:** Basel traffic-light add-ons apply only to standard VaR; SVaR multiplier is independent of exception counts.
- **Substitution for standard VaR:** SVaR does not replace APEX-MDL-0001.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| CRO | Risk Management | Capital calculation; DFAST |
| Regulatory Reporting Team | Finance | 10-K, Pillar 3 capital disclosures |
| Model Validation Officer | Model Risk | Annual stressed period re-identification |
| Internal Audit | Audit | Capital adequacy audit |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Priya Nair | CRO / Model Owner | 2026-03-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-03-01 |

### Use Conditions
- Stressed period must be re-identified annually. While SVAR-F1 remains open, CRO must certify in writing (quarterly) that the GFC 2007-2009 window remains the most severe period for current portfolio composition.
- SVaR/VaR ratio ≥ 2.0× required in normal conditions; automatic escalation to MVO if ratio falls below 1.5×.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| SVAR-F1 | Major | Stressed period identification not re-certified since 2024-01; COVID-2020 window may produce higher SVaR than GFC for current portfolio composition | Open |
