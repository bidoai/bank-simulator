# Model Development Document: ALM / Fund Transfer Pricing Engine
**Model ID:** APEX-MDL-0017
**Version:** 1.0
**Owner:** Dr. Priya Nair (CRO)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** In Validation
**Last Review:** 2026-04-01 | **Next Review:** 2027-04-01
**Regulatory:** SR 12-17 (Liquidity Risk), SR 10-6 (FTP), Basel III LCR (12 CFR 249), NSFR (12 CFR 249), SR 11-7

---

## 1. Model Overview

### Purpose
The ALM (Asset-Liability Management) / Fund Transfer Pricing engine consists of two integrated components:

**ALM component:** Measures and manages structural interest rate risk in the banking book. Produces NII (Net Interest Income) sensitivity and EVE (Economic Value of Equity) sensitivity across parallel and non-parallel rate shocks. Supports regulatory supervisory interest rate risk (SIIR) reporting and SVB-style concentration risk warnings.

**FTP component:** Allocates the cost and benefit of funding to individual business lines through a matched-maturity transfer pricing framework. FTP charges ensure that every asset originator bears the true cost of funding, and every liability originator receives the true benefit, eliminating cross-subsidy between short-duration deposits and long-duration loans.

Together, ALM and FTP form the bank's structural risk and profitability measurement framework. Neither produces a single number in isolation; they are integrative tools that tie together the balance sheet, rate environment, and business line P&L.

### Business Use
- **NII sensitivity reporting:** CRO and ALM Committee monitor NII change under ±100bps, ±200bps rate scenarios. Board risk appetite limits NII sensitivity to ±15% of projected annual NII.
- **EVE sensitivity (Pillar 2):** EVE sensitivity under +200bps stress is a Pillar 2 supervisory metric; > -20% EVE triggers a regulatory capital surcharge discussion with the Fed.
- **FTP desk P&L attribution:** FTP charges/credits are booked monthly to each trading desk and business line, producing an FTP-adjusted net P&L that reflects the true cost of the balance sheet.
- **DFAST NII channel:** NII projections under adverse/severely adverse rate scenarios feed DFAST PPNR model (APEX-MDL-0015).
- **Liquidity pricing:** FTP liquidity premium component prices the cost of the Contingency Funding Plan (CFP) buffer into loan rates.

---

## 2. Theoretical Basis

### Repricing Gap Schedule

The repricing gap schedule buckets assets and liabilities by the time until their rate resets:

```
Gap(bucket_k) = Assets(bucket_k) - Liabilities(bucket_k)
```

A positive gap (asset-sensitive) in a bucket means a rate rise increases NII for that bucket. The cumulative 12-month gap determines the bank's overall asset/liability sensitivity:

```
Cumulative_gap_12m = Σ_{k=1}^{K_12m} Gap(bucket_k)
```

**Apex 7-bucket repricing schedule:**

| Bucket | Label | Reprices within |
|--------|-------|----------------|
| 1 | Overnight | 1 day |
| 2 | Short | 1–30 days |
| 3 | 1M–3M | 1–3 months |
| 4 | 3M–6M | 3–6 months |
| 5 | 6M–1Y | 6–12 months |
| 6 | 1Y–5Y | 1–5 years |
| 7 | 5Y+ | >5 years |

### NII Sensitivity

Sensitivity of NII to a parallel rate shift Δr over a 12-month horizon:

```
ΔNII = Σ_k Gap(bucket_k) × Δr × w_k
```

where `w_k` is the average repricing weight within the bucket (days_remaining / 365).

**Behavioural deposit modelling:** Core deposits do not reprice instantaneously; a behavioural model assigns an effective tenor:
- Demand deposits: 70% core (5-year effective tenor), 30% rate-sensitive (30-day tenor)
- Savings deposits: 60% core (3-year effective tenor), 40% rate-sensitive

**ALM NII sensitivities (current portfolio):**

| Rate Shock | ΔNII ($B) | % of Baseline NII |
|-----------|-----------|-------------------|
| +100bps | +$3.4B | +8.5% |
| +200bps | +$6.8B | +17.0% |
| -100bps | -$3.1B | -7.8% |
| -200bps | -$5.9B | -14.8% |

Apex is asset-sensitive (positive NII sensitivity to rising rates). Risk appetite limit: ±15% of projected annual NII.

### EVE Sensitivity

Economic Value of Equity is the present value of all assets minus the present value of all liabilities under the current rate environment:

```
EVE = PV_assets(r) - PV_liabilities(r)
ΔEVE = EVE(r + Δr) - EVE(r)
```

