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
# Readiness gate — pre-paper-trading validation
# ---------------------------------------------------------------------------

READINESS_AGENTS = ['risk', 'compliance', 'trading', 'performance_audit']

MICA_PAIRS = [
    "BTC/USDC", "ETH/USDC", "XRP/USDC", "XLM/USDC", "HBAR/USDC",
    "ALGO/USDC", "ADA/USDC", "LINK/USDC", "IOTA/USDC", "VET/USDC",
    "XDC/USDC", "ONDO/USDC",
]
EXCHANGES = ["binance", "coinbase", "kraken", "kucoin", "okx", "bybit", "gate"]
STRATEGIES = ["arbitrage", "fibonacci", "grid", "dca", "mean_reversion", "pairs_arbitrage", "momentum"]

MIN_STRATEGIES_READY = 3
MIN_HEALTH_SCORE = 80


def _check_models() -> List[Finding]:
    """Check model availability across strategies, exchanges, and pairs."""
    findings = []
    models_dir = PROJECT_ROOT / "models" / "strategies"
    strategy_status = {}

    for strategy in STRATEGIES:
        ready_count = 0
        total_expected = 0
        for exchange in EXCHANGES:
            for pair in MICA_PAIRS:
                total_expected += 1
                coin = pair.split("/")[0].lower()
                # Pattern: {strategy}_{coin}_usdc_{exchange}.pth
                model_path = models_dir / f"{strategy}_{coin}_usdc_{exchange}.pth"
                meta_path = models_dir / f"{strategy}_{coin}_usdc_{exchange}_meta.json"
                if model_path.exists():
                    ready_count += 1
        strategy_status[strategy] = (ready_count, total_expected)

    strategies_ready = sum(1 for s, (r, t) in strategy_status.items() if r > 0)

    for strategy, (ready, total) in strategy_status.items():
        pct = (ready / total * 100) if total else 0
        if ready == 0:
            findings.append(Finding(
                severity="medium",
                file="models/",
                line=None,
                category="model_coverage",
                description=f"Strategy '{strategy}': 0/{total} models trained",
                recommendation=f"Run: python gpu_train.py --strategy {strategy} --all-pairs",
            ))
        else:
            findings.append(Finding(
                severity="info",
                file="models/",
                line=None,
                category="model_coverage",
                description=f"Strategy '{strategy}': {ready}/{total} models ({pct:.0f}%)",
                recommendation="OK" if pct > 50 else f"Continue training for better coverage",
            ))

    if strategies_ready < MIN_STRATEGIES_READY:
        findings.append(Finding(
            severity="critical",
            file="models/",
            line=None,
            category="model_coverage",
            description=f"Only {strategies_ready}/{len(STRATEGIES)} strategies have any models. Minimum {MIN_STRATEGIES_READY} required.",
            recommendation="Complete training for at least 3 strategies before paper trading.",
        ))

    return findings, strategy_status, strategies_ready


