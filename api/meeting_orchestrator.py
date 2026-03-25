"""
Meeting orchestrator — runs a live multi-agent boardroom session.

Each agent speaks in sequence. Their response streams token-by-token through
the BoardroomBroadcaster so the UI shows live typing. Every completed turn is
persisted to the MeetingStore for future replay.

Multi-turn context: each agent receives the full transcript of what was
said before them as a formatted context block, so they respond coherently
to prior speakers rather than in isolation.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Callable

import structlog

log = structlog.get_logger(__name__)

# ── Agent registry ─────────────────────────────────────────────────────────────
# Maps display name → (creator_fn_path, color)
# Lazy imports to avoid loading all agents on startup.

_AGENT_REGISTRY: dict[str, dict] = {
    "Alexandra Chen": {
        "module":        "agents.executive.ceo",
        "creator":       "create_ceo",
        "title":         "Chief Executive Officer",
        "color":         "#e3b341",
        "voice_profile": {"gender": "female", "accent": "en-US", "rate": 1.00, "pitch": 1.05},
    },
    "Dr. Priya Nair": {
        "module":        "agents.executive.cro",
        "creator":       "create_cro",
        "title":         "Chief Risk Officer",
        "color":         "#f85149",
        "voice_profile": {"gender": "female", "accent": "en-GB", "rate": 0.85, "pitch": 0.95},
    },
    "Dr. Yuki Tanaka": {
        "module":        "agents.markets.quant_researcher",
        "creator":       "create_quant_researcher",
        "title":         "Head of Quantitative Research",
        "color":         "#58a6ff",
        "voice_profile": {"gender": "male", "accent": "en-US", "rate": 1.00, "pitch": 1.10},
    },
    "James Okafor": {
        "module":        "agents.markets.lead_trader",
        "creator":       "create_lead_trader",
        "title":         "Head of Global Markets",
        "color":         "#3fb950",
        "voice_profile": {"gender": "male", "accent": "en-US", "rate": 1.15, "pitch": 1.00},
    },
    "Sarah Mitchell": {
        "module":        "agents.compliance.compliance_officer",
        "creator":       "create_compliance_officer",
        "title":         "Chief Compliance Officer",
        "color":         "#bc8cff",
        "voice_profile": {"gender": "female", "accent": "en-US", "rate": 0.90, "pitch": 1.05},
    },
    "Marcus Rivera": {
        "module":        "agents.executive.cto",
        "creator":       "create_cto",
        "title":         "Chief Technology Officer",
        "color":         "#79c0ff",
        "voice_profile": {"gender": "male", "accent": "en-US", "rate": 1.05, "pitch": 1.05},
    },
    "Amara Diallo": {
        "module":        "agents.executive.head_of_treasury",
        "creator":       "create_head_of_treasury",
        "title":         "Head of Treasury & ALM",
        "color":         "#ffa657",
        "voice_profile": {"gender": "female", "accent": "en-US", "rate": 0.90, "pitch": 1.00},
    },
    "Diana Osei": {
        "module":        "agents.executive.cfo",
        "creator":       "create_cfo",
        "title":         "Chief Financial Officer",
        "color":         "#e3b341",
        "voice_profile": {"gender": "female", "accent": "en-US", "rate": 0.95, "pitch": 1.00},
    },
    "The Observer": {
        "module":        "agents.narrator.observer",
        "creator":       "create_observer",
        "title":         "Independent Narrator",
        "color":         "#8b949e",
        "voice_profile": {"gender": "male", "accent": "en-US", "rate": 0.88, "pitch": 0.92},
    },
    "Dr. Fatima Al-Rashid": {
        "module":        "agents.technology.cdo",
        "creator":       "create_cdo",
        "title":         "Chief Data Officer",
        "color":         "#b39ddb",
        "voice_profile": {"gender": "female", "accent": "en-US", "rate": 0.95, "pitch": 1.05},
    },
    "Jordan Pierce": {
        "module":        "agents.audit.internal_audit",
        "creator":       "create_internal_auditor",
        "title":         "Head of Internal Audit",
        "color":         "#c62828",
        "voice_profile": {"gender": "neutral", "accent": "en-US", "rate": 0.88, "pitch": 0.97},
    },
    "Margaret Okonkwo": {
        "module":        "agents.legal.general_counsel",
        "creator":       "create_general_counsel",
        "title":         "General Counsel & Corporate Secretary",
        "color":         "#4fc3f7",
        "voice_profile": {"gender": "female", "accent": "en-GB", "rate": 0.90, "pitch": 1.00},
    },
    "Dr. Samuel Achebe": {
        "module":        "agents.risk_desk.model_validation_officer",
        "creator":       "create_model_validation_officer",
        "title":         "Head of Model Validation",
        "color":         "#ce93d8",
        "voice_profile": {"gender": "male", "accent": "en-US", "rate": 0.88, "pitch": 0.95},
    },
}

# Default agent order for a full board meeting
DEFAULT_AGENTS = [
    "Alexandra Chen",
    "Dr. Priya Nair",
    "Marcus Rivera",
    "Dr. Yuki Tanaka",
    "James Okafor",
    "The Observer",
]


def _load_agent(name: str, client):
    """Dynamically import and instantiate an agent by display name."""
    meta = _AGENT_REGISTRY.get(name)
    if not meta:
        raise ValueError(f"Unknown agent: {name!r}. Valid: {list(_AGENT_REGISTRY)}")
    import importlib
    mod = importlib.import_module(meta["module"])
    creator = getattr(mod, meta["creator"])
    return creator(client)


def _format_shock(key: str, value: float) -> str:
    """Convert a raw shock key/value pair into a readable description."""
    labels = {
        "ir_sigma_multiplier":      f"IR volatility {value:.2f}× baseline",
        "fx_vol_multiplier":        f"FX volatility {value:.2f}× baseline",
        "eq_vol_multiplier":        f"Equity volatility {value:.2f}× baseline",
        "credit_spread_multiplier": f"Credit spreads {value:.2f}× baseline",
        "ir_level_shift":           f"IR curves +{value*100:.0f}bp parallel shift",
        "ig_spread_multiplier":     f"IG credit spreads {value:.1f}× baseline",
        "hy_spread_multiplier":     f"HY credit spreads {value:.1f}× baseline",
    }
    return labels.get(key, f"{key}: {value}")


def _build_context_prompt(topic: str, transcript: list[dict], agent_name: str) -> str:
    """
    Build the prompt fed to each agent.

    Includes:
      - Active market scenario (if any) injected at the top
      - The meeting topic/question
      - All prior turns as a formatted transcript
      - An instruction to respond naturally to prior speakers
    """
    lines: list[str] = []

    # Inject active scenario context so agents react in character
    try:
        from api.scenario_state import scenario_state
        snap = scenario_state.snapshot()
        if snap["active"]:
            lines.append("⚠️  ACTIVE MARKET SCENARIO")
            lines.append("─" * 60)
            lines.append(f"Scenario: {snap['scenario_name']}")
            lines.append("Market conditions now in effect:")
            for k, v in snap["shocks"].items():
                lines.append(f"  • {_format_shock(k, v)}")
            lines.append("")
            lines.append(
                "This scenario is LIVE. Factor these market conditions into "
                "your response — react as you would if this shock hit the "
                "bank right now. Be specific about the implications for your "
                "area of responsibility."
            )
            lines.append("─" * 60)
            lines.append("")
    except Exception:
        pass  # Never let scenario injection break a meeting

    lines += [
        f"BOARD MEETING TOPIC: {topic}",
        "",
    ]

    if transcript:
        lines.append("TRANSCRIPT SO FAR:")
        lines.append("─" * 60)
        # Cap to last 20 turns to prevent unbounded context growth (TODO-001)
        for turn in transcript[-20:]:
            lines.append(f"{turn['agent']} ({turn['title']}):")
            lines.append(turn["text"])
            lines.append("")
        lines.append("─" * 60)
        lines.append("")
        lines.append(
            f"It is now your turn to speak, {agent_name}. "
            "Respond to what has been said, add your unique perspective, "
            "and advance the discussion. Speak as yourself — in character, "
            "with the expertise and voice defined in your role. "
            "Be substantive but concise (300-600 words)."
        )
    else:
        lines.append(
            f"You are the first to speak, {agent_name}. "
            "Open the discussion on this topic with your most important "
            "framing, priorities, or concerns. "
            "Be substantive but concise (300-600 words)."
        )

    return "\n".join(lines)


async def run_live_meeting(
    topic: str,
    agent_names: list[str],
    meeting_id: str,
    broadcaster,
    store,
    client=None,
) -> None:
    """
    Run a full multi-agent boardroom meeting.

    Streams each agent's response token-by-token through `broadcaster`.
    Persists every completed turn to `store`.
    Handles API errors gracefully — broadcasts the error and marks
    the meeting as errored rather than hanging.
    """
    import anthropic as _anthropic

    # Load .env if API key not already set
    if not os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).parent.parent / ".env")
        except ImportError:
            pass

    if client is None:
        try:
            client = _anthropic.Anthropic()
        except Exception as exc:
            await broadcaster.broadcast_system(f"ERROR: Could not initialise Anthropic client — {exc}")
            store.complete_meeting(meeting_id, status="error")
            return

    transcript: list[dict] = []

    await broadcaster.broadcast_system(
        f"Boardroom session started — topic: \"{topic}\""
    )

    for agent_name in agent_names:
        meta = _AGENT_REGISTRY.get(agent_name)
        if not meta:
            log.warning("orchestrator.unknown_agent", name=agent_name)
            continue

        color = meta["color"]
        title = meta["title"]

        try:
            agent = _load_agent(agent_name, client)
        except Exception as exc:
            log.error("orchestrator.agent_load_failed", name=agent_name, error=str(exc))
            await broadcaster.broadcast_system(f"Could not load agent {agent_name}: {exc}")
            continue

        prompt = _build_context_prompt(topic, transcript, agent_name)

        # Signal turn start (shows typing indicator)
        await broadcaster.broadcast_turn_start(agent_name, title, color)

        full_text = ""
        try:
            # Stream directly — gives us token-level control
            messages = [{"role": "user", "content": prompt}]

            # Run blocking stream in executor so we don't block the event loop
            loop = asyncio.get_running_loop()
            token_queue: asyncio.Queue = asyncio.Queue()

            def _stream_worker():
                """Run in a thread; puts tokens onto the queue."""
                try:
                    with client.messages.stream(
                        model="claude-opus-4-6",
                        max_tokens=1024,
                        system=agent.system_prompt,
                        messages=messages,
                    ) as stream:
                        for chunk in stream.text_stream:
                            # thread-safe put
                            loop.call_soon_threadsafe(token_queue.put_nowait, chunk)
                    loop.call_soon_threadsafe(token_queue.put_nowait, None)  # sentinel
                except Exception as exc:
                    loop.call_soon_threadsafe(
                        token_queue.put_nowait, f"\n\n[ERROR: {exc}]"
                    )
                    loop.call_soon_threadsafe(token_queue.put_nowait, None)

            # Start the blocking stream in a thread pool
            stream_future = loop.run_in_executor(None, _stream_worker)

            # Drain the queue on the event loop
            while True:
                token = await token_queue.get()
                if token is None:
                    break
                full_text += token
                await broadcaster.broadcast_token(agent_name, token, color)

            await stream_future  # ensure thread cleanup

        except Exception as exc:
            error_msg = f"[API error for {agent_name}: {exc}]"
            log.error("orchestrator.stream_failed", agent=agent_name, error=str(exc))
            await broadcaster.broadcast_system(error_msg)
            store.complete_meeting(meeting_id, status="error")
            return

        if not full_text.strip():
            full_text = "[No response generated]"

        # Finalise turn
        await broadcaster.broadcast_turn_end(agent_name)
        await broadcaster.broadcast_agent_turn(agent_name, title, full_text, color)

        # Persist
        store.add_turn(meeting_id, agent_name, title, full_text, color)

        # Add to shared transcript so next agents can read it
        transcript.append({
            "agent": agent_name,
            "title": title,
            "text":  full_text,
            "color": color,
        })

        # Brief pause between speakers
        await asyncio.sleep(0.5)

    store.complete_meeting(meeting_id, status="completed")
    await broadcaster.broadcast_system(
        f"Session concluded — {len(transcript)} turns. "
        "Transcript saved and available in session history."
    )
    log.info("orchestrator.meeting_completed", meeting_id=meeting_id, turns=len(transcript))
