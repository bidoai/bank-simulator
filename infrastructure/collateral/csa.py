"""
Collateral data model — CSA, CollateralAccount, MarginCall.

Implements the core data structures for bilateral collateral management
under ISDA Master Agreement / Credit Support Annex framework.

Key concepts:
  - CSA: governs collateral terms per counterparty relationship
  - CollateralAccount: tracks posted/received balances per CSA
  - MarginCall: lifecycle of a single VM or IM call
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import Enum
from typing import Optional
import uuid


class MarginCallStatus(str, Enum):
    PENDING   = "PENDING"
    DELIVERED = "DELIVERED"
    DISPUTED  = "DISPUTED"
    LATE      = "LATE"
    SETTLED   = "SETTLED"
    DEFAULTED = "DEFAULTED"


class MarginCallDirection(str, Enum):
    OUTBOUND = "OUTBOUND"  # we must post collateral to counterparty
    INBOUND  = "INBOUND"   # counterparty must post collateral to us


class CollateralAssetType(str, Enum):
    USD_CASH = "USD_CASH"
    EUR_CASH = "EUR_CASH"
    UST      = "UST"        # US Treasuries
    AGENCY   = "AGENCY"     # Agency bonds (Fannie, Freddie)
    GILT     = "GILT"       # UK Gilts
    BUND     = "BUND"       # German Bunds
    IG_CORP  = "IG_CORP"    # Investment grade corporate bonds


# Published haircuts (% markdown to market value when used as collateral)
STANDARD_HAIRCUTS: dict[str, float] = {
    CollateralAssetType.USD_CASH: 0.000,
    CollateralAssetType.EUR_CASH: 0.000,
    CollateralAssetType.UST:      0.020,
    CollateralAssetType.AGENCY:   0.040,
    CollateralAssetType.GILT:     0.025,
    CollateralAssetType.BUND:     0.020,
    CollateralAssetType.IG_CORP:  0.150,
}


@dataclass
class CSA:
    """
    Credit Support Annex — governs bilateral collateral for one ISDA relationship.
    """
    csa_id:                   str
    counterparty_id:          str
    counterparty_name:        str
    our_legal_entity:         str   # which Apex entity is party (e.g. "Apex Global Bank N.A.")
    governing_law:            str   # "English" | "New York"

    # Threshold below which no collateral is required (0 = zero-threshold CSA)
    threshold_usd:            float = 0.0

    # Smallest increment triggering a call
    mta_usd:                  float = 500_000.0

    # Required initial margin (independent amount) — UMR-driven
    independent_amount_usd:   float = 0.0

    # Margin period of risk in business days (10 bilateral, 5 cleared)
    mpor_days:                int   = 10

    # Eligible collateral (default: cash + G10 govvies)
    eligible_collateral: list[str] = field(default_factory=lambda: [
        CollateralAssetType.USD_CASH,
        CollateralAssetType.UST,
        CollateralAssetType.AGENCY,
    ])

    # Haircuts (if None, uses STANDARD_HAIRCUTS)
    haircuts: dict[str, float] = field(default_factory=dict)

    rehypothecation_allowed: bool = True
    is_cleared:              bool = False   # CCP-cleared = 5-day MPoR

    def get_haircut(self, asset_type: str) -> float:
        return self.haircuts.get(asset_type, STANDARD_HAIRCUTS.get(asset_type, 0.15))

    def to_dict(self) -> dict:
        return {
            "csa_id": self.csa_id,
            "counterparty_id": self.counterparty_id,
            "counterparty_name": self.counterparty_name,
            "our_legal_entity": self.our_legal_entity,
            "governing_law": self.governing_law,
            "threshold_usd": self.threshold_usd,
            "mta_usd": self.mta_usd,
            "independent_amount_usd": self.independent_amount_usd,
            "mpor_days": self.mpor_days,
            "eligible_collateral": self.eligible_collateral,
            "rehypothecation_allowed": self.rehypothecation_allowed,
            "is_cleared": self.is_cleared,
        }


@dataclass
class CollateralAccount:
    """
    Tracks the collateral balance for a single CSA.
    """
    account_id:         str
    csa_id:             str
    counterparty_id:    str

    # Amounts in USD (mark-to-market of posted assets)
    vm_posted_usd:      float = 0.0   # we have posted as VM
    vm_received_usd:    float = 0.0   # counterparty has posted to us as VM
    im_posted_usd:      float = 0.0   # we have posted as IM (segregated)
    im_received_usd:    float = 0.0   # counterparty has posted to us as IM

    primary_asset_type: str = CollateralAssetType.USD_CASH
    custodian:          str = "BNY Mellon"
    last_call_date:     Optional[date] = None
    last_delivery_date: Optional[date] = None

    @property
    def net_collateral_usd(self) -> float:
        """Positive = net receiver (counterparty owes us). Negative = net poster."""
        return (self.vm_received_usd + self.im_received_usd) - (self.vm_posted_usd + self.im_posted_usd)

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "csa_id": self.csa_id,
            "counterparty_id": self.counterparty_id,
            "vm_posted_usd": self.vm_posted_usd,
            "vm_received_usd": self.vm_received_usd,
            "im_posted_usd": self.im_posted_usd,
            "im_received_usd": self.im_received_usd,
            "net_collateral_usd": self.net_collateral_usd,
            "primary_asset_type": self.primary_asset_type,
            "custodian": self.custodian,
            "last_call_date": str(self.last_call_date) if self.last_call_date else None,
            "last_delivery_date": str(self.last_delivery_date) if self.last_delivery_date else None,
        }


@dataclass
class MarginCall:
    """
    A single margin call — VM or IM — with full lifecycle tracking.
    """
    call_id:           str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    csa_id:            str   = ""
    counterparty_id:   str   = ""
    call_type:         str   = "VM"    # "VM" | "IM"
    direction:         str   = MarginCallDirection.OUTBOUND

    # Called amount and dispute
    amount_usd:        float = 0.0
    disputed_amount:   float = 0.0    # disputed portion (rest is undisputed)
    agreed_amount:     float = 0.0    # resolved amount after dispute process

    status:            str   = MarginCallStatus.PENDING
    asset_type:        str   = CollateralAssetType.USD_CASH

    call_date:         Optional[date] = None
    due_date:          Optional[date] = None
    delivery_date:     Optional[date] = None

    # Close-out context (populated if this triggers or follows a default)
    is_close_out:      bool  = False
    close_out_loss:    float = 0.0    # replacement cost − last MTM − IM held

    notes:             str   = ""

    @property
    def undisputed_amount(self) -> float:
        return self.amount_usd - self.disputed_amount

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "csa_id": self.csa_id,
            "counterparty_id": self.counterparty_id,
            "call_type": self.call_type,
            "direction": self.direction,
            "amount_usd": self.amount_usd,
            "disputed_amount": self.disputed_amount,
            "undisputed_amount": self.undisputed_amount,
            "agreed_amount": self.agreed_amount,
            "status": self.status,
            "asset_type": self.asset_type,
            "call_date": str(self.call_date) if self.call_date else None,
            "due_date": str(self.due_date) if self.due_date else None,
            "delivery_date": str(self.delivery_date) if self.delivery_date else None,
            "is_close_out": self.is_close_out,
            "close_out_loss": self.close_out_loss,
            "notes": self.notes,
        }
