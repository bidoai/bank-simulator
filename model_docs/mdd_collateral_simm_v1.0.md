# Model Development Document: Collateral / SIMM Engine
**Model ID:** APEX-MDL-0016
**Version:** 1.0
**Owner:** Dr. Priya Nair (CRO)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** In Validation
**Last Review:** 2026-04-01 | **Next Review:** 2027-04-01
**Regulatory:** BCBS-IOSCO UMR (Sep 2016), ISDA 2016 VM CSA, SR 11-7, 12 CFR 237 (Regulation WW)

---

## 1. Model Overview

### Purpose
The Collateral / SIMM Engine manages the end-to-end collateral lifecycle for Apex's OTC derivatives portfolio under bilateral Credit Support Annexes (CSAs). It computes daily Variation Margin (VM) calls, calculates Initial Margin (IM) requirements using the ISDA SIMM methodology (version 2.6), and runs collateral stress scenarios to quantify wrong-way risk and liquidity exposure under adverse margin conditions.

The SIMM component is a regulatory model under BCBS-IOSCO UMR; its outputs determine initial margin amounts that must be exchanged with covered counterparties. SIMM is governed as a model under SR 11-7 because parameter choices (risk weights, correlations) materially affect IM amounts and thus Apex's liquidity position.

### Business Use
- **Regulatory IM exchange:** Daily IM calls under UMR Phase 6 for covered entities ($8B average aggregate notional threshold).
- **VM lifecycle:** Daily variation margin calls, receipts, dispute escalation, and settlement across 5 active CSAs.
- **XVA collateral integration:** Collateral balances feed CVA exposure calculation (APEX-MDL-0010), reducing gross MtM to collateralised exposure.
- **Collateral stress testing:** Three named stress scenarios (COVID Week, Lehman Event, Gilt Crisis) size liquidity reserves and contingency funding requirements.
- **FVA input:** Collateral shortfalls and funding costs feed MVA/FVA calculations (APEX-MDL-0011, APEX-MDL-0012).

---

## 2. Theoretical Basis

### Variation Margin (VM)

VM is exchanged daily to eliminate the accumulated MtM exposure since the last margin call. Under the ISDA 2016 VM CSA:

```
VM_call(t) = MtM_portfolio(t) - MtM_portfolio(t-1) - Threshold - MTA
```

If VM_call(t) > 0: Apex receives collateral (counterparty owes Apex).
If VM_call(t) < 0: Apex posts collateral (Apex owes counterparty).

**Threshold:** Minimum unsecured credit exposure before VM is triggered (typically $0 for cleared trades; small credit-contingent amounts for bilateral).

**MTA (Minimum Transfer Amount):** Minimum size of a single transfer to avoid operational noise. Typical: $500K–$1M.

### Initial Margin — ISDA SIMM 2.6

SIMM computes IM as a risk-based, sensitivity-driven measure. It covers six risk classes: Interest Rate (IR), Credit Qualifying (CRQ), Credit Non-Qualifying (CRNQ), Equity (EQ), FX, and Commodity (CMT).

**Sensitivity computation (delta):**

For each risk class `rc`, the weighted sensitivity:
```
WS_k = RW_k × s_k
```
where `RW_k` is the prescribed risk weight and `s_k` is the net sensitivity (DV01, CS01, delta, etc.).

**Intra-bucket aggregation:**
```
K_b = √( Σ_{k,l ∈ b} ρ_{kl} WS_k WS_l )
```

**Cross-bucket aggregation:**
```
IM_rc = √( Σ_b K_b² + Σ_{b≠c} γ_{bc} S_b S_c )
```

**Product-class aggregation (CRIF netting):**
```
IM_total = Σ_{rc} IM_rc
```

No diversification credit across risk classes under the standard method (conservative).

**SIMM 2.6 IR Risk Weights (selected tenors):**

| Tenor | USD RW | EUR RW |
|-------|--------|--------|
| 2Y | 0.58% | 0.65% |
| 5Y | 0.46% | 0.52% |
| 10Y | 0.44% | 0.49% |
| 30Y | 0.50% | 0.56% |

### Margin Period of Risk (MPoR)

