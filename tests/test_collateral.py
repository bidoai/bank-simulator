"""
Tests for the collateral module:
  - CSA / CollateralAccount / MarginCall data model
  - VMEngine: VM calculation, behaviour flags, settle, close-out
  - SIMMEngine: IR and CRQ IM computation
  - Stress scenarios: covid_week, lehman_event, gilt_crisis
  - API routes: /api/collateral/*
"""
from __future__ import annotations

import math
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ── Data model ──────────────────────────────────────────────────────────────

class TestCSADataModel:
    def test_csa_default_haircut(self):
        from infrastructure.collateral.csa import CSA, CollateralAssetType
        csa = CSA(
            csa_id="TEST-001", counterparty_id="CP_X", counterparty_name="Test",
            our_legal_entity="Apex", governing_law="New York",
        )
        assert csa.get_haircut(CollateralAssetType.UST) == pytest.approx(0.02)
        assert csa.get_haircut(CollateralAssetType.USD_CASH) == pytest.approx(0.0)
        assert csa.get_haircut("UNKNOWN") == pytest.approx(0.15)

    def test_csa_custom_haircut_overrides_standard(self):
        from infrastructure.collateral.csa import CSA, CollateralAssetType
        csa = CSA(
            csa_id="TEST-002", counterparty_id="CP_X", counterparty_name="Test",
            our_legal_entity="Apex", governing_law="English",
            haircuts={CollateralAssetType.UST: 0.05},
        )
        assert csa.get_haircut(CollateralAssetType.UST) == pytest.approx(0.05)

    def test_collateral_account_net(self):
        from infrastructure.collateral.csa import CollateralAccount
        acct = CollateralAccount(
            account_id="A1", csa_id="C1", counterparty_id="CP1",
            vm_posted_usd=50e6, vm_received_usd=80e6,
            im_posted_usd=100e6, im_received_usd=90e6,
        )
        # net = (80+90) - (50+100) = 20M
        assert acct.net_collateral_usd == pytest.approx(20e6)

    def test_margin_call_undisputed_amount(self):
        from infrastructure.collateral.csa import MarginCall
        call = MarginCall(amount_usd=10_000_000, disputed_amount=1_500_000)
        assert call.undisputed_amount == pytest.approx(8_500_000)

    def test_margin_call_to_dict_keys(self):
        from infrastructure.collateral.csa import MarginCall
        d = MarginCall().to_dict()
        for key in ("call_id", "csa_id", "direction", "amount_usd", "status"):
            assert key in d


# ── VMEngine ────────────────────────────────────────────────────────────────

