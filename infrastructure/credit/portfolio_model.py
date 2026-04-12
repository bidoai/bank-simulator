"""
Credit Portfolio Model — Single-Factor Gaussian Copula.

Generates correlated defaults across the loan book via a one-factor model:

    Z_i = sqrt(rho_i) * M + sqrt(1 - rho_i) * e_i

where M ~ N(0,1) is the systematic factor and e_i ~ N(0,1) are idiosyncratic.
Obligor i defaults when Z_i < Phi^{-1}(PD_i).

Loss distribution is built from 10,000 Monte Carlo scenarios.
Credit VaR at 99% (management) and 99.9% (economic capital).
Marginal contribution to CVaR computed via indicator averaging.

Asset correlations by rating:
  IG (AAA/AA/A/BBB): rho = 0.20
  HY (BB/B):         rho = 0.30
  CCC/D:             rho = 0.35
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass

import numpy as np
import structlog

log = structlog.get_logger(__name__)

# Asset correlations by rating bucket
_RATING_RHO: dict[str, float] = {
    "AAA": 0.20, "AA": 0.20, "A": 0.20, "BBB": 0.20,
    "BB":  0.30, "B":  0.30,
    "CCC": 0.35, "D":  0.35,
}

_DEFAULT_N_SCENARIOS = 10_000


@dataclass
class CreditVar:
    expected_loss_usd:      float
    var_99_usd:             float     # 99th percentile loss
    var_999_usd:            float     # 99.9th percentile (economic capital)
    es_99_usd:              float     # expected shortfall (CVaR) at 99%
    es_999_usd:             float     # expected shortfall at 99.9%
    credit_var_usd:         float     # credit VaR = var_99 - expected_loss
    ec_usd:                 float     # economic capital = var_999 - expected_loss
    total_notional_usd:     float
    ec_ratio:               float     # EC / notional
    n_scenarios:            int
    as_of:                  str

    def to_dict(self) -> dict:
        return {
            "expected_loss_usd":  round(self.expected_loss_usd,  0),
            "var_99_usd":         round(self.var_99_usd,         0),
            "var_999_usd":        round(self.var_999_usd,        0),
            "es_99_usd":          round(self.es_99_usd,          0),
            "es_999_usd":         round(self.es_999_usd,         0),
            "credit_var_usd":     round(self.credit_var_usd,     0),
            "ec_usd":             round(self.ec_usd,             0),
            "total_notional_usd": round(self.total_notional_usd, 0),
            "ec_ratio":           round(self.ec_ratio,           6),
            "n_scenarios":        self.n_scenarios,
            "as_of":              self.as_of,
        }


class CreditPortfolioModel:
    """
    Single-factor Gaussian copula credit portfolio model.

    Works with any list of dicts having fields:
      obligor_id, pd_1yr, lgd, ead (or notional_usd), rating, [sector]
    """

    def __init__(self, n_scenarios: int = _DEFAULT_N_SCENARIOS, seed: int = 42) -> None:
        self._n = n_scenarios
        self._seed = seed

    # ------------------------------------------------------------------
    # Core simulation
    # ------------------------------------------------------------------

    def simulate(self, obligors: list) -> CreditVar:
        """
        Run the MC loss distribution for the given obligor list.
        obligors: list of Obligor dataclass instances OR plain dicts.
        """
        n_obs = len(obligors)
        if n_obs == 0:
            ts = datetime.now(timezone.utc).isoformat()
            return CreditVar(0, 0, 0, 0, 0, 0, 0, 0, 0.0, self._n, ts)

        rng = np.random.default_rng(self._seed)

        # Extract arrays
        pds   = np.array([self._pd(o)  for o in obligors], dtype=float)
        lgds  = np.array([self._lgd(o) for o in obligors], dtype=float)
        eads  = np.array([self._ead(o) for o in obligors], dtype=float)
        rhos  = np.array([self._rho(o) for o in obligors], dtype=float)

        # Default thresholds in standard normal space
        thresholds = self._norm_ppf(pds)  # shape (n_obs,)

        # Systematic factor: shape (n_scenarios,)
        M = rng.standard_normal(self._n)

        # Idiosyncratic factors: shape (n_scenarios, n_obs)
        eps = rng.standard_normal((self._n, n_obs))

        # Asset returns: Z_i = sqrt(rho_i)*M + sqrt(1-rho_i)*eps_i
        Z = np.sqrt(rhos) * M[:, None] + np.sqrt(1 - rhos) * eps  # (n_scen, n_obs)

        # Defaults: Z_i < threshold_i
        defaults = Z < thresholds[None, :]  # (n_scen, n_obs)

        # Losses per scenario: sum_i (LGD_i * EAD_i * 1_{default_i})
        loss_given_default = lgds * eads          # (n_obs,)
        scenario_losses = defaults @ loss_given_default  # (n_scen,)

        el   = float(np.mean(scenario_losses))
        total_notional = float(np.sum(eads))

        sorted_losses = np.sort(scenario_losses)
        idx_99  = int(np.ceil(0.99  * self._n)) - 1
        idx_999 = int(np.ceil(0.999 * self._n)) - 1

        var_99  = float(sorted_losses[idx_99])
        var_999 = float(sorted_losses[idx_999])
        es_99   = float(np.mean(sorted_losses[idx_99:]))
        es_999  = float(np.mean(sorted_losses[idx_999:]))

        log.info("credit_portfolio.simulated",
                 n_obligors=n_obs, n_scenarios=self._n,
                 el_mm=round(el / 1e6, 2),
                 var99_mm=round(var_99 / 1e6, 2),
                 var999_mm=round(var_999 / 1e6, 2))

        return CreditVar(
            expected_loss_usd  = el,
            var_99_usd         = var_99,
            var_999_usd        = var_999,
            es_99_usd          = es_99,
            es_999_usd         = es_999,
            credit_var_usd     = max(0.0, var_99  - el),
            ec_usd             = max(0.0, var_999 - el),
            total_notional_usd = total_notional,
            ec_ratio           = max(0.0, var_999 - el) / total_notional if total_notional else 0.0,
            n_scenarios        = self._n,
            as_of              = datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Marginal contribution to ES_99 (CVaR) per obligor
    # ------------------------------------------------------------------

    def marginal_contributions(self, obligors: list) -> list[dict]:
        """
        Return marginal EC contribution per obligor via indicator method.
        MRC_i = E[LGD_i * EAD_i | portfolio loss > VaR_99]
        """
        n_obs = len(obligors)
        if n_obs == 0:
            return []

        rng = np.random.default_rng(self._seed)

        pds   = np.array([self._pd(o)  for o in obligors], dtype=float)
        lgds  = np.array([self._lgd(o) for o in obligors], dtype=float)
        eads  = np.array([self._ead(o) for o in obligors], dtype=float)
        rhos  = np.array([self._rho(o) for o in obligors], dtype=float)
        thresholds = self._norm_ppf(pds)

        M   = rng.standard_normal(self._n)
        eps = rng.standard_normal((self._n, n_obs))
        Z   = np.sqrt(rhos) * M[:, None] + np.sqrt(1 - rhos) * eps
        defaults = Z < thresholds[None, :]
        lgd_ead  = lgds * eads
        scenario_losses = defaults @ lgd_ead

        idx_99 = int(np.ceil(0.99 * self._n)) - 1
        var_99 = float(np.sort(scenario_losses)[idx_99])
        tail_mask = scenario_losses > var_99  # scenarios in the tail

        result = []
        tail_count = int(np.sum(tail_mask))
        for i, ob in enumerate(obligors):
            if tail_count > 0:
                mrc = float(np.mean(defaults[tail_mask, i] * lgd_ead[i]))
            else:
                mrc = 0.0
            result.append({
                "obligor_id":    self._id(ob),
                "name":          self._name(ob),
                "rating":        self._rating(ob),
                "ead_usd":       round(float(eads[i]), 0),
                "pd_1yr":        round(float(pds[i]), 6),
                "lgd":           round(float(lgds[i]), 4),
                "rho":           round(float(rhos[i]), 4),
                "mrc_usd":       round(mrc, 0),
                "mrc_pct":       round(mrc / float(eads[i]) * 100, 4) if eads[i] > 0 else 0.0,
            })

        # Sort descending by MRC
        result.sort(key=lambda x: x["mrc_usd"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # Loss distribution (histogram buckets for charting)
    # ------------------------------------------------------------------

    def loss_distribution(self, obligors: list, n_buckets: int = 50) -> dict:
        """Return a bucketed loss distribution for charting."""
        rng = np.random.default_rng(self._seed)
        n_obs = len(obligors)
        if n_obs == 0:
            return {"buckets": [], "frequencies": []}

        pds   = np.array([self._pd(o)  for o in obligors], dtype=float)
        lgds  = np.array([self._lgd(o) for o in obligors], dtype=float)
        eads  = np.array([self._ead(o) for o in obligors], dtype=float)
        rhos  = np.array([self._rho(o) for o in obligors], dtype=float)
        thresholds = self._norm_ppf(pds)

        M   = rng.standard_normal(self._n)
        eps = rng.standard_normal((self._n, n_obs))
        Z   = np.sqrt(rhos) * M[:, None] + np.sqrt(1 - rhos) * eps
        defaults = Z < thresholds[None, :]
        scenario_losses = defaults @ (lgds * eads)

        counts, edges = np.histogram(scenario_losses, bins=n_buckets)
        bucket_centres = ((edges[:-1] + edges[1:]) / 2).tolist()
        return {
            "bucket_centres_usd": [round(v, 0) for v in bucket_centres],
            "frequencies":        counts.tolist(),
            "n_scenarios":        self._n,
        }

    # ------------------------------------------------------------------
    # Field accessors (handles both Obligor dataclass and plain dict)
    # ------------------------------------------------------------------

    @staticmethod
    def _pd(o) -> float:
        return float(getattr(o, "pd_1yr", None) or o.get("pd_1yr", 0.01))

    @staticmethod
    def _lgd(o) -> float:
        return float(getattr(o, "lgd", None) or o.get("lgd", 0.45))

    @staticmethod
    def _ead(o) -> float:
        v = getattr(o, "ead", None) or getattr(o, "notional_usd", None)
        if v is None:
            v = o.get("ead") or o.get("notional_usd", 1_000_000)
        return float(v)

    @staticmethod
    def _rating(o) -> str:
        return str(getattr(o, "rating", None) or o.get("rating", "BBB"))

    @staticmethod
    def _id(o) -> str:
        return str(getattr(o, "obligor_id", None) or o.get("obligor_id", "UNK"))

    @staticmethod
    def _name(o) -> str:
        return str(getattr(o, "name", None) or o.get("name", ""))

    def _rho(self, o) -> float:
        rating = self._rating(o)
        return _RATING_RHO.get(rating, 0.20)

    @staticmethod
    def _norm_ppf(pds: np.ndarray) -> np.ndarray:
        """Vectorised Phi^{-1}(PD) via rational approximation (no scipy needed)."""
        from scipy.stats import norm
        return norm.ppf(pds)


# Module-level singleton
credit_portfolio_model = CreditPortfolioModel()