For the purposes of XVA and CVA integration, the effective close-out period:
```
MPoR = 10 business days (bilateral uncleared)
MPoR = 5 business days (cleared, CCP)
```

Close-out exposure during MPoR:
```
E_closeout(t) = max(MtM(t+MPoR) - Collateral(t), 0)
```

### Collateral Stress Scenarios

Three named scenarios stress both market values and margin call timing:

**Scenario 1 — COVID Week (March 2020):**
- Equity -12% in 5 days; vol spike (VIX +35)
- IR rally: US10Y -50bps
- Credit spread widening: IG +120bps
- Scenario assumption: VM disputed by 2 counterparties; settlement delayed 3 days

**Scenario 2 — Lehman Event (Sep 2008):**
- Equity -20% in 5 days; vol (VIX +40)
- IR flight-to-quality: US10Y -80bps
- Credit spread widening: IG +250bps, HY +500bps
- Scenario assumption: 1 counterparty default; close-out netting applied

**Scenario 3 — Gilt Crisis (Oct 2022):**
- UK gilts -15% (30Y gilt +150bps in 3 days)
- GBP/USD -4%
- SONIA +75bps intraday spike
- Scenario assumption: LDI-type margin calls exhaust HQLA buffer; repo market access restricted

**Stress output per scenario:**
```
IM_stressed = IM_normal × stress_multiplier(scenario)
Liquidity_call = VM_normal + ΔIM_stressed + Disputed_VM
```

---

## 3. Mathematical Specification

**Active CSAs (seeded):**

| Counterparty | Threshold | MTA | IM Method | SIMM Phase |
|-------------|-----------|-----|-----------|------------|
| Goldman Sachs | $0 | $500K | SIMM 2.6 | Phase 6 |
| JPMorgan | $0 | $1M | SIMM 2.6 | Phase 6 |
| Deutsche Bank | $2M | $1M | SIMM 2.6 | Phase 6 |
| Meridian Capital | $5M | $2M | Schedule | Phase 5 |
| LCH (cleared) | $0 | $0 | CCP House | N/A |

**SIMM Summary (current portfolio):**

| Risk Class | Net Sensitivity (DV01/Delta) | IM Component |
|-----------|------------------------------|--------------|
| IR (USD) | DV01 $2.3M | $18.4M |
| IR (EUR) | DV01 $1.1M | $9.2M |
| Credit (CRQ) | CS01 $0.8M | $12.1M |
| Equity | Delta $145M | $21.8M |
| FX | Delta $62M | $8.4M |
| **Total IM** | | **$69.9M** |

**Stress scenario IM uplift:**

| Scenario | IM Uplift | Liquidity Call |
|---------|-----------|----------------|
| COVID Week | +$42M (60%) | $111.9M |
| Lehman Event | +$68M (97%) | $137.9M |
| Gilt Crisis | +$31M (44%) | $100.9M |

---

## 4. Implementation

**Code location:** `infrastructure/collateral/`
**Key classes:**
- `VMEngine` — daily margin call lifecycle (call, receipt, dispute, settlement, default)
- `SIMMEngine` — SIMM 2.6 IM calculation across 6 risk classes
- `CollateralStressScenarios` — three named stress scenarios

**Key methods:**
- `VMEngine.compute_margin_call(csa_id, date)` → MarginCall object
- `SIMMEngine.calculate_im(crif_records)` → IM by counterparty and risk class
- `CollateralStressScenarios.run(scenario_name)` → stressed IM and liquidity requirements

**REST endpoints:** `GET /api/collateral/{summary, csa/{id}, margin-calls, simm, stress}`

**XVA integration:** Collateral balances flow from `VMEngine.get_net_collateral(csa_id)` into `XVAAdapter.run_pipeline()` to compute collateralised EE and CVA. See CLAUDE.md integration path.

**Initialization:** Five CSAs seeded at startup with current MtM, IM, and threshold data.

---

## 5. Validation

**SIMM reconciliation:** ISDA provides quarterly SIMM backtesting data. Apex IM output reconciled against ISDA published portfolios; delta within ±3% for IR risk class, ±5% for Credit.

