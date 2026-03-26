"""
Thread-safe active scenario state — shared between scenario routes and the
meeting orchestrator.

The singleton `scenario_state` holds whatever stress scenario is currently
"live" in the simulation. When a scenario is active, the meeting orchestrator
injects its market conditions into every agent's prompt so they respond in
character to the shock.

Only one scenario can be active at a time. Activation is in-memory only —
a server restart resets it (acceptable for v1; SQLite history already covers
past runs).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _ScenarioState:
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    active: bool = False
    scenario_id: str = ""
    scenario_name: str = ""
    shocks: dict[str, Any] = field(default_factory=dict)

    def activate(self, scenario_id: str, scenario_name: str, shocks: dict[str, Any]) -> None:
        with self._lock:
            self.active = True
            self.scenario_id = scenario_id
            self.scenario_name = scenario_name
            self.shocks = dict(shocks)

    def deactivate(self) -> None:
        with self._lock:
            self.active = False
            self.scenario_id = ""
            self.scenario_name = ""
            self.shocks = {}

    def snapshot(self) -> dict[str, Any]:
        """Return a thread-safe copy of current state."""
        with self._lock:
            return {
                "active": self.active,
                "scenario_id": self.scenario_id,
                "scenario_name": self.scenario_name,
                "shocks": dict(self.shocks),
            }


# Module-level singleton — import this everywhere.
scenario_state = _ScenarioState()