PV computation uses full discounted cash flow for fixed-rate instruments; for floating-rate instruments, expected cash flows are updated at the next repricing date.

**Duration gap:**

```
Duration_gap = Duration_assets - (Liabilities / Assets) × Duration_liabilities
ΔEVE ≈ -Duration_gap × Assets × Δr / (1 + r)
```

**Apex EVE sensitivities:**

| Rate Shock | ΔEVE ($B) | % of Starting Equity |
|-----------|-----------|---------------------|
| +100bps | -$13.0B | -4.4% |
| +200bps | -$26.0B | -8.8% |
| -100bps | +$13.3B | +4.5% |
| -200bps | +$27.1B | +9.2% |

At +200bps, EVE declines 8.8% — below the 20% supervisory threshold. No SVB-style warning triggered at current duration gap (0.41 years).

### Fund Transfer Pricing

The FTP rate for a transaction is the sum of the risk-free funding cost, a liquidity premium, and an optionality premium:

```
FTP_rate(instrument) = OIS_swap_rate(maturity) + Liquidity_premium + Optionality_premium
```

**Matched-maturity principle:** The FTP rate uses the OIS swap rate at the instrument's contractual maturity, not the overnight rate. This correctly attributes the cost of long-term funding to long-dated assets.

**OIS swap curve (9 tenor points, linear interpolation):**

| Tenor | OIS Rate |
|-------|----------|
| O/N | 5.25% |
| 1M | 5.20% |
| 3M | 5.15% |
| 6M | 5.00% |
| 1Y | 4.85% |
| 2Y | 4.60% |
| 5Y | 4.40% |
| 10Y | 4.55% |
| 30Y | 4.70% |

**Liquidity premium by product type:**

| Product | Liquidity Premium | Rationale |
|---------|-------------------|-----------|
| Term loans | +45bps | Committed facility, not revolving |
| Revolving credit | +65bps | Drawdown uncertainty |
| Fixed-rate mortgages | +55bps | Prepayment and extension risk |
| Unsecured deposits | -15bps | Stable funding credit |
| Time deposits | -10bps | Relatively stable |

**FTP-adjusted desk P&L:**

```
P&L_FTP_adjusted(desk) = P&L_gross(desk) - Σ_{instruments} FTP_charge(instrument)
```

where `FTP_charge > 0` for assets (desk pays FTP) and `FTP_charge < 0` for liabilities (desk receives FTP credit).

---

## 3. Mathematical Specification

| Parameter | Value | Source |
|-----------|-------|--------|
| Total banking book assets | $285B | Balance sheet |
| Total banking book liabilities | $263B | Balance sheet |
| Asset duration (behavioural-adjusted) | 2.8 years | ALM model |
| Liability duration (behavioural-adjusted) | 2.4 years | ALM model |
| Duration gap | 0.41 years | (2.8 - (263/285) × 2.4) |
| Core deposit behavioural tenor | 5 years (demand), 3 years (savings) | Behavioural model |
| Baseline NII | $40B annual | Income statement |
| Starting EVE | $295B | Balance sheet |

---

## 4. Implementation

**Code locations:**
- `infrastructure/treasury/alm.py` — `ALMEngine`
- `infrastructure/treasury/ftp.py` — `FTPEngine`, `SwapCurve`

**Key methods (ALM):**
- `get_nii_sensitivity(shock_bps)` → ΔNII for rate shock
- `get_eve_sensitivity(shock_bps)` → ΔEVE for rate shock
- `get_repricing_gap()` → 7-bucket gap schedule
- `get_alm_report()` → full ALM summary dict

**Key methods (FTP):**
- `calculate_desk_charges()` → FTP charge/credit per desk
- `get_adjusted_pnl()` → gross P&L minus FTP charges per desk
- `get_ftp_summary()` → portfolio-wide FTP summary
- `SwapCurve.rate(tenor_years)` → OIS rate via linear interpolation

**REST endpoints:**
- `GET /api/treasury/alm/{report, nii-sensitivity, eve-sensitivity, repricing-gap}`
- `GET /api/treasury/ftp/{summary, adjusted-pnl, curve}`

**Integration:**
- ALM NII sensitivity feeds DFAST PPNR model (APEX-MDL-0015) as the rate-channel income projection
- FTP charges flow to each desk's P&L calculation; `RiskService.get_position_report()["by_desk"]` provides gross P&L input

---

## 5. Validation

