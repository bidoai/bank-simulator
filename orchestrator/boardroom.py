"""
Boardroom Orchestrator — The multi-agent discussion engine.

The Boardroom facilitates structured conversations between agents. It handles:
- Turn-by-turn dialogue with configurable speaker sequences
- Cross-agent context injection (agents can "hear" what others said)
- Observer narration interspersed throughout
- Rich terminal output for the learning experience
- Full transcript export

This is modeled on how real strategy sessions work: an agenda, a facilitator,
specific experts called on in sequence, open discussion, and a chair who
synthesizes decisions.
"""

from __future__ import annotations
import os
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.markdown import Markdown
import structlog

from agents.base_agent import BankAgent

log = structlog.get_logger()
console = Console(width=120)


# Agent color/style mapping for visual distinction in the terminal
AGENT_STYLES: dict[str, dict] = {
    # Executive
    "Alexandra Chen":      {"color": "bold gold1",       "emoji": "👑"},
    "Marcus Rivera":       {"color": "bold cyan",         "emoji": "⚙️ "},
    "Diana Osei":          {"color": "bold green4",       "emoji": "💰"},
    "Dr. Priya Nair":      {"color": "bold red",          "emoji": "🛡️ "},
    "Robert Adeyemi":      {"color": "bold orange3",      "emoji": "🏦"},
    "Amara Diallo":        {"color": "bold deep_sky_blue1","emoji": "💧"},
    # Markets
    "James Okafor":        {"color": "bold green",        "emoji": "📈"},
    "Trading Desk":        {"color": "bold bright_green", "emoji": "🖥️ "},
    "Dr. Yuki Tanaka":     {"color": "bold magenta",      "emoji": "🔬"},
    # Investment Banking
    "Sophie Laurent":      {"color": "bold steel_blue1",  "emoji": "🤝"},
    # Wealth
    "Isabella Rossi":      {"color": "bold plum2",        "emoji": "💎"},
    # Compliance & Ops
    "Sarah Mitchell":      {"color": "bold yellow",       "emoji": "⚖️ "},
    "Chen Wei":            {"color": "bold turquoise2",   "emoji": "⚡"},
    # Technology
    "Dr. Fatima Al-Rashid":{"color": "bold violet",       "emoji": "🗄️ "},
    "Ivan Petrov":         {"color": "bold red3",         "emoji": "🔐"},
    # Risk Desk
    "Dr. Marcus Webb":     {"color": "bold red3",         "emoji": "📊"},
    "Elena Vasquez":       {"color": "bold dark_orange",  "emoji": "🏛️ "},
    "Dr. Rebecca Chen":    {"color": "bold orchid",       "emoji": "🔍"},
    "Thomas Nakamura":     {"color": "bold sky_blue1",    "emoji": "💧"},
    # Narrator
    "The Observer":        {"color": "italic dim white",  "emoji": "🔭"},
}

DEFAULT_STYLE = {"color": "white", "emoji": "🏦"}


class Turn:
    """A single turn in the boardroom discussion."""
    def __init__(self, speaker: BankAgent, prompt: str, response: str, timestamp: datetime):
        self.speaker = speaker
        self.prompt = prompt
        self.response = response
        self.timestamp = timestamp


