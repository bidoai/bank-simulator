"""FastAPI routes for the Securitized Products dashboard."""
from __future__ import annotations

from fastapi import APIRouter

from infrastructure.securitized_products.service import securitized_products_service

router = APIRouter(prefix="/securitized", tags=["securitized"])


@router.get("/overview")
def overview() -> dict:
    return securitized_products_service.get_overview()


@router.get("/inventory")
def inventory() -> list[dict]:
    return securitized_products_service.get_inventory()


@router.get("/relative-value")
def relative_value() -> dict:
    return securitized_products_service.get_relative_value()


@router.get("/stress")
def stress() -> dict:
    return securitized_products_service.run_stress()


@router.get("/pipeline")
def pipeline() -> dict:
    return securitized_products_service.get_pipeline()