def _check_config() -> List[Finding]:
    """Validate trading config for paper trading safety."""
    findings = []
    config_path = PROJECT_ROOT / "config" / "trading_config.json"

    if not config_path.exists():
        findings.append(Finding(
            severity="critical",
            file="config/trading_config.json",
            line=None,
            category="config",
            description="Trading config file not found",
            recommendation="Create config/trading_config.json with required parameters",
        ))
        return findings

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        findings.append(Finding(
            severity="critical",
            file="config/trading_config.json",
            line=None,
            category="config",
            description=f"Failed to parse config: {e}",
            recommendation="Fix JSON syntax in trading_config.json",
        ))
        return findings

    # Check capital floor
    risk = config.get("risk_management", {})
    capital_floor = risk.get("capital_floor", 50)
    initial = config.get("initial_capital", 300)
    if capital_floor < 50:
        findings.append(Finding(
            severity="high",
            file="config/trading_config.json",
            line=None,
            category="risk_config",
            description=f"Capital floor ${capital_floor} is dangerously low",
            recommendation="Set capital_floor to at least $50 (recommend $150 for $300 capital)",
        ))

    # Check Kelly fraction
    kelly = risk.get("kelly_fraction", 0.25)
    if kelly > 0.5:
        findings.append(Finding(
            severity="high",
            file="config/trading_config.json",
            line=None,
            category="risk_config",
            description=f"Kelly fraction {kelly} exceeds safe threshold (0.5). Risk of ruin.",
            recommendation="Use quarter-Kelly (0.25) for conservative sizing",
        ))

    # Check max daily loss
    max_daily = risk.get("max_daily_loss_pct", 0.02)
    if max_daily > 0.05:
        findings.append(Finding(
            severity="high",
            file="config/trading_config.json",
            line=None,
            category="risk_config",
            description=f"Max daily loss {max_daily*100:.0f}% is too high for ${initial} capital",
            recommendation="Set max_daily_loss_pct to 2-5%",
        ))

    # Check for USDT contamination
    config_text = config_path.read_text(encoding="utf-8")
    if "USDT" in config_text.upper():
        findings.append(Finding(
            severity="critical",
            file="config/trading_config.json",
            line=None,
            category="mica_compliance",
            description="USDT reference found in trading config — MiCA violation",
            recommendation="Remove all USDT references. Use USDC only.",
        ))

    # Check strategy weights sum
    strategies = config.get("strategies", {})
    total_weight = sum(
        s.get("weight", 0) for s in strategies.values() if isinstance(s, dict)
    )
    if strategies and abs(total_weight - 1.0) > 0.05:
        findings.append(Finding(
            severity="medium",
            file="config/trading_config.json",
            line=None,
            category="config",
            description=f"Strategy weights sum to {total_weight:.2f} (expected ~1.0)",
            recommendation="Normalize strategy weights to sum to 1.0",
        ))

    if not findings:
        findings.append(Finding(
            severity="info",
            file="config/trading_config.json",
            line=None,
            category="config",
            description=f"Config OK: ${initial} capital, {kelly} Kelly, ${capital_floor} floor, {max_daily*100:.0f}% max daily loss",
            recommendation="OK",
        ))

    return findings


def _check_data_pipeline() -> List[Finding]:
    """Check that OHLCV data exists for paper trading."""
    findings = []
    data_dir = PROJECT_ROOT / "data"

    csv_count = 0
    exchanges_with_data = set()
    pairs_with_data = set()

    if data_dir.exists():
        for csv_file in data_dir.rglob("*.csv"):
            csv_count += 1
            parts = csv_file.stem.split("_")
            if len(parts) >= 2:
                exchanges_with_data.add(parts[0] if parts[0] in EXCHANGES else None)
                pairs_with_data.add(parts[-2].upper() if len(parts) >= 3 else None)

    exchanges_with_data.discard(None)
    pairs_with_data.discard(None)

    if csv_count == 0:
        findings.append(Finding(
            severity="critical",
            file="data/",
            line=None,
            category="data_pipeline",
            description="No OHLCV CSV data found",
            recommendation="Run: python fetch_exchange_data.py",
        ))
    else:
        findings.append(Finding(
            severity="info",
            file="data/",
            line=None,
            category="data_pipeline",
            description=f"{csv_count} CSV files, {len(exchanges_with_data)} exchanges, data available",
            recommendation="OK",
        ))

    return findings


