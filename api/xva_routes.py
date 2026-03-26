"""FastAPI routes for XVA analytics."""
from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter

router = APIRouter(prefix="/xva", tags=["xva"])

# ---------------------------------------------------------------------------
# Optional pyxva import
# ---------------------------------------------------------------------------
try:
    from pyxva import RiskEngine, MarketData, ScenarioBump, BumpType
    _PYXVA_AVAILABLE = True
except ImportError:
    _PYXVA_AVAILABLE = False

# ---------------------------------------------------------------------------
# Sample config (mirrors demo.py pipeline_config)
# ---------------------------------------------------------------------------

def sample_config(n_paths: int = 2_000) -> dict:
    return {
        "simulation": {
            "n_paths": n_paths,
            "seed": 42,
            "antithetic": False,
            "time_grid": {"type": "standard"},
        },
        "market_data": {
            "curves": {
                "USD_OIS": {
                    "tenors": [0.5, 1, 2, 3, 5, 7, 10],
                    "rates":  [0.038, 0.040, 0.042, 0.044, 0.047, 0.050, 0.053],
                },
            },
            "spots": {"SPX": 100.0},
            "vols":  {"SPX": 0.22},
        },
        "models": [
            {
                "name": "rates_usd",
                "type": "HullWhite1F",
                "params": {"a": 0.15, "sigma": 0.01, "r0": 0.04},
                "calibrate_to": "USD_OIS",
            },
            {
                "name": "equity_spx",
                "type": "GBM",
                "params": {"S0": 100.0, "mu": 0.06, "sigma": 0.22},
            },
        ],
        "correlation": [
            ["rates_usd", "equity_spx", 0.10],
        ],
        "agreements": [
            {
                "id": "AGR_GOLDMAN",
                "counterparty": "Goldman_Sachs",
                "cp_hazard_rate": 0.010,
                "own_hazard_rate": 0.005,
                "funding_spread": 0.008,
                "cost_of_capital": 0.10,
                "csa": {"mta": 10_000, "threshold": 0, "margin_regime": "REGVM"},
                "netting_sets": [
                    {
                        "id": "NS_IR",
                        "trades": [
                            {
                                "id": "trade_payer_5y",
                                "type": "InterestRateSwap",
                                "model": "rates_usd",
                                "params": {
                                    "fixed_rate": 0.045,
                                    "maturity": 5.0,
                                    "notional": 1_000_000,
                                    "payer": True,
                                },
                            },
                            {
                                "id": "trade_recv_3y",
                                "type": "InterestRateSwap",
                                "model": "rates_usd",
                                "params": {
                                    "fixed_rate": 0.035,
                                    "maturity": 3.0,
                                    "notional": 500_000,
                                    "payer": False,
                                },
                            },
                        ],
                    },
                    {
                        "id": "NS_EQ",
                        "trades": [
                            {
                                "id": "trade_call_2y",
                                "type": "EuropeanOption",
                                "model": "equity_spx",
                                "params": {
                                    "strike": 105.0,
                                    "expiry": 2.0,
                                    "sigma": 0.22,
                                    "risk_free_rate": 0.04,
                                    "option_type": "call",
                                },
                            },
                        ],
                    },
                ],
            },
            {
                "id": "AGR_JPMORGAN",
                "counterparty": "JPMorgan_Chase",
                "cp_hazard_rate": 0.008,
                "own_hazard_rate": 0.005,
                "funding_spread": 0.007,
                "cost_of_capital": 0.10,
                "csa": {"mta": 25_000, "threshold": 50_000, "margin_regime": "REGVM"},
                "netting_sets": [
                    {
                        "id": "NS_IR_JPM",
                        "trades": [
                            {
                                "id": "trade_payer_3y",
                                "type": "InterestRateSwap",
                                "model": "rates_usd",
                                "params": {
                                    "fixed_rate": 0.043,
                                    "maturity": 3.0,
                                    "notional": 2_000_000,
                                    "payer": True,
                                },
                            },
                        ],
                    },
                ],
            },
            {
                "id": "AGR_DEUTSCHE",
                "counterparty": "Deutsche_Bank",
                "cp_hazard_rate": 0.018,
                "own_hazard_rate": 0.005,
                "funding_spread": 0.012,
                "cost_of_capital": 0.10,
                "csa": {"mta": 50_000, "threshold": 100_000, "margin_regime": "REGVM"},
                "netting_sets": [
                    {
                        "id": "NS_IR_DB",
                        "trades": [
                            {
                                "id": "trade_payer_7y",
                                "type": "InterestRateSwap",
                                "model": "rates_usd",
                                "params": {
                                    "fixed_rate": 0.048,
                                    "maturity": 7.0,
                                    "notional": 1_500_000,
                                    "payer": True,
                                },
                            },
                            {
                                "id": "trade_recv_5y_db",
                                "type": "InterestRateSwap",
                                "model": "rates_usd",
                                "params": {
                                    "fixed_rate": 0.039,
                                    "maturity": 5.0,
                                    "notional": 750_000,
                                    "payer": False,
                                },
                            },
                        ],
                    },
                ],
            },
            {
                "id": "AGR_BNP",
                "counterparty": "BNP_Paribas",
                "cp_hazard_rate": 0.012,
                "own_hazard_rate": 0.005,
                "funding_spread": 0.009,
                "cost_of_capital": 0.10,
                "csa": {"mta": 20_000, "threshold": 0, "margin_regime": "REGVM"},
                "netting_sets": [
                    {
                        "id": "NS_IR_BNP",
                        "trades": [
                            {
                                "id": "trade_payer_5y_bnp",
                                "type": "InterestRateSwap",
                                "model": "rates_usd",
                                "params": {
                                    "fixed_rate": 0.046,
                                    "maturity": 5.0,
                                    "notional": 800_000,
                                    "payer": True,
                                },
                            },
                        ],
                    },
                    {
                        "id": "NS_EQ_BNP",
                        "trades": [
                            {
                                "id": "trade_put_1y",
                                "type": "EuropeanOption",
                                "model": "equity_spx",
                                "params": {
                                    "strike": 95.0,
                                    "expiry": 1.0,
                                    "sigma": 0.22,
                                    "risk_free_rate": 0.04,
                                    "option_type": "put",
                                },
                            },
                        ],
                    },
                ],
            },
            {
                "id": "AGR_HSBC",
                "counterparty": "HSBC",
                "cp_hazard_rate": 0.007,
                "own_hazard_rate": 0.005,
                "funding_spread": 0.006,
                "cost_of_capital": 0.10,
                "csa": {"mta": 15_000, "threshold": 0, "margin_regime": "REGVM"},
                "netting_sets": [
                    {
                        "id": "NS_IR_HSBC",
                        "trades": [
                            {
                                "id": "trade_recv_10y",
                                "type": "InterestRateSwap",
                                "model": "rates_usd",
                                "params": {
                                    "fixed_rate": 0.050,
                                    "maturity": 10.0,
                                    "notional": 1_200_000,
                                    "payer": False,
                                },
                            },
                            {
                                "id": "trade_payer_2y_hsbc",
                                "type": "InterestRateSwap",
                                "model": "rates_usd",
                                "params": {
                                    "fixed_rate": 0.041,
                                    "maturity": 2.0,
                                    "notional": 600_000,
                                    "payer": True,
                                },
                            },
                        ],
                    },
                ],
            },
        ],
        "outputs": {
            "metrics": ["EE", "PFE", "CVA"],
            "confidence": 0.975,
            "write_raw_paths": False,
        },
    }


