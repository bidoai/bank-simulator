"""
Legal Entity / Booking Model — TODO-022.

Defines the four Apex Global Bank legal entities and the mapping from trading
desk to booking entity. Used by SimulationXVAService to group netting sets by
entity (only netting=True entities net positions for XVA).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegalEntity:
    id: str
    name: str
    jurisdiction: str   # 2-letter ISO country code
    regime: str         # Primary regulatory regime
    netting: bool       # True = positions within entity can be netted for XVA


LEGAL_ENTITIES: dict[str, LegalEntity] = {
    "APEX_NA": LegalEntity(
        id="APEX_NA",
        name="Apex Global Bank N.A.",
        jurisdiction="US",
        regime="FRB/OCC",
        netting=True,
    ),
    "APEX_LDN": LegalEntity(
        id="APEX_LDN",
        name="Apex Global Bank London",
        jurisdiction="GB",
        regime="PRA",
        netting=True,
    ),
    "APEX_SEC": LegalEntity(
        id="APEX_SEC",
        name="Apex Securities LLC",
        jurisdiction="US",
        regime="SEC",
        netting=False,   # broker-dealer; no netting agreement in place
    ),
    "APEX_MKT": LegalEntity(
        id="APEX_MKT",
        name="Apex Markets (Cayman)",
        jurisdiction="KY",
        regime="CIMA",
        netting=True,
    ),
}

# Trading desk → booking entity
DESK_ENTITY: dict[str, str] = {
    "EQUITY":      "APEX_SEC",
    "RATES":       "APEX_NA",
    "FX":          "APEX_LDN",
    "CREDIT":      "APEX_NA",
    "COMMODITIES": "APEX_NA",
    "DERIVATIVES": "APEX_LDN",
}


def get_entity_for_desk(desk: str) -> LegalEntity:
    """Return the booking entity for a given trading desk."""
    entity_id = DESK_ENTITY.get(desk.upper(), "APEX_NA")
    return LEGAL_ENTITIES[entity_id]


def get_all_entities() -> list[dict]:
    """Serialisable list of all legal entities."""
    return [
        {
            "id": e.id,
            "name": e.name,
            "jurisdiction": e.jurisdiction,
            "regime": e.regime,
            "netting": e.netting,
        }
        for e in LEGAL_ENTITIES.values()
    ]
