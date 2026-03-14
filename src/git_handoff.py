#!/usr/bin/env python3
"""
SovereignForge - Git Handoff

After major training completions, creates a handoff file with training summary
and commits training artifacts to git.
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


def create_training_handoff(results: Dict[str, Any], version: str) -> str:
    """Create a handoff file and git commit after training completion.

    Args:
        results: Full training results dict (may include backtest data)
        version: Current version string (e.g. "v1.0.5")

    Returns:
        Path to the created handoff file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    memory_dir = PROJECT_ROOT / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    # Count trained models
    trained = {k: v for k, v in results.items()
               if isinstance(v, dict) and v.get("status") == "trained"}

    # Extract backtest summary if available
    backtest = results.get("backtest", {})
    bt_summary = backtest.get("_summary", {}) if isinstance(backtest, dict) else {}

    # Build handoff
    handoff = {
        "version": version,
        "timestamp": timestamp,
        "created_at": datetime.now().isoformat(),
        "training_summary": {
            "models_trained": len(trained),
            "strategies": list(set(v.get("strategy", "") for v in trained.values())),
            "exchanges": list(set(v.get("exchange", "") for v in trained.values())),
            "best_val_loss": min(
                (v.get("best_val_loss", float("inf")) for v in trained.values()),
                default=None
            ),
        },
        "backtest_summary": {
            "avg_sharpe": bt_summary.get("avg_sharpe", None),
            "avg_win_rate": bt_summary.get("avg_win_rate", None),
            "total_net_pnl": bt_summary.get("total_net_pnl", None),
        },
        "next_steps": [
            "Review backtest metrics per model",
            "Deploy best-performing models to live pipeline",
            "Monitor live inference performance",
            "Fetch fresh data and retrain underperformers",
        ],
    }

    handoff_path = memory_dir / f"handoff_{timestamp}.json"
    with open(handoff_path, "w") as f:
        json.dump(handoff, f, indent=2, default=str)

    logger.info(f"Handoff file created: {handoff_path}")

    # Git commit training artifacts
    _git_commit(version, timestamp)

    return str(handoff_path)


def _git_commit(version: str, timestamp: str) -> None:
    """Stage and commit training artifacts."""
    try:
        dirs_to_add = [
            "models/strategies/",
            "reports/",
            "memory/",
            "learnings/",
            "data/training_knowledge_graph.json",
        ]

        for d in dirs_to_add:
            path = PROJECT_ROOT / d
            if path.exists():
                subprocess.run(
                    ["git", "add", str(d)],
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    timeout=30,
                )

        result = subprocess.run(
            ["git", "commit", "-m",
             f"Training run complete {version} — {timestamp}"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            logger.info(f"Git commit created for {version}")
        else:
            logger.warning(f"Git commit returned {result.returncode}: {result.stderr.strip()}")

    except subprocess.TimeoutExpired:
        logger.error("Git commit timed out")
    except FileNotFoundError:
        logger.warning("Git not found, skipping commit")
    except Exception as e:
        logger.error(f"Git handoff failed: {e}")
