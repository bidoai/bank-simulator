"""
FastAPI routes for the Boardroom interface.

Mounted by api/main.py with prefix="/api", producing:

  GET  /api/boardroom/meetings          — list of all past meetings (from SQLite)
  GET  /api/boardroom/meetings/{id}     — full transcript of a past meeting
  GET  /api/boardroom/history           — in-memory history of current session
  POST /api/boardroom/new-meeting       — create a meeting record (no agents started)
  POST /api/boardroom/start             — start a live meeting (real agents via orchestrator)
  POST /api/boardroom/inject-turn       — inject a completed agent turn (Claude Code mode)
  POST /api/boardroom/inject            — inject a user question as a system message

WebSocket /ws/boardroom is handled by api/main.py and delegates to the broadcaster.
"""
from __future__ import annotations

import asyncio
import uuid as _uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks

from api.boardroom_broadcaster import broadcaster
from api.meeting_store import store as meeting_store
from api.meeting_orchestrator import DEFAULT_AGENTS, _AGENT_REGISTRY, run_live_meeting

router = APIRouter(prefix="/boardroom", tags=["boardroom"])

# ── Mode flag ──────────────────────────────────────────────────────────────────
# "claude_code" → questions/meetings are queued for the assistant to answer
# "live_api"    → meetings are run directly via Anthropic API (requires credits)
_MODE: str = "claude_code"

# ── Pending queue (in-memory) ──────────────────────────────────────────────────
# Items: {id, type: "meeting"|"question", status: "pending"|"done", ...data}
_pending_queue: list[dict] = []


def _enqueue(item_type: str, data: dict) -> str:
    item_id = str(_uuid.uuid4())
    _pending_queue.append({"id": item_id, "type": item_type, "status": "pending", **data})
    return item_id


# ── Mode config endpoints ──────────────────────────────────────────────────────

@router.get("/config")
async def get_config() -> dict:
    return {"mode": _MODE}


@router.post("/config")
async def set_config(body: dict) -> dict:
    global _MODE
    mode = (body.get("mode") or "").strip()
    if mode not in ("claude_code", "live_api"):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="mode must be 'claude_code' or 'live_api'")
    _MODE = mode
    return {"mode": _MODE}


# ── Queue endpoints (for Claude Code polling) ──────────────────────────────────

@router.get("/queue")
async def get_queue() -> list[dict]:
    """Return all pending queue items — polled by Claude Code mode."""
    return [item for item in _pending_queue if item["status"] == "pending"]


@router.post("/queue/{item_id}/done")
async def mark_queue_done(item_id: str) -> dict:
    """Mark a queue item as handled."""
    for item in _pending_queue:
        if item["id"] == item_id:
            item["status"] = "done"
            pending = sum(1 for i in _pending_queue if i["status"] == "pending")
            await broadcaster.broadcast_queue_update(pending)
            return {"status": "ok", "id": item_id}
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Queue item not found")


# ── Past meetings ──────────────────────────────────────────────────────────────

@router.get("/meetings")
async def list_meetings() -> list[dict]:
    """Return all past board sessions from the persistent store."""
    meetings = meeting_store.list_meetings(limit=100)
    # Enrich with participant_count for UI compatibility
    for m in meetings:
        m["participant_count"] = len(m.get("agent_names") or [])
        m["date"] = m.get("started_at", "")
        m["title"] = m.get("title", "Untitled Session")
    return meetings


@router.get("/meetings/{meeting_id}")
async def get_meeting_transcript(meeting_id: str) -> dict:
    """Return the full turn-by-turn transcript of a specific meeting."""
    meeting = meeting_store.get_meeting(meeting_id)
    if not meeting:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Meeting not found")
    turns = meeting_store.get_turns(meeting_id)
    return {"meeting": meeting, "turns": turns}


# ── Live session state ─────────────────────────────────────────────────────────

