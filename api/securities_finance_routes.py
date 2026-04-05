"""FastAPI routes for the Securities Finance dashboard."""
from __future__ import annotations

from fastapi import APIRouter

from infrastructure.securities_finance.service import securities_finance_service
from infrastructure.securities_finance.lifecycle import repo_ladder, margin_engine

router = APIRouter(prefix="/securities-finance", tags=["securities_finance"])


@router.get("/overview")
def overview() -> dict:
    return securities_finance_service.get_overview()


@router.get("/books")
def books() -> list[dict]:
    return securities_finance_service.get_books()


@router.get("/inventory")
def inventory() -> list[dict]:
    return securities_finance_service.get_inventory()


@router.get("/client-financing")
def client_financing() -> list[dict]:
    return securities_finance_service.get_client_financing()


@router.get("/stress")
def stress() -> dict:
    return securities_finance_service.run_stress()


@router.get("/repo-ladder")
def get_repo_ladder() -> dict:
    """Live repo ladder — rates pulled from FRED yield curve and interpolated across tenors."""
    return repo_ladder.get_ladder()


@router.post("/repo-ladder/reprice")
def reprice_repo_ladder() -> dict:
    """Reprice repo book against current FRED rates. Returns legs that moved >2bps."""
    repriced = repo_ladder.reprice()
    ladder = repo_ladder.get_ladder()
    return {"repriced_legs": repriced, "ladder": ladder}


@router.get("/margin")
def get_margin_summary() -> dict:
    """Margin account summary across repo counterparties."""
    return margin_engine.get_margin_summary()


@router.post("/margin/shock")
def apply_margin_shock(body: dict) -> dict:
    """
    Simulate a collateral price move and trigger margin calls.
    Body: { asset: str, price_change_pct: float }
    """
    asset = str(body.get("asset", "UST"))
    change = float(body.get("price_change_pct", -0.01))
    calls = margin_engine.apply_price_move(asset, change)
    summary = margin_engine.get_margin_summary()
    return {"margin_calls_triggered": calls, "margin_summary": summary}
