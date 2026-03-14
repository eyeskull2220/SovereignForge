#!/usr/bin/env python3
"""
SovereignForge Agent Runner -- orchestrates multi-personality audit and research agents.

Usage:
    python src/agents/runner.py list                       # Show all agents
    python src/agents/runner.py audit --all                # Run all 6 audit agents
    python src/agents/runner.py audit --agent security     # Run specific audit agent
    python src/agents/runner.py research                   # Run all 3 research agents
    python src/agents/runner.py synthesize                 # Synthesize existing reports
    python src/agents/runner.py audit --all --output ./my_reports
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

from agents.base import AgentReport, Finding, load_all_reports, save_report

# Import all agent classes
from agents.audit_security import SecurityAuditor
from agents.audit_performance import PerformanceAnalyst
from agents.audit_trading import TradingLogicReviewer
from agents.audit_risk import RiskAuditor
from agents.audit_compliance import MiCAComplianceChecker
from agents.audit_quality import CodeQualityGuardian
from agents.research_sentiment import MarketSentimentAgent
from agents.research_technical import TechnicalAnalysisAgent
from agents.research_performance import StrategyPerformanceAgent

# --- Agent Registries ---

AUDIT_AGENTS = {
    'security': SecurityAuditor,
    'performance_audit': PerformanceAnalyst,
    'trading': TradingLogicReviewer,
    'risk': RiskAuditor,
    'compliance': MiCAComplianceChecker,
    'quality': CodeQualityGuardian,
}

RESEARCH_AGENTS = {
    'sentiment': MarketSentimentAgent,
    'technical': TechnicalAnalysisAgent,
    'strategy_performance': StrategyPerformanceAgent,
}

ALL_AGENTS = {**AUDIT_AGENTS, **RESEARCH_AGENTS}

DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports" / "audits"


# ---------------------------------------------------------------------------
# List command
# ---------------------------------------------------------------------------

def list_agents():
    """Print a formatted table of all registered agents."""
    print("\n  SovereignForge Agent Registry")
    print("  " + "=" * 68)

    print("\n  AUDIT AGENTS (6)")
    print("  " + "-" * 68)
    print(f"  {'Key':<20} {'Name':<30} {'Personality':<20}")
    print("  " + "-" * 68)
    for key, cls in AUDIT_AGENTS.items():
        name = cls.name if cls else "(unavailable)"
        pers = getattr(cls, 'personality', '-') if cls else '-'
        targets = len(cls.target_files) if cls and hasattr(cls, 'target_files') else 0
        print(f"  {key:<20} {name:<30} {pers:<20} [{targets} files]")

    print("\n  RESEARCH AGENTS (3)")
    print("  " + "-" * 68)
    print(f"  {'Key':<20} {'Name':<30}")
    print("  " + "-" * 68)
    for key, cls in RESEARCH_AGENTS.items():
        name = cls.name if hasattr(cls, 'name') else cls.__name__ if cls else "(unavailable)"
        print(f"  {key:<20} {name:<30}")

    print(f"\n  Total: {len(ALL_AGENTS)} agents ({len(AUDIT_AGENTS)} audit + {len(RESEARCH_AGENTS)} research)")
    print()


# ---------------------------------------------------------------------------
# Audit dispatch
# ---------------------------------------------------------------------------

def _run_single_audit(key: str, cls, output_dir: Path) -> Optional[AgentReport]:
    """Run a single audit agent and save its report.

    In subagent mode, this builds the prompt and prints instructions for
    launching the agent via Claude Code's Agent tool. The actual audit
    execution happens in the subagent context.

    Returns a stub AgentReport indicating the agent was dispatched.
    """
    if cls is None:
        print(f"  [SKIP] {key}: agent class not available")
        return None

    start = time.time()
    prompt = cls.build_prompt()

    # Build dispatch instructions
    print(f"  [DISPATCH] {cls.name} ({cls.personality})")
    print(f"             Target files: {len(cls.target_files)}")
    print(f"             Checklist items: {len(cls.checklist)}")

    # Save the prompt to a file so it can be fed to a subagent
    prompt_dir = output_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / f"{key}_prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    elapsed = round(time.time() - start, 2)

    # Create a stub report marking the agent as dispatched
    report = AgentReport(
        agent_name=cls.name,
        agent_type="audit",
        timestamp=datetime.now().isoformat(),
        health_score=0.0,  # To be filled by subagent
        findings=[],
        summary=f"Agent dispatched. Prompt saved to {prompt_file.name}. "
                f"Launch as Claude Code subagent to execute audit.",
        files_scanned=len(cls.target_files),
        execution_time_seconds=elapsed,
        recommendations=["Run this agent as a Claude Code subagent with the saved prompt"],
    )

    save_report(report, output_dir)
    print(f"             Prompt saved: {prompt_file}")
    return report


def run_audit(agents: Dict[str, type], output_dir: Path, parallel: bool = True):
    """Dispatch one or more audit agents.

    Args:
        agents: dict of {key: AgentClass} to run
        output_dir: directory for reports and prompts
        parallel: if True, dispatch agents in parallel threads
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Dispatching {len(agents)} audit agent(s)...")
    print(f"  Reports directory: {output_dir}")
    print()

    reports = []

    if parallel and len(agents) > 1:
        with ThreadPoolExecutor(max_workers=min(len(agents), 6)) as pool:
            futures = {
                pool.submit(_run_single_audit, key, cls, output_dir): key
                for key, cls in agents.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    report = future.result()
                    if report:
                        reports.append(report)
                except Exception as exc:
                    print(f"  [ERROR] {key}: {exc}")
    else:
        for key, cls in agents.items():
            try:
                report = _run_single_audit(key, cls, output_dir)
                if report:
                    reports.append(report)
            except Exception as exc:
                print(f"  [ERROR] {key}: {exc}")

    print(f"\n  Dispatched {len(reports)}/{len(agents)} agents.")
    print(f"  Prompts saved to: {output_dir / 'prompts'}")
    print()
    print("  Next steps:")
    print("    1. Launch each agent as a Claude Code subagent using the saved prompts")
    print("    2. Save subagent reports to the reports directory")
    print("    3. Run 'python src/agents/runner.py synthesize' to consolidate results")
    print()

    return reports


# ---------------------------------------------------------------------------
# Research dispatch
# ---------------------------------------------------------------------------

def run_research(output_dir: Path):
    """Run all research agents and save reports."""
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Running {len(RESEARCH_AGENTS)} research agent(s)...")
    print(f"  Reports directory: {output_dir}")
    print()

    reports = []
    for key, cls in RESEARCH_AGENTS.items():
        if cls is None:
            print(f"  [SKIP] {key}: agent class not available")
            continue

        start = time.time()
        try:
            agent = cls()
            result = agent.analyze()
            elapsed = round(time.time() - start, 2)

            # Convert research result to AgentReport format
            report = AgentReport(
                agent_name=getattr(agent, 'name', cls.__name__),
                agent_type="research",
                timestamp=datetime.now().isoformat(),
                health_score=100.0,  # Research agents don't score health
                findings=[],
                summary=json.dumps(result, indent=2, default=str),
                files_scanned=0,
                execution_time_seconds=elapsed,
            )
            save_report(report, output_dir)
            reports.append(report)
            print(f"  [DONE] {agent.name} ({elapsed:.1f}s)")

        except Exception as exc:
            print(f"  [ERROR] {key}: {exc}")

    print(f"\n  Completed {len(reports)}/{len(RESEARCH_AGENTS)} research agents.")
    print()
    return reports


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def synthesize_reports(reports_dir: Path = None) -> Optional[AgentReport]:
    """Consolidate all agent reports into a synthesis report."""
    reports_dir = reports_dir or DEFAULT_REPORTS_DIR
    reports = load_all_reports(reports_dir)
    if not reports:
        print("No reports found to synthesize.")
        return None

    all_findings = []
    total_score = 0
    total_files = 0

    for r in reports:
        all_findings.extend(r.findings)
        total_score += r.health_score
        total_files += r.files_scanned

    avg_score = total_score / len(reports) if reports else 0

    # Group by severity
    critical = [f for f in all_findings if f.severity == "critical"]
    high = [f for f in all_findings if f.severity == "high"]
    medium = [f for f in all_findings if f.severity == "medium"]

    # Cross-cutting: findings from 2+ agents on same file
    file_agents = {}
    for f in all_findings:
        if f.severity in ("critical", "high", "medium"):
            file_agents.setdefault(f.file, set()).add(f.category)
    cross_cutting = {f: cats for f, cats in file_agents.items() if len(cats) > 1}

    summary_parts = [
        f"Synthesized {len(reports)} agent reports.",
        f"Total findings: {len(all_findings)} ({len(critical)} critical, {len(high)} high, {len(medium)} medium).",
        f"Overall health score: {avg_score:.0f}/100.",
    ]
    if cross_cutting:
        summary_parts.append(f"Cross-cutting issues in {len(cross_cutting)} files flagged by multiple agents.")

    recommendations = []
    if critical:
        recommendations.append(f"FIX IMMEDIATELY: {len(critical)} critical issues")
    if high:
        recommendations.append(f"Fix soon: {len(high)} high-severity issues")
    if cross_cutting:
        for f, cats in sorted(cross_cutting.items()):
            recommendations.append(f"Multi-agent concern: {f} flagged by {', '.join(sorted(cats))}")

    synthesis = AgentReport(
        agent_name="Synthesis",
        agent_type="synthesis",
        timestamp=datetime.now().isoformat(),
        health_score=avg_score,
        findings=sorted(all_findings, key=lambda f: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(f.severity, 5)),
        summary=" ".join(summary_parts),
        files_scanned=total_files,
        recommendations=recommendations,
    )

    save_report(synthesis, reports_dir)
    print(f"\n  Synthesis complete: {avg_score:.0f}/100 health score")
    print(f"    Critical: {len(critical)} | High: {len(high)} | Medium: {len(medium)}")
    print(f"    Report: {reports_dir / 'synthesis.md'}")
    return synthesis


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SovereignForge Agent Runner -- orchestrate audit and research agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python src/agents/runner.py list
  python src/agents/runner.py audit --all
  python src/agents/runner.py audit --agent security
  python src/agents/runner.py audit --agent security --agent risk
  python src/agents/runner.py research
  python src/agents/runner.py synthesize
  python src/agents/runner.py audit --all --output ./custom_reports
        """,
    )
    parser.add_argument(
        '--output', type=str, default=None,
        help=f"Report output directory (default: {DEFAULT_REPORTS_DIR})",
    )

    sub = parser.add_subparsers(dest="command")

    # list
    sub.add_parser("list", help="List all registered agents")

    # audit
    audit_p = sub.add_parser("audit", help="Run audit agents")
    audit_p.add_argument("--all", action="store_true", help="Run all 6 audit agents")
    audit_p.add_argument(
        "--agent", type=str, action="append", dest="agents",
        help="Run specific audit agent(s) by key (repeatable)",
    )
    audit_p.add_argument(
        "--sequential", action="store_true",
        help="Run agents sequentially instead of in parallel",
    )

    # research
    sub.add_parser("research", help="Run all 3 research agents")

    # synthesize
    sub.add_parser("synthesize", help="Synthesize existing reports into a consolidated view")

    args = parser.parse_args()
    output_dir = Path(args.output) if args.output else DEFAULT_REPORTS_DIR

    if args.command == "list":
        list_agents()

    elif args.command == "audit":
        if args.all:
            run_audit(AUDIT_AGENTS, output_dir, parallel=not getattr(args, 'sequential', False))
        elif args.agents:
            selected = {}
            for key in args.agents:
                if key in AUDIT_AGENTS:
                    selected[key] = AUDIT_AGENTS[key]
                else:
                    print(f"  [WARN] Unknown audit agent: '{key}'")
                    print(f"         Available: {', '.join(AUDIT_AGENTS.keys())}")
            if selected:
                run_audit(selected, output_dir, parallel=not getattr(args, 'sequential', False))
        else:
            print("  Specify --all or --agent <name>. Use 'list' to see available agents.")
            audit_p.print_help()

    elif args.command == "research":
        run_research(output_dir)

    elif args.command == "synthesize":
        synthesize_reports(output_dir)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
