# Model Development Document: Correlation Regime Model
**Model ID:** APEX-MDL-0009
**Version:** 1.0
**Owner:** Dr. Yuki Tanaka (Quant Researcher)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** In Validation
**Last Review:** 2026-03-01 | **Next Review:** 2027-03-01
**Regulatory:** Basel III Annex 4, SR 11-7, BCBS Correlation Trading (Jul 2009)

---

## 1. Model Overview

### Purpose
The Correlation Regime Model (CRM) provides a real-time regime indicator (NORMAL / STRESS) used by the VaR Monte Carlo engine to switch between normal-market and stress-market correlation matrices. During STRESS regimes, cross-asset correlations increase dramatically (equity-credit negative correlation breaks down; equity-equity correlations spike toward 1), causing VaR to increase materially. Using a single static correlation matrix underestimates tail risk by 20–40% during stress periods.

### Business Use
- **VaR Monte Carlo path generation:** CRM regime indicator selects which 6×6 correlation matrix is used for Cholesky factor decomposition in the MC engine
- **Capital planning:** Stressed VaR uses the stress-regime correlation matrix unconditionally during the 2007-2009 GFC reference window
- **Risk limit calibration:** Risk appetite limits are set in reference to stressed-regime VaR, ensuring limits do not implicitly rely on normal-market correlations
- **FRTB-SA scenario:** CRM feeds the "high correlation" scenario in the FRTB Standardised Approach three-scenario capital computation

---

## 2. Theoretical Basis

### Regime Detection
The regime indicator uses a 2-state Hidden Markov Model (HMM) proxy based on realized cross-asset correlation. The observable is the 20-day rolling Pearson correlation between:
- `R_eq`: daily returns of the Apex equity book (proxy: SPY)
- `R_cr`: daily changes in credit spread (proxy: CDX IG 5Y index)

```
ρ_obs(t) = Corr(R_eq(t-19:t), R_cr(t-19:t))
```

Under normal markets, equity and credit spreads are negatively correlated (equities rally, spreads tighten). Under stress, this correlation breaks down and can become positive (equity selloff accompanies spread widening).

### Regime Classification with Hysteresis
A hysteresis band prevents oscillation between regimes when the indicator hovers near a threshold:

```
If current regime = NORMAL:
    Switch to STRESS if ρ_obs > 0.65 (upper threshold)

If current regime = STRESS:
    Switch to NORMAL if ρ_obs < 0.40 (lower threshold)

Hysteresis band [0.40, 0.65]: no regime switch, hold current state
```

### Correlation Matrices

**Normal Regime — 6×6 matrix (asset classes: EQ, IR, FX, CR, CMD, VOL):**
```
         EQ     IR     FX     CR     CMD    VOL
EQ   [ 1.00  -0.20   0.30  -0.20   0.10  -0.60 ]
IR   [-0.20   1.00  -0.15   0.10  -0.05   0.15 ]
FX   [ 0.30  -0.15   1.00  -0.10   0.20  -0.25 ]
CR   [-0.20   0.10  -0.10   1.00  -0.05   0.30 ]
CMD  [ 0.10  -0.05   0.20  -0.05   1.00  -0.10 ]
VOL  [-0.60   0.15  -0.25   0.30  -0.10   1.00 ]
```

**Stress Regime — 6×6 matrix:**
```
         EQ     IR     FX     CR     CMD    VOL
EQ   [ 1.00  -0.50   0.55  -0.80   0.30  -0.90 ]
IR   [-0.50   1.00  -0.35   0.40  -0.20   0.45 ]
FX   [ 0.55  -0.35   1.00  -0.30   0.45  -0.50 ]
CR   [-0.80   0.40  -0.30   1.00  -0.15   0.70 ]
CMD  [ 0.30  -0.20   0.45  -0.15   1.00  -0.25 ]
VOL  [-0.90   0.45  -0.50   0.70  -0.25   1.00 ]
```

Key stress-regime changes vs normal:
- ρ_eq-cr: -0.20 → -0.80 (equity-credit correlation intensifies under stress)
- ρ_eq-vol: -0.60 → -0.90 (equity selloff drives vol spike)
- ρ_eq-eq cross-sector (absorbed in EQ diagonal bucketing): +0.60 → +0.90
- ρ_fx-cr: -0.10 → -0.30 (FX-credit contagion under stress)

Both matrices are positive semi-definite (verified via Cholesky factorability check at initialisation).

### Cholesky Decomposition in VaR MC
The VaR Monte Carlo engine draws correlated risk factor shocks:
```
Z ~ N(0, I)           # uncorrelated standard normals
L = cholesky(Σ)       # lower triangular, where Σ = regime correlation matrix
X = L @ Z             # correlated shocks
```

The regime matrix Σ is selected at each Monte Carlo run based on current regime indicator. During a stress regime, the Cholesky decomposition of the stress matrix amplifies co-movement across risk factors, increasing the portfolio's simulated tail losses.

---

## 3. Mathematical Specification

| Parameter | Value | Source |
|-----------|-------|--------|
| Lookback window | 20 business days | ~1 calendar month |
| Upper threshold (NORMAL→STRESS) | ρ_obs > 0.65 | Calibrated to GFC onset |
| Lower threshold (STRESS→NORMAL) | ρ_obs < 0.40 | Calibrated to GFC recovery |
| Regime smoothing | Hysteresis band | Prevents oscillation |
| Proxy for equity returns | SPY daily returns | Broad market proxy |
| Proxy for credit spreads | CDX IG 5Y daily ΔS | Most liquid credit proxy |
| Correlation matrices | 6×6, 2 states | Calibrated 2007-2023 |
| Matrix factorability | PSD verified | Cholesky check at init |

