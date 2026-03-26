from __future__ import annotations

from datetime import date
from threading import Lock

import structlog

log = structlog.get_logger(__name__)

# Claude Sonnet 4.6 pricing (USD per million tokens)
_INPUT_COST_PER_MTOK = 3.0
_OUTPUT_COST_PER_MTOK = 15.0


class APIMetrics:
    """Track Anthropic API usage to prevent runaway spend."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._date: date = date.today()
        self._total_calls: int = 0
        self._total_tokens_in: int = 0
        self._total_tokens_out: int = 0
        self._per_agent: dict[str, dict] = {}

    def _check_rollover(self) -> None:
        today = date.today()
        if today != self._date:
            log.info("api_metrics.daily_rollover", previous_date=str(self._date))
            self._date = today
            self._total_calls = 0
            self._total_tokens_in = 0
            self._total_tokens_out = 0
            self._per_agent = {}

    def record_call(self, agent_name: str, tokens_in: int, tokens_out: int) -> None:
        with self._lock:
            self._check_rollover()
            self._total_calls += 1
            self._total_tokens_in += tokens_in
            self._total_tokens_out += tokens_out
            if agent_name not in self._per_agent:
                self._per_agent[agent_name] = {"calls": 0, "tokens_in": 0, "tokens_out": 0}
            self._per_agent[agent_name]["calls"] += 1
            self._per_agent[agent_name]["tokens_in"] += tokens_in
            self._per_agent[agent_name]["tokens_out"] += tokens_out
        log.info("api_metrics.recorded", agent=agent_name, tokens_in=tokens_in, tokens_out=tokens_out)

    def _cost_usd(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in / 1_000_000) * _INPUT_COST_PER_MTOK + (tokens_out / 1_000_000) * _OUTPUT_COST_PER_MTOK

    def get_daily_summary(self) -> dict:
        with self._lock:
            self._check_rollover()
            return {
                "date": str(self._date),
                "total_calls": self._total_calls,
                "total_tokens_in": self._total_tokens_in,
                "total_tokens_out": self._total_tokens_out,
                "total_tokens": self._total_tokens_in + self._total_tokens_out,
                "estimated_cost_usd": round(self._cost_usd(self._total_tokens_in, self._total_tokens_out), 4),
            }

    def get_per_agent(self) -> dict:
        with self._lock:
            self._check_rollover()
            result = {}
            for agent, stats in self._per_agent.items():
                result[agent] = {
                    **stats,
                    "estimated_cost_usd": round(
                        self._cost_usd(stats["tokens_in"], stats["tokens_out"]), 4
                    ),
                }
            return result

    def reset_daily(self) -> None:
        with self._lock:
            self._date = date.today()
            self._total_calls = 0
            self._total_tokens_in = 0
            self._total_tokens_out = 0
            self._per_agent = {}
        log.info("api_metrics.reset")

    def check_alert(self, threshold_usd: float = 10.0) -> bool:
        summary = self.get_daily_summary()
        return summary["estimated_cost_usd"] >= threshold_usd


api_metrics = APIMetrics()
