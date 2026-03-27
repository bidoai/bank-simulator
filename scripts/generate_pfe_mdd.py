"""
Generate the PFE / CCR Exposure Engine MDD (APEX-MDL-0014) as a LaTeX document.

Uses Dr. Yuki Tanaka (Head of Quantitative Research) as the primary author,
with a focused prompt that asks for the complete SR 11-7 model development
document covering netting, collateral, MPoR, PFE, EPE/ENE, and SA-CCR.

Output: model_docs/latex/mdd_pfe_ccr_v1.0.tex
"""

import os
import sys
from pathlib import Path

# ── project root on sys.path ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import anthropic
from agents.markets.quant_researcher import create_quant_researcher
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console(width=120)

# ── output path ───────────────────────────────────────────────────────────────
OUTPUT_DIR = ROOT / "model_docs" / "latex"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "mdd_pfe_ccr_v1.0.tex"

# ── prompt ────────────────────────────────────────────────────────────────────
PROMPT = """
You are writing the official Model Development Document (MDD) for the
PFE / CCR Exposure Engine at Apex Global Bank. This is APEX-MDL-0014,
Tier 1, the foundational simulation model that generates all exposure
profiles (PFE, EPE, ENE) used by CVA (APEX-MDL-0010), FVA (APEX-MDL-0011),
and MVA (APEX-MDL-0012).

Write the COMPLETE document as a LaTeX file. The document must be a
self-contained, compilable LaTeX file using the article class.

LATEX REQUIREMENTS:
- \\documentclass[11pt,a4paper]{article}
- Packages: geometry, amsmath, amssymb, booktabs, hyperref, xcolor,
  longtable, array, graphicx, fancyhdr, titlesec
- geometry: margin=2.5cm
- Color definitions: define apexblue as RGB(0,51,102) and apexgray as RGB(100,100,100)
- Header/footer with document title, classification, and page numbers
- All mathematical formulas in proper LaTeX math mode
- Tables using booktabs (\\toprule, \\midrule, \\bottomrule)
- Section numbering consistent with the other Apex MDDs (12 sections + appendix)
- Do NOT include \\begin{document}...\\end{document} wrapper — just the preamble
  and then the full document body including \\begin{document} and \\end{document}

DOCUMENT STRUCTURE (follow exactly):
1. DOCUMENT METADATA — tabular block with Model Name, ID (APEX-MDL-0014),
   Version 1.0, Status In Validation, Risk Tier Tier 1,
   Regulatory Framework (Basel III SA-CCR; IFRS 13; SR 11-7),
   Date March 2026, Business Owner James Okafor,
   Model Developer XVA Quant Team,
   MRO Review Pending Dr. Rebecca Chen,
   CRO Approval Pending Dr. Priya Nair.
   Include version history table: v0.1 Jan 2026 (initial netting framework),
   v0.8 Feb 2026 (collateral offset + SA-CCR), v1.0 Mar 2026 (production candidate).

2. EXECUTIVE SUMMARY — purpose (upstream simulation engine for all XVA models),
   outputs (PFE for credit limits, EPE/ENE for CVA/FVA/MVA, SA-CCR capital),
   key assumptions (risk-neutral measure, lognormal/normal factor models,
   independent netting sets), known limitations.

3. BUSINESS CONTEXT — why CCR exposure matters, the 2008 crisis lesson
   (Bear Stearns/Lehman exposures that were not netting-aware), regulatory
   history (Basel II IMM, Basel III SA-CCR, FRTB-CVA), model users
   (credit officers using PFE for limits, XVA desk using EPE/ENE for pricing,
   regulators reviewing SA-CCR capital).

4. THEORETICAL FOUNDATION — cover all of:
   a) Close-out netting: V_net(t) = sum_k V_k(t) under ISDA Master Agreement.
      Formula for netting benefit: NettingBenefit = sum max(V_k,0) - max(sum V_k, 0)
   b) Collateral offset with CSA: V_collateralised(t) = max(V_net(t) - C(t) - Threshold - MTA, 0)
      where C(t) is posted collateral, Threshold and MTA are CSA parameters
   c) Margin Period of Risk: 10 business days (daily-margined), 20 days (weekly),
      explain BCBS 261 source. Effect on effective collateral:
      C_effective(t) = C(t - MPoR)
   d) Exposure metrics:
      EE(t) = E[max(V_net(t) - C_effective(t), 0)]  (Expected Exposure)
      EPE = (1/T) integral_0^T EE(t) dt  (Effective EPE for Basel)
      ENE(t) = E[min(V_net(t) - C_effective(t), 0)]
      PFE_alpha(t) = Q_alpha[V_net(t) - C_effective(t)]  (alpha-quantile, typically 97.5%)
      EffEE(t) = max(EE(t), EffEE(t-1))  (non-decreasing for regulatory EPE)
   e) Market factor models:
      Interest rates: 2-factor Hull-White:
        dr(t) = [theta(t) - a*r(t)] dt + sigma_r dW_r
      FX: GBM: dS/S = (r_d - r_f) dt + sigma_FX dW_FX
      Equity: GBM with stochastic vol (Heston):
        dS/S = mu dt + sqrt(v) dW_S
        dv = kappa(theta - v)dt + xi*sqrt(v) dW_v
      Credit spreads: CIR: d(lambda) = kappa*(theta-lambda)dt + sigma*sqrt(lambda) dW
   f) SA-CCR (Basel III Standardised Approach):
      EAD = alpha * (RC + PFE_addon)
      where alpha = 1.4, RC = max(V - C, 0) for unmargined
      RC = max(V - C, TH + MTA - NICA, 0) for margined
      PFE_addon = aggregated add-on across 5 asset classes:
        IR add-on: supervisory delta * notional * maturity factor * sigma_IR
        FX add-on: abs(notional_CCY1 - notional_CCY2) * sigma_FX
        Equity: abs(S * number_shares) * sigma_EQ
        Credit: notional * MF * sigma_credit
        Commodity: abs(P * quantity) * sigma_com
      Full SA-CCR aggregation formula across hedging sets

5. DATA REQUIREMENTS — market data (yield curves all CCY, FX spots, equity prices,
   credit spreads, vol surfaces), counterparty data (ISDA Master Agreement records,
   CSA terms database), trade data (all OTC derivatives, notionals, tenors,
   underlying), calibration data (historical for vol params). Table format.

6. METHODOLOGY AND IMPLEMENTATION —
   a) Monte Carlo engine: 10,000 paths, 200 time steps (weekly to 5Y, monthly beyond)
   b) Netting set aggregation algorithm
   c) Collateral offset algorithm with MPoR delay
   d) Correlation matrix: 47x47 Cholesky decomposition, source from historical data
   e) GPU acceleration: cuBLAS for Cholesky, path batching
   f) Computational performance: full portfolio in <4 hours, intraday Greeks in <30 min
   g) Shared infrastructure: CVA, FVA, MVA run on same path set

7. MODEL TESTING AND BACKTESTING —
   a) P&L explain: daily EE predicted vs actual, threshold 85%
   b) SA-CCR benchmark: compare internal PFE to SA-CCR at 95th percentile
   c) Historical backtesting: compare EE predictions to actual exposure realisations
      over rolling 1-year windows (Basel traffic light test applied to CCR)
   d) Stress testing: 5 scenarios (2008 GFC, 2020 COVID, Rates+200bp,
      Credit+100bp, FX +/-20%), expected EE increase for each

8. PERFORMANCE METRICS AND CALIBRATION — table of metrics, thresholds, action triggers.
   Include: EE P&L explain >85%, SA-CCR vs internal PFE ratio 0.9-1.5,
   Correlation matrix condition number <1000, Factor model calibration frequency.

9. LIMITATIONS AND KNOWN WEAKNESSES —
   a) Gaussian copula for joint defaults (underestimates tail dependence)
   b) Static correlation matrix (recalibrated annually, not dynamic)
   c) No gap risk for equity derivatives
   d) Proxy mapping for illiquid counterparties
   e) Computational approximation for path-dependent exotics

10. COMPENSATING CONTROLS — table of risks, controls, owners.
    Include model reserve: $35M total ($15M correlation, $10M proxy mapping,
    $10M exotic path dependency).

11. CHANGE MANAGEMENT — material vs. non-material changes, re-validation triggers.

12. APPROVALS AND SIGN-OFF — table with Model Developer (submitted), MRO (pending),
    CRO (pending), Business Owner (pending).

STYLE REQUIREMENTS:
- Write in the first person plural ("We model...", "Our simulation...") consistent
  with a quant team authoring the document
- Include subsection numbers (4.1, 4.2, etc.)
- Every formula must be numbered using the equation environment
- Tables must have descriptive captions
- The document must be comprehensive — a real regulator reviewing this should
  find no gaps
- DO NOT truncate or abbreviate — write the FULL document
- Output ONLY valid LaTeX — no markdown, no explanation, no preamble text
  before \\documentclass
"""

def main() -> None:
    console.rule("[bold white]Apex Global Bank — MDD Generation[/bold white]")
    console.print("[dim]Model: PFE / CCR Exposure Engine  |  APEX-MDL-0014  |  LaTeX output[/dim]")
    console.print()

    client = anthropic.Anthropic()
    quant = create_quant_researcher(client=client)

    console.print("[bold cyan]Author:[/bold cyan] Dr. Yuki Tanaka — Head of Quantitative Research")
    console.print(f"[bold cyan]Output:[/bold cyan] {OUTPUT_FILE}")
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating LaTeX MDD (streaming)...", total=None)

        latex_content = quant.stream_speak(
            PROMPT,
            max_tokens=16000,
        )

        progress.update(task, description="Writing file...")

    # ── save ──────────────────────────────────────────────────────────────────
    OUTPUT_FILE.write_text(latex_content, encoding="utf-8")

    console.print(f"\n[bold green]✓[/bold green] Written to [bold]{OUTPUT_FILE}[/bold]")
    console.print(f"[dim]Characters: {len(latex_content):,}[/dim]")


if __name__ == "__main__":
    main()
