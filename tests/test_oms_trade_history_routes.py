from __future__ import annotations

import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import oms_routes


def _seed_trade_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE oms_trades (
            trade_id TEXT PRIMARY KEY,
            ticker TEXT,
            side TEXT,
            quantity REAL,
            fill_price REAL,
            notional REAL,
            desk TEXT,
            book_id TEXT,
            trader_id TEXT,
            executed_at TEXT,
            greeks_json TEXT,
            var_before REAL,
            var_after REAL,
            limit_status TEXT,
            counterparty_id TEXT,
            product_subtype TEXT,
            product_details TEXT,
            pre_trade_message TEXT,
            limit_headroom_pct REAL
        )
        """
    )
    conn.executemany(
        "INSERT INTO oms_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "TRD-1001",
                "AAPL",
                "BUY",
                5000,
                214.67,
                1_073_350,
                "EQUITY",
                "EQ_BOOK_1",
                "system",
                "2026-04-11T13:00:00+00:00",
                json.dumps({"delta": 5000, "gamma": 0, "vega": 0, "dv01": 0}),
                100000,
                120000,
                "GREEN",
                None,
                None,
                json.dumps({}),
                "Within desk limits",
                76.5,
            ),
            (
                "TRD-1002",
                "MSFT",
                "SELL",
                2500,
                412.11,
                1_030_275,
                "EQUITY",
                "EQ_BOOK_2",
                "system",
                "2026-04-11T14:00:00+00:00",
                json.dumps({"delta": -2500, "gamma": 0, "vega": 0, "dv01": 0}),
                120000,
                140000,
                "YELLOW",
                None,
                None,
                json.dumps({}),
                "Near soft threshold",
                61.2,
            ),
        ],
    )
    conn.commit()
    conn.close()


def _client_for_db(monkeypatch, tmp_path) -> TestClient:
    db_path = tmp_path / "oms_trades.db"
    _seed_trade_db(str(db_path))
    monkeypatch.setattr(oms_routes, "_DB_PATH", str(db_path))

    app = FastAPI()
    app.include_router(oms_routes.router, prefix="/api")
    return TestClient(app, raise_server_exceptions=True)


def test_blotter_filters_by_trade_id(monkeypatch, tmp_path):
    client = _client_for_db(monkeypatch, tmp_path)

    response = client.get("/api/trading/blotter", params={"trade_id": "TRD-1001"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["trades"][0]["trade_id"] == "TRD-1001"
    assert payload["trades"][0]["instrument"] == "AAPL"


def test_blotter_filters_by_book_and_instrument(monkeypatch, tmp_path):
    client = _client_for_db(monkeypatch, tmp_path)

    response = client.get("/api/trading/blotter", params={"book": "EQ_BOOK_2", "instrument": "MSF"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["trades"][0]["trade_id"] == "TRD-1002"


def test_trade_detail_returns_full_record(monkeypatch, tmp_path):
    client = _client_for_db(monkeypatch, tmp_path)

    response = client.get("/api/trading/trades/TRD-1001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trade_id"] == "TRD-1001"
    assert payload["book"] == "EQ_BOOK_1"
    assert payload["pre_trade_message"] == "Within desk limits"
    assert payload["greeks"]["delta"] == 5000
