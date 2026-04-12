"""SimulationXVAService — bridges OMS blotter → pyxva → cached XVA results."""
from __future__ import annotations

import asyncio
from infrastructure.xva.adapter import XVAAdapter
from infrastructure.trading.oms import oms
from infrastructure.risk.counterparty_registry import counterparty_registry

import structlog
log = structlog.get_logger(__name__)

# Desk → counterparty assignment for netting sets
_DESK_COUNTERPARTIES = {
    "RATES": ["Goldman Sachs", "JPMorgan", "Deutsche Bank"],
    "DERIVATIVES": ["Goldman Sachs", "JPMorgan", "Deutsche Bank"],
    "FX": ["BNP Paribas", "HSBC"],
    "EQUITY": ["Goldman Sachs", "JPMorgan"],
    "CREDIT": ["Goldman Sachs", "JPMorgan"],
}

_EQUITY_TICKERS = {"AAPL", "MSFT", "SPY", "NVDA"}
_FX_TICKERS = {"EURUSD", "GBPUSD"}
_BOND_TICKERS = {"US10Y", "US2Y"}

LGD_DEFAULT = 0.6
SPREAD_DEFAULT = 0.015  # 150bps fallback


class SimulationXVAService:
    def __init__(self) -> None:
        # asyncio.Lock MUST be created in __init__ (not class variable)
        self._lock = asyncio.Lock()
        self._refreshing: bool = False
        self._cache: dict | None = None

    def _get_counterparty_spread(self, name: str) -> float:
        try:
            report = counterparty_registry.get_report()
            for cp in report:
                if name in cp.get("name", ""):
                    return cp.get("credit_spread", SPREAD_DEFAULT)
        except Exception:
            pass
        return SPREAD_DEFAULT

    def _map_fills_to_pyxva_config(self, fills: list[dict]) -> dict:
        """Map OMS blotter entries to pyxva EngineConfig format."""
        if not fills:
            return {
                "trades": [{"id": "SAMPLE_IRS_001", "product": "irs", "notional": 50_000_000.0, "tenor": 5, "counterparty": "Goldman Sachs"}],
                "counterparty_spreads": {"Goldman Sachs": 0.0085},
            }

        trades = []
        cp_spreads: dict[str, float] = {}

        for i, fill in enumerate(fills):
            ticker = fill.get("ticker", "")
            desk = fill.get("desk", "RATES").upper()
            notional = abs(fill.get("notional", 0.0))
            if notional <= 0:
                continue

            # Equity tickers: handle analytically, skip pyxva
            if ticker in _EQUITY_TICKERS:
                continue

            # Assign counterparty by desk (round-robin)
            cps = _DESK_COUNTERPARTIES.get(desk, _DESK_COUNTERPARTIES["RATES"])
            cp_name = cps[i % len(cps)]

            # Determine product type
            if "IRS" in ticker:
                product = "irs"
                tenor = 5
            elif "_CALL_" in ticker:
                product = "european_call"
                tenor = 0.25
            elif "_PUT_" in ticker:
                product = "european_put"
                tenor = 0.25
            elif ticker in _BOND_TICKERS:
                product = "fixed_rate_bond"
                tenor = 10 if "10Y" in ticker else 2
            elif ticker in _FX_TICKERS:
                product = "fx_forward"
                tenor = 1
            else:
                product = "irs"
                tenor = 5

            trades.append({
                "id": fill.get("trade_id", f"T{i}"),
                "product": product,
                "notional": notional,
                "tenor": tenor,
                "counterparty": cp_name,
            })

            if cp_name not in cp_spreads:
                cp_spreads[cp_name] = self._get_counterparty_spread(cp_name)

        # Compute analytical equity CVA separately
        equity_cva = 0.0
        for fill in fills:
            if fill.get("ticker", "") in _EQUITY_TICKERS:
                notional = abs(fill.get("notional", 0.0))
                desk = fill.get("desk", "EQUITY").upper()
                cps = _DESK_COUNTERPARTIES.get("EQUITY", ["Goldman Sachs"])
                cp_name = cps[0]
                spread = cp_spreads.get(cp_name, self._get_counterparty_spread(cp_name))
                equity_cva += LGD_DEFAULT * spread * notional * 1.0  # 1yr tenor

        return {
            "trades": trades,
            "counterparty_spreads": cp_spreads,
            "_equity_cva": equity_cva,
        }

    def _run_pipeline(self) -> dict:
        """Run pyxva pipeline synchronously (call from thread pool executor)."""
        fills = oms.get_blotter()
        config = self._map_fills_to_pyxva_config(fills)
        result = XVAAdapter.run_pipeline(config)  # single pyxva call site
        result["source"] = "live" if fills else "demo"
        # Merge equity analytical CVA
        if config.get("_equity_cva", 0.0) > 0:
            result["cva"] = result.get("cva", 0.0) + config["_equity_cva"]
        return result

    async def refresh(self) -> dict:
        """Refresh XVA via thread pool. If already refreshing, return cache."""
        if self._refreshing:
            return self.get_cached()
        async with self._lock:
            self._refreshing = True
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, self._run_pipeline)
                self._cache = result
                # Broadcast to WS clients (import here to avoid circular)
                try:
                    from infrastructure.xva.broadcaster import xva_broadcaster
                    asyncio.create_task(xva_broadcaster.broadcast_refresh(result))
                except Exception as exc:
                    log.warning("xva.broadcast_failed", error=str(exc))
                return result
            except Exception as exc:
                log.error("xva.refresh_failed", error=str(exc))
                return self.get_cached()
            finally:
                self._refreshing = False

    def get_cached(self) -> dict:
        """Return last result or sample data if never computed."""
        if self._cache is not None:
            return self._cache
        result = XVAAdapter._sample_results()
        result["source"] = "demo"
        return result


xva_service = SimulationXVAService()
