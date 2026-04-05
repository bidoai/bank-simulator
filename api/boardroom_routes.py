"""
FastAPI routes for the Boardroom interface.

Mounted by api/main.py with prefix="/api", producing:

  GET  /api/boardroom/meetings          — list of all past meetings (from SQLite)
  GET  /api/boardroom/meetings/{id}     — full transcript of a past meeting
  GET  /api/boardroom/history           — in-memory history of current session
  POST /api/boardroom/start             — start a live meeting (real agents via orchestrator)
  POST /api/boardroom/inject            — inject a user question as a system message

WebSocket /ws/boardroom is handled by api/main.py and delegates to the broadcaster.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from api.boardroom_broadcaster import broadcaster
from api.meeting_store import store as meeting_store
from api.meeting_orchestrator import DEFAULT_AGENTS, _AGENT_REGISTRY, run_live_meeting

router = APIRouter(prefix="/boardroom", tags=["boardroom"])


# ── Past meetings ──────────────────────────────────────────────────────────────

@router.get("/meetings")
async def list_meetings() -> list[dict]:
    """Return all past board sessions from the persistent store."""
    meetings = meeting_store.list_meetings(limit=100)
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


@router.get("/meetings/{meeting_id}/export")
async def export_meeting_transcript(meeting_id: str):
    """Return a plain-text transcript for download."""
    from fastapi import HTTPException
    from fastapi.responses import Response
    import datetime

    meeting = meeting_store.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    turns = meeting_store.get_turns(meeting_id)

    lines = []
    for turn in turns:
        ts = turn.get("timestamp") or ""
        try:
            dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M")
        except Exception:
            time_str = ts[:5] if ts else "00:00"
        agent = turn.get("agent") or "Unknown"
        text  = turn.get("text") or ""
        lines.append(f"[{time_str}] {agent}: {text}")

    body = "\n".join(lines)
    filename = f"meeting_{meeting_id}.txt"
    return Response(
        content=body,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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

    meeting_id = meeting_store.create_meeting(
        title=title,
        topic=topic,
        agent_names=agent_names,
    )

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


# ── Archive an inline discussion ──────────────────────────────────────────────

@router.post("/archive")
async def archive_inline_discussion(body: dict) -> dict:
    """
    Persist an in-conversation (inline) discussion to the meetings database.

    Body:
        {
            "title":  "Session display title",
            "topic":  "What was discussed",
            "turns":  [
                {
                    "agent":  "Dr. Priya Nair",
                    "title":  "Chief Risk Officer",
                    "text":   "Full response text…",
                    "color":  "#ff9800"          // optional — looked up from registry if omitted
                },
                …
            ]
        }

    The endpoint resolves missing colors from the agent registry automatically.
    Returns { "meeting_id": "...", "status": "archived", "turn_count": N }.
    """
    title  = (body.get("title") or "").strip() or "Inline Discussion"
    topic  = (body.get("topic") or "").strip() or ""
    turns  = body.get("turns") or []

    if not turns:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="turns must be a non-empty list")

    # Resolve agent colors from the registry for any turn that omits color.
    color_map = {name: meta["color"] for name, meta in _AGENT_REGISTRY.items()}
    resolved_turns = []
    for t in turns:
        agent = (t.get("agent") or "").strip()
        resolved_turns.append({
            "agent":  agent,
            "title":  (t.get("title") or "").strip(),
            "text":   (t.get("text") or "").strip(),
            "color":  t.get("color") or color_map.get(agent, "#c9d1d9"),
        })

    meeting_id = meeting_store.archive_meeting(
        title=title,
        topic=topic,
        turns=resolved_turns,
    )

    return {
        "status":     "archived",
        "meeting_id": meeting_id,
        "turn_count": len(resolved_turns),
    }


# ── Worker system-message ──────────────────────────────────────────────────────

@router.post("/system")
async def system_message(body: dict) -> dict:
    """Broadcast a system message."""
    text = (body.get("text") or "").strip()
    if text:
        await broadcaster.broadcast_system(text)
    return {"status": "ok"}


# ── Inject a question ──────────────────────────────────────────────────────────

@router.post("/inject")
async def inject_message(body: dict) -> dict:
    """Inject a user question into the active session — appears as a system message."""
    text = (body.get("text") or "").strip()
    if text:
        await broadcaster.broadcast_system(f'[Board asked]: "{text}"')
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
