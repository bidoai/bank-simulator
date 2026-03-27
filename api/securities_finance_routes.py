"""FastAPI routes for the Securities Finance dashboard."""
from __future__ import annotations

from fastapi import APIRouter

from infrastructure.securities_finance.service import securities_finance_service

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
