"""
Base agent class — all bank agents inherit from this.

Each agent is a Claude Opus 4.6 instance with a specialized system prompt.
Agents maintain their own conversation history and can be addressed directly
or participate in multi-agent discussions through the Boardroom orchestrator.

The architecture mirrors how LLM agents work in production systems:
- A persistent system prompt defines identity, expertise, and behavior
- A message history maintains conversational context
- Streaming is used for long responses (avoids HTTP timeouts)
- Tools can be injected per-agent to give them access to live data
"""

from __future__ import annotations
import anthropic
from typing import Optional, AsyncIterator
import structlog

log = structlog.get_logger()


class BankAgent:
    """
    Base class for all AI agents in the bank simulator.

    Uses Claude Opus 4.6 with adaptive thinking — the model decides
    how deeply to reason based on question complexity.
    """

    MODEL = "claude-opus-4-6"

    def __init__(
        self,
        name: str,
        title: str,
        system_prompt: str,
        client: Optional[anthropic.Anthropic] = None,
    ):
        self.name = name
        self.title = title
        self.system_prompt = system_prompt
        self.client = client or anthropic.Anthropic()
        self.history: list[dict] = []

    def speak(
        self,
        message: str,
        temperature: float = 1.0,
        max_tokens: int = 2048,
        use_thinking: bool = False,
    ) -> str:
        """
        Send a message to the agent and get a response.
        Maintains conversation history for multi-turn exchanges.
        """
        self.history.append({"role": "user", "content": message})

        kwargs: dict = dict(
            model=self.MODEL,
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=self.history,
        )
        if use_thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        response = self.client.messages.create(**kwargs)

        # Collect text blocks (thinking blocks are internal, not shown in transcript)
        reply = "\n".join(
            block.text for block in response.content if block.type == "text"
        )

        self.history.append({"role": "assistant", "content": reply})
        log.debug("agent.spoke", agent=self.name, tokens=response.usage.output_tokens)
        return reply

    def stream_speak(
        self,
        message: str,
        max_tokens: int = 2048,
        use_thinking: bool = False,
    ) -> str:
        """
        Stream a response — used for long-form answers.
        Returns the complete text after streaming.
        """
        self.history.append({"role": "user", "content": message})

        kwargs: dict = dict(
            model=self.MODEL,
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=self.history,
        )
        if use_thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        with self.client.messages.stream(**kwargs) as stream:
            reply = stream.get_final_message()

        text = "\n".join(
            block.text for block in reply.content if block.type == "text"
        )
        self.history.append({"role": "assistant", "content": text})
        return text

    def reset_history(self) -> None:
        """Clear conversation history — start a fresh session."""
        self.history = []

    def inject_context(self, context: str) -> None:
        """
        Inject real-time data into the conversation as a system-level observation.
        Used to give agents live market data, risk metrics, P&L, etc.
        """
        self.history.append({
            "role": "user",
            "content": f"[SYSTEM DATA FEED]\n{context}"
        })
        # Silent acknowledgment
        self.history.append({
            "role": "assistant",
            "content": "[Data received and integrated into analysis.]"
        })

    def __repr__(self) -> str:
        return f"<BankAgent {self.name} ({self.title})>"