**NII sensitivity benchmarking:** ALM NII sensitivity (+200bps: +$6.8B) benchmarked against peer Category III bank disclosures; within ±20% of peer median (+$5.5B on comparable balance sheet size). Apex is more asset-sensitive than peers, consistent with shorter-duration loan book composition.

**EVE validation:** Duration gap (0.41 years) validated by independent DCF calculation on a sample 10% of the balance sheet; within ±2% of model output.

**FTP curve validation:** OIS swap curve interpolated rates validated against Bloomberg SWPM for benchmark tenors (1Y, 5Y, 10Y); within ±2bps.

**Behavioural deposit model:** Core deposit behavioural tenors (5Y demand, 3Y savings) consistent with Fed SR 12-17 guidance and peer bank regulatory submissions. Annual back-test of deposit attrition vs. model assumptions.

---

## 6. Model Limitations

1. **Flat rate shock assumption:** NII sensitivity computed for parallel shifts only; non-parallel shocks (bear steepener, bull flattener) are not modelled. Rate twist risk is not captured in the EVE calculation.
2. **Static behavioural model:** Core deposit tenors are fixed; dynamic repricing behaviour (e.g., deposit migration to money-market funds at high rates) is not captured. SVB 2023 demonstrated that behavioural model assumptions can fail rapidly under stress.
3. **No prepayment model for mortgages:** Fixed-rate mortgages are assumed to mature at contractual date; prepayment risk (faster prepayment in falling-rate environment) understates negative convexity.
4. **OIS curve only:** FTP uses OIS (risk-free) curve; does not incorporate the bank's own credit spread or term funding premium. This may understate the true cost of long-term unsecured funding.
5. **Static product type liquidity premiums:** Liquidity premiums are calibrated annually; intra-year changes in funding market conditions are not reflected.

---

## 7. Use Authorization

### Authorized Uses
1. **Supervisory interest rate risk (SIIR) reporting:** NII and EVE sensitivities reported to the Federal Reserve quarterly under enhanced prudential standards.
2. **ALM Committee governance:** CRO and CFO use NII/EVE output to manage balance sheet positioning and set duration gap targets.
3. **FTP desk P&L attribution:** Monthly FTP charges booked to business lines for performance measurement, incentive compensation, and pricing discipline.
4. **DFAST PPNR input:** NII sensitivity under adverse/severely adverse rate scenarios feeds the DFAST income projection (APEX-MDL-0015).
5. **Liquidity pricing:** FTP liquidity premium embedded in new loan rates to ensure all loans are priced above the marginal cost of funds.

### Prohibited Uses
- **Standalone capital adequacy metric:** ALM NII/EVE sensitivity is a Pillar 2 metric; it must not substitute for Pillar 1 capital ratios in capital adequacy communications.
- **FTP as the sole profit metric for a desk:** FTP-adjusted P&L is one component of performance; it must be interpreted alongside allocated capital and risk metrics.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| CRO | Risk Management | ALM monitoring; SIIR reporting |
| CFO / Treasurer | Finance / Treasury | Balance sheet management; FTP governance |
| ALM Committee | Cross-functional | Rate risk positioning; hedging decisions |
| Desk Heads | Trading / Banking | FTP-adjusted P&L review |
| Regulatory Reporting Team | Finance | Fed SIIR submission |
| Model Validation Officer | Model Risk | Validation; behavioural model review |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Priya Nair | CRO / Model Owner | 2026-04-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-04-01 (provisional) |
| CFO | Chief Financial Officer | 2026-04-01 |

### Use Conditions
- FTP curve must be updated monthly using live OIS swap market rates. Stale FTP curve (> 30 days) must trigger notification to Treasury.
- Behavioural deposit assumptions must be re-validated annually. Material changes in deposit attrition rates (> 10pp vs. model) require immediate ALM Committee review and potential re-run of EVE stress.
- Any balance sheet duration gap exceeding 1.5 years requires CRO escalation to the ALM Committee with a hedging recommendation.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| ALM-F1 | Major | Behavioural deposit model uses fixed core deposit tenors; dynamic repricing behaviour (deposit migration to MMFs) not modelled; SVB 2023 demonstrated material failure mode for static behavioural models | Open |
| ALM-F2 | Major | Non-parallel rate shocks (bear steepener, bull flattener) not included in NII or EVE sensitivity calculation; Fed SIIR guidance expects at least 6 shock scenarios including twist and curvature | Open |
| ALM-F3 | Minor | FTP liquidity premiums recalibrated annually; intra-year funding market dislocations not reflected in desk charges until the next calibration cycle | Open |
