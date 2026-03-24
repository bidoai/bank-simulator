"""
Boardroom Worker — autonomous background agent runner.

Polls /api/boardroom/queue for pending items and handles them via the
Anthropic API, completely independently of any active Claude Code session.

Usage:
    python3 -m api.boardroom_worker
    python3 -m api.boardroom_worker --poll-interval 5
    python3 -m api.boardroom_worker --model claude-sonnet-4-6

Requires ANTHROPIC_API_KEY in the environment or a .env file at the project root.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("boardroom_worker")

DEFAULT_BASE_URL      = "http://localhost:8000/api/boardroom"
DEFAULT_POLL_INTERVAL = 5    # seconds between queue checks
DEFAULT_MODEL         = "claude-opus-4-6"
DEFAULT_MAX_TOKENS    = 1024


# ── Agent helpers ──────────────────────────────────────────────────────────────

def _load_agent_meta(agent_name: str):
    """Return (system_prompt, title, color) for a named agent."""
    from api.meeting_orchestrator import _AGENT_REGISTRY, _load_agent
    meta = _AGENT_REGISTRY.get(agent_name)
    if not meta:
        raise ValueError(f"Unknown agent: {agent_name!r}")
    agent = _load_agent(agent_name, client=None)
    return agent.system_prompt, meta["title"], meta["color"]


def _build_prompt(topic: str, transcript: list[dict], agent_name: str) -> str:
    from api.meeting_orchestrator import _build_context_prompt
    return _build_context_prompt(topic, transcript, agent_name)


# ── Worker ─────────────────────────────────────────────────────────────────────

class BoardroomWorker:
    def __init__(self, base_url: str, poll_interval: int, model: str) -> None:
        self.base_url      = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self.model         = model
        self._http: httpx.AsyncClient | None = None
        self._anthropic = None

    # ── Startup ───────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._init_anthropic()
        async with httpx.AsyncClient(timeout=180) as http:
            self._http = http
            log.info("Worker started — polling %s every %ds (model=%s)",
                     self.base_url, self.poll_interval, self.model)
            await self._loop()

    def _init_anthropic(self) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            try:
                from dotenv import load_dotenv
                load_dotenv(Path(__file__).parent.parent / ".env")
            except ImportError:
                pass
        import anthropic
        self._anthropic = anthropic.Anthropic()
        log.info("Anthropic client ready")

    # ── Polling loop ──────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as exc:
                log.error("tick error: %s", exc, exc_info=True)
            await asyncio.sleep(self.poll_interval)

    async def _tick(self) -> None:
        res = await self._http.get(f"{self.base_url}/queue")
        res.raise_for_status()
        for item in res.json():
            if item.get("status") == "pending":
                await self._handle(item)

    # ── Item dispatch ─────────────────────────────────────────────────────────

    async def _handle(self, item: dict) -> None:
        log.info("handling %s item %s", item["type"], item["id"])
        try:
            if item["type"] == "meeting":
                await self._run_meeting(item)
            elif item["type"] == "question":
                await self._run_question(item)
            else:
                log.warning("unknown item type: %s", item["type"])
        except Exception as exc:
            log.error("item %s failed: %s", item["id"], exc, exc_info=True)
            await self._system(f"[Worker error]: {exc}")
        finally:
            await self._mark_done(item["id"])

    # ── Meeting ───────────────────────────────────────────────────────────────

    async def _run_meeting(self, item: dict) -> None:
        meeting_id  = item["meeting_id"]
        topic       = item["topic"]
        agent_names = item["agents"]

        await self._system(f'Boardroom session started — topic: "{topic}"')

        transcript: list[dict] = []

        for agent_name in agent_names:
            try:
                system_prompt, title, color = _load_agent_meta(agent_name)
            except ValueError as exc:
                log.warning("skipping: %s", exc)
                continue

            prompt    = _build_prompt(topic, transcript, agent_name)
            full_text = await self._generate(system_prompt, prompt, agent_name)

            await self._inject_turn(meeting_id, agent_name, title, full_text, color)

            transcript.append({
                "agent": agent_name,
                "title": title,
                "text":  full_text,
                "color": color,
            })

            await asyncio.sleep(0.5)

        # Mark meeting complete in the store
        try:
            from api.meeting_store import store
            store.complete_meeting(meeting_id, status="completed")
        except Exception as exc:
            log.warning("could not complete meeting in store: %s", exc)

        await self._system(
            f"Session concluded — {len(transcript)} turns. "
            "Transcript saved and available in session history."
        )
        log.info("meeting %s complete (%d turns)", meeting_id, len(transcript))

    # ── Question ──────────────────────────────────────────────────────────────

    async def _run_question(self, item: dict) -> None:
        question   = item["text"]
        meeting_id = item.get("meeting_id", "")

        # Load meeting context if available
        agent_names = []
        transcript  = []
        topic       = question

        if meeting_id:
            try:
                res  = await self._http.get(f"{self.base_url}/meetings/{meeting_id}")
                data = res.json()
                mtg  = data.get("meeting", {})
                agent_names = mtg.get("agent_names", [])
                topic       = mtg.get("topic", question)
                transcript  = [
                    {"agent": t["agent"], "title": t["title"],
                     "text": t["text"], "color": t["color"]}
                    for t in data.get("turns", [])
                ]
            except Exception as exc:
                log.warning("could not load meeting %s: %s", meeting_id, exc)

        if not agent_names:
            from api.meeting_orchestrator import DEFAULT_AGENTS
            agent_names = DEFAULT_AGENTS

        # Append the question to transcript so agents can respond to it
        transcript.append({
            "agent": "Board",
            "title": "Question",
            "text":  question,
            "color": "#ffffff",
        })

        for agent_name in agent_names:
            try:
                system_prompt, title, color = _load_agent_meta(agent_name)
            except ValueError:
                continue

            prompt    = _build_prompt(topic, transcript, agent_name)
            full_text = await self._generate(system_prompt, prompt, agent_name)

            await self._inject_turn(meeting_id, agent_name, title, full_text, color)

            transcript.append({
                "agent": agent_name,
                "title": title,
                "text":  full_text,
                "color": color,
            })

            await asyncio.sleep(0.5)

    # ── Anthropic API call ────────────────────────────────────────────────────

    async def _generate(self, system_prompt: str, user_prompt: str, agent_name: str) -> str:
        log.info("generating: %s", agent_name)
        loop = asyncio.get_event_loop()

        def _call() -> str:
            with self._anthropic.messages.stream(
                model=self.model,
                max_tokens=DEFAULT_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                return stream.get_final_message().content[0].text

        text = await loop.run_in_executor(None, _call)
        log.info("  → %d chars", len(text))
        return text

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    async def _inject_turn(
        self,
        meeting_id: str,
        agent_name: str,
        agent_title: str,
        text: str,
        color: str,
    ) -> None:
        res = await self._http.post(
            f"{self.base_url}/inject-turn",
            json={
                "meeting_id":  meeting_id,
                "agent_name":  agent_name,
                "agent_title": agent_title,
                "text":        text,
                "color":       color,
                "stream":      True,
            },
        )
        res.raise_for_status()

    async def _system(self, message: str) -> None:
        try:
            await self._http.post(
                f"{self.base_url}/system",
                json={"text": message},
            )
        except Exception:
            pass

    async def _mark_done(self, item_id: str) -> None:
        try:
            await self._http.post(f"{self.base_url}/queue/{item_id}/done")
        except Exception as exc:
            log.warning("could not mark %s done: %s", item_id, exc)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Apex Boardroom background worker")
    parser.add_argument("--base-url",      default=DEFAULT_BASE_URL,
                        help="Boardroom API base URL")
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL,
                        help="Seconds between queue checks (default: 5)")
    parser.add_argument("--model",         default=DEFAULT_MODEL,
                        help="Anthropic model ID (default: claude-opus-4-6)")
    args = parser.parse_args()

    worker = BoardroomWorker(
        base_url=args.base_url,
        poll_interval=args.poll_interval,
        model=args.model,
    )
    asyncio.run(worker.start())


if __name__ == "__main__":
    main()
