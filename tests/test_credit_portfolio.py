"""Tests for the single-factor Gaussian copula credit portfolio model."""
from __future__ import annotations

import pytest
from infrastructure.credit.portfolio_model import CreditPortfolioModel, CreditVar
from infrastructure.credit.ifrs9_ecl import IFRS9ECLEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_obligors(n: int = 20, seed: int = 0) -> list:
    """Generate a small sample portfolio using the IFRS9 generator."""
    engine = IFRS9ECLEngine()
    portfolio = engine.generate_sample_portfolio(seed=seed)
    return portfolio[:n]


# ---------------------------------------------------------------------------
# CreditVar structure
# ---------------------------------------------------------------------------

def test_simulate_returns_credit_var():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(20)
    result = model.simulate(obs)
    assert isinstance(result, CreditVar)


def test_credit_var_fields():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(20)
    cv = model.simulate(obs)
    d = cv.to_dict()
    for key in ("expected_loss_usd", "var_99_usd", "var_999_usd",
                "es_99_usd", "es_999_usd", "credit_var_usd", "ec_usd",
                "total_notional_usd", "ec_ratio", "n_scenarios", "as_of"):
        assert key in d, f"missing key: {key}"


def test_var_ordering():
    """VaR 99.9% >= VaR 99% >= EL."""
    model = CreditPortfolioModel(n_scenarios=2_000, seed=42)
    obs = make_obligors(20)
    cv = model.simulate(obs)
    assert cv.var_999_usd >= cv.var_99_usd >= cv.expected_loss_usd


def test_es_ordering():
    """ES >= VaR at the same confidence level."""
    model = CreditPortfolioModel(n_scenarios=2_000, seed=42)
    obs = make_obligors(20)
    cv = model.simulate(obs)
    assert cv.es_99_usd >= cv.var_99_usd
    assert cv.es_999_usd >= cv.var_999_usd


def test_ec_is_var999_minus_el():
    model = CreditPortfolioModel(n_scenarios=2_000, seed=42)
    obs = make_obligors(20)
    cv = model.simulate(obs)
    assert cv.ec_usd == pytest.approx(max(0.0, cv.var_999_usd - cv.expected_loss_usd), abs=1.0)


def test_credit_var_is_var99_minus_el():
    model = CreditPortfolioModel(n_scenarios=2_000, seed=42)
    obs = make_obligors(20)
    cv = model.simulate(obs)
    assert cv.credit_var_usd == pytest.approx(max(0.0, cv.var_99_usd - cv.expected_loss_usd), abs=1.0)


def test_ec_ratio_bounded():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(20)
    cv = model.simulate(obs)
    assert 0.0 <= cv.ec_ratio <= 1.0


def test_total_notional_positive():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(20)
    cv = model.simulate(obs)
    assert cv.total_notional_usd > 0


# ---------------------------------------------------------------------------
# Stressed VaR > baseline
# ---------------------------------------------------------------------------

def test_stressed_var_exceeds_baseline():
    model = CreditPortfolioModel(n_scenarios=2_000, seed=42)
    obs = make_obligors(20)
    base = model.simulate(obs)

    # Double all PDs
    import dataclasses
    stressed = [dataclasses.replace(o, pd_1yr=min(o.pd_1yr * 2, 0.9999)) for o in obs]
    stressed_result = model.simulate(stressed)

    assert stressed_result.var_99_usd >= base.var_99_usd
    assert stressed_result.expected_loss_usd >= base.expected_loss_usd


# ---------------------------------------------------------------------------
# Marginal contributions
# ---------------------------------------------------------------------------

def test_marginal_contributions_length():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(10)
    mrc = model.marginal_contributions(obs)
    assert len(mrc) == 10


def test_marginal_contribution_fields():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(5)
    mrc = model.marginal_contributions(obs)
    for entry in mrc:
        for key in ("obligor_id", "rating", "ead_usd", "pd_1yr", "mrc_usd", "mrc_pct"):
            assert key in entry, f"missing key: {key}"


def test_marginal_contributions_sorted_descending():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(10)
    mrc = model.marginal_contributions(obs)
    mrcs = [e["mrc_usd"] for e in mrc]
    assert mrcs == sorted(mrcs, reverse=True)


def test_marginal_contribution_non_negative():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(10)
    mrc = model.marginal_contributions(obs)
    for entry in mrc:
        assert entry["mrc_usd"] >= 0


# ---------------------------------------------------------------------------
# Loss distribution
# ---------------------------------------------------------------------------

def test_loss_distribution_structure():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(10)
    dist = model.loss_distribution(obs, n_buckets=20)
    assert "bucket_centres_usd" in dist
    assert "frequencies" in dist
    assert len(dist["bucket_centres_usd"]) == 20
    assert len(dist["frequencies"]) == 20
    assert sum(dist["frequencies"]) == 1_000


def test_loss_distribution_frequencies_non_negative():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    obs = make_obligors(10)
    dist = model.loss_distribution(obs)
    assert all(f >= 0 for f in dist["frequencies"])


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_portfolio():
    model = CreditPortfolioModel(n_scenarios=1_000, seed=42)
    cv = model.simulate([])
    assert cv.expected_loss_usd == 0
    assert cv.ec_usd == 0


def test_full_portfolio():
    """Full 50-obligor portfolio runs without error."""
    model = CreditPortfolioModel(n_scenarios=5_000, seed=42)
    engine = IFRS9ECLEngine()
    portfolio = engine.generate_sample_portfolio()
    cv = model.simulate(portfolio)
    assert cv.var_999_usd > 0
    # EC ratio should be sub-10% for a typical IG-heavy book
    assert cv.ec_ratio < 0.15