@router.get("/history")
async def get_history() -> list[dict]:
    """Return the in-memory conversation history for the current live session."""
    return list(broadcaster._history)


# ── Start a meeting ────────────────────────────────────────────────────────────

@router.post("/start")
async def start_meeting(body: dict = None, background_tasks: BackgroundTasks = None) -> dict:
    """
    Start a live board meeting.

    Body (all optional):
        {
            "topic":  "The topic for discussion",
            "agents": ["Alexandra Chen", "Dr. Priya Nair", ...]   // subset of available agents
            "title":  "Session display title"
        }

    Returns immediately with meeting_id; meeting streams via WebSocket.
    """
    body = body or {}
    topic = (body.get("topic") or "").strip() or "Strategic review — open agenda"
    agent_names = body.get("agents") or DEFAULT_AGENTS
    title = (body.get("title") or "").strip() or _auto_title(topic)

    # Create meeting record immediately so UI can reference it
    meeting_id = meeting_store.create_meeting(
        title=title,
        topic=topic,
        agent_names=agent_names,
    )

    if _MODE == "claude_code":
        # Queue for the assistant to generate agent turns in-chat
        _enqueue("meeting", {
            "meeting_id": meeting_id,
            "topic":      topic,
            "title":      title,
            "agents":     agent_names,
        })
        pending = sum(1 for i in _pending_queue if i["status"] == "pending")
        await broadcaster.broadcast_queue_update(pending)
        await broadcaster.broadcast_system(
            f'[Claude Code] Meeting queued: "{title}" — waiting for agent responses…'
        )
        return {
            "status":     "queued",
            "meeting_id": meeting_id,
            "title":      title,
            "topic":      topic,
            "agents":     agent_names,
            "mode":       "claude_code",
        }

    # Live API mode — kick off real agent calls in the background
    background_tasks.add_task(
        _run_meeting_task,
        topic=topic,
        agent_names=agent_names,
        meeting_id=meeting_id,
    )

    return {
        "status":     "started",
        "meeting_id": meeting_id,
        "title":      title,
        "topic":      topic,
        "agents":     agent_names,
        "mode":       "live_api",
    }


