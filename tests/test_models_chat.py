"""
Tests for POST /api/models/chat endpoint.

Covers:
- Unknown model_id → 422
- Tanaka persona routing for BSM (APEX-MDL-0004), HW1F (APEX-MDL-0005), LMM (APEX-MDL-0006)
- Achebe persona routing for all others (VaR, SVaR, ECL, etc.)
- MDD file not found → graceful degradation (no crash)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """TestClient wrapping the full FastAPI app."""
    from api.main import app
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Unknown model_id → 422
# ---------------------------------------------------------------------------

def test_chat_unknown_model_id_returns_422(client):
    resp = client.post("/api/models/chat", json={
        "model_id": "APEX-MDL-FAKE-9999",
        "question": "What is this model?",
        "stream": False,
    })
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Persona routing
# ---------------------------------------------------------------------------

def _mock_stream_context(text="Mock response"):
    """Return a context manager that yields text tokens."""
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter([text])
    return mock_stream


@pytest.mark.parametrize("model_id,expected_persona", [
    ("APEX-MDL-0004", "Dr. Yuki Tanaka"),   # BSM
    ("APEX-MDL-0005", "Dr. Yuki Tanaka"),   # HW1F
    ("APEX-MDL-0006", "Dr. Yuki Tanaka"),   # LMM/SOFR
    ("APEX-MDL-0001", "Dr. Samuel Achebe"), # VaR
    ("APEX-MDL-0002", "Dr. Samuel Achebe"), # SVaR
    ("APEX-MDL-0007", "Dr. Samuel Achebe"), # IFRS 9 ECL
    ("APEX-MDL-0008", "Dr. Samuel Achebe"), # AML
    ("APEX-MDL-0009", "Dr. Samuel Achebe"), # CRM
])
def test_chat_persona_routing(client, model_id, expected_persona):
    """Each model should route to the correct persona."""
    with patch("api.models_routes.anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.stream.return_value = _mock_stream_context("Hello")

        resp = client.post("/api/models/chat", json={
            "model_id": model_id,
            "question": "Describe this model briefly.",
            "stream": True,
        })

        assert resp.status_code == 200
        # Parse SSE response — look for persona field
        raw = resp.text
        found_persona = False
        for line in raw.split("\n"):
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload.get("persona") == expected_persona:
                    found_persona = True
                    break
        assert found_persona, f"Expected persona '{expected_persona}' in SSE for {model_id}"


# ---------------------------------------------------------------------------
# MDD file missing → graceful degradation
# ---------------------------------------------------------------------------

def test_chat_missing_mdd_does_not_crash(client):
    """If the MDD file doesn't exist on disk, the endpoint should still respond."""
    with patch("api.models_routes.anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.stream.return_value = _mock_stream_context("No MDD available")

        with patch("api.models_routes._load_mdd_content", return_value=""):
            resp = client.post("/api/models/chat", json={
                "model_id": "APEX-MDL-0001",
                "question": "What are the open findings?",
                "stream": True,
            })
            assert resp.status_code == 200