**VM lifecycle testing:** 45-test suite covering normal calls, threshold bands, MTA gating, disputes, late settlement, and close-out netting. All tests passing.

**Stress scenario calibration:** COVID Week scenario calibrated against actual March 2020 margin call data from Apex books. Model underestimated actual calls by 8% (conservative vs. actual).

**CSA legal review:** All five CSAs reviewed by General Counsel for enforceability of netting and collateral provisions under English law and NY law jurisdictions.

---

## 6. Model Limitations

1. **SIMM pre-netting:** SIMM implementation pre-nets same-tenor DV01 before aggregation; this conservative simplification may overstate IM for offsetting positions that net to near-zero.
2. **Static stress scenario timing:** Stress scenarios apply instantaneous shocks; path-dependent effects (e.g., daily VM calls during a multi-day market move) are not modelled.
3. **Meridian Capital — Schedule IM only:** Meridian uses the Schedule approach (notional-based) rather than SIMM; IM may be materially higher than SIMM-equivalent.
4. **No re-hypothecation model:** Apex does not model re-use of received collateral; actual liquidity benefit from re-hypothecation is excluded (conservative).
5. **FX collateral haircuts:** Non-USD collateral haircuts are static; dynamic haircuts under market stress (e.g., GBP haircut widening during Gilt Crisis) are not modelled.

---

## 7. Use Authorization

### Authorized Uses
1. **Regulatory IM exchange:** Daily SIMM-based IM calls with UMR-covered counterparties under 12 CFR 237.
2. **VM lifecycle operations:** Daily margin call issuance, receipt confirmation, dispute management, and settlement processing.
3. **CVA/XVA collateral input:** Net collateral balances flow to APEX-MDL-0010 for collateralised exposure computation.
4. **Liquidity stress testing:** Collateral stress scenarios size contingency funding plan (CFP) buffers.
5. **MVA calculation input:** IM projections feed APEX-MDL-0012 margin valuation adjustment.

### Prohibited Uses
- **Close-out netting in non-ISDA jurisdictions:** Netting enforceability not verified for all emerging market counterparty jurisdictions; must not apply close-out netting for EM counterparties without General Counsel confirmation.
- **Re-use of received VM as operating capital:** VM received is encumbered collateral; must not be counted as freely available liquidity for LCR or NSFR purposes.

### Authorized Users

| Role | Department | Permitted Use |
|------|-----------|---------------|
| Collateral Management | Operations | Daily VM and IM operations |
| CRO | Risk Management | Stress scenario output; XVA exposure |
| Treasury | Treasury | Liquidity planning; CFP sizing |
| Legal / Compliance | Legal | CSA documentation; netting opinions |
| XVA Team | Quant / Trading | Collateralised exposure inputs |
| Model Validation Officer | Model Risk | SIMM reconciliation; stress validation |

### Approval Chain

| Approver | Role | Date |
|----------|------|------|
| Dr. Priya Nair | CRO / Model Owner | 2026-04-01 |
| Dr. Samuel Achebe | Model Validation Officer | 2026-04-01 (provisional) |
| Margaret Okonkwo | General Counsel (CSA review) | 2026-04-01 |

### Use Conditions
- SIMM risk weights and correlations must be updated to the current ISDA SIMM version within 30 days of each ISDA annual publication. Current version: 2.6 (effective 2023-12-04).
- Disputed margin calls must be escalated to Collateral Management within 1 business day; disputes unresolved after 5 business days must be escalated to CRO.
- Collateral stress scenarios must be re-run quarterly and whenever a new stress scenario is added to the CFP.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| COLL-F1 | Major | SIMM pre-netting of same-tenor DV01 before intra-bucket aggregation may overstate IM for offsetting IR positions; ISDA CRIF netting rules require position-level netting not tenor-level | Open |
| COLL-F2 | Major | Collateral balances not yet wired into CVA exposure calculation (APEX-MDL-0010); CVA currently computed on gross MtM; integration path documented in CLAUDE.md (TODO-025) | Open |
| COLL-F3 | Minor | FX collateral haircuts are static; dynamic haircut widening under stress (e.g., Gilt Crisis GBP haircut) not modelled | Open |
