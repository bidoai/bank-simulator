from __future__ import annotations

from fastapi import APIRouter

from infrastructure.metrics.api_metrics import api_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/api")
def get_api_metrics() -> dict:
    return {
        "summary": api_metrics.get_daily_summary(),
        "per_agent": api_metrics.get_per_agent(),
    }


@router.get("/api/alert")
def get_api_alert(threshold_usd: float = 10.0) -> dict:
    summary = api_metrics.get_daily_summary()
    return {
        "alert": api_metrics.check_alert(threshold_usd),
        "cost_usd": summary["estimated_cost_usd"],
        "threshold_usd": threshold_usd,
    }


@router.post("/api/reset")
def reset_api_metrics() -> dict:
    api_metrics.reset_daily()
    return {"status": "ok", "message": "Daily counters reset"}