class TestVMEngine:
    def _fresh_engine(self):
        """Return a VMEngine with default seeded CSAs."""
        from infrastructure.collateral.vm_engine import VMEngine
        return VMEngine()

    def test_no_call_below_mta(self):
        engine = self._fresh_engine()
        # Zero out the account so required ≈ current balance
        engine._accounts["CSA-GS-001"].vm_posted_usd = 0.0
        engine._accounts["CSA-GS-001"].vm_received_usd = 0.0
        # MTM = 100K — below $500K MTA → no call
        call = engine.calculate_vm_call("CSA-GS-001", current_mtm=100_000)
        assert call is None

    def test_generates_outbound_call(self):
        engine = self._fresh_engine()
        # Force a large MTM move against us
        engine._prev_mtm["CSA-GS-001"] = 0.0
        engine._accounts["CSA-GS-001"].vm_posted_usd = 0.0
        engine._accounts["CSA-GS-001"].vm_received_usd = 0.0
        # MTM = -50M (we owe them 50M, above MTA)
        call = engine.calculate_vm_call("CSA-GS-001", current_mtm=-50_000_000)
        assert call is not None
        assert call.direction == "OUTBOUND"
        assert call.amount_usd == pytest.approx(50_000_000)

    def test_generates_inbound_call(self):
        engine = self._fresh_engine()
        engine._prev_mtm["CSA-JPM-001"] = 0.0
        engine._accounts["CSA-JPM-001"].vm_posted_usd = 0.0
        engine._accounts["CSA-JPM-001"].vm_received_usd = 0.0
        # MTM = +40M (they owe us 40M, above MTA)
        call = engine.calculate_vm_call("CSA-JPM-001", current_mtm=40_000_000)
        assert call is not None
        assert call.direction == "INBOUND"
        assert call.amount_usd == pytest.approx(40_000_000)

    def test_threshold_csa_no_call_below_threshold(self):
        engine = self._fresh_engine()
        # CSA-MER-001 has $10M threshold
        engine._prev_mtm["CSA-MER-001"] = 0.0
        engine._accounts["CSA-MER-001"].vm_received_usd = 0.0
        # MTM = 8M — below $10M threshold, no call
        call = engine.calculate_vm_call("CSA-MER-001", current_mtm=8_000_000)
        assert call is None

    def test_threshold_csa_call_above_threshold(self):
        engine = self._fresh_engine()
        engine._prev_mtm["CSA-MER-001"] = 0.0
        engine._accounts["CSA-MER-001"].vm_received_usd = 0.0
        # MTM = 15M — $5M above $10M threshold → inbound call for $5M
        call = engine.calculate_vm_call("CSA-MER-001", current_mtm=15_000_000)
        assert call is not None
        assert call.direction == "INBOUND"
        assert call.amount_usd == pytest.approx(5_000_000)

    def test_apply_dispute_behaviour(self):
        engine = self._fresh_engine()
        engine._prev_mtm["CSA-JPM-001"] = 0.0
        engine._accounts["CSA-JPM-001"].vm_posted_usd = 0.0
        engine._accounts["CSA-JPM-001"].vm_received_usd = 0.0
        call = engine.calculate_vm_call("CSA-JPM-001", current_mtm=20_000_000)
        assert call is not None
        updated = engine.apply_behaviour(call, engine.COUNTERPARTY_BEHAVIOUR_DISPUTE)
        assert updated.status == "DISPUTED"
        assert updated.disputed_amount == pytest.approx(call.amount_usd * 0.15, rel=0.01)

    def test_apply_late_behaviour(self):
        engine = self._fresh_engine()
        engine._prev_mtm["CSA-GS-001"] = 0.0
        engine._accounts["CSA-GS-001"].vm_received_usd = 0.0
        call = engine.calculate_vm_call("CSA-GS-001", current_mtm=30_000_000)
        assert call is not None
        updated = engine.apply_behaviour(call, engine.COUNTERPARTY_BEHAVIOUR_LATE)
        assert updated.status == "LATE"

    def test_apply_default_behaviour(self):
        engine = self._fresh_engine()
        engine._prev_mtm["CSA-MER-001"] = 0.0
        engine._accounts["CSA-MER-001"].vm_received_usd = 0.0
        call = engine.calculate_vm_call("CSA-MER-001", current_mtm=25_000_000)
        assert call is not None
        updated = engine.apply_behaviour(call, engine.COUNTERPARTY_BEHAVIOUR_DEFAULT)
        assert updated.status == "DEFAULTED"
        assert updated.is_close_out is True

    def test_settle_call_updates_account(self):
        engine = self._fresh_engine()
        engine._prev_mtm["CSA-GS-001"] = 0.0
        engine._accounts["CSA-GS-001"].vm_posted_usd = 0.0
        call = engine.calculate_vm_call("CSA-GS-001", current_mtm=-20_000_000)
        assert call is not None
        settled = engine.settle_call(call.call_id, delivered_amount=20_000_000)
        assert settled is True
        assert engine._accounts["CSA-GS-001"].vm_posted_usd == pytest.approx(20_000_000)

    def test_close_out_netting(self):
        engine = self._fresh_engine()
        mtm = {"CSA-MER-001": 18_000_000}
        result = engine.compute_close_out("CP004", mtm)
        assert result["counterparty_id"] == "CP004"
        assert result["total_net_mtm_usd"] == pytest.approx(18_000_000)
        # With 2% slippage and 0 IM held, close-out loss > 0
        assert result["total_close_out_loss_usd"] > 0

    def test_close_out_unknown_counterparty(self):
        engine = self._fresh_engine()
        result = engine.compute_close_out("UNKNOWN_CP", {})
        assert "error" in result

    def test_portfolio_summary_structure(self):
        engine = self._fresh_engine()
        summary = engine.get_portfolio_summary()
        for key in ("csa_count", "total_vm_posted_usd", "total_vm_received_usd",
                    "total_im_posted_usd", "net_im_usd", "open_call_count"):
            assert key in summary

    def test_run_daily_margining_returns_list(self):
        engine = self._fresh_engine()
        # Zero out all balances and prev MTM so we can control the output
        for acct in engine._accounts.values():
            acct.vm_posted_usd = 0.0
            acct.vm_received_usd = 0.0
        for k in engine._prev_mtm:
            engine._prev_mtm[k] = 0.0

        mtm = {
            "CSA-GS-001":  -50_000_000,
            "CSA-JPM-001":  30_000_000,
        }
        calls = engine.run_daily_margining(mtm)
        assert isinstance(calls, list)
        assert len(calls) == 2


