"""
Centralised configuration for Apex Global Bank Simulator.

All environment variable loading and shared constants live here.
Import from this module instead of calling load_dotenv() directly.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Single authoritative load — importing this module is sufficient.
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / "data"

DB_MEETINGS          = DATA_DIR / "meetings.db"
DB_OMS               = DATA_DIR / "oms_trades.db"
DB_POSITIONS         = DATA_DIR / "position_snapshots.db"
DB_EVENTS            = DATA_DIR / "events.db"
DB_LOSS_EVENTS       = DATA_DIR / "loss_events.db"
DB_RETAINED_EARNINGS = DATA_DIR / "retained_earnings.db"
DB_LOANS             = DATA_DIR / "loans.db"
DB_DEPOSITS          = DATA_DIR / "deposits.db"
DB_PAYMENTS          = DATA_DIR / "payments.db"
DB_CUSTODY           = DATA_DIR / "custody.db"

# ---------------------------------------------------------------------------
# API credentials
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS: list[str] = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:8000,http://localhost:8000",
).split(",")

# ---------------------------------------------------------------------------
# Risk constants  (regulatory / policy — change here, applied everywhere)
# ---------------------------------------------------------------------------

# VaR
VAR_CONFIDENCE: float = 0.99
VAR_HORIZON_DAYS: int = 1
VAR_MIN_HISTORY: int = 30       # minimum P&L observations for historical VaR

# P&L explain thresholds (% unexplained triggers flag)
PNL_INVESTIGATE_PCT: float = 10.0
PNL_ESCALATE_PCT: float = 20.0

# Limit utilisation colour bands (%)
LIMIT_YELLOW_PCT: float = 80.0
LIMIT_ORANGE_PCT: float = 90.0
LIMIT_RED_PCT: float = 100.0
LIMIT_BREACH_PCT: float = 120.0

# XVA defaults
XVA_LGD_DEFAULT: float = 0.60       # 60% loss-given-default
XVA_SPREAD_DEFAULT: float = 0.015   # 150 bps fallback CDS spread
XVA_N_PATHS: int = 2000
XVA_HORIZON_YEARS: float = 10.0
