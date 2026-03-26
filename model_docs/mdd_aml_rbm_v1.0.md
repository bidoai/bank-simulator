# Model Development Document: AML Transaction Monitoring
**Model ID:** APEX-MDL-0008
**Version:** 1.0
**Owner:** Sarah Mitchell (BSA/AML Officer)
**Validator:** Dr. Samuel Achebe (Model Validation Officer)
**Status:** In Validation
**Last Review:** 2026-03-01 | **Next Review:** 2027-03-01
**Regulatory:** BSA 31 USC 5318, FinCEN 31 CFR 1020, SR 11-7, FFIEC BSA/AML Examination Manual

---

## 1. Model Overview

### Purpose
The AML Rule-Based Monitoring (RBM) model detects potentially suspicious financial activity across Apex Global Bank accounts. Rule alerts are reviewed by compliance analysts; confirmed suspicious activity is filed with FinCEN via Suspicious Activity Reports (SARs). SR 11-7 applies because the rules constitute a "model" under the regulatory definition — they are used to make material compliance decisions (SAR filing, account restrictions, law enforcement referrals).

### Business Use
- **Primary SAR workflow:** Alert → L1 analyst review → L2 adjudication → SAR filing or dismiss
- **Regulatory examination:** FFIEC examiners review alert rates, SAR conversion rates, and rule thresholds annually
- **Customer risk scoring:** Alert history feeds customer risk tier (Low/Medium/High/Prohibited)
- **Law enforcement referrals:** Structured transaction and sanctions alerts escalate directly to legal

---

## 2. Theoretical Basis

### SR 11-7 Model Risk Governance for Rule-Based Systems
Under SR 11-7 (2011), a "model" is any quantitative method or system used to translate inputs into estimates that influence decisions. AML rule engines qualify when:
- Rule outputs drive material decisions (SAR filing, account closure)
- Rules involve parameter choices (thresholds, lookback windows) subject to expert judgment
- Errors in rules could expose the bank to regulatory sanction (civil money penalties, formal agreements)

Rule-based systems are not exempt from SR 11-7 model risk governance merely because they lack stochastic components.

### Rule Typologies

**Typology 1 — Structuring (31 CFR 1020.315):**
```
ALERT if: Σ cash_deposits over 5 rolling days > $9,000
          AND any single deposit ≥ $2,000
          AND at least 3 deposits in the window
```
Rationale: Structuring is the act of breaking transactions into sub-$10,000 increments to evade Bank Secrecy Act reporting. The threshold is set at $9,000 (not $9,999) to provide detection buffer.

**Typology 2 — Velocity (Unusual Transaction Frequency):**
```
ALERT if: Transaction count in 24 hours > μ_customer + 3σ_customer
          AND total_volume > $50,000
```
where μ_customer and σ_customer are the 90-day rolling mean and standard deviation of daily transaction count for that customer segment.

**Typology 3 — Round-Dollar Transactions:**
```
ALERT if: ≥ 3 transactions with amount mod 1000 = 0
          within 7 days
          AND total > $25,000
```
Rationale: Round-dollar amounts are statistically anomalous in legitimate commerce and a common money laundering indicator.

**Typology 4 — Geographic Anomaly:**
```
ALERT if: Transaction originates from jurisdiction on FATF grey-list or OFAC SDN-adjacent
          AND amount > $5,000
          AND no prior transactions from that jurisdiction in 180 days
```
FATF grey-list and OFAC SDN list checked at transaction time via real-time lookup.

**Typology 5 — Layering (Rapid In/Out):**
```
ALERT if: Incoming wire > $25,000
          AND ≥ 70% of incoming amount transferred out within 48 hours
          AND receiving account not on approved counterparty list
```
Rationale: Rapid movement of funds through an account without plausible business purpose is a primary layering indicator.

**Typology 6 — PEP / High-Risk Customer:**
```
ALERT if: Customer is Politically Exposed Person (PEP) or immediate family of PEP
          AND transaction > $10,000 (any type)
```
PEP status from Dow Jones Risk & Compliance feed, refreshed weekly.

