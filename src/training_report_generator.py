#!/usr/bin/env python3
"""
SovereignForge - Training Report Generator

Generates:
  1. JSON dashboard data for React/lightweight-charts consumption
  2. Markdown training reports
  3. Epoch loss curve data for lightweight-charts-python
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class TrainingReportGenerator:
    """Generates reports and dashboard data from training + backtest results."""

    def __init__(self, reports_dir: str = "reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_all(self, training_results: Dict,
                     backtest_results: Optional[Dict] = None,
                     version: str = "v1.0.4") -> Dict:
        """Generate all reports from training and backtest results.

        Returns:
            Dict with paths to generated report files
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        generated = {}

        # Dashboard JSON
        dashboard_data = self.generate_dashboard_data(
            training_results, backtest_results
        )
        dashboard_path = self.reports_dir / "training_dashboard_data.json"
        with open(dashboard_path, "w") as f:
            json.dump(dashboard_data, f, indent=2, default=str)
        generated["dashboard_json"] = str(dashboard_path)

        # Markdown report
        md_path = self.reports_dir / f"training_report_{timestamp}.md"
        self.generate_markdown_report(dashboard_data, md_path, version)
        generated["markdown_report"] = str(md_path)

        # Lightweight charts data
        charts_data = self.generate_lightweight_charts_data(training_results)
        charts_path = self.reports_dir / "training_charts_data.json"
        with open(charts_path, "w") as f:
            json.dump(charts_data, f, indent=2, default=str)
        generated["charts_data"] = str(charts_path)

        logger.info(f"Reports generated: {list(generated.keys())}")
        return generated

    def generate_dashboard_data(self, training_results: Dict,
                                backtest_results: Optional[Dict] = None) -> Dict:
        """Structure data for dashboard cards consumption.

        Output format:
        {
            "strategies": {
                "arbitrage": [
                    {"pair": "BTC/USDC", "exchange": "binance", "val_loss": 0.123,
                     "pnl": 45.2, "risk_score": 0.3, "sharpe": 1.5, ...}
                ]
            },
            "summary": {...}
        }
        """
        strategies = {}

        for key, result in training_results.items():
            if not isinstance(result, dict) or result.get("status") != "trained":
                continue

            strategy = result.get("strategy", "unknown")
            exchange = result.get("exchange", "unknown")
            pair = key.split(":")[0] if ":" in key else key

            entry = {
                "pair": pair,
                "exchange": exchange,
                "val_loss": result.get("best_val_loss", None),
                "epochs_completed": result.get("epochs_completed", 0),
                "samples": result.get("samples", 0),
            }

            # Merge backtest data if available
            if backtest_results and key in backtest_results:
                bt = backtest_results[key]
                if isinstance(bt, dict) and "sharpe" in bt:
                    entry.update({
                        "sharpe": bt.get("sharpe", 0),
                        "win_rate": bt.get("win_rate", 0),
                        "net_pnl": bt.get("net_pnl", 0),
                        "gross_pnl": bt.get("gross_pnl", 0),
                        "max_drawdown": bt.get("max_drawdown", 0),
                        "total_trades": bt.get("total_trades", 0),
                    })

            # Compute risk score from val_loss trajectory
            epoch_results = result.get("epoch_results", [])
            if epoch_results:
                entry["risk_score"] = self._estimate_risk_score(epoch_results)

            strategies.setdefault(strategy, []).append(entry)

        # Summary
        all_entries = [e for entries in strategies.values() for e in entries]
        summary = {
            "total_models": len(all_entries),
            "strategies_trained": list(strategies.keys()),
            "timestamp": datetime.now().isoformat(),
        }

        if all_entries:
            val_losses = [e["val_loss"] for e in all_entries if e.get("val_loss")]
            if val_losses:
                summary["avg_val_loss"] = float(np.mean(val_losses))
                summary["best_val_loss"] = float(min(val_losses))

            pnls = [e.get("net_pnl", 0) for e in all_entries if "net_pnl" in e]
            if pnls:
                summary["total_net_pnl"] = float(sum(pnls))

        return {"strategies": strategies, "summary": summary}

    def generate_markdown_report(self, data: Dict, output_path: Path,
                                 version: str = "v1.0.4") -> None:
        """Generate human-readable markdown training report."""
        summary = data.get("summary", {})
        strategies = data.get("strategies", {})

        lines = [
            f"# SovereignForge Training Report — {version}",
            f"",
            f"**Generated:** {summary.get('timestamp', 'N/A')}",
            f"**Models Trained:** {summary.get('total_models', 0)}",
            f"**Strategies:** {', '.join(summary.get('strategies_trained', []))}",
            f"",
        ]

        if "avg_val_loss" in summary:
            lines.append(f"**Avg Val Loss:** {summary['avg_val_loss']:.6f}")
        if "best_val_loss" in summary:
            lines.append(f"**Best Val Loss:** {summary['best_val_loss']:.6f}")
        if "total_net_pnl" in summary:
            lines.append(f"**Total Net P&L:** ${summary['total_net_pnl']:.2f}")
        lines.append("")

        for strategy, entries in strategies.items():
            lines.append(f"## {strategy.title()} Strategy")
            lines.append("")
            lines.append("| Pair | Exchange | Val Loss | Sharpe | Win Rate | Net P&L |")
            lines.append("|------|----------|----------|--------|----------|---------|")

            for e in sorted(entries, key=lambda x: x.get("val_loss", 999)):
                vl = f"{e['val_loss']:.6f}" if e.get("val_loss") else "N/A"
                sh = f"{e.get('sharpe', 0):.3f}" if "sharpe" in e else "—"
                wr = f"{e.get('win_rate', 0):.1%}" if "win_rate" in e else "—"
                pnl = f"${e.get('net_pnl', 0):.2f}" if "net_pnl" in e else "—"
                lines.append(f"| {e['pair']} | {e['exchange']} | {vl} | {sh} | {wr} | {pnl} |")

            lines.append("")

        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"Markdown report written to {output_path}")

    def generate_lightweight_charts_data(self, training_results: Dict) -> Dict:
        """Generate epoch-by-epoch loss curve data for lightweight-charts-python.

        Output format:
        {
            "loss_curves": {
                "arbitrage_btc_usdc_binance": [
                    {"epoch": 1, "train_loss": 0.5, "val_loss": 0.6}, ...
                ]
            }
        }
        """
        loss_curves = {}

        for key, result in training_results.items():
            if not isinstance(result, dict) or result.get("status") != "trained":
                continue

            epoch_results = result.get("epoch_results", [])
            if not epoch_results:
                continue

            strategy = result.get("strategy", "")
            exchange = result.get("exchange", "")
            pair = key.split(":")[0] if ":" in key else ""
            pair_slug = pair.replace("/", "_").lower()
            curve_key = f"{strategy}_{pair_slug}_{exchange}"

            loss_curves[curve_key] = [
                {
                    "epoch": er.get("epoch", i + 1),
                    "train_loss": er.get("train_loss", 0),
                    "val_loss": er.get("val_loss", 0),
                }
                for i, er in enumerate(epoch_results)
            ]

        return {"loss_curves": loss_curves}

    def _estimate_risk_score(self, epoch_results: List[Dict]) -> float:
        """Estimate a 0-1 risk score from training epoch trajectory."""
        if len(epoch_results) < 5:
            return 0.5

        recent = epoch_results[-5:]
        val_losses = [e.get("val_loss", 0) for e in recent]
        train_losses = [e.get("train_loss", 0) for e in recent]

        # Divergence: val >> train
        avg_val = np.mean(val_losses) if val_losses else 0
        avg_train = np.mean(train_losses) if train_losses else 0
        divergence = min(1.0, max(0, avg_val - avg_train) / (avg_train + 1e-10))

        # Trend: is val_loss increasing?
        if len(val_losses) >= 3:
            trend = (val_losses[-1] - val_losses[0]) / (abs(val_losses[0]) + 1e-10)
            trend = min(1.0, max(0.0, trend))
        else:
            trend = 0.0

        # Magnitude
        magnitude = min(1.0, avg_val / 1.0)  # Normalize to 1.0 being high

        score = 0.4 * divergence + 0.3 * trend + 0.3 * magnitude
        return float(np.clip(score, 0.0, 1.0))
