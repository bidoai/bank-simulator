"""
Apex Global Bank Simulator — Entry Point

Usage:
    python main.py                    # Run the founding board meeting
    python main.py --scenario stress  # Run a market stress scenario (coming soon)
    python main.py --list-agents      # List all available agents

Requirements:
    pip install -r requirements.txt
    cp .env.example .env && edit .env with your ANTHROPIC_API_KEY
"""

import os
import sys
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import structlog

load_dotenv()

app = typer.Typer(help="Apex Global Bank — AI Agent Simulator")
console = Console(width=120)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(file=open(os.devnull, "w")),
)


AGENTS_TABLE = [
    # ── EXECUTIVE ──────────────────────────────────────────────────────────────────────────
    ("CEO",              "Alexandra Chen",    "Chief Executive Officer",           "Strategy, vision, capital allocation, AI leadership"),
    ("CTO",              "Marcus Rivera",     "Chief Technology Officer",          "Tech stack, latency, AI platform, engineering org"),
    ("CFO",              "Diana Osei",        "Chief Financial Officer",           "Balance sheet, P&L, capital allocation, ROTCE, investor relations"),
    ("CRO",              "Dr. Priya Nair",    "Chief Risk Officer",                "VaR, stress testing, limits, Basel III regulatory capital"),
    ("Chief Credit",     "Robert Adeyemi",    "Chief Credit Officer",              "Loan portfolio $1.8T, credit models, PD/LGD/EAD, ECL reserves"),
    ("Head of Treasury", "Amara Diallo",      "Global Head of Treasury & ALM",     "Liquidity (LCR/NSFR), funding, NIM, interest rate risk"),
    # ── MARKETS ────────────────────────────────────────────────────────────────────────────
    ("Lead Trader",      "James Okafor",      "Head of Global Markets Trading",    "Trading strategy, risk capital allocation, desk P&L $4.2B target"),
    ("Trading Desk",     "Trading Desk",      "Global Markets Trading Desk",       "Live order execution, book management, real-time Greek hedging"),
    ("Quant",            "Dr. Yuki Tanaka",   "Head of Quantitative Research",     "Pricing/risk models, alpha signals, ML strategies"),
    # ── INVESTMENT BANKING ─────────────────────────────────────────────────────────────────
    ("Head of IBD",      "Sophie Laurent",    "Head of Investment Banking",        "M&A advisory, ECM/DCM, leveraged finance, $8.4B fee target"),
    # ── WEALTH MANAGEMENT ──────────────────────────────────────────────────────────────────
    ("Head of Wealth",   "Isabella Rossi",    "Head of Wealth Management",         "UHNW private banking, $1.4T AUM, estate & tax planning"),
    # ── CONTROL & COMPLIANCE ───────────────────────────────────────────────────────────────
    ("Compliance",       "Sarah Mitchell",    "Chief Compliance Officer",          "AML/KYC, OFAC, Volcker Rule, MiFID II, three lines of defense"),
    # ── OPERATIONS ─────────────────────────────────────────────────────────────────────────
    ("Head of Ops",      "Chen Wei",          "Head of Global Operations",         "Settlement (T+2→T+1), clearing, custody, SWIFT, 97.3% STP rate"),
    # ── TECHNOLOGY ─────────────────────────────────────────────────────────────────────────
    ("CDO",              "Dr. Fatima Al-Rashid", "Chief Data Officer",             "Data governance, ML data pipelines, GDPR/BCBS239, feature store"),
    ("CISO",             "Ivan Petrov",       "Chief Information Security Officer","Zero trust, SOC 24/7, SWIFT controls, quantum-safe crypto"),
    # ── NARRATOR ───────────────────────────────────────────────────────────────────────────
    ("Observer",         "The Observer",      "Independent Narrator",              "Explains everything to the reader — the curtain puller"),
]


def print_agent_roster() -> None:
    table = Table(title="Current Agent Team", border_style="gold1", show_lines=True)
    table.add_column("Role Key", style="bold cyan", width=14)
    table.add_column("Name", style="white", width=20)
    table.add_column("Title", style="bold", width=34)
    table.add_column("Domain", style="dim", width=48)
    for row in AGENTS_TABLE:
        table.add_row(*row)
    console.print(table)

    NEXT_AGENTS = [
        ("Head of Consumer",  "Head of Consumer Banking",      "Retail deposits, mortgages, credit cards, branches, digital banking"),
        ("Head of Comms",     "Head of Commercial Banking",    "SME/mid-market lending, treasury management, trade finance"),
        ("Chief HR Officer",  "Chief Human Resources Officer", "Talent, compensation, culture, 280,000 employees"),
        ("Chief Legal",       "General Counsel",               "Litigation, regulatory legal, contracts, ISDA, entity structure"),
        ("Head of Research",  "Head of Global Research",       "Macro/equity/credit research; ratings; client distribution"),
        ("Head of Prime",     "Head of Prime Brokerage",       "Hedge fund financing, securities lending, margin, custody"),
        ("Chief Audit",       "Chief Internal Auditor",        "Third line of defense, SOX, regulatory examination liaison"),
        ("Head of Climate",   "Head of Sustainable Finance",   "ESG integration, climate risk, green bonds, TCFD reporting"),
    ]
    console.print()
    proposed = Table(title="Next Agents to Build", border_style="dim white", show_lines=True)
    proposed.add_column("Role", style="bold", width=18)
    proposed.add_column("Title", style="white", width=34)
    proposed.add_column("Domain", style="dim", width=56)
    for row in NEXT_AGENTS:
        proposed.add_row(*row)
    console.print(proposed)


@app.command()
def main(
    scenario: str = typer.Option("founding", help="Scenario: founding | stress (more coming)"),
    list_agents: bool = typer.Option(False, "--list-agents", help="Print agent roster and exit"),
    export: str = typer.Option("transcript.md", "--export", help="Path for transcript export"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the scenario plan without calling the API"),
):
    """
    Run the Apex Global Bank agent simulator.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key and not dry_run and not list_agents:
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        raise typer.Exit(1)

    console.print(Panel(
        "[bold gold1]APEX GLOBAL BANK[/bold gold1]\n"
        "[dim]AI Agent Simulator · Powered by Claude Opus 4.6[/dim]",
        border_style="gold1",
        padding=(1, 4),
    ))

    if list_agents:
        print_agent_roster()
        return

    if dry_run:
        console.print("\n[bold]DRY RUN — Scenario plan:[/bold]")
        console.print(f"  Scenario: [cyan]{scenario}[/cyan]")
        console.print(f"  Export:   [cyan]{export}[/cyan]")
        console.print("\n[bold]Agent roster:[/bold]")
        print_agent_roster()
        console.print("\n[dim]Run without --dry-run to execute with Claude Opus 4.6[/dim]")
        return

    if scenario == "founding":
        console.print(f"\n[dim]Running founding board meeting → {export}[/dim]\n")
        from scenarios.founding_board_meeting import run_founding_meeting
        run_founding_meeting(export_path=export)
    elif scenario == "stress":
        console.print("[yellow]Stress scenario coming soon. Run 'founding' for now.[/yellow]")
    else:
        console.print(f"[red]Unknown scenario: {scenario}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