---

## 4. Implementation

**Code location:** `infrastructure/risk/correlation_regime.py`
**Class:** `CorrelationRegimeModel`
**Key methods:**
- `update(eq_return, cr_spread_change)` — adds new observation, recomputes ρ_obs, updates regime
- `get_regime()` → `"NORMAL"` or `"STRESS"`
- `get_correlation_matrix()` → np.ndarray (6×6) for current regime
- `get_cholesky_factor()` → np.ndarray (6×6 lower triangular)

**Integration with VaR MC:** `RiskService.run_snapshot()` calls `correlation_regime.get_cholesky_factor()` before each Monte Carlo batch. No per-path regime switching — regime is fixed for the duration of the batch.

**Initialisation:** Regime history loaded from SQLite on startup; rolling window pre-populated from 20 most recent market data points.

---

## 5. Validation

**Regime detection accuracy:** Backtested over GFC (2007-2009), COVID-19 (2020-Q1), and 2022 rate shock. STRESS regime correctly flagged during all three periods. Regime onset lag: 3-8 days (inherent to 20-day lookback window).

**VaR uplift validation:** Under STRESS regime, portfolio VaR increases by 25-45% relative to NORMAL regime, consistent with Basel Annex 4 guidance that stressed correlations should materially increase capital.

**PSD verification:** Both matrices verified positive semi-definite via `np.linalg.cholesky()` at model initialisation. Any non-PSD matrix would raise an exception before reaching the MC engine.

**Correlation stability:** Normal and stress matrices estimated using a 16-year history (2007-2023), covering 2 full stress cycles. Eigenvalue decomposition confirms stability.

---

## 6. Model Limitations

1. **Single regime boundary:** Binary NORMAL/STRESS classification misses partial stress states (e.g., credit stress without equity selloff, or sector-level stress without systemic contagion). A 3-state model (NORMAL/ELEVATED/STRESS) would capture more nuance.
2. **Lookback lag:** 20-day window means regime detection lags stress onset by 3-8 days — VaR underestimates during the onset window.
3. **Proxy limitations:** SPY and CDX IG are US-centric proxies. European or EM stress events may not trigger the regime switch until US markets are affected.
4. **Static stress matrix:** Stress correlation matrix is a fixed historical average; actual correlations during any given stress event will differ. The Lehman shock and the 2022 rate shock produced different stress correlation structures.
5. **Hysteresis calibration:** Band [0.40, 0.65] calibrated to GFC; may not be optimal for shorter or shallower stress events.

---

## 7. Use Authorization

### Authorized Uses
1. **VaR Monte Carlo regime selection:** CRM regime indicator (NORMAL/STRESS) selects the Cholesky correlation matrix used in each MC VaR batch (APEX-MDL-0001).
2. **Stressed VaR correlation (SVaR):** Stress-regime matrix applied unconditionally in APEX-MDL-0002 for GFC-window SVaR.
3. **Risk appetite calibration:** Risk limits set with reference to stressed-regime VaR, ensuring limits do not implicitly rely on normal-market correlations.
4. **FRTB-SA high-correlation scenario:** CRM stress matrix feeds the "high correlation" scenario in the FRTB three-scenario capital computation (APEX-MDL-0003).

### Prohibited Uses
- **Trading signal or position trigger:** CRM regime indicator must not be used as a trading signal or to trigger position reduction autonomously. Regime detection is a risk measurement input only.
- **Real-time intraday switching:** Regime is fixed for the duration of each MC batch; intraday regime switching is not supported and would invalidate VaR consistency.
- **Substitution for macroeconomic regime analysis:** CRM is a narrow cross-asset correlation proxy; it must not be used as a general macroeconomic recession or stress indicator for strategic planning.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| VaR Engine (automated) | Risk (system) | Regime-driven matrix selection |
| CRO | Risk Management | Regime status monitoring; limit governance |
| Market Risk Managers | Risk Management | Stress-period VaR interpretation |
| Model Validation Officer | Model Risk | Backtesting; threshold calibration review |
| Quant Research | Quant | Correlation matrix maintenance |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Yuki Tanaka | Head of Quant Research / Model Owner | 2026-03-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-03-01 |
| Dr. Priya Nair | CRO | 2026-03-01 |

### Use Conditions
- CRM-F2 (regime lag) is an open Major finding. During market dislocation, Risk must manually review CRM regime status daily and may override to STRESS regime with CRO approval if market conditions warrant before the 20-day signal triggers.
- Correlation matrices must be re-estimated at minimum annually, incorporating any new stress periods identified since the last calibration. Next scheduled re-estimation: 2027-03-01.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| CRM-F1 | Major | Single regime boundary misses partial-stress states; 3-state model (NORMAL/ELEVATED/STRESS) would reduce VaR estimation error during shallow stress episodes | Open |
| CRM-F2 | Major | 20-day lookback lag: regime switches 3-8 days after stress onset; VaR underestimation during regime transition window not quantified | Open |
| CRM-F3 | Minor | US-centric proxies (SPY, CDX IG); European/EM stress onset not captured until contagion reaches US markets | Open |