def run_readiness(output_dir: Path) -> bool:
    """Run paper trading readiness gate. Returns True if ready, False otherwise."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print("  SOVEREIGNFORGE PAPER TRADING READINESS GATE")
    print("=" * 70)

    start = time.time()
    all_findings = []
    blockers = []

    # --- Check 1: Model coverage ---
    print("\n  [1/4] Checking model coverage...")
    model_findings, strategy_status, strategies_ready = _check_models()
    all_findings.extend(model_findings)
    print(f"        {strategies_ready}/{len(STRATEGIES)} strategies have trained models")
    for s, (r, t) in strategy_status.items():
        status = "OK" if r > 0 else "MISSING"
        print(f"          {s:<20} {r:>3}/{t} models  [{status}]")
    if strategies_ready < MIN_STRATEGIES_READY:
        blockers.append(f"Need >= {MIN_STRATEGIES_READY} strategies with models (have {strategies_ready})")

    # --- Check 2: Config validation ---
    print("\n  [2/4] Validating trading config...")
    config_findings = _check_config()
    all_findings.extend(config_findings)
    config_criticals = [f for f in config_findings if f.severity == "critical"]
    config_highs = [f for f in config_findings if f.severity == "high"]
    if config_criticals:
        for f in config_criticals:
            blockers.append(f.description)
            print(f"        CRITICAL: {f.description}")
    if config_highs:
        for f in config_highs:
            print(f"        WARNING:  {f.description}")
    if not config_criticals and not config_highs:
        print("        Config OK")

    # --- Check 3: Data pipeline ---
    print("\n  [3/4] Checking data pipeline...")
    data_findings = _check_data_pipeline()
    all_findings.extend(data_findings)
    data_criticals = [f for f in data_findings if f.severity == "critical"]
    if data_criticals:
        for f in data_criticals:
            blockers.append(f.description)
            print(f"        CRITICAL: {f.description}")
    else:
        for f in data_findings:
            print(f"        {f.description}")

    # --- Check 4: Dispatch audit agents ---
    print("\n  [4/4] Dispatching readiness audit agents...")
    readiness_subset = {k: AUDIT_AGENTS[k] for k in READINESS_AGENTS if k in AUDIT_AGENTS}
    run_audit(readiness_subset, output_dir, parallel=True)

    # --- Check existing reports for health score ---
    reports = load_all_reports(output_dir)
    scored_reports = [r for r in reports if r.health_score > 0]
    if scored_reports:
        avg_score = sum(r.health_score for r in scored_reports) / len(scored_reports)
        print(f"\n  Existing report health score: {avg_score:.0f}/100")
        if avg_score < MIN_HEALTH_SCORE:
            blockers.append(f"Health score {avg_score:.0f} below minimum {MIN_HEALTH_SCORE}")
    else:
        print("\n  No scored audit reports found yet (run subagents to populate)")

    # --- Verdict ---
    elapsed = round(time.time() - start, 2)

    critical_count = sum(1 for f in all_findings if f.severity == "critical")
    high_count = sum(1 for f in all_findings if f.severity == "high")

    print("\n" + "=" * 70)
    if blockers:
        verdict = "FAIL"
        print(f"  VERDICT: FAIL — {len(blockers)} blocker(s)")
        for b in blockers:
            print(f"    - {b}")
    else:
        verdict = "PASS"
        print("  VERDICT: PASS — Ready for paper trading")
        if high_count:
            print(f"    (with {high_count} warning(s) — review before live trading)")
    print(f"  Time: {elapsed}s | Findings: {len(all_findings)} ({critical_count} critical, {high_count} high)")
    print("=" * 70 + "\n")

    # Save readiness report
    report = AgentReport(
        agent_name="Readiness_Gate",
        agent_type="readiness",
        timestamp=datetime.now().isoformat(),
        health_score=100.0 if not blockers else max(0, 100 - len(blockers) * 25),
        findings=all_findings,
        summary=f"Paper Trading Readiness: {verdict}. "
                f"{strategies_ready} strategies ready, {critical_count} critical, {high_count} high findings. "
                + (f"Blockers: {'; '.join(blockers)}" if blockers else "No blockers."),
        files_scanned=0,
        execution_time_seconds=elapsed,
        recommendations=[f"BLOCKER: {b}" for b in blockers] if blockers else ["Proceed with: python launcher.py start --paper"],
    )
    save_report(report, output_dir)

    return verdict == "PASS"


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
  python src/agents/runner.py readiness
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

    # readiness
    sub.add_parser("readiness", help="Run paper trading readiness gate (models, config, data, audits)")

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

    elif args.command == "readiness":
        passed = run_readiness(output_dir)
        sys.exit(0 if passed else 1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
