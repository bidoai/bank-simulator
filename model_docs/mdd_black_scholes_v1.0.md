# Model Development Document: Black-Scholes-Merton Options Pricing
**Model ID:** APEX-MDL-0004
**Version:** 1.0
**Owner:** Dr. Yuki Tanaka (Quant Researcher)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** Validated
**Last Review:** 2026-03-01 | **Next Review:** 2027-03-01
**Regulatory:** SR 11-7, IFRS 13 Level 3

---

## 1. Model Overview

### Purpose
The Black-Scholes-Merton (BSM) model prices European call and put options on equities and provides the full Greeks suite used for risk management and XVA exposure simulation.

### Business Use
- **Trade pricing:** Mark-to-market for all equity option positions (AAPL_CALL_200)
- **Greeks:** Delta/gamma/vega/theta/rho/charm fed to VaR Monte Carlo and FRTB-SA sensitivities
- **XVA:** Delta and gamma used in PFE exposure simulation
- **IFRS 13:** Deep OTM options classified Level 3 (unobservable vol inputs)

---

## 2. Theoretical Basis

### Geometric Brownian Motion
```
dS = (r - q) S dt + σ S dW_t
```
Under risk-neutral measure Q, the stock price S follows GBM with risk-free rate r, dividend yield q, and constant volatility σ.

### Black-Scholes Pricing Formula (European call)
```
C = S e^{-qT} N(d₁) - K e^{-rT} N(d₂)
P = K e^{-rT} N(-d₂) - S e^{-qT} N(-d₁)

d₁ = [ln(S/K) + (r - q + σ²/2) T] / (σ √T)
d₂ = d₁ - σ √T
```
where N(·) is the standard normal CDF.

### Greeks
| Greek | Formula |
|-------|---------|
| Delta (call) | e^{-qT} N(d₁) |
| Delta (put) | -e^{-qT} N(-d₁) |
| Gamma | e^{-qT} φ(d₁) / (S σ √T) |
| Vega | S e^{-qT} φ(d₁) √T |
| Theta (call) | -(S σ e^{-qT} φ(d₁))/(2√T) - r K e^{-rT} N(d₂) + q S e^{-qT} N(d₁) |
| Rho (call) | K T e^{-rT} N(d₂) |
| Charm | e^{-qT} [φ(d₁) (2(r-q)T - d₂ σ√T)/(2T σ√T) - q N(d₁)] |

φ(·) = standard normal PDF.

---

## 3. Mathematical Specification

**Current Apex parameters:**

| Parameter | Value |
|-----------|-------|
| Risk-free rate r | 4.5% (US OIS approximation) |
| Dividend yield q | 0% (no dividends modelled) |
| Implied volatility σ | 30% (flat surface, calibrated quarterly) |
| Time to expiry T | 0.25 years (90-day standard) |
| Option multiplier | 100 shares/contract |

---

## 4. Implementation

**Code location:** `infrastructure/trading/greeks.py` — `GreeksCalculator._option_greeks()`

**Key implementation notes:**
- `_CALL_` in ticker → call option; `_PUT_` → put option
- Multiplier 100 applied to all greeks
- scipy.stats.norm used for N(·) and φ(·)
- T = 0.25 hardcoded (review quarterly)

---

## 5. Validation

**Benchmark:** Call prices validated against put-call parity (C - P = Se^{-qT} - Ke^{-rT}); max error <$0.01.

**Greeks backtesting:** Delta P&L explain: `ΔP ≈ Δ ΔS + ½Γ ΔS²`; R² > 0.98 for daily hedges.

**IFRS 13 assessment:** ATM options (within ±10% moneyness) classified Level 2 (observable vol inputs). Deep OTM/ITM (>20% moneyness) classified Level 3 per IFRS 13.81.

---

## 6. Model Limitations

1. **Flat volatility surface:** No smile or skew; BSM underprices OTM puts and overprices OTM calls relative to market. Material error for deep OTM options.
2. **Constant volatility:** Stochastic vol (Heston, SABR) not implemented; BSM vega risk may be misestimated by ±30% for long-dated options.
3. **No early exercise:** European-style only; American options mispriced (compensating control: only European-style contracts traded).
4. **No discrete dividends:** Continuous dividend yield is a poor approximation for discrete ex-dividend events.
5. **Fixed T=0.25:** Fails to reflect time decay correctly for options approaching expiry or beyond 90 days.

---

## 7. Use Authorization

### Authorized Uses
1. **European vanilla option pricing:** Mark-to-market for all Apex equity option positions (AAPL_CALL_200 and equivalents).
2. **Greeks for VaR and FRTB-SA:** Delta, gamma, vega, and rho output fed to VaR Monte Carlo (APEX-MDL-0001) and FRTB-SA sensitivity-based method (APEX-MDL-0003).
3. **XVA exposure simulation:** Delta and gamma used in PFE exposure profile generation (APEX-MDL-0014).
4. **IFRS 13 fair value classification:** BSM output used to classify options as Level 2 (ATM) or Level 3 (deep OTM/ITM) per IFRS 13.81.

### Prohibited Uses
- **American-style options:** BSM is European-only; American exercise feature not modelled. American options must not be priced using this model without Quant approval of an early-exercise adjustment.
- **Exotic or barrier options:** Path-dependent payoffs, digital options, and barrier products require separate models with MVO approval.
- **Standalone Level 3 fair value without override disclosure:** Deep OTM options classified Level 3 must include disclosure of model uncertainty in financial statements.
- **Vol surface extrapolation:** BSM uses a flat surface; extrapolating to strikes >25% OTM or tenors >1 year requires explicit MVO approval.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| Equity Options Desk | Trading | Trade pricing; MTM |
| Risk Management | Risk | Greeks for VaR and FRTB |
| XVA Team | Quant / Trading | Exposure simulation inputs |
| Finance / Accounting | Finance | IFRS 13 fair value reporting |
| Model Validation Officer | Model Risk | Validation and benchmarking |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Yuki Tanaka | Head of Quant Research / Model Owner | 2026-03-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-03-01 |
| Dr. Priya Nair | CRO | 2026-03-01 |

### Use Conditions
- BSM-F1 (flat vol surface) is an open Major finding. For OTM options >15% moneyness, traders must apply a manual volatility override approved by Quant and documented in the trade blotter.
- T = 0.25 is a hardcoded approximation; this is a known production defect. Trades with expiry significantly different from 90 days require Quant review of the T parameter.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| BSM-F1 | Major | Flat volatility surface — no smile/skew calibration; material mispricing for OTM options (>15% moneyness) | Open |
| BSM-F2 | Minor | No discrete dividend handling; continuous yield approximation used; error <2% for low-yield stocks | Open |