### Threshold Calibration Methodology
Thresholds are calibrated to achieve:
- Alert rate < 2% of total transactions (minimize analyst workload)
- SAR conversion rate > 15% of alerts (maximize true positive rate)
- False negative minimisation for structuring (regulatory zero-tolerance)

Calibration uses a 12-month lookback of historical alerts, SAR filings, and FinCEN industry benchmarks. Thresholds are reviewed annually or following material changes in transaction volumes.

---

## 3. Mathematical Specification

### Alert Rate Formula
```
Alert_rate = Alerts_30d / Transactions_30d
Target: Alert_rate < 0.02
```

### SAR Conversion Rate
```
SAR_conversion = SARs_filed_90d / Alerts_reviewed_90d
Target: SAR_conversion > 0.15
```

### Customer Risk Score (Simple Additive)
```
Risk_score = w_alert × alert_count_12m
           + w_sar × sar_count_lifetime
           + w_geo × geographic_risk_tier
           + w_pep × pep_flag
           + w_seg × segment_risk_tier

Risk_tier: [0, 25) = Low, [25, 60) = Medium, [60, 85) = High, [85, 100] = Prohibited
```

Weights (w) calibrated annually against confirmed fraud/SAR outcomes.

---

## 4. Implementation

**Code location:** `infrastructure/compliance/aml_monitor.py`
**Class:** `AMLMonitor`
**Key methods:**
- `screen_transaction(txn)` — applies all 6 typologies, returns list of triggered rules
- `calculate_risk_score(customer_id)` — computes customer risk tier
- `generate_alert(txn, rule_id)` — creates alert record for analyst queue

**Lookback windows:** Implemented using rolling 5-day, 7-day, 24-hour, and 90-day windows over the transaction database.

**External data dependencies:**
- FATF grey-list: updated quarterly, stored in `reference_data/fatf_greylist.json`
- OFAC SDN list: updated daily via FinCEN feed
- PEP database: Dow Jones Risk & Compliance API, refreshed weekly

---

## 5. Validation

**Alert rate backtesting:** Monthly alert rate tracked against 2% threshold. Current rate: 1.4% (within target).

**SAR conversion backtesting:** 90-day rolling SAR conversion rate tracked against 15% floor. Current rate: 19% (above target).

**Typology effectiveness audit:** Annual review compares alert volume and SAR conversion by typology. Typologies with SAR conversion < 5% are reviewed for threshold recalibration or retirement.

**Benchmark:** Alert rates compared against FFIEC BSA/AML peer bank data. Apex alert rate of 1.4% is below peer median 2.1% — within acceptable range; further reduction would risk under-detection.

**Independent testing:** Annual penetration test: compliance team constructs synthetic structuring and layering scenarios; confirms all 6 typologies fire correctly.

---

## 6. Model Limitations

1. **Rule-based only:** No machine learning or network analysis. Sophisticated laundering schemes that individually fall below thresholds but collectively represent suspicious patterns are not detected.
2. **No transaction network analysis:** Shell company chains and circular fund flows not modelled. Beneficial ownership network analysis is a known gap.
3. **Static velocity thresholds:** Velocity limits (Typology 2) use segment-level averages; not dynamically adjusted for individual customer behaviour patterns.
4. **FATF grey-list lag:** FATF updates quarterly; a jurisdiction added in Q4 will not trigger Typology 4 until the next reference data refresh.
5. **PEP database coverage:** Dow Jones PEP coverage limited to tier-1 geographies; sub-national PEPs in certain emerging markets may not be captured.

---

## 8. Open Findings

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| AML-F1 | Major | No transaction network analysis — shell company layering not detected; peer banks deploying graph analytics show 40% improvement in SAR conversion | Open |
| AML-F2 | Major | Velocity thresholds (Typology 2) use segment averages, not individual customer baselines; elevated false positive rate for legitimate high-frequency traders | Open |
| AML-F3 | Minor | FATF grey-list refresh is quarterly; FinCEN expects real-time or near-real-time country risk updates | Open |