# ---------------------------------------------------------------------------
# Mock / fallback data
# ---------------------------------------------------------------------------

# Per-counterparty mock exposure shapes (IRS hump shape, scaled)
_MOCK_COUNTERPARTIES = {
    "Goldman_Sachs":  {"scale": 1.00, "cva": -0.42, "dva": 0.08,  "bcva": -0.34, "fva": -0.15, "mva": -0.06, "kva": -0.03, "eepe": 1.12, "ead": 8.4,  "limit": 15.0},
    "JPMorgan_Chase": {"scale": 1.40, "cva": -0.38, "dva": 0.07,  "bcva": -0.31, "fva": -0.11, "mva": -0.04, "kva": -0.02, "eepe": 1.52, "ead": 11.2, "limit": 20.0},
    "Deutsche_Bank":  {"scale": 0.85, "cva": -0.71, "dva": 0.06,  "bcva": -0.65, "fva": -0.22, "mva": -0.08, "kva": -0.04, "eepe": 0.88, "ead": 7.1,  "limit": 10.0},
    "BNP_Paribas":    {"scale": 0.60, "cva": -0.28, "dva": 0.05,  "bcva": -0.23, "fva": -0.09, "mva": -0.03, "kva": -0.01, "eepe": 0.67, "ead": 5.3,  "limit": 12.0},
    "HSBC":           {"scale": 0.75, "cva": -0.19, "dva": 0.04,  "bcva": -0.15, "fva": -0.07, "mva": -0.02, "kva": -0.01, "eepe": 0.82, "ead": 6.0,  "limit": 18.0},
}

