"""Legal entity registry — booking entity per desk."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class LegalEntity:
    id: str
    name: str
    jurisdiction: str
    regime: str
    netting: bool

LEGAL_ENTITIES: dict[str, LegalEntity] = {
    "APEX_NA":  LegalEntity("APEX_NA",  "Apex Global Bank N.A.",    "US", "FRB/OCC", True),
    "APEX_LDN": LegalEntity("APEX_LDN", "Apex Global Bank London",  "UK", "PRA",     True),
    "APEX_SEC": LegalEntity("APEX_SEC", "Apex Securities LLC",       "US", "SEC",     False),
    "APEX_MKT": LegalEntity("APEX_MKT", "Apex Markets (Cayman)",    "KY", "CIMA",    True),
}

DESK_ENTITY: dict[str, str] = {
    "EQUITY":      "APEX_SEC",
    "RATES":       "APEX_NA",
    "FX":          "APEX_LDN",
    "CREDIT":      "APEX_NA",
    "DERIVATIVES": "APEX_LDN",
}

def get_entity_for_desk(desk: str) -> LegalEntity:
    eid = DESK_ENTITY.get(desk.upper(), "APEX_NA")
    return LEGAL_ENTITIES[eid]
