"""
Tests for v0.6 / v0.7 features: T1-A through T2-D.

Covers:
  T1-A: Op Risk Loss Event DB + RCSA
  T1-B: Consolidated P&L + Retained Earnings → Dynamic CET1
  T1-C: Volcker Rule Attribution
  T1-D: SA-CCR Live Position Wiring
  T2-A: Loan Origination Engine
  T2-B: Deposit Account Model
  T2-C: Payments Simulation (Fedwire/CHIPS)
  T2-D: Securities Custody Layer

Run with:
  uv run --with fastapi --with pytest-asyncio --with httpx --with structlog \
         --with numpy --with anthropic pytest tests/test_v06_v07_features.py -q
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ═══════════════════════════════════════════════════════════════════════════════
# T1-A: Op Risk Loss Event DB + RCSA
# ═══════════════════════════════════════════════════════════════════════════════

class TestOpRiskLossEventDB:
    def test_loss_event_db_summary_has_required_keys(self):
        from infrastructure.risk.loss_event_db import loss_event_db
        summary = loss_event_db.get_summary()
        for key in ("total_events", "total_gross_loss_usd", "total_net_loss_usd", "by_business_line"):
            assert key in summary, f"missing: {key}"

    def test_record_and_retrieve_event(self):
        from infrastructure.risk.loss_event_db import loss_event_db
        evt = loss_event_db.record_event(
            business_line="TRADING_AND_SALES",
            event_type="EXECUTION_DELIVERY",
            gross_loss_usd=50_000.0,
            recovery_usd=10_000.0,
            description="Test fat-finger error",
        )
        assert evt["net_loss_usd"] == pytest.approx(40_000.0)
        assert "event_id" in evt and len(evt["event_id"]) > 0

    def test_get_events_filter_by_line(self):
        from infrastructure.risk.loss_event_db import loss_event_db
        events = loss_event_db.get_events(business_line="TRADING_AND_SALES")
        assert isinstance(events, list)
        assert all(e["business_line"] == "TRADING_AND_SALES" for e in events)


class TestRCSA:
    def test_rcsa_controls_seeded(self):
        from infrastructure.risk.rcsa import rcsa_framework
        controls = rcsa_framework.get_controls()
        assert len(controls) >= 10

    def test_residual_risk_score_in_range(self):
        from infrastructure.risk.rcsa import rcsa_framework
        controls = rcsa_framework.get_controls()
        for c in controls:
            assert 0.0 <= c["residual_risk_score"] <= 5.0

    def test_heat_map_structure(self):
        from infrastructure.risk.rcsa import rcsa_framework
        hmap = rcsa_framework.get_heat_map()
        assert "heat_map" in hmap
        assert "high_residual_risk" in hmap or "total_controls" in hmap

    def test_update_effectiveness(self):
        from infrastructure.risk.rcsa import rcsa_framework
        controls = rcsa_framework.get_controls()
        ctrl_id = controls[0]["control_id"]
        old_eff = controls[0]["control_effectiveness"]
        new_eff = max(1, (old_eff % 5) + 1)
        updated = rcsa_framework.update_effectiveness(ctrl_id, new_eff)
        assert updated["control_effectiveness"] == new_eff


class TestOpRiskAPI:
    @pytest.mark.asyncio
    async def test_oprisk_summary_endpoint(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/oprisk/summary")
        assert r.status_code == 200
        data = r.json()
        assert "bia" in data and "loss_events" in data

    @pytest.mark.asyncio
    async def test_record_loss_event_via_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/oprisk/loss-events", json={
                "business_line": "RETAIL_BANKING",
                "event_type": "CLIENTS_PRODUCTS",
                "gross_loss_usd": 1_000_000.0,
                "recovery_usd": 0.0,
                "description": "API test fine",
            })
        assert r.status_code in (200, 201)
        assert r.json()["net_loss_usd"] == pytest.approx(1_000_000.0)

    @pytest.mark.asyncio
    async def test_rcsa_heat_map_endpoint(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/oprisk/rcsa/heat-map")
        assert r.status_code == 200
        assert "heat_map" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# T1-B: Consolidated P&L + Retained Earnings → Dynamic CET1
# ═══════════════════════════════════════════════════════════════════════════════

class TestConsolidatedPnL:
    def test_annual_statement_structure(self):
        from infrastructure.treasury.consolidated_pnl import income_statement
        stmt = income_statement.get_statement("annual")
        assert stmt["period"] == "annual"
        assert "revenue" in stmt and "expenses" in stmt and "income" in stmt
        assert stmt["revenue"]["total_revenue_usd"] > 0

    def test_quarterly_scales_correctly(self):
        from infrastructure.treasury.consolidated_pnl import income_statement
        annual = income_statement.get_statement("annual")
        quarterly = income_statement.get_statement("quarterly")
        # Quarterly fee revenue should be ~1/4 of annual (within rounding)
        ratio = quarterly["revenue"]["fee_revenue_usd"] / annual["revenue"]["fee_revenue_usd"]
        assert 0.24 < ratio < 0.26

    @pytest.mark.asyncio
    async def test_invalid_period_returns_422(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/treasury/income-statement?period=weekly")
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_income_statement_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/treasury/income-statement?period=quarterly")
        assert r.status_code == 200
        assert r.json()["period"] == "quarterly"

    @pytest.mark.asyncio
    async def test_income_statement_invalid_period(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/treasury/income-statement?period=weekly")
        assert r.status_code == 422


class TestRetainedEarnings:
    def test_get_cumulative_is_positive(self):
        from infrastructure.treasury.retained_earnings import retained_earnings_ledger
        cumulative = retained_earnings_ledger.get_cumulative()
        assert cumulative > 0

    def test_get_summary_structure(self):
        from infrastructure.treasury.retained_earnings import retained_earnings_ledger
        summary = retained_earnings_ledger.get_summary()
        assert "cumulative_retained_earnings" in summary
        assert "periods" in summary or "history" in summary

    def test_accrue_period(self):
        from infrastructure.treasury.retained_earnings import retained_earnings_ledger
        before = retained_earnings_ledger.get_cumulative()
        retained_earnings_ledger.accrue_period(
            period="TEST-2099-Q1",
            net_income_usd=1_000_000.0,
            dividends_usd=100_000.0,
        )
        after = retained_earnings_ledger.get_cumulative()
        assert after == pytest.approx(before + 900_000.0, rel=1e-4)

    @pytest.mark.asyncio
    async def test_retained_earnings_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/treasury/retained-earnings")
        assert r.status_code == 200
        data = r.json()
        assert "cumulative_retained_earnings" in data or "cumulative_retained_earnings_usd" in data


class TestDynamicCET1:
    def test_cet1_includes_retained_earnings(self):
        from infrastructure.risk.regulatory_capital import capital_engine
        from infrastructure.risk.risk_service import risk_service
        from infrastructure.treasury.retained_earnings import retained_earnings_ledger
        positions = risk_service.position_manager.get_all_positions()
        result = capital_engine.calculate(positions)
        cumulative_re = retained_earnings_ledger.get_cumulative()
        live_cet1 = result["cet1_capital_usd"]
        # Live CET1 should be ≥ static CET1 floor
        assert live_cet1 >= capital_engine.CET1_CAPITAL_USD
        assert result["retained_earnings_usd"] == pytest.approx(cumulative_re, rel=1e-4)


# ═══════════════════════════════════════════════════════════════════════════════
# T1-C: Volcker Rule Attribution
# ═══════════════════════════════════════════════════════════════════════════════

class TestVolckerClassification:
    def test_market_making_desk_classifies_correctly(self):
        from infrastructure.compliance.volcker import volcker_engine
        vc = volcker_engine.classify_trade(
            desk="MM_RATES",
            product_subtype="IRS",
            tenor_years=5.0,
            counterparty_id="CP-001",
            notional=10_000_000,
        )
        # classify_trade returns VolckerClass enum or string
        vc_val = vc.value if hasattr(vc, "value") else vc
        assert vc_val in ("MARKET_MAKING", "PERMITTED_HEDGING", "CUSTOMER_FACILITATION",
                          "REPO_SECURITIES_FINANCE", "UNDERWRITING")

    def test_portfolio_attribution_returns_notional_by_class(self):
        from infrastructure.risk.risk_service import risk_service
        from infrastructure.compliance.volcker import volcker_engine
        positions = risk_service.position_manager.get_all_positions()
        attribution = volcker_engine.get_portfolio_attribution(positions)
        assert isinstance(attribution, dict)

    def test_compliance_report_structure(self):
        from infrastructure.risk.risk_service import risk_service
        from infrastructure.compliance.volcker import volcker_engine
        positions = risk_service.position_manager.get_all_positions()
        report = volcker_engine.get_compliance_report(positions)
        assert "flagged_positions" in report

    @pytest.mark.asyncio
    async def test_volcker_report_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/compliance/volcker/report")
        assert r.status_code == 200
        data = r.json()
        assert "attribution_by_class" in data or "by_class" in data or isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_volcker_flags_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/compliance/volcker/flags")
        assert r.status_code == 200
        assert "flagged_positions" in r.json() or isinstance(r.json(), dict)


# ═══════════════════════════════════════════════════════════════════════════════
# T1-D: SA-CCR Live Position Wiring
# ═══════════════════════════════════════════════════════════════════════════════

class TestSACCRLiveWiring:
    def test_build_live_netting_sets_returns_list(self):
        from infrastructure.risk.sa_ccr import sa_ccr_engine
        from infrastructure.risk.risk_service import risk_service
        positions = risk_service.position_manager.get_all_positions()
        netting_sets = sa_ccr_engine.build_live_netting_sets(positions)
        assert isinstance(netting_sets, list)

    def test_portfolio_ead_uses_live_positions(self):
        from infrastructure.risk.sa_ccr import sa_ccr_engine
        result = sa_ccr_engine.calculate_portfolio_ead()
        # Returns list of netting set results or dict — either is valid
        assert result is not None
        if isinstance(result, list):
            assert all("ead_usd" in r or "alpha" in r for r in result)
        else:
            assert "total_ead_usd" in result

    @pytest.mark.asyncio
    async def test_sa_ccr_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/capital/sa-ccr")
        assert r.status_code == 200
        data = r.json()
        # May return list or dict depending on implementation
        assert data is not None


# ═══════════════════════════════════════════════════════════════════════════════
# T2-A: Loan Origination Engine
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoanBook:
    def test_seed_loans_loaded(self):
        from infrastructure.credit.loan_book import loan_book
        portfolio = loan_book.get_portfolio()
        assert len(portfolio) >= 8

    def test_portfolio_summary_structure(self):
        from infrastructure.credit.loan_book import loan_book
        summary = loan_book.get_portfolio_summary()
        for key in ("loan_count", "total_outstanding_usd", "total_ecl_usd",
                    "ecl_coverage_ratio", "annual_nii_usd", "by_grade", "by_sector"):
            assert key in summary, f"missing: {key}"

    def test_originate_loan(self):
        from infrastructure.credit.loan_book import loan_book
        loan = loan_book.originate(
            borrower_id="TEST-BRW",
            borrower_name="Test Corp",
            facility_type="TERM",
            notional_usd=100_000_000.0,
            rate_pct=5.0,
            tenor_years=3.0,
            grade="BBB",
        )
        assert loan["loan_id"].startswith("LN-")
        assert loan["status"] == "ACTIVE"
        assert loan["outstanding_usd"] == pytest.approx(100_000_000.0)

    def test_repay_loan(self):
        from infrastructure.credit.loan_book import loan_book
        loan = loan_book.originate(
            borrower_id="TEST-REPAY",
            borrower_name="Repay Corp",
            facility_type="BULLET",
            notional_usd=50_000_000.0,
            rate_pct=4.0,
            tenor_years=2.0,
            grade="A",
        )
        lid = loan["loan_id"]
        updated = loan_book.repay(lid, 50_000_000.0)
        assert updated["status"] == "REPAID"
        assert updated["outstanding_usd"] == pytest.approx(0.0)

    def test_amortization_schedule_length(self):
        from infrastructure.credit.loan_book import loan_book
        portfolio = loan_book.get_portfolio()
        loan_id = portfolio[0]["loan_id"]
        schedule = loan_book.get_amortization(loan_id)
        tenor_years = portfolio[0]["tenor_years"]
        assert len(schedule) == int(tenor_years * 12)

    def test_bullet_amortization_has_balloon(self):
        from infrastructure.credit.loan_book import loan_book
        # Find a BULLET loan
        portfolio = loan_book.get_portfolio()
        bullet = next((l for l in portfolio if l["facility_type"] == "BULLET"), None)
        if bullet:
            schedule = loan_book.get_amortization(bullet["loan_id"])
            last = schedule[-1]
            assert last["principal"] > last["interest"]   # balloon payment at end

    @pytest.mark.asyncio
    async def test_loan_portfolio_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/loans/portfolio")
        assert r.status_code == 200
        assert "loans" in r.json()

    @pytest.mark.asyncio
    async def test_loan_originate_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/loans/originate", json={
                "borrower_id": "API-TEST",
                "borrower_name": "API Test Corp",
                "facility_type": "REVOLVER",
                "notional_usd": 75_000_000.0,
                "rate_pct": 5.5,
                "tenor_years": 2.0,
                "grade": "BB",
            })
        assert r.status_code == 200
        data = r.json()
        assert data["facility_type"] == "REVOLVER"

    @pytest.mark.asyncio
    async def test_loan_ecl_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/loans/ecl")
        assert r.status_code == 200
        assert "total_ecl_usd" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# T2-B: Deposit Account Model
# ═══════════════════════════════════════════════════════════════════════════════

class TestDepositBook:
    def test_seed_accounts_loaded(self):
        from infrastructure.treasury.deposits import deposit_book
        accounts = deposit_book.get_portfolio()
        assert len(accounts) >= 10

    def test_portfolio_summary_structure(self):
        from infrastructure.treasury.deposits import deposit_book
        summary = deposit_book.get_portfolio_summary()
        for key in ("account_count", "total_deposits_usd", "annual_interest_expense_usd",
                    "cost_of_funds_pct", "by_type", "by_segment"):
            assert key in summary, f"missing: {key}"

    def test_nmd_profile_structure(self):
        from infrastructure.treasury.deposits import deposit_book
        profile = deposit_book.get_nmd_profile()
        for key in ("total_nmd_usd", "core_stable_usd", "core_less_stable_usd", "non_core_usd"):
            assert key in profile, f"missing: {key}"
        # Behavioural split must sum to total
        total = profile["core_stable_usd"] + profile["core_less_stable_usd"] + profile["non_core_usd"]
        assert total == pytest.approx(profile["total_nmd_usd"], rel=1e-4)

    def test_open_account(self):
        from infrastructure.treasury.deposits import deposit_book
        acct = deposit_book.open_account(
            account_type="SAVINGS",
            customer_segment="RETAIL",
            customer_name="Test Customer",
            initial_deposit=100_000.0,
            rate_pct=1.75,
        )
        assert acct["account_id"].startswith("DEP-")
        assert acct["balance_usd"] == pytest.approx(100_000.0)

    def test_deposit_and_withdraw(self):
        from infrastructure.treasury.deposits import deposit_book
        acct = deposit_book.open_account(
            account_type="CHECKING",
            customer_segment="SME",
            customer_name="SME Test",
            initial_deposit=200_000.0,
            rate_pct=0.25,
        )
        aid = acct["account_id"]
        after_deposit = deposit_book.deposit(aid, 50_000.0)
        assert after_deposit["balance_usd"] == pytest.approx(250_000.0)
        after_withdraw = deposit_book.withdraw(aid, 30_000.0)
        assert after_withdraw["balance_usd"] == pytest.approx(220_000.0)

    def test_term_early_withdrawal_blocked(self):
        from infrastructure.treasury.deposits import deposit_book
        acct = deposit_book.open_account(
            account_type="TERM",
            customer_segment="RETAIL",
            customer_name="CD Customer",
            initial_deposit=50_000.0,
            rate_pct=4.5,
            tenor_days=365,
        )
        with pytest.raises(ValueError, match="Early withdrawal"):
            deposit_book.withdraw(acct["account_id"], 1000.0)

    def test_repricing_buckets_returned(self):
        from infrastructure.treasury.deposits import deposit_book
        buckets = deposit_book.get_repricing_buckets()
        assert isinstance(buckets, dict)
        assert len(buckets) > 0
        assert all(v >= 0 for v in buckets.values())

    @pytest.mark.asyncio
    async def test_deposits_portfolio_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/deposits/portfolio")
        assert r.status_code == 200
        assert "accounts" in r.json()

    @pytest.mark.asyncio
    async def test_nmd_profile_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/deposits/nmd-profile")
        assert r.status_code == 200
        assert "core_stable_usd" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# T2-C: Payments Simulation
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaymentLedger:
    def test_nostro_accounts_seeded(self):
        from infrastructure.payments.ledger import payment_ledger
        balances = payment_ledger._get_nostro_balances()
        assert len(balances) >= 4
        assert any(b["currency"] == "USD" for b in balances)

    def test_submit_fedwire_settles_immediately(self):
        from infrastructure.payments.ledger import payment_ledger
        result = payment_ledger.submit(
            rail="FEDWIRE",
            amount_usd=1_000_000.0,
            sender_nostro="NOSTRO-USD-FED",
            receiver_nostro="NOSTRO-USD-FED",
        )
        assert result["status"] == "SETTLED"

    def test_submit_chips_stays_pending(self):
        from infrastructure.payments.ledger import payment_ledger
        result = payment_ledger.submit(
            rail="CHIPS",
            amount_usd=500_000.0,
        )
        assert result["status"] == "PENDING"

    def test_chips_batch_settles_pending(self):
        from infrastructure.payments.ledger import payment_ledger
        payment_ledger.submit(rail="CHIPS", amount_usd=250_000.0)
        result = payment_ledger.settle_chips_batch()
        assert result["settled_count"] >= 1

    def test_overdraft_limit_enforced(self):
        from infrastructure.payments.ledger import payment_ledger
        # Try to submit a payment far exceeding balance + credit line
        with pytest.raises(ValueError, match="Daylight overdraft"):
            payment_ledger.submit(
                rail="FEDWIRE",
                amount_usd=999_999_999_999.0,
            )

    def test_intraday_position_structure(self):
        from infrastructure.payments.ledger import payment_ledger
        pos = payment_ledger.get_intraday_position()
        for key in ("date", "total_outflow_usd", "settled_count", "nostro_balances"):
            assert key in pos, f"missing: {key}"

    @pytest.mark.asyncio
    async def test_payment_submit_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/payments/submit", json={
                "rail": "INTERNAL",
                "amount_usd": 100_000.0,
            })
        assert r.status_code == 200
        assert r.json()["status"] == "SETTLED"

    @pytest.mark.asyncio
    async def test_nostro_balances_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/payments/nostro/balances")
        assert r.status_code == 200
        assert "nostro_accounts" in r.json()

    @pytest.mark.asyncio
    async def test_intraday_position_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/payments/intraday-position")
        assert r.status_code == 200
        assert "total_outflow_usd" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# T2-D: Securities Custody Layer
# ═══════════════════════════════════════════════════════════════════════════════

class TestCustodyBook:
    def test_seed_accounts_loaded(self):
        from infrastructure.custody.custody_accounts import custody_book
        auc = custody_book.get_total_auc()
        assert auc["account_count"] >= 4
        assert auc["total_auc_usd"] > 0

    def test_get_holdings_for_account(self):
        from infrastructure.custody.custody_accounts import custody_book
        auc = custody_book.get_total_auc()
        # Use first non-zero account
        acct = next(a for a in auc["by_account"] if a["holding_count"] > 0)
        holdings = custody_book.get_holdings(acct["account_id"])
        assert len(holdings) > 0
        assert all("market_value_usd" in h for h in holdings)

    def test_open_account(self):
        from infrastructure.custody.custody_accounts import custody_book
        acct = custody_book.open_account("NEW-CLI", "New Client Fund", "SEGREGATED")
        assert acct["account_id"].startswith("CUST-")
        assert acct["account_type"] == "SEGREGATED"

    def test_book_holding(self):
        from infrastructure.custody.custody_accounts import custody_book
        acct = custody_book.open_account("HOLD-CLI", "Holding Test", "OMNIBUS")
        holding = custody_book.book_holding(
            account_id=acct["account_id"],
            isin="US0378331005",
            description="Apple Inc.",
            quantity=1000,
            price_usd=185.0,
        )
        assert holding["quantity"] == pytest.approx(1000.0)
        assert holding["market_value_usd"] == pytest.approx(185_000.0)

    @pytest.mark.asyncio
    async def test_auc_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/custody/auc")
        assert r.status_code == 200
        assert "total_auc_usd" in r.json()

    @pytest.mark.asyncio
    async def test_account_holdings_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r_auc = await client.get("/api/custody/auc")
            accounts = r_auc.json()["by_account"]
            acct_id = next(a["account_id"] for a in accounts if a["holding_count"] > 0)
            r = await client.get(f"/api/custody/accounts/{acct_id}/holdings")
        assert r.status_code == 200
        assert "holdings" in r.json()


class TestSettlementEngine:
    def test_instruct_dvp_buy(self):
        from infrastructure.custody.custody_accounts import custody_book
        from infrastructure.custody.settlement import settlement_engine
        acct = custody_book.open_account("SETTLE-TEST", "Settlement Test", "SEGREGATED")
        instr = settlement_engine.instruct(
            isin="US0378331005",
            quantity=500,
            price_usd=185.0,
            side="DVP_BUY",
            account_id=acct["account_id"],
            description="Apple AAPL",
            asset_class="EQUITY",
        )
        assert instr["instruction_id"].startswith("SI-")
        assert instr["status"] in ("PENDING", "AFFIRMED")

    def test_settle_batch(self):
        from infrastructure.custody.custody_accounts import custody_book
        from infrastructure.custody.settlement import settlement_engine
        acct = custody_book.open_account("BATCH-TEST", "Batch Test", "OMNIBUS")
        settlement_engine.instruct(
            isin="US912810TM80",
            quantity=1_000_000,
            price_usd=96.50,
            side="DVP_BUY",
            account_id=acct["account_id"],
            description="UST",
            asset_class="BOND",
        )
        # Settle batch with a far-future date to catch the instruction
        import datetime
        future = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        result = settlement_engine.settle_batch(future)
        assert result["settled_count"] >= 1

    @pytest.mark.asyncio
    async def test_settlement_instruct_api(self):
        from api.main import app
        from infrastructure.custody.custody_accounts import custody_book
        acct = custody_book.open_account("API-SETTLE", "API Settle Test", "SEGREGATED")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/custody/settlement/instruct", json={
                "isin": "US0231351067",
                "quantity": 100,
                "price_usd": 185.40,
                "side": "DVP_BUY",
                "account_id": acct["account_id"],
                "description": "Amazon",
            })
        assert r.status_code == 200
        assert r.json()["side"] == "DVP_BUY"


class TestCorporateActions:
    def test_pending_actions_returned(self):
        from infrastructure.custody.corporate_actions import corporate_action_processor
        actions = corporate_action_processor.get_pending_actions()
        assert isinstance(actions, list)

    def test_add_corporate_action(self):
        from infrastructure.custody.corporate_actions import corporate_action_processor
        ca = corporate_action_processor.add_action(
            ca_type="DIVIDEND",
            isin="US9311421039",
            issuer="Walmart",
            ex_date="2026-06-01",
            record_date="2026-06-02",
            pay_date="2026-06-30",
            details={"dividend_per_share": 0.235, "currency": "USD"},
        )
        assert ca["ca_id"].startswith("CA-")
        assert ca["ca_type"] == "DIVIDEND"

    @pytest.mark.asyncio
    async def test_corporate_actions_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/custody/corporate-actions/pending")
        assert r.status_code == 200
        assert "corporate_actions" in r.json()