async def _run_meeting_task(topic: str, agent_names: list[str], meeting_id: str) -> None:
    """Background task wrapper — catches top-level exceptions."""
    try:
        await run_live_meeting(
            topic=topic,
            agent_names=agent_names,
            meeting_id=meeting_id,
            broadcaster=broadcaster,
            store=meeting_store,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("meeting_task.failed", exc_info=exc)
        try:
            await broadcaster.broadcast_system(f"Meeting task failed: {exc}")
            meeting_store.complete_meeting(meeting_id, status="error")
        except Exception:
            pass


# ── Claude Code mode ──────────────────────────────────────────────────────────

@router.post("/new-meeting")
async def new_meeting(body: dict = None) -> dict:
    """
    Create a meeting record without starting any agent processes.
    Used by Claude Code mode: I create the meeting, then inject turns one by one.

    Body:
        {
            "topic":  "Discussion topic",
            "title":  "Optional display title",
            "agents": ["Alexandra Chen", ...]
        }
    """
    body = body or {}
    topic = (body.get("topic") or "").strip() or "Open agenda"
    agent_names = body.get("agents") or DEFAULT_AGENTS
    title = (body.get("title") or "").strip() or _auto_title(topic)

    meeting_id = meeting_store.create_meeting(
        title=title,
        topic=topic,
        agent_names=agent_names,
    )
    await broadcaster.broadcast_system(
        f'Meeting opened: "{title}"'
    )
    return {
        "status":     "created",
        "meeting_id": meeting_id,
        "title":      title,
        "topic":      topic,
        "agents":     agent_names,
    }


@router.post("/inject-turn")
async def inject_turn(body: dict) -> dict:
    """
    Inject a completed agent turn into the active meeting.

    Used by Claude Code mode: after generating a response in-character,
    call this endpoint to broadcast + persist it.

    Body:
        {
            "meeting_id":  "uuid",
            "agent_name":  "Alexandra Chen",
            "agent_title": "Chief Executive Officer",
            "text":        "Full response text…",
            "color":       "#e3b341",   // optional, looked up from registry if absent
            "stream":      true         // optional, default true — simulates token streaming
        }
    """
    meeting_id  = body.get("meeting_id", "")
    agent_name  = (body.get("agent_name") or "").strip()
    agent_title = (body.get("agent_title") or "").strip()
    text        = (body.get("text") or "").strip()
    do_stream   = body.get("stream", True)

    if not agent_name or not text:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="agent_name and text are required")

    if agent_name not in _AGENT_REGISTRY:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"Unknown agent: {agent_name!r}. Valid: {sorted(_AGENT_REGISTRY)}",
        )

    # Resolve color from registry
    color = body.get("color") or _AGENT_REGISTRY[agent_name]["color"]

    # Signal turn start (shows typing indicator in UI)
    await broadcaster.broadcast_turn_start(agent_name, agent_title, color)

    if do_stream:
        # Simulate token streaming: emit ~8-word chunks with a short delay
        # so the UI looks live rather than popping in all at once
        words = text.split()
        chunk_size = 8
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size])
            # Add trailing space between chunks (except the last)
            if i + chunk_size < len(words):
                chunk += " "
            await broadcaster.broadcast_token(agent_name, chunk, color)
            await asyncio.sleep(0.06)

    await broadcaster.broadcast_turn_end(agent_name)

    # Broadcast the finalised message block
    await broadcaster.broadcast_agent_turn(agent_name, agent_title, text, color)

    # Persist to SQLite
    if meeting_id:
        meeting_store.add_turn(meeting_id, agent_name, agent_title, text, color)

    return {"status": "ok", "agent": agent_name, "chars": len(text)}


# ── Worker system-message (never queued) ──────────────────────────────────────

@router.post("/system")
async def system_message(body: dict) -> dict:
    """Broadcast a system message from the worker — bypasses the queue."""
    text = (body.get("text") or "").strip()
    if text:
        await broadcaster.broadcast_system(text)
    return {"status": "ok"}


# ── Inject a question ──────────────────────────────────────────────────────────

@router.post("/inject")
async def inject_message(body: dict) -> dict:
    """
    Inject a user question into the active session.

    In claude_code mode the question is also queued so the assistant can
    respond in-character via inject-turn.  In live_api mode it is broadcast
    as context only (real agents don't read it yet).
    """
    text       = (body.get("text") or "").strip()
    meeting_id = (body.get("meeting_id") or "").strip()

    if not text:
        return {"status": "received"}

    # Always broadcast so the question appears in the UI immediately
    await broadcaster.broadcast_system(f'[Board asked]: "{text}"')

    if _MODE == "claude_code":
        item_id = _enqueue("question", {"text": text, "meeting_id": meeting_id})
        pending = sum(1 for i in _pending_queue if i["status"] == "pending")
        await broadcaster.broadcast_queue_update(pending)
        return {"status": "queued", "item_id": item_id}

    return {"status": "received"}


# ── Available agents (for UI picker) ──────────────────────────────────────────

@router.get("/agents")
async def list_agents() -> list[dict]:
    """Return the full roster of available agents for meeting configuration."""
    from api.meeting_orchestrator import _AGENT_REGISTRY
    return [
        {
            "name":          name,
            "title":         meta["title"],
            "color":         meta["color"],
            "voice_profile": meta.get("voice_profile"),
        }
        for name, meta in _AGENT_REGISTRY.items()
    ]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _auto_title(topic: str) -> str:
    """Generate a short session title from the topic string."""
    words = topic.split()
    if len(words) <= 6:
        return topic.title()
    return " ".join(words[:6]).title() + "…"