class Boardroom:
    """
    Multi-agent discussion facilitator.

    Manages a session where multiple agents interact around an agenda.
    The Observer can be called at any point to narrate what just happened.
    """

    def __init__(
        self,
        agents: dict[str, BankAgent],
        observer: Optional[BankAgent] = None,
        session_name: str = "Board Meeting",
    ):
        self.agents = agents          # name → agent
        self.observer = observer
        self.session_name = session_name
        self.transcript: list[Turn] = []
        self.session_start = datetime.utcnow()

    def _render_speaker_panel(self, agent: BankAgent, content: str) -> None:
        """Render an agent's response as a styled panel."""
        style_info = AGENT_STYLES.get(agent.name, DEFAULT_STYLE)
        emoji = style_info["emoji"]
        color = style_info["color"]

        header = f"{emoji}  {agent.name}  ·  {agent.title}"
        console.print()
        console.print(Panel(
            Markdown(content),
            title=f"[{color}]{header}[/{color}]",
            border_style=color.replace("bold ", "").replace("italic ", "").replace("dim ", ""),
            padding=(1, 2),
        ))

    def _render_observer(self, content: str) -> None:
        """Render the observer's narration in a distinct style."""
        console.print()
        console.print(Panel(
            Markdown(content),
            title="[italic dim white]🔭  THE OBSERVER  ·  Independent Narrator[/italic dim white]",
            border_style="dim white",
            padding=(1, 2),
            subtitle="[dim]— for the reader —[/dim]",
        ))

    def _render_section_header(self, title: str) -> None:
        console.print()
        console.print(Rule(f"[bold white]{title}[/bold white]", style="dim white"))

    def call_agent(
        self,
        agent_name: str,
        prompt: str,
        show_prompt: bool = False,
        max_tokens: int = 1500,
        use_thinking: bool = False,
    ) -> str:
        """
        Prompt a specific agent and render their response.
        Returns the response text for use in subsequent prompts.
        """
        agent = self.agents.get(agent_name)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_name}. Available: {list(self.agents.keys())}")

        if show_prompt:
            console.print(f"\n[dim italic]Facilitator: {prompt}[/dim italic]")

        response = agent.speak(prompt, max_tokens=max_tokens, use_thinking=use_thinking)

        self._render_speaker_panel(agent, response)
        self.transcript.append(Turn(agent, prompt, response, datetime.utcnow()))

        log.info("boardroom.turn", agent=agent_name, tokens=len(response.split()))
        return response

    def narrate(
        self,
        context: str,
        max_tokens: int = 800,
    ) -> str:
        """
        Ask the Observer to narrate the current moment.
        Pass recent discussion context so the Observer can comment on it.
        """
        if not self.observer:
            return ""
        response = self.observer.speak(context, max_tokens=max_tokens)
        self._render_observer(response)
        return response

    def cross_prompt(
        self,
        responder_name: str,
        questioner_name: str,
        question: str,
        include_recent_context: bool = True,
        max_tokens: int = 1200,
    ) -> str:
        """
        One agent responds to a question/comment from another agent.
        The questioner's recent response is injected as context.
        """
        questioner = self.agents.get(questioner_name)
        responder = self.agents.get(responder_name)

        if not questioner or not responder:
            raise ValueError(f"Unknown agent(s): {questioner_name}, {responder_name}")

        # Build the prompt with attribution
        full_prompt = f"{questioner.name} ({questioner.title}) says:\n\n{question}\n\nPlease respond directly to this."

        return self.call_agent(responder_name, full_prompt, max_tokens=max_tokens)

    def round_table(
        self,
        topic: str,
        speaker_names: list[str],
        prompt_template: str = "Share your perspective on: {topic}",
        narrate_after: bool = True,
        max_tokens_each: int = 1000,
    ) -> dict[str, str]:
        """
        Ask multiple agents the same question in sequence.
        Returns dict of agent_name → response.
        """
        self._render_section_header(f"ROUND TABLE: {topic.upper()}")
        responses = {}

        for name in speaker_names:
            prompt = prompt_template.format(topic=topic)
            response = self.call_agent(name, prompt, max_tokens=max_tokens_each)
            responses[name] = response

        if narrate_after and self.observer:
            summary = "\n\n".join(
                f"**{name}** said:\n{resp[:500]}..."
                for name, resp in responses.items()
            )
            self.narrate(
                f"The team just had a round table on: '{topic}'. Here's what each said:\n\n{summary}\n\n"
                "Please narrate what happened, what tensions emerged, and what this reveals about how a bank works."
            )

        return responses

    def open_session(self) -> None:
        """Print the session header."""
        console.print()
        console.print(Panel(
            f"[bold white]{self.session_name}[/bold white]\n"
            f"[dim]{self.session_start.strftime('%A, %B %d, %Y  %H:%M UTC')}[/dim]\n\n"
            f"[dim italic]Apex Global Bank — Executive Leadership Session[/dim italic]",
            border_style="gold1",
            padding=(1, 4),
        ))

    def close_session(self) -> None:
        """Print session summary."""
        elapsed = (datetime.utcnow() - self.session_start).seconds
        console.print()
        console.print(Panel(
            f"[dim]Session concluded · {len(self.transcript)} exchanges · {elapsed}s elapsed[/dim]",
            border_style="dim",
        ))

    def export_transcript(self, path: Optional[str] = None) -> str:
        """Export the full session transcript as Markdown."""
        lines = [
            f"# {self.session_name}",
            f"*{self.session_start.strftime('%Y-%m-%d %H:%M UTC')}*",
            "",
        ]
        for turn in self.transcript:
            lines.append(f"## {turn.speaker.name} — {turn.speaker.title}")
            lines.append(f"*{turn.timestamp.strftime('%H:%M:%S')}*")
            lines.append("")
            lines.append(turn.response)
            lines.append("")
            lines.append("---")
            lines.append("")

        text = "\n".join(lines)

        if path:
            with open(path, "w") as f:
                f.write(text)
            console.print(f"\n[dim]Transcript saved to {path}[/dim]")

        return text
