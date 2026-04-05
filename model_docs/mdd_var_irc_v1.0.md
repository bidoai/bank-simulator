# Model Development Document: Market Risk VaR Model
**Model ID:** APEX-MDL-0001
**Version:** 1.0
**Owner:** Dr. Priya Nair (CRO)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** Validated
**Last Review:** 2026-03-01 | **Next Review:** 2027-03-01
**Regulatory:** 12 CFR 3.132, Basel III Annex 10, SR 11-7

---

## 1. Model Overview

### Purpose
The Market Risk VaR Model quantifies the potential loss in the trading book over a 1-day horizon at 99% confidence. It is the primary input to regulatory market risk capital under 12 CFR 3.132 (Basel III IMA) and drives desk-level risk limits in LimitManager.

### Business Use
- **Regulatory capital**: Basel multiplier 3× on the higher of current VaR and 60-day average VaR
- **Risk limits**: Daily delta and vega utilisation reported against board-approved limits
- **Pre-trade checks**: Parametric VaR delta used for pre-trade limit approval in OMS
- **Stress testing**: Inputs to DFAST adverse scenario projections

### Scope
All instruments in the Apex trading book: AAPL, MSFT, SPY, NVDA (equities), EURUSD, GBPUSD (FX), US10Y, US2Y (rates), AAPL_CALL_200 (equity option), USD_IRS_5Y (interest rate swap).

---

## 2. Theoretical Basis

### GBM Assumption
Asset returns are modelled as log-normal under geometric Brownian motion:

```
dS_t = μ S_t dt + σ S_t dW_t
```

For a 1-day horizon, the log-return is approximately normal: `r_1d ~ N(0, σ²)`.

### Three VaR Methodologies

**Method 1 — Historical Simulation (primary):**
```
VaR_HS = -Percentile(P&L_t, 1%)   for t = {t-1, ..., t-250}
```
Full revaluation of current portfolio under 250 historical 1-day scenarios. No distributional assumption.

**Method 2 — Parametric Delta-Normal:**
```
VaR_param = 1.645 × σ_portfolio × √W
```
where `σ_portfolio = √(Δ' Σ Δ)`, `Δ` is the vector of delta sensitivities, `Σ` is the return covariance matrix, and `W` is the notional weight.

**Method 3 — Monte Carlo Cholesky (regime-aware):**
```
L = Chol(Σ_regime)
Z_t ~ N(0, I)
r_t = μ + L Z_t
Portfolio P&L = Σ_i Δ_i × r_t,i × S_i
VaR_MC = -Percentile(P&L, 1%)   over 2,000 paths
```
The correlation matrix `Σ_regime` is selected by `CorrelationRegimeModel` (APEX-MDL-0009): NORMAL or STRESS depending on realized equity-credit correlation.

### Basel Multiplier
```
Capital_charge = max(VaR_t, k × VaR_avg60) × √10
k = 3.0 + add-on (0–1 based on backtesting exceptions)
```

---

## 3. Mathematical Specification

| Parameter | Value | Source |
|-----------|-------|--------|
| Confidence level | 99% | 12 CFR 3.132 |
| Horizon | 1-day (scaled to 10-day for capital) | Basel III |
| Historical window | 250 business days | SR 11-7 |
| MC paths | 2,000 | Internal calibration |
| Basel multiplier k | 3.0 (base) | 12 CFR 3.132(d) |
| Scaling to 10-day | ×√10 (square root of time) | Basel III |

### Backtesting Traffic Light (BCBS):
| Exceptions in 250 days | Zone | Add-on |
|------------------------|------|--------|
| 0–4 | Green | 0.00 |
| 5–9 | Amber | 0.40–0.85 |
| ≥10 | Red | 1.00 |

---

## 4. Implementation

**Code location:** `infrastructure/risk/var_calculator.py`
**Class:** `VaRCalculator`
**Key methods:**
- `calculate(positions, prices)` — Monte Carlo VaR, regime-aware
- `calculate_parametric(positions, prices)` — delta-normal for pre-trade

