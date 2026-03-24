"""
Tests for meeting_orchestrator.py

Verifies:
  - _build_context_prompt: first-speaker path (empty transcript)
  - _build_context_prompt: subsequent-speaker path (transcript included)
  - _AGENT_REGISTRY: every registered agent has a voice_profile with the
    four required keys (gender, accent, rate, pitch)
"""
from __future__ import annotations

import pytest

from api.meeting_orchestrator import _AGENT_REGISTRY, _build_context_prompt


# ── _build_context_prompt ─────────────────────────────────────────────────────

def test_first_speaker_prompt_contains_topic():
    prompt = _build_context_prompt("VaR limits discussion", [], "Alexandra Chen")
    assert "VaR limits discussion" in prompt


def test_first_speaker_prompt_no_transcript_section():
    prompt = _build_context_prompt("Any topic", [], "Alexandra Chen")
    assert "TRANSCRIPT SO FAR" not in prompt
    assert "first to speak" in prompt.lower()


def test_subsequent_speaker_prompt_contains_transcript():
    transcript = [
        {"agent": "Alexandra Chen", "title": "CEO", "text": "We need to act."},
    ]
    prompt = _build_context_prompt("Capital allocation", transcript, "Dr. Priya Nair")
    assert "TRANSCRIPT SO FAR" in prompt
    assert "We need to act." in prompt


def test_subsequent_speaker_prompt_addresses_correct_agent():
    transcript = [
        {"agent": "Alexandra Chen", "title": "CEO", "text": "Opening remarks."},
    ]
    prompt = _build_context_prompt("Topic", transcript, "Dr. Priya Nair")
    assert "Dr. Priya Nair" in prompt


def test_prompt_includes_all_transcript_turns():
    transcript = [
        {"agent": "Alexandra Chen",  "title": "CEO", "text": "Turn 1."},
        {"agent": "Dr. Priya Nair",  "title": "CRO", "text": "Turn 2."},
        {"agent": "Dr. Yuki Tanaka", "title": "Quant", "text": "Turn 3."},
    ]
    prompt = _build_context_prompt("Risk", transcript, "James Okafor")
    assert "Turn 1." in prompt
    assert "Turn 2." in prompt
    assert "Turn 3." in prompt


# ── Voice profiles ────────────────────────────────────────────────────────────

REQUIRED_VOICE_KEYS = {"gender", "accent", "rate", "pitch"}


@pytest.mark.parametrize("agent_name,meta", list(_AGENT_REGISTRY.items()))
def test_agent_has_voice_profile(agent_name, meta):
    assert "voice_profile" in meta, f"{agent_name} missing voice_profile"


@pytest.mark.parametrize("agent_name,meta", list(_AGENT_REGISTRY.items()))
def test_voice_profile_has_required_keys(agent_name, meta):
    vp = meta["voice_profile"]
    missing = REQUIRED_VOICE_KEYS - set(vp.keys())
    assert not missing, f"{agent_name} voice_profile missing keys: {missing}"


@pytest.mark.parametrize("agent_name,meta", list(_AGENT_REGISTRY.items()))
def test_voice_profile_gender_valid(agent_name, meta):
    assert meta["voice_profile"]["gender"] in ("male", "female"), (
        f"{agent_name} voice_profile.gender must be 'male' or 'female'"
    )


@pytest.mark.parametrize("agent_name,meta", list(_AGENT_REGISTRY.items()))
def test_voice_profile_rate_in_range(agent_name, meta):
    rate = meta["voice_profile"]["rate"]
    assert 0.5 <= rate <= 2.0, f"{agent_name} voice_profile.rate {rate} out of range"


@pytest.mark.parametrize("agent_name,meta", list(_AGENT_REGISTRY.items()))
def test_voice_profile_pitch_in_range(agent_name, meta):
    pitch = meta["voice_profile"]["pitch"]
    assert 0.5 <= pitch <= 2.0, f"{agent_name} voice_profile.pitch {pitch} out of range"
