#!/usr/bin/env python3
"""
SovereignForge - Post-Training Backtesting & P&L Simulation

After training completes, runs each model against held-out data to compute
simulated P&L (with realistic fees and slippage), Sharpe ratio, max drawdown,
and win rate per strategy/pair/exchange.
"""

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class PostTrainingBacktester:
    """Backtests freshly trained models using held-out validation data."""

    # Fixed fee and slippage per trade
    TRADE_FEE = 0.0005      # 0.05%
    TRADE_SLIPPAGE = 0.0008  # 0.08%

    def __init__(self, models_dir: str = "models/strategies",
                 data_dir: str = "data/historical",
                 initial_capital: float = 10000.0):
        self.models_dir = Path(models_dir)
        self.data_dir = Path(data_dir)
        self.initial_capital = initial_capital

    def run_all_backtests(self, training_results: Dict) -> Dict:
        """Backtest all successfully trained models from a training run.

        Args:
            training_results: Dict from train_strategy_model() or train_all_strategies()

        Returns:
            Dict mapping result_key to backtest metrics
        """
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available, skipping backtesting")
            return {"status": "skipped", "reason": "torch not available"}

        backtest_results = {}

        for key, result in training_results.items():
            if not isinstance(result, dict):
                continue
            if result.get("status") != "trained":
                continue

            strategy = result.get("strategy", "")
            exchange = result.get("exchange", "")
            pair = key.split(":")[0] if ":" in key else ""

            if not all([strategy, exchange, pair]):
                continue

            pair_slug = pair.replace("/", "_").lower()
            model_path = self.models_dir / f"{strategy}_{pair_slug}_{exchange}.pth"

            if not model_path.exists():
                logger.warning(f"Model not found: {model_path}")
                backtest_results[key] = {"status": "skipped", "reason": "model not found"}
                continue

            try:
                metrics = self.backtest_model(strategy, pair, exchange, model_path)
                backtest_results[key] = metrics
                logger.info(
                    f"Backtest {key}: Sharpe={metrics['sharpe']:.3f}, "
                    f"Win={metrics['win_rate']:.1%}, Net P&L=${metrics['net_pnl']:.2f}"
                )
            except Exception as e:
                logger.error(f"Backtest failed for {key}: {e}")
                backtest_results[key] = {"status": "failed", "error": str(e)}

        # Summary stats
        successful = [v for v in backtest_results.values() if isinstance(v, dict) and "sharpe" in v]
        if successful:
            backtest_results["_summary"] = {
                "models_backtested": len(successful),
                "avg_sharpe": np.mean([s["sharpe"] for s in successful]),
                "avg_win_rate": np.mean([s["win_rate"] for s in successful]),
                "total_net_pnl": sum(s["net_pnl"] for s in successful),
                "avg_max_drawdown": np.mean([s["max_drawdown"] for s in successful]),
            }

        return backtest_results

    def backtest_model(self, strategy: str, pair: str, exchange: str,
                       model_path: Path) -> Dict:
        """Load model and run backtest on held-out validation data.

        Uses the last 20% of available data (matching the training val split).
        """
        import torch
        from multi_strategy_training import (
            STRATEGY_MODELS, StrategyType, engineer_features,
            generate_labels, _load_pair_data
        )

        # Load model checkpoint
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
        config = checkpoint["config"]
        strategy_type = StrategyType(strategy)

        # Load data
        data_path = f"{self.data_dir}/{exchange}"
        ohlcv = _load_pair_data(pair, data_path)
        if ohlcv is None or len(ohlcv) < 100:
            return {"status": "skipped", "reason": "insufficient data"}

        # Use last 25% as test (same 75/25 split as training: 45d train / 15d test)
        split_idx = int(len(ohlcv) * 0.75)
        val_ohlcv = ohlcv[split_idx:]

        # Engineer features on validation data
        features, n_features = engineer_features(val_ohlcv, seq_len=config.get("seq_len", 128))
        if len(features) == 0:
            return {"status": "skipped", "reason": "too few validation samples"}

        # Create model and load weights
        model_factory = STRATEGY_MODELS[strategy_type]
        model = model_factory(config["input_size"], config["output_size"])
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

        # Run inference
        features_tensor = torch.FloatTensor(features)
        with torch.no_grad():
            predictions = model(features_tensor).numpy()

        # Extract close prices for P&L calculation (aligned with predictions)
        seq_len = config.get("seq_len", 24)
        close_prices = val_ohlcv[seq_len:seq_len + len(predictions), 4].astype(float)

        # Simulate trades
        trades = self._simulate_trades(predictions, close_prices)

        # Compute metrics
        return self.compute_metrics(trades)

    def _simulate_trades(self, predictions: np.ndarray,
                         close_prices: np.ndarray) -> List[Dict]:
        """Simulate trades from model predictions with realistic costs.

        Predictions format: [signal, confidence, magnitude]
        signal > 0.5 = buy, signal < -0.5 = sell, else hold
        """
        trades = []
        position = 0  # 0 = flat, 1 = long, -1 = short
        entry_price = 0.0
        min_len = min(len(predictions), len(close_prices))

        for i in range(min_len):
            signal = predictions[i][0] if len(predictions[i]) > 0 else 0
            confidence = abs(predictions[i][1]) if len(predictions[i]) > 1 else 0.5
            price = close_prices[i]

            # Entry signal
            if position == 0 and abs(signal) > 0.5 and confidence > 0.3:
                position = 1 if signal > 0 else -1
                entry_price = price
                continue

            # Exit: opposite signal or end of data
            if position != 0 and (
                (position == 1 and signal < -0.3) or
                (position == -1 and signal > 0.3) or
                i == min_len - 1
            ):
                trade = self._compute_trade_pnl(
                    entry_price=entry_price,
                    exit_price=price,
                    direction=position,
                    trade_value=self.initial_capital * 0.02  # 2% position size
                )
                trades.append(trade)
                position = 0

        return trades

    def _compute_trade_pnl(self, entry_price: float, exit_price: float,
                           direction: int, trade_value: float) -> Dict:
        """Compute P&L for a single trade with fixed fees and slippage."""
        fee_rate = self.TRADE_FEE        # 0.05%
        slippage_rate = self.TRADE_SLIPPAGE  # 0.08%

        price_change = (exit_price - entry_price) / entry_price * direction
        gross_pnl = price_change * trade_value
        total_cost_rate = (fee_rate + slippage_rate) * 2  # Entry + exit
        costs = total_cost_rate * trade_value
        net_pnl = gross_pnl - costs

        return {
            "entry_price": entry_price,
            "exit_price": exit_price,
            "direction": direction,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "fee": fee_rate,
            "slippage": slippage_rate,
            "costs": costs,
        }

    def compute_metrics(self, trades: List[Dict]) -> Dict:
        """Compute performance metrics from trade list."""
        if not trades:
            return {
                "status": "no_trades",
                "sharpe": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "gross_pnl": 0.0,
                "net_pnl": 0.0,
                "total_trades": 0,
                "avg_fee_rate": 0.0,
                "avg_slippage_rate": 0.0,
            }

        net_returns = [t["net_pnl"] for t in trades]
        gross_returns = [t["gross_pnl"] for t in trades]

        # Sharpe ratio (annualized, assuming ~8760 hourly periods / avg_trade_duration)
        mean_ret = np.mean(net_returns)
        std_ret = np.std(net_returns) if len(net_returns) > 1 else 1e-10
        sharpe = (mean_ret / (std_ret + 1e-10)) * np.sqrt(252)  # Annualized

        # Max drawdown
        cumulative = np.cumsum(net_returns)
        peak = np.maximum.accumulate(cumulative)
        drawdown = peak - cumulative
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0.0

        # Win rate
        wins = sum(1 for r in net_returns if r > 0)
        win_rate = wins / len(net_returns) if net_returns else 0.0

        return {
            "status": "backtested",
            "sharpe": float(sharpe),
            "max_drawdown": float(max_drawdown),
            "win_rate": float(win_rate),
            "gross_pnl": float(sum(gross_returns)),
            "net_pnl": float(sum(net_returns)),
            "total_trades": len(trades),
            "avg_fee_rate": float(np.mean([t["fee"] for t in trades])),
            "avg_slippage_rate": float(np.mean([t["slippage"] for t in trades])),
            "avg_trade_pnl": float(mean_ret),
            "best_trade": float(max(net_returns)),
            "worst_trade": float(min(net_returns)),
        }
