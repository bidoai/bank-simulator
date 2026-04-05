# Model Development Document: Hull-White 1F Rate Model
**Model ID:** APEX-MDL-0005
**Version:** 1.0
**Owner:** Dr. Yuki Tanaka (Quant Researcher)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** In Validation
**Last Review:** 2026-03-01 | **Next Review:** 2027-03-01
**Regulatory:** SR 11-7, FRTB delta-IR sensitivity

---

## 1. Model Overview

### Purpose
The Hull-White 1-Factor (HW1F) model is an arbitrage-free short-rate model used for pricing and risk-managing interest rate derivatives. It perfectly fits the initial yield curve by construction and provides closed-form solutions for zero-coupon bonds and European swaptions.

### Business Use
- **IRS valuation:** Fixed-float leg decomposition using HW1F zero-coupon bond prices
- **PFE simulation:** Monte Carlo IR path generation for XVA exposure profiles
- **FRTB-SA IR delta:** Sensitivity bumps applied along HW1F term structure
- **Option pricing:** Cap/floor and swaption valuations for rates desk

---

## 2. Theoretical Basis

### Short-Rate Dynamics
Under the risk-neutral measure Q:
```
dr_t = [θ(t) - a r_t] dt + σ dW_t
```
where:
- `a` = mean-reversion speed (typically 0.05–0.20)
- `σ` = short-rate volatility
- `θ(t)` = time-dependent drift calibrated to match initial term structure

### Analytical Zero-Coupon Bond
```
P(t,T) = A(t,T) exp[-B(t,T) r_t]

B(t,T) = (1 - e^{-a(T-t)}) / a

ln A(t,T) = ln P_mkt(0,T)/P_mkt(0,t) - B(t,T) F(0,t)
            - (σ²/4a)(1 - e^{-2at}) B(t,T)²
```
where `F(0,t) = -∂ ln P_mkt(0,t)/∂t` is the instantaneous forward rate.

### IRS Valuation
Fixed leg: `V_fixed = N R Σ_i τ_i P(0, T_i)`
Float leg: `V_float = N (P(0, T_0) - P(0, T_n))`
IRS value (payer): `V_IRS = V_float - V_fixed`

### Swaption (European payer)
```
V_swaption = Σ_i c_i × ZBP(t, S, T_i, K_i)
```
where ZBP is the Hull-White zero-coupon bond put formula with effective strike adjustment.

---

## 3. Mathematical Specification

| Parameter | Calibrated Value | Calibration Target |
|-----------|-----------------|---------------------|
| Mean reversion a | 0.08 | 10Y IRS rate stability |
| Short-rate vol σ | 0.012 | ATM swaption vol |
| Calibration instruments | US2Y, US10Y live prices | OIS curve from market feed |

---

## 4. Implementation

**Code location:** Referenced in `infrastructure/trading/greeks.py` for IRS DV01 computation; full HW1F path generation in PFE engine (`infrastructure/xva/adapter.py`).

**IRS DV01 approximation:**
```
DV01_IRS = quantity × 0.0004  (USD per 1bp per $1 notional)
```
This is a flat DV01 approximation; HW1F gives the full term-structure sensitivity used for FRTB.

**Calibration procedure:** Daily calibration to US2Y and US10Y prices from `FeedHandler`. `a` calibrated to fit the ATM 2Y×5Y swaption vol target; `σ` fitted to replicate 10Y yield level.

---

## 5. Validation

**Benchmark:** IRS fair value compared against QuantLib HW1F; within ±0.01% of notional for par swaps.

**Swaption validation:** ATM swaption prices within ±2bps implied vol of market references.

**PFE profile check:** 5Y USD IRS expected exposure profile: peak at ~3Y (18% of notional), declines to zero at maturity. Consistent with industry benchmarks.

---

## 6. Model Limitations

1. **Single factor:** HW1F captures only parallel yield curve shifts. Twist (steepening/flattening) and curvature moves are not captured. Error for 2-year yield vs 10-year yield movements can exceed 15% of DV01.
2. **Constant a and σ:** Time-homogeneous parameters mis-price long-dated swaptions and fail to reproduce the volatility hump at 2-3 year expiry.
3. **Gaussian rates:** HW1F allows negative rates; this is a feature under negative rate environments but may mis-price floors at zero strike.
4. **OIS calibration only:** HW1F calibrated to USD OIS; USD LIBOR/SOFR basis not modelled.

---

## 7. Use Authorization

### Authorized Uses
1. **IRS valuation:** Fixed-float interest rate swap mark-to-market using HW1F zero-coupon bond prices.
2. **PFE exposure simulation:** Monte Carlo IR path generation for XVA expected exposure profiles (APEX-MDL-0014).
3. **FRTB-SA IR delta sensitivities:** Yield curve sensitivity bumps along HW1F term structure for GIRR capital.
4. **Vanilla cap/floor and swaption pricing:** European-style rates options for standard hedging products.

### Prohibited Uses
- **CMS spread products:** Constant maturity swap spreads require at minimum a 2-factor model (HW2F); CMS products must not be priced using this model without MVO exception approval.
- **Callable bond or Bermuda swaption pricing:** Multi-exercise optionality requires a lattice or multi-factor model; HW1F single-factor European swaption formula is not applicable.
- **DV01 flat approximation as HW1F output:** The `DV01 = quantity × 0.0004` hardcode in `greeks.py` is a known simplification and must not be represented as a full HW1F sensitivity computation.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| Rates Desk | Trading | IRS pricing; cap/floor hedging |
| XVA Team | Quant / Trading | PFE simulation |
| Risk Management | Risk | FRTB IR delta; VaR |
| Model Validation Officer | Model Risk | Validation; QuantLib benchmark |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Yuki Tanaka | Head of Quant Research / Model Owner | 2026-03-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-03-01 |
| Dr. Priya Nair | CRO | 2026-03-01 |

### Use Conditions
- HW1F-F1 (single-factor) is an open Major finding. For butterfly swaps and other yield-curve-shape products, Risk must apply a model uncertainty reserve of ≥5bps DV01-equivalent.
- Calibration must run daily against live OIS curve. Calibration failure requires fall-back to prior-day parameters and immediate notification to Quant.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| HW1F-F1 | Major | Single-factor limitation: twist and curvature yield curve moves not captured; material error for butterfly swaps and CMS products | Open |
| HW1F-F2 | Minor | Calibration uses only US2Y and US10Y; US5Y/US30Y excluded from calibration objective | Open |
