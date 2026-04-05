# Model Development Document: IFRS 9 Expected Credit Loss
**Model ID:** APEX-MDL-0007
**Version:** 1.0
**Owner:** Dr. Priya Nair (CRO)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** Validated
**Last Review:** 2026-03-01 | **Next Review:** 2027-03-01
**Regulatory:** IFRS 9.5.5, EBA/GL/2020/06, SR 11-7

---

## 1. Model Overview

### Purpose
The IFRS 9 ECL model computes Expected Credit Loss provisions for the loan portfolio under the three-stage impairment framework. Provisions are recognised on a 12-month basis (Stage 1) or lifetime basis (Stage 2/3) depending on significant increases in credit risk (SICR).

### Business Use
- **Financial reporting:** ECL provision recorded on income statement; affects CET1 ratio via retained earnings
- **Credit risk management:** Stage classification drives credit officer workout strategy
- **Capital planning:** Stressed ECL feeds DFAST adverse scenario P&L projections
- **Pricing:** Risk-adjusted return on equity uses ECL as expected loss charge

---

## 2. Theoretical Basis

### ECL Formula
```
ECL = PD × LGD × EAD × (discount factor)
```

For each obligor i in each period t:
```
ECL_i = Σ_{t=1}^{T_i} PD_i(t|t-1) × LGD_i × EAD_i(t) × DF(t)
```

**Stage 1 (no SICR):** 12-month ECL
```
ECL_S1 = PD_12m × LGD × EAD
```

**Stage 2 (SICR):** Lifetime ECL
```
ECL_S2 = Σ_{t=1}^{remaining life} PD_marginal(t) × LGD × EAD(t) × DF(t)
```

**Stage 3 (default, >90 DPD):** Simplified lifetime
```
ECL_S3 = LGD × EAD_at_default
```

### SICR Definition
An obligor is reclassified Stage 1→2 if ANY of:
- Credit rating downgrade ≥ 2 notches since origination
- Days past due > 30
- Watch-list or watchlist-equivalent designation
- Qualitative override (credit officer judgment)

### PD Estimation
Through-the-cycle (TTC) PD from Moody's idealized cumulative default rates, mapped to internal rating scale (AAA=1 through CCC=17). Point-in-time (PIT) adjustment via macro overlay:

```
PD_PIT(t) = PD_TTC × exp(β_GDP × ΔGDP(t) + β_UR × ΔUR(t))
```

β_GDP = -0.8 (GDP growth 1% → PD -8%)
β_UR = +0.6 (unemployment +1pp → PD +6%)

### LGD
Collateral-adjusted:
```
LGD = (1 - Recovery_rate)
Recovery_rate = min(Collateral_value / EAD, 0.90) × haircut
```
Unsecured: LGD = 0.45 (corporate loans), 0.25 (secured mortgages). Haircuts: CRE 30%, residential 10%.

### EAD
Committed: `EAD = drawn_balance + CCF × undrawn_commitment`
CCF = 0.75 (revolving credit), 0.50 (term loans).

---

## 3. Mathematical Specification

**Sample portfolio:** 50 obligors
- Rating distribution: 60% investment grade (BBB+/BBB/BBB-), 30% BB, 10% B/CCC
- Average PD (Stage 1): 1.2%
- Average LGD: 42%
- Portfolio ECL coverage ratio: ~1.8% (normal), ~3.5% (stressed)

---

## 4. Implementation

**Code location:** `infrastructure/credit/ifrs9_ecl.py`
**Class:** `IFRS9ECLEngine`
**Key methods:**
- `calculate_portfolio_ecl()` — full portfolio ECL
- `classify_stages()` — SICR assessment
- `run_scenario(macro_params)` — stressed ECL for DFAST

**Runtime:** ~5ms for 50 obligors.

---

## 5. Validation

**Benchmark:** Stage classification validated against sample obligors with known PD migration history; accuracy 94%.

**Macro sensitivity:** β_GDP sensitivity validated against EBA stress test results for comparable European banks; within ±15%.

**Coverage ratio:** Portfolio coverage ratio 1.8% (normal) vs EBA peer average 1.6%; slightly conservative, acceptable.

---

## 6. Model Limitations

1. **TTC PD basis:** TTC PD underestimates current default risk in downturns; PIT adjustment via macro satellite model partially corrects this.
2. **50-obligor sample:** Production portfolio has 850 obligors; demo portfolio is illustrative only.
3. **Flat LGD:** Collateral values not mark-to-market; static LGD may understate loss in collateral price declines (e.g., real estate crash).
4. **Macro satellite not post-COVID calibrated:** GDP/unemployment coefficients estimated pre-2020; pandemic non-linearity not captured.

---

## 7. Use Authorization

### Authorized Uses
1. **IFRS 9 provision calculation:** Stage 1/2/3 ECL recognition on the Apex loan portfolio for financial reporting purposes. ECL charge recorded on the income statement; provision balance on the balance sheet.
2. **Credit risk staging:** Stage classification (1→2 SICR trigger; 2→3 default) drives credit officer workout strategy and covenant monitoring.
3. **DFAST adverse scenario P&L:** Stressed ECL (run_scenario) used in 9-quarter CET1 projections under DFAST adverse and severely adverse scenarios.
4. **Risk-adjusted pricing:** ECL used as expected loss charge in RAROC pricing framework for new loan origination.
5. **Capital planning:** ECL provisioning impacts CET1 via retained earnings; Finance uses ECL projections in capital buffer planning.

### Prohibited Uses
- **Production portfolio assertion (850 obligors) without recalibration:** Current implementation covers a 50-obligor demo portfolio. Output must not be presented as representing the full 850-obligor production book without explicit MVO approval of the full portfolio extension.
- **SPPI test substitute:** BSM does not assess Solely Payments of Principal and Interest classification; SPPI test for IFRS 9 asset classification must be conducted separately by Finance.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| CRO / Credit Risk | Risk Management | ECL calculation; credit staging |
| CFO / Finance | Finance | IFRS 9 provision booking; capital planning |
| Loan Officers | Commercial Banking | Stage classification for workout |
| Regulatory Reporting Team | Finance | DFAST submission; EBA stress test |
| Model Validation Officer | Model Risk | Validation; macro sensitivity review |
| External Auditors | Audit (external) | IFRS 9 provision audit (read-only) |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Priya Nair | CRO / Model Owner | 2026-03-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-03-01 |
| CFO | Chief Financial Officer | 2026-03-01 |

### Use Conditions
- ECL-F1 (macro satellite not post-COVID calibrated) is an open Major finding. Until β_GDP is recalibrated, a conservative management overlay of +15% on total ECL provision must be applied in downside scenario planning, approved quarterly by the CRO and CFO.
- Stage 2 qualitative override (credit officer judgment) must be documented with a written credit memo before overriding the quantitative SICR trigger.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| ECL-F1 | Major | Macro satellite model GDP coefficient (β_GDP = -0.8) not recalibrated post-COVID; pandemic demonstrated non-linear response; EBA/GL/2020/06 requires calibration to reflect current economic uncertainty | Open |