_AGR_TO_CP = {
    "AGR_GOLDMAN":  "Goldman_Sachs",
    "AGR_JPMORGAN": "JPMorgan_Chase",
    "AGR_DEUTSCHE": "Deutsche_Bank",
    "AGR_BNP":      "BNP_Paribas",
    "AGR_HSBC":     "HSBC",
}

# Base mock time grid and exposure shapes (all values in MM USD)
_BASE_TIME_GRID = [0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0]
_BASE_EE        = [0.0, 0.80, 1.40, 2.10, 2.80, 2.20, 0.00]
_BASE_PFE       = [0.0, 2.10, 3.60, 5.40, 7.20, 5.60, 0.00]
_BASE_EE_MPOR   = [0.0, 1.05, 1.82, 2.73, 3.64, 2.86, 0.00]


def _scale(base: list[float], s: float) -> list[float]:
    return [round(v * s, 4) for v in base]


def _mock_agreement_result(agr_id: str) -> dict:
    cp = _AGR_TO_CP.get(agr_id, "Goldman_Sachs")
    p  = _MOCK_COUNTERPARTIES[cp]
    s  = p["scale"]
    total_xva = p["cva"] - p["dva"] + p["fva"] + p["mva"] + p["kva"]
    return {
        "id": agr_id,
        "counterparty_id": cp,
        "time_grid":       _BASE_TIME_GRID,
        "ee_profile":      _scale(_BASE_EE,      s),
        "pfe_profile":     _scale(_BASE_PFE,     s),
        "ee_mpor_profile": _scale(_BASE_EE_MPOR, s),
        "cva":   p["cva"],
        "dva":   p["dva"],
        "bcva":  p["bcva"],
        "fva":   p["fva"],
        "mva":   p["mva"],
        "kva":   p["kva"],
        "eepe":  p["eepe"],
        "total_xva": round(total_xva, 4),
    }


def _mock_run_result() -> dict:
    agreements = {}
    for agr_id in _AGR_TO_CP:
        agreements[agr_id] = _mock_agreement_result(agr_id)

    total_cva = sum(a["cva"] for a in agreements.values())
    total_dva = sum(a["dva"] for a in agreements.values())
    total_fva = sum(a["fva"] for a in agreements.values())
    total_mva = sum(a["mva"] for a in agreements.values())
    total_kva = sum(a["kva"] for a in agreements.values())
    peak_pfe  = max(max(a["pfe_profile"]) for a in agreements.values())
    avg_eepe  = sum(a["eepe"] for a in agreements.values())

    return {
        "source": "mock",
        "time_grid": _BASE_TIME_GRID,
        "total_cva":  round(total_cva, 4),
        "total_dva":  round(total_dva, 4),
        "total_fva":  round(total_fva, 4),
        "total_mva":  round(total_mva, 4),
        "total_kva":  round(total_kva, 4),
        "peak_pfe":   round(peak_pfe, 4),
        "total_eepe": round(avg_eepe, 4),
        "agreements": agreements,
    }


# ---------------------------------------------------------------------------
# Helper: serialise a real RunResult
# ---------------------------------------------------------------------------