# ── SIMMEngine ──────────────────────────────────────────────────────────────

class TestSIMMEngine:
    def test_zero_sensitivities(self):
        from infrastructure.collateral.simm import SIMMEngine, SIMMInput
        result = SIMMEngine().compute(SIMMInput())
        assert result.total_im_usd == 0.0

    def test_single_ir_tenor(self):
        from infrastructure.collateral.simm import SIMMEngine, SIMMInput, IRDelta
        inputs = SIMMInput(ir_deltas=[IRDelta("10y", dv01_usd=1_000_000)])
        result = SIMMEngine().compute(inputs)
        # IR IM = DV01 × RW = 1,000,000 × 44bps = $44,000
        expected_ir_im = 1_000_000 * (44.0 / 10_000)
        assert result.ir_im_usd == pytest.approx(expected_ir_im, rel=0.01)
        assert result.crq_im_usd == 0.0

    def test_offsetting_ir_deltas_reduces_im(self):
        from infrastructure.collateral.simm import SIMMEngine, SIMMInput, IRDelta
        # Long and short same tenor — should net to near zero
        inputs = SIMMInput(ir_deltas=[
            IRDelta("10y", dv01_usd= 1_000_000),
            IRDelta("10y", dv01_usd=-1_000_000),
        ])
        result = SIMMEngine().compute(inputs)
        # Weighted sensitivities cancel — IM should be ~0
        assert result.ir_im_usd == pytest.approx(0.0, abs=1.0)

    def test_diversified_ir_portfolio_lower_than_sum(self):
        from infrastructure.collateral.simm import SIMMEngine, SIMMInput, IRDelta
        long_only = SIMMInput(ir_deltas=[
            IRDelta("2y", dv01_usd=1_000_000),
            IRDelta("10y", dv01_usd=1_000_000),
        ])
        individual_2y  = SIMMEngine().compute(SIMMInput(ir_deltas=[IRDelta("2y",  dv01_usd=1_000_000)]))
        individual_10y = SIMMEngine().compute(SIMMInput(ir_deltas=[IRDelta("10y", dv01_usd=1_000_000)]))
        combined = SIMMEngine().compute(long_only)
        # Combined IM < sum of individual IMs (correlation < 1.0)
        assert combined.total_im_usd <= individual_2y.total_im_usd + individual_10y.total_im_usd

    def test_single_crq_position(self):
        from infrastructure.collateral.simm import SIMMEngine, SIMMInput, CRQDelta
        inputs = SIMMInput(crq_deltas=[CRQDelta("TEST", cs01_usd=100_000, rating="BBB")])
        result = SIMMEngine().compute(inputs)
        expected = 100_000 * (54.0 / 10_000)
        assert result.crq_im_usd == pytest.approx(expected, rel=0.01)

    def test_sample_portfolio_positive_im(self):
        from infrastructure.collateral.simm import simm_engine
        result = simm_engine.compute_sample_portfolio()
        assert result.ir_im_usd > 0
        assert result.total_im_usd > 0

    def test_total_im_at_least_max_component(self):
        from infrastructure.collateral.simm import simm_engine
        result = simm_engine.compute_sample_portfolio()
        # Total IM ≥ max(IR_IM, CRQ_IM)
        assert result.total_im_usd >= max(result.ir_im_usd, result.crq_im_usd)

    def test_to_dict_keys(self):
        from infrastructure.collateral.simm import simm_engine
        d = simm_engine.compute_sample_portfolio().to_dict()
        for key in ("ir_im_usd", "crq_im_usd", "total_im_usd", "detail"):
            assert key in d


# ── Stress scenarios ─────────────────────────────────────────────────────────

