"""
Observer Q&A route — ask the Observer about anything happening in the simulation.

POST /api/observer/chat

The Observer loads recent transcript context from the active meeting (if
meeting_id is provided) and answers the question in character as the
Independent Narrator, explaining jargon, tensions, and history in plain English.

The Observer agent is a module-level singleton so it persists conversational
context across requests. Its history is capped at _OBSERVER_MAX_HISTORY messages
(~20 turns) to prevent context window overflow.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, HTTPException

if TYPE_CHECKING:
    from agents.base_agent import BankAgent

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/observer", tags=["observer"])

# Singleton — one Observer instance shared across all requests.
_observer: "BankAgent | None" = None
_OBSERVER_MAX_HISTORY = 40  # 20 user + 20 assistant messages


def _get_observer() -> "BankAgent":
    """Return the module-level Observer singleton, creating it on first call."""
    global _observer
    if _observer is None:
        import anthropic
        from agents.narrator.observer import create_observer
        if not os.environ.get("ANTHROPIC_API_KEY"):
            try:
                from dotenv import load_dotenv
                load_dotenv(Path(__file__).parent.parent / ".env")
            except ImportError:
                pass
        _observer = create_observer(anthropic.Anthropic())
        log.info("observer.singleton_created")
    return _observer


@router.post("/chat")
async def observer_chat(body: dict) -> dict:
    """
    Ask the Observer a question about the simulation.

    Body:
        {
            "question":   "What just happened with the VaR limit?",
            "meeting_id": "uuid",   // optional — loads recent turns as context
        }

    Returns:
        {"answer": "...", "agent": "The Observer", "title": "Independent Narrator"}
    """
    question = (body.get("question") or "").strip()
    meeting_id = (body.get("meeting_id") or "").strip()

    if not question:
        raise HTTPException(status_code=422, detail="question is required")

    # Load recent transcript context from SQLite if a meeting is referenced
    context_block = ""
    if meeting_id:
        try:
            from api.meeting_store import store
            turns = store.get_turns(meeting_id, limit=10)
            if turns:
                lines = [
                    f"{t['agent']} ({t['title']}):\n{t['text']}"
                    for t in turns
                ]
                context_block = (
                    "RECENT BOARDROOM DISCUSSION:\n"
                    + "\n\n".join(lines)
                    + "\n\n" + "─" * 60 + "\n"
                )
        except Exception as exc:
            log.warning("observer.context_load_failed", meeting_id=meeting_id, error=str(exc))

    prompt = (
        context_block
        + f"A viewer asks: {question}\n\n"
        "Answer as the Observer — explain what's happening in accessible, engaging terms. "
        "Connect it to the broader banking context, name the tensions at play, and use "
        "analogies where helpful. Be concise (150–300 words)."
    )

    def _ask() -> str:
        agent = _get_observer()
        answer = agent.speak(prompt, max_tokens=600)
        # Trim history to prevent context window overflow
        if len(agent.history) > _OBSERVER_MAX_HISTORY:
            agent.history = agent.history[-_OBSERVER_MAX_HISTORY:]
        return answer

    loop = asyncio.get_running_loop()
    try:
        answer = await loop.run_in_executor(None, _ask)
    except Exception as exc:
        log.error("observer.chat_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Observer unavailable: {exc}")

    log.info("observer.chat_completed", question_len=len(question), answer_len=len(answer))
    return {
        "answer": answer,
        "agent":  "The Observer",
        "title":  "Independent Narrator",
    }