**Calibration:** Covariance matrix estimated from 60-day exponentially-weighted returns (λ=0.94). Regime selection from `CorrelationRegimeModel.detect_regime()`.

**Runtime:** ~50ms for 2,000-path MC on 11 instruments.

---

## 5. Validation

**Backtesting methodology:** Compare daily P&L realisation against prior-day VaR. Exceptions recorded in exception log. Traffic-light assessment quarterly.

**Independent replication:** Validator replicated MC VaR using NumPy; confirmed within ±2% for equity-only portfolio. IRS DV01 sensitivity confirmed against Bloomberg SWPM.

**Benchmarking:** Parametric VaR benchmarked against RiskMetrics delta-normal; within ±5% for equity portfolio.

---

## 6. Model Limitations

1. **Normality assumption (parametric):** Fat tails not captured; parametric VaR underestimates tail risk in stressed markets by 20-40% (empirical observation, GFC window).
2. **250-day window sensitivity:** In low-volatility regimes, VaR may understate risk if the window excludes stress events. Compensating control: SVaR (APEX-MDL-0002) adds stressed capital buffer.
3. **Square-root-of-time scaling:** Assumes IID returns; serial correlation violates this assumption for fixed income instruments.
4. **2,000-path MC estimation error:** Sampling noise at 99th percentile ≈ ±8% at 2,000 paths. Partially mitigated by antithetic variates.

---

## 7. Use Authorization

### Authorized Uses
1. **Regulatory capital calculation:** Daily IMA market risk capital under 12 CFR 3.132 and Basel III Annex 10. Output feeds the Regulatory Capital Engine as the IMA numerator.
2. **Desk-level risk limit monitoring:** Daily VaR utilisation reported against board-approved per-desk and portfolio limits in LimitManager.
3. **Pre-trade limit approval:** Parametric VaR delta used by OMS for real-time pre-trade checks; limit breach blocks order submission.
4. **DFAST adverse scenario inputs:** MC VaR outputs used as the starting-point loss distribution in DFAST severely adverse projections.
5. **Management reporting:** Daily VaR summary included in CRO risk dashboard and Board Risk Committee pack.

### Prohibited Uses
- **Sole basis for limit increases:** VaR output alone must not be used to approve an increase in trading limits; independent CRO sign-off required.
- **External disclosure without MVO certification:** VaR figures in Pillar 3 or 10-K require Model Validation Officer review and CRO certification prior to filing.
- **Standalone capital adequacy assertion:** APEX-MDL-0001 alone is not a complete capital assessment; SVaR (APEX-MDL-0002) and FRTB-SA floor (APEX-MDL-0003) are required components.
- **Unvalidated methodology changes:** Changes to lookback window, path count, or regime model dependency require MVO approval before production deployment.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| CRO | Risk Management | Full output; capital reporting; limit governance |
| Market Risk Managers | Risk Management | Desk VaR utilisation monitoring |
| OMS System (automated) | Trading | Pre-trade parametric VaR check |
| Model Validation Officer | Model Risk | Validation, backtesting oversight |
| Internal Audit | Audit | Annual model audit, exception review |
| Regulatory Reporting Team | Finance | Pillar 3 / 10-K market risk disclosures |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Priya Nair | CRO / Model Owner | 2026-03-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-03-01 |
| Board Risk Committee | Board | 2026-03-01 |

### Use Conditions
- Model must produce VaR by T+1 09:00; failure triggers CRO escalation.
- Exception log must be maintained. ≥5 backtesting exceptions in 250 days triggers MVO review and possible transition to FRTB-SA.
- Regime selection from APEX-MDL-0009 must be operational; if CRM is unavailable, STRESS matrix must be used as default.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| VAR-F1 | Major | Look-back window sensitivity not stress-tested across multiple window lengths (125d, 250d, 500d) | Open |
| VAR-F2 | Minor | Parametric method uses flat normal assumption; Cornish-Fisher expansion not applied | Open |