class TestStressScenarios:
    def _scenarios(self):
        from infrastructure.collateral.vm_engine import VMEngine
        from infrastructure.collateral.stress_scenarios import CollateralStressScenarios
        engine = VMEngine()
        return CollateralStressScenarios(engine=engine)

    def test_covid_week_produces_result(self):
        result = self._scenarios().run_covid_week()
        assert result.scenario_name == "COVID Week — Systemic Margin Call"
        assert result.total_outbound_calls_usd >= 0
        assert len(result.agent_decision_points) >= 3
        assert len(result.risk_flags) >= 1

    def test_covid_week_has_ceo_decision(self):
        result = self._scenarios().run_covid_week()
        agents = [dp.agent for dp in result.agent_decision_points]
        assert "CEO" in agents

    def test_lehman_event_produces_default(self):
        result = self._scenarios().run_lehman_event()
        assert "CP004" in result.defaulted_counterparties
        assert result.close_out_losses_usd >= 0

    def test_lehman_event_has_gc_decision(self):
        result = self._scenarios().run_lehman_event()
        agents = [dp.agent for dp in result.agent_decision_points]
        assert "GC" in agents

    def test_gilt_crisis_quality_adjustment(self):
        result = self._scenarios().run_gilt_crisis(bond_price_shock_pct=-0.12)
        assert result.collateral_quality_adjustment_usd >= 0
        assert result.scenario_name == "Gilt Crisis — Collateral Quality Shock"

    def test_gilt_crisis_larger_shock_larger_adjustment(self):
        s = self._scenarios()
        r1 = s.run_gilt_crisis(bond_price_shock_pct=-0.05)
        r2 = s.run_gilt_crisis(bond_price_shock_pct=-0.15)
        assert r2.collateral_quality_adjustment_usd >= r1.collateral_quality_adjustment_usd

    def test_scenario_result_to_dict(self):
        result = self._scenarios().run_covid_week()
        d = result.to_dict()
        for key in ("scenario_name", "total_outbound_calls_usd", "risk_flags",
                    "agent_decision_points", "call_detail"):
            assert key in d


# ── API routes ───────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


class TestCollateralRoutes:
    def test_summary_200(self, client):
        r = client.get("/api/collateral/summary")
        assert r.status_code == 200
        data = r.json()
        assert "csa_count" in data
        assert data["csa_count"] > 0

    def test_accounts_200(self, client):
        r = client.get("/api/collateral/accounts")
        assert r.status_code == 200
        assert "accounts" in r.json()

    def test_csas_200(self, client):
        r = client.get("/api/collateral/csas")
        assert r.status_code == 200
        data = r.json()
        assert "csas" in data
        assert len(data["csas"]) >= 5

    def test_calls_200(self, client):
        r = client.get("/api/collateral/calls")
        assert r.status_code == 200
        assert "calls" in r.json()

    def test_simm_sample_200(self, client):
        r = client.get("/api/collateral/simm/sample")
        assert r.status_code == 200
        data = r.json()
        assert "total_im_usd" in data
        assert data["total_im_usd"] > 0

    def test_simm_compute_200(self, client):
        r = client.post("/api/collateral/simm/compute", json={
            "ir_deltas": [{"tenor": "10y", "dv01_usd": 500000}],
            "crq_deltas": [],
        })
        assert r.status_code == 200
        assert r.json()["ir_im_usd"] > 0

    def test_close_out_known_counterparty(self, client):
        r = client.get("/api/collateral/close-out/CP004")
        assert r.status_code == 200
        data = r.json()
        assert data["counterparty_id"] == "CP004"

    def test_close_out_unknown_counterparty_404(self, client):
        r = client.get("/api/collateral/close-out/NOBODY")
        assert r.status_code == 404

    def test_scenario_covid_week(self, client):
        r = client.post("/api/collateral/scenario", json={"scenario": "covid_week"})
        assert r.status_code == 200
        data = r.json()
        assert "COVID" in data["scenario_name"]

    def test_scenario_lehman_event(self, client):
        r = client.post("/api/collateral/scenario", json={
            "scenario": "lehman_event",
            "params": {"counterparty_id": "CP004"},
        })
        assert r.status_code == 200
        assert "CP004" in r.json()["defaulted_counterparties"]

    def test_scenario_gilt_crisis(self, client):
        r = client.post("/api/collateral/scenario", json={
            "scenario": "gilt_crisis",
            "params": {"bond_price_shock_pct": -0.10},
        })
        assert r.status_code == 200
        assert "Gilt" in r.json()["scenario_name"]

    def test_scenario_invalid_name_400(self, client):
        r = client.post("/api/collateral/scenario", json={"scenario": "moon_landing"})
        assert r.status_code == 400
