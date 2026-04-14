"""
Tests for v0.8 Tier 3 features — Revenue Diversification.

  T3-A: IBD Deal Pipeline
  T3-B: Wealth Management Client Book
  T3-C: FRTB IMA Completion
  T3-D: Historical Crisis Replay

Run with:
  uv run --with fastapi --with pytest-asyncio --with httpx --with structlog \\
         --with numpy --with anthropic --with python-dotenv --with scipy \\
         pytest tests/test_t3_features.py -q
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ═══════════════════════════════════════════════════════════════════════════════
# T3-A: IBD Deal Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

class TestDealPipeline:
    def test_seed_deals_loaded(self):
        from infrastructure.ibd.deal_pipeline import deal_pipeline
        deals = deal_pipeline.get_pipeline()
        assert len(deals) >= 8

    def test_closed_deals_have_fee_revenue(self):
        from infrastructure.ibd.deal_pipeline import deal_pipeline
        closed = deal_pipeline.get_pipeline(stage="CLOSED")
        assert len(closed) >= 3
        assert all(d["fee_earned_usd"] > 0 for d in closed)

    def test_non_closed_deals_have_zero_fee(self):
        from infrastructure.ibd.deal_pipeline import deal_pipeline
        non_closed_stages = ["ORIGINATION", "MANDATE", "PITCHING", "SIGNED"]
        for stage in non_closed_stages:
            deals = deal_pipeline.get_pipeline(stage=stage)
            for d in deals:
                assert d["fee_earned_usd"] == pytest.approx(0.0), \
                    f"Expected 0 fee for stage {stage}, got {d['fee_earned_usd']}"

    def test_advance_to_closed_accrues_fee(self):
        from infrastructure.ibd.deal_pipeline import deal_pipeline
        new = deal_pipeline.add_deal(
            deal_type="MA",
            deal_name="Test Acquisition",
            client_name="Test Corp",
            deal_value_usd=1_000_000_000.0,
            fee_rate=0.010,
            stage="EXECUTION",
        )
        did = new["deal_id"]
        closed = deal_pipeline.advance_stage(did, "CLOSED")
        assert closed["fee_earned_usd"] == pytest.approx(10_000_000.0)  # 1% × $1B

    def test_advance_to_fallen_away_zeroes_fee(self):
        from infrastructure.ibd.deal_pipeline import deal_pipeline
        new = deal_pipeline.add_deal(
            deal_type="ECM",
            deal_name="Test IPO",
            client_name="Startup Inc",
            deal_value_usd=500_000_000.0,
            fee_rate=0.04,
            stage="PITCHING",
        )
        fallen = deal_pipeline.advance_stage(new["deal_id"], "FALLEN_AWAY")
        assert fallen["fee_earned_usd"] == pytest.approx(0.0)
        assert fallen["stage"] == "FALLEN_AWAY"

    def test_league_table_structure(self):
        from infrastructure.ibd.deal_pipeline import deal_pipeline
        lt = deal_pipeline.get_league_table()
        assert "by_type" in lt
        assert "MA" in lt["by_type"]
        assert "ECM" in lt["by_type"]
        assert "DCM" in lt["by_type"]
        assert "summary" in lt
        assert lt["summary"]["total_fees_earned_usd"] > 0

    def test_annual_fee_revenue_positive(self):
        from infrastructure.ibd.deal_pipeline import deal_pipeline
        rev = deal_pipeline.get_annual_fee_revenue()
        assert rev > 0

    def test_add_deal_and_retrieve(self):
        from infrastructure.ibd.deal_pipeline import deal_pipeline
        new = deal_pipeline.add_deal(
            deal_type="DCM",
            deal_name="Retrieve Test Bond",
            client_name="Bond Issuer Ltd",
            deal_value_usd=2_000_000_000.0,
            fee_rate=0.008,
        )
        retrieved = deal_pipeline.get_deal(new["deal_id"])
        assert retrieved is not None
        assert retrieved["deal_name"] == "Retrieve Test Bond"

    @pytest.mark.asyncio
    async def test_ibd_pipeline_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/ibd/pipeline")
        assert r.status_code == 200
        data = r.json()
        assert "deals" in data and len(data["deals"]) >= 8

    @pytest.mark.asyncio
    async def test_ibd_league_table_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/ibd/league-table")
        assert r.status_code == 200
        assert "by_type" in r.json()

    @pytest.mark.asyncio
    async def test_ibd_revenue_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/ibd/revenue")
        assert r.status_code == 200
        assert r.json()["annual_fee_revenue_usd"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# T3-B: Wealth Management Client Book
# ═══════════════════════════════════════════════════════════════════════════════

class TestClientBook:
    def test_seed_clients_loaded(self):
        from infrastructure.wealth.client_book import client_book
        clients = client_book.get_all_clients()
        assert len(clients) >= 6

    def test_total_aum_approx_8b(self):
        from infrastructure.wealth.client_book import client_book
        clients = client_book.get_all_clients()
        total = sum(c["aum_usd"] for c in clients)
        # Seed data = $8.1B; allow tolerance for test-added clients
        assert total >= 8_000_000_000.0

    def test_fee_bps_by_segment(self):
        from infrastructure.wealth.client_book import client_book, _FEE_BPS
        clients = client_book.get_all_clients()
        for c in clients:
            expected_bps = _FEE_BPS[c["segment"]]
            assert c["fee_bps"] == expected_bps, \
                f"Client {c['client_id']} segment {c['segment']}: expected {expected_bps}bps"

    def test_holdings_sum_to_aum(self):
        from infrastructure.wealth.client_book import client_book
        clients = client_book.get_all_clients()
        for c in clients:
            holdings = client_book.get_holdings(c["client_id"])
            if holdings:
                total_mv = sum(h["market_value_usd"] for h in holdings)
                assert abs(total_mv - c["aum_usd"]) < 1.0, \
                    f"Holdings MV {total_mv} != AUM {c['aum_usd']}"

    def test_fee_formula_family_office(self):
        from infrastructure.wealth.client_book import client_book
        # WM-001: $2.4B @ 40bps = $9.6M
        c = client_book.get_client("WM-001")
        if c:
            expected_fee = 2_400_000_000.0 * 40 / 10000
            assert c["annual_fee_usd"] == pytest.approx(expected_fee, rel=1e-3)

    def test_calculate_annual_fees_positive(self):
        from infrastructure.wealth.client_book import client_book
        fees = client_book.calculate_annual_fees()
        assert fees > 0

    def test_add_client_then_retrieve(self):
        from infrastructure.wealth.client_book import client_book
        client_book.add_client(
            client_id="WM-TEST-99",
            client_name="Test HNWI Client",
            segment="HNWI",
            aum_usd=500_000_000.0,
            mandate_type="ADVISORY",
            risk_profile="BALANCED",
        )
        c = client_book.get_client("WM-TEST-99")
        assert c is not None
        assert c["fee_bps"] == 75
        assert c["annual_fee_usd"] == pytest.approx(500_000_000.0 * 75 / 10000)

    def test_update_aum_recalculates_fee(self):
        import uuid as _uuid
        from infrastructure.wealth.client_book import client_book
        uid = f"WM-AUM-{_uuid.uuid4().hex[:8].upper()}"
        c = client_book.add_client(
            client_id=uid,
            client_name="AUM Test",
            segment="UHNWI",
            aum_usd=1_000_000_000.0,
            mandate_type="DISCRETIONARY",
            risk_profile="GROWTH",
        )
        before_fee = c["annual_fee_usd"]
        updated = client_book.update_aum(uid, 2_000_000_000.0)
        assert updated["aum_usd"] == pytest.approx(2_000_000_000.0)
        assert updated["annual_fee_usd"] == pytest.approx(before_fee * 2, rel=1e-3)

    @pytest.mark.asyncio
    async def test_wealth_clients_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/wealth/clients")
        assert r.status_code == 200
        assert "clients" in r.json()

    @pytest.mark.asyncio
    async def test_wealth_revenue_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/wealth/revenue")
        assert r.status_code == 200
        assert r.json()["annual_fee_revenue_usd"] > 0

    @pytest.mark.asyncio
    async def test_wealth_summary_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/wealth/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_aum_usd" in data and "by_segment" in data


# ═══════════════════════════════════════════════════════════════════════════════
# T3-B Integration: Fee sources in ConsolidatedIncomeStatement
# ═══════════════════════════════════════════════════════════════════════════════

class TestLiveFeeRevenue:
    def test_ibd_fee_source_is_live(self):
        from infrastructure.treasury.consolidated_pnl import income_statement
        stmt = income_statement.get_statement("annual")
        assert stmt["fee_sources"]["investment_banking"] == "live"

    def test_wealth_fee_source_is_live(self):
        from infrastructure.treasury.consolidated_pnl import income_statement
        stmt = income_statement.get_statement("annual")
        assert stmt["fee_sources"]["wealth_management"] == "live"

    def test_fee_revenue_is_stub_false(self):
        from infrastructure.treasury.consolidated_pnl import income_statement
        stmt = income_statement.get_statement("annual")
        assert stmt["fee_revenue_is_stub"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# T3-C: FRTB IMA Completion
# ═══════════════════════════════════════════════════════════════════════════════

class TestFRTBIMA:
    def test_calculate_es_returns_dict(self):
        from infrastructure.risk.frtb_ima import frtb_ima_engine
        result = frtb_ima_engine.calculate_es()
        assert "es_97_5_1d_usd" in result
        assert "es_97_5_10d_usd" in result

    def test_es_greater_than_zero(self):
        from infrastructure.risk.frtb_ima import frtb_ima_engine
        result = frtb_ima_engine.calculate_es()
        assert result["es_97_5_1d_usd"] > 0

    def test_es_10d_equals_1d_times_sqrt10(self):
        from infrastructure.risk.frtb_ima import frtb_ima_engine
        import math
        result = frtb_ima_engine.calculate_es()
        expected_10d = result["es_97_5_1d_usd"] * math.sqrt(10)
        assert result["es_97_5_10d_usd"] == pytest.approx(expected_10d, rel=1e-3)

    def test_pla_test_returns_bool(self):
        from infrastructure.risk.frtb_ima import frtb_ima_engine
        result = frtb_ima_engine.run_pla_test("FIRM")
        assert "pla_pass" in result
        assert isinstance(result["pla_pass"], bool)

    def test_pla_spearman_in_valid_range(self):
        from infrastructure.risk.frtb_ima import frtb_ima_engine
        result = frtb_ima_engine.run_pla_test("FIRM")
        if result["spearman_corr"] is not None:
            assert -1.0 <= result["spearman_corr"] <= 1.0

    def test_desk_routing_covers_all_desks(self):
        from infrastructure.risk.frtb_ima import frtb_ima_engine, _DESKS
        routing = frtb_ima_engine.get_desk_routing()
        for desk in _DESKS:
            assert desk in routing["routing"], f"Missing desk: {desk}"

    def test_routing_values_are_ima_or_sa(self):
        from infrastructure.risk.frtb_ima import frtb_ima_engine
        routing = frtb_ima_engine.get_desk_routing()
        for desk, route in routing["routing"].items():
            assert route in ("IMA", "SA"), f"Invalid routing for {desk}: {route}"

    def test_portfolio_capital_structure(self):
        from infrastructure.risk.frtb_ima import frtb_ima_engine
        result = frtb_ima_engine.calculate_portfolio_capital()
        assert "total_frtb_capital_usd" in result
        assert result["total_frtb_capital_usd"] >= 0

    @pytest.mark.asyncio
    async def test_frtb_capital_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/capital/frtb/capital")
        assert r.status_code == 200
        assert "total_frtb_capital_usd" in r.json()

    @pytest.mark.asyncio
    async def test_frtb_pla_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/capital/frtb/pla/FIRM")
        assert r.status_code == 200
        assert "pla_pass" in r.json()

    @pytest.mark.asyncio
    async def test_frtb_routing_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/capital/frtb/routing")
        assert r.status_code == 200
        assert "routing" in r.json()

    @pytest.mark.asyncio
    async def test_frtb_es_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/capital/frtb/es")
        assert r.status_code == 200
        assert "es_97_5_1d_usd" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# T3-D: Historical Crisis Replay
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrisisReplay:
    def test_get_scenarios_returns_three(self):
        from infrastructure.stress.crisis_replay import crisis_replay_engine
        scenarios = crisis_replay_engine.get_scenarios()
        assert scenarios["count"] == 3

    def test_scenario_ids_correct(self):
        from infrastructure.stress.crisis_replay import crisis_replay_engine
        scenarios = crisis_replay_engine.get_scenarios()
        assert "GFC_2008" in scenarios["scenarios"]
        assert "COVID_2020" in scenarios["scenarios"]
        assert "UK_GILT_2022" in scenarios["scenarios"]

    def test_gfc_replay_returns_pnl(self):
        from infrastructure.stress.crisis_replay import crisis_replay_engine
        result = crisis_replay_engine.run_replay("GFC_2008")
        assert "summary" in result
        assert "total_pnl_impact_usd" in result["summary"]
        # GFC with long equity positions should produce a loss
        assert result["summary"]["total_pnl_impact_usd"] < 0

    def test_covid_replay_has_position_impacts(self):
        from infrastructure.stress.crisis_replay import crisis_replay_engine
        result = crisis_replay_engine.run_replay("COVID_2020")
        assert "position_impacts" in result
        assert isinstance(result["position_impacts"], list)
        assert len(result["position_impacts"]) > 0

    def test_replay_has_rwa_delta(self):
        from infrastructure.stress.crisis_replay import crisis_replay_engine
        result = crisis_replay_engine.run_replay("GFC_2008")
        assert "rwa_delta_usd" in result["summary"]
        assert result["summary"]["rwa_delta_usd"] >= 0

    def test_rwa_delta_formula(self):
        from infrastructure.stress.crisis_replay import crisis_replay_engine
        result = crisis_replay_engine.run_replay("GFC_2008")
        total_pnl = result["summary"]["total_pnl_impact_usd"]
        rwa_delta = result["summary"]["rwa_delta_usd"]
        assert rwa_delta == pytest.approx(abs(total_pnl) * 12.5, rel=1e-3)

    def test_by_desk_in_summary(self):
        from infrastructure.stress.crisis_replay import crisis_replay_engine
        result = crisis_replay_engine.run_replay("COVID_2020")
        by_desk = result["summary"]["by_desk"]
        assert isinstance(by_desk, dict)
        assert len(by_desk) > 0

    def test_limit_breaches_is_list(self):
        from infrastructure.stress.crisis_replay import crisis_replay_engine
        result = crisis_replay_engine.run_replay("GFC_2008")
        breaches = crisis_replay_engine.get_limit_breaches(result)
        assert isinstance(breaches, list)

    def test_run_all_scenarios(self):
        from infrastructure.stress.crisis_replay import crisis_replay_engine
        all_results = crisis_replay_engine.run_all_scenarios()
        assert "scenarios" in all_results
        assert "comparative" in all_results
        assert len(all_results["scenarios"]) == 3

    @pytest.mark.asyncio
    async def test_crisis_scenarios_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/stress/crisis/scenarios")
        assert r.status_code == 200
        assert r.json()["count"] == 3

    @pytest.mark.asyncio
    async def test_crisis_replay_gfc_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/stress/crisis/replay/GFC_2008")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "total_pnl_impact_usd" in data["summary"]

    @pytest.mark.asyncio
    async def test_crisis_replay_unknown_scenario(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/stress/crisis/replay/UNKNOWN_2099")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_crisis_replay_all_api(self):
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/stress/crisis/replay-all")
        assert r.status_code == 200
        data = r.json()
        assert "comparative" in data
        assert data["comparative"]["worst_scenario"] in ("GFC_2008", "COVID_2020", "UK_GILT_2022")