def _serialise_run_result(run_result) -> dict:
    """Convert pyxva RunResult to JSON-serialisable dict."""
    import numpy as np

    def _to_list(x):
        if hasattr(x, "tolist"):
            return [0.0 if (math.isnan(v) or math.isinf(v)) else round(v, 6) for v in x.tolist()]
        return x

    agreements = {}
    for agr_id, agr in run_result.agreement_results.items():
        total_xva = agr.cva - agr.dva + agr.fva + agr.mva + agr.kva
        agreements[agr_id] = {
            "id": agr.id,
            "counterparty_id": agr.counterparty_id,
            "time_grid":       _to_list(agr.time_grid),
            "ee_profile":      _to_list(agr.ee_profile / 1e6),     # convert to MM USD
            "pfe_profile":     _to_list(agr.pfe_profile / 1e6),
            "ee_mpor_profile": _to_list(agr.ee_mpor_profile / 1e6),
            "cva":   round(agr.cva / 1e6, 4),
            "dva":   round(agr.dva / 1e6, 4),
            "bcva":  round(agr.bcva / 1e6, 4),
            "fva":   round(agr.fva / 1e6, 4),
            "mva":   round(agr.mva / 1e6, 4),
            "kva":   round(agr.kva / 1e6, 4),
            "eepe":  round(agr.eepe / 1e6, 4),
            "total_xva": round(total_xva / 1e6, 4),
        }

    time_grid = _to_list(run_result.time_grid)
    all_pfe = [v for agr in agreements.values() for v in agr["pfe_profile"]]
    peak_pfe = max(all_pfe) if all_pfe else 0.0

    return {
        "source": "pyxva",
        "time_grid":  time_grid,
        "total_cva":  round(run_result.total_cva / 1e6, 4),
        "total_dva":  round(run_result.total_dva / 1e6, 4),
        "total_fva":  round(run_result.total_fva / 1e6, 4),
        "total_mva":  round(run_result.total_mva / 1e6, 4),
        "total_kva":  round(run_result.total_kva / 1e6, 4),
        "peak_pfe":   round(peak_pfe, 4),
        "total_eepe": round(sum(a["eepe"] for a in agreements.values()), 4),
        "agreements": agreements,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
def health():
    """Health check — confirms service is up and reports pyxva availability."""
    return {"status": "ok", "pyxva_available": _PYXVA_AVAILABLE}


@router.post("/run")
def run_xva(body: dict = None):
    """
    Run XVA calculation.

    Body (optional JSON):
        {
            "config": { ...EngineConfig dict... }
        }

    Returns serialised RunResult with exposure profiles and XVA scalars.
    Uses pyxva RiskEngine if available, otherwise returns realistic mock data.
    """
    body = body or {}
    config_dict = body.get("config") or sample_config()

    if _PYXVA_AVAILABLE:
        try:
            engine = RiskEngine(config_dict)
            run_result = engine.run()
            return _serialise_run_result(run_result)
        except Exception as exc:
            return {**_mock_run_result(), "source": "mock_fallback", "error": str(exc)}

    return _mock_run_result()


@router.get("/demo")
def demo_xva():
    """
    Instant demo run with sample portfolio (5 counterparties).
    Uses pyxva if available, else returns pre-computed mock data.
    """
    if _PYXVA_AVAILABLE:
        try:
            engine = RiskEngine(sample_config(n_paths=2_000))
            run_result = engine.run()
            return _serialise_run_result(run_result)
        except Exception as exc:
            return {**_mock_run_result(), "source": "mock_fallback", "error": str(exc)}

    return _mock_run_result()


# ---------------------------------------------------------------------------
# Stress scenario multipliers (mock)
# ---------------------------------------------------------------------------

_STRESS_MULTIPLIERS = {
    "gfc":               {"cva": 3.2,  "pfe": 2.8,  "ee": 2.4},
    "covid":             {"cva": 2.1,  "pfe": 1.9,  "ee": 1.7},
    "rate_shock_200bp":  {"cva": 1.8,  "pfe": 1.6,  "ee": 1.5},
    "credit_widening":   {"cva": 2.5,  "pfe": 1.4,  "ee": 1.3},
}

_STRESS_BUMPS = {
    "gfc":              [("USD_OIS", -0.020, "PARALLEL")],
    "covid":            [("USD_OIS", -0.015, "PARALLEL")],
    "rate_shock_200bp": [("USD_OIS",  0.020, "PARALLEL")],
    "credit_widening":  [("USD_OIS",  0.005, "PARALLEL")],
}


@router.post("/stress")
def stress_xva(body: dict = None):
    """
    Run stress scenario.

    Body:
        {
            "scenario": "gfc" | "covid" | "rate_shock_200bp" | "credit_widening",
            "config": { ...optional EngineConfig dict... }
        }

    Returns baseline and stressed results side by side.
    """
    body = body or {}
    scenario = (body.get("scenario") or "gfc").lower()
    config_dict = body.get("config") or sample_config()

    if scenario not in _STRESS_MULTIPLIERS:
        return {"error": f"Unknown scenario '{scenario}'. Valid: {list(_STRESS_MULTIPLIERS)}"}

    mult = _STRESS_MULTIPLIERS[scenario]

    if _PYXVA_AVAILABLE:
        try:
            engine = RiskEngine(config_dict)
            base_result = engine.run()
            base_md = MarketData.from_dict(config_dict.get("market_data", {}))

            bumps_raw = _STRESS_BUMPS.get(scenario, [])
            bumps = []
            for curve, size, bump_type in bumps_raw:
                bumps.append(ScenarioBump(curve, size, BumpType[bump_type]))

            stressed_result = base_result.stress_test(bumps, base_md)
            return {
                "scenario": scenario,
                "baseline": _serialise_run_result(base_result),
                "stressed": _serialise_run_result(stressed_result),
            }
        except Exception as exc:
            pass  # fall through to mock

    # Mock stress: scale mock results
    baseline = _mock_run_result()
    stressed = _mock_run_result()

    def _apply_stress(data: dict, mult: dict) -> dict:
        stressed = dict(data)
        stressed["total_cva"]  = round(data["total_cva"]  * mult["cva"], 4)
        stressed["total_fva"]  = round(data["total_fva"]  * mult["cva"], 4)
        stressed["peak_pfe"]   = round(data["peak_pfe"]   * mult["pfe"], 4)

        new_agreements = {}
        for agr_id, agr in data["agreements"].items():
            new_agr = dict(agr)
            new_agr["cva"]         = round(agr["cva"]  * mult["cva"], 4)
            new_agr["fva"]         = round(agr["fva"]  * mult["cva"], 4)
            new_agr["pfe_profile"] = [round(v * mult["pfe"], 4) for v in agr["pfe_profile"]]
            new_agr["ee_profile"]  = [round(v * mult["ee"],  4) for v in agr["ee_profile"]]
            new_agr["ee_mpor_profile"] = [round(v * mult["ee"], 4) for v in agr["ee_mpor_profile"]]
            new_agr["total_xva"]   = round(
                new_agr["cva"] - new_agr["dva"] + new_agr["fva"] + new_agr["mva"] + new_agr["kva"], 4
            )
            new_agreements[agr_id] = new_agr
        stressed["agreements"] = new_agreements
        stressed["source"] = "mock_stress"
        return stressed

    return {
        "scenario": scenario,
        "baseline": baseline,
        "stressed": _apply_stress(baseline, mult),
    }


@router.get("/counterparties")
def counterparties():
    """
    Returns current XVA metrics for all counterparties.
    """
    result = []
    for cp_name, p in _MOCK_COUNTERPARTIES.items():
        utilization = round(p["ead"] / p["limit"] * 100, 1)
        total_xva = p["cva"] - p["dva"] + p["fva"] + p["mva"] + p["kva"]
        result.append({
            "name":        cp_name.replace("_", " "),
            "id":          cp_name,
            "cva":         p["cva"],
            "dva":         p["dva"],
            "bcva":        p["bcva"],
            "fva":         p["fva"],
            "mva":         p["mva"],
            "kva":         p["kva"],
            "total_xva":   round(total_xva, 4),
            "eepe":        p["eepe"],
            "pfe_975":     round(max(_scale(_BASE_PFE, p["scale"])), 4),
            "ead":         p["ead"],
            "limit":       p["limit"],
            "utilization": utilization,
        })

    return {"counterparties": result}
