# Model Development Document: SOFR / LMM Term Rate Model
**Model ID:** APEX-MDL-0006
**Version:** 1.0
**Owner:** Dr. Yuki Tanaka (Quant Researcher)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** Draft
**Last Review:** 2026-03-01 | **Next Review:** 2027-03-01
**Regulatory:** ARRC SOFR Transition Guidance, ISDA 2020 Fallback Protocol

---

## 1. Model Overview

### Purpose
Following LIBOR cessation on 2023-06-30, this model governs SOFR compounding-in-arrears rate computation, Term SOFR CME reference rate usage, and LIBOR fallback mechanics per the ISDA 2020 protocol. The LMM extension provides cap/floor pricing in the SOFR framework.

### Business Use
- **Loan and swap pricing:** All floating-rate instruments now reference SOFR
- **Fallback processing:** Legacy LIBOR contracts converted per ISDA waterfall
- **Cap/floor pricing:** LMM used for client hedging products
- **FRTB delta-IR:** SOFR curve sensitivities replace LIBOR curve under FRTB

---

## 2. Theoretical Basis

### SOFR Compounding In Arrears

For a SOFR-referencing floating period [T_s, T_e]:
```
Compound_rate = (∏_{i=0}^{N-1} (1 + SOFR_i × d_i/360)) - 1) × 360/(T_e - T_s)
```
where SOFR_i is the daily SOFR fixing, d_i is the day count (ACT/360), and N is the number of business days in the period.

**Lookback mechanics:** 5-business-day lookback (observation date = settlement date - 5bd) allows rate to be known 2 days before payment date.

### Term SOFR (CME)
Term SOFR rates (1M, 3M, 6M, 12M) published by CME daily. Use restricted by ARRC: allowed for loan products and interdealer derivatives hedging loans; NOT for financial contracts unrelated to loans.

### LIBOR Fallback Waterfall (ISDA 2020)
Upon LIBOR cessation:
1. **Primary:** Term SOFR + spread adjustment (ISDA-prescribed static spread)
2. **Fallback 1:** Compounded SOFR in arrears + spread
3. **Fallback 2:** Central bank rate + spread
4. **Fallback 3:** Last published LIBOR rate (for short-term disruptions only)

ISDA-prescribed USD LIBOR spread adjustments (5-year historical median):
- 1M LIBOR → SOFR: +11.448bps
- 3M LIBOR → SOFR: +26.161bps
- 6M LIBOR → SOFR: +42.826bps

### LMM (SOFR)

The SOFR LMM models the joint evolution of SOFR forward rates F_j(t) for tenor periods [T_j, T_{j+1}]:
```
dF_j(t) = μ_j(t) F_j(t) dt + σ_j F_j(t) dW_j(t)
```
Under the T_{j+1}-forward measure, the drift is zero. Under the spot measure:
```
μ_j = Σ_{k=j+1}^{n} ρ_{jk} σ_j σ_k F_k(t) τ_k / (1 + F_k(t) τ_k)
```

**Caplet pricing (Black formula under LMM):**
```
Caplet(T_j, K) = P(0, T_{j+1}) τ [F_j(0) N(d₁) - K N(d₂)]
d₁ = [ln(F_j/K) + ½ σ_j² T_j] / (σ_j √T_j)
d₂ = d₁ - σ_j √T_j
```

---

## 3. Mathematical Specification

| Parameter | Value |
|-----------|-------|
| Tenors modelled | 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y |
| LMM vol calibration | ATM SOFR caplet market quotes |
| Lookback convention | 5 business days (ARRC recommendation) |
| Day count | ACT/360 |
| Business day convention | Modified Following (NY) |

---

## 4. Implementation

**Code location:** `infrastructure/treasury/ftp.py` — SOFR-based FTP curve uses compounded SOFR approximation via swap curve.

**Calibration:** Vol surface calibrated quarterly to CME SOFR caps. Spread adjustments hard-coded per ISDA published values.

---

## 5. Validation

**SOFR compounding accuracy:** Replication test: compound 20 days of SOFR fixings; confirm within $0.01 of analytic formula.

**Spread adjustment:** ISDA-prescribed spreads hard-coded and confirmed against published ISDA supplement.

**LMM caplet:** Benchmark against Black caplet at ATM; within 1bp implied vol.

---

## 6. Model Limitations

1. **SOFR-Fed Funds basis:** SOFR/Fed Funds basis not explicitly modelled; can diverge by 5-20bps during month-end/quarter-end.
2. **Term SOFR restrictions:** ARRC prohibits Term SOFR in financial derivatives not hedging loans; compliance team must approve each Term SOFR usage.
3. **LMM vol surface:** Calibrated using pre-LIBOR vol surface as proxy during 2022-2023 transition; SOFR-specific vol history now available and full recalibration is pending.
4. **Backward-looking risk:** SOFR in arrears creates P&L uncertainty during the accrual period; risk systems must account for daily revaluation.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| LMM-F1 | Major | SOFR-Fed Funds basis risk not modelled; EOM/EOM spikes can cause 15-20bps P&L mis-estimation | Open |
| LMM-F2 | Major | Term SOFR use-case documentation incomplete; ARRC pre-approval not recorded for 3 existing client contracts | Open |
| LMM-F3 | Minor | LMM vol calibration uses pre-LIBOR proxy surface; SOFR-native vol history sufficient for full recalibration since 2024-Q1 | Open |
