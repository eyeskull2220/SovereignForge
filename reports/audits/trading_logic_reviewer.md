# Trading Logic Reviewer Audit Report
**Type:** audit | **Score:** 52.0/100 | **Time:** 140.0s
**Files Scanned:** 8 | **Findings:** 20

## Summary
3 critical issues: Kelly params swapped, $10k hardcoded capital (should be $300), training crashes for 3 new strategies. Fee model dangerously assumes flat 0.1% when Coinbase charges 0.6%. Paper trading limited to 4 of 7 strategies with stale weights.

## CRITICAL (3)
- **[kelly]** `src/risk_management.py:745` — TradingRiskManager._kelly_criterion swaps parameter semantics: spread_pct passed as win_probability, confidence as win_amount. Kelly formula computes with wrong inputs.
  - Fix: Fix call site at line 712 to pass parameters in correct order
- **[hardcoded]** `src/live_arbitrage_pipeline.py:696` — base_capital hardcoded to $10,000 ignoring actual portfolio value. $300 account sizes positions as if $10k = 33x too large.
  - Fix: Read from config capital_allocation.initial_capital or RiskManager portfolio_value
- **[consistency]** `src/multi_strategy_training.py:953` — forward_windows dict missing 3 of 7 strategies (mean_reversion, pairs_arbitrage, momentum). Training crashes with KeyError.
  - Fix: Add MEAN_REVERSION:10, PAIRS_ARBITRAGE:20, MOMENTUM:48 to forward_windows

## HIGH (6)
- **[fees]** `src/order_executor.py:197` — Flat 0.1% fee assumption for profitability check. Coinbase is 0.6% taker. 0.3% spread passes validation but loses money on Coinbase.
  - Fix: Use exchange-specific fee schedules
- **[fees]** `src/order_executor.py:588` — PaperTradingExecutor uses flat 0.1% fee. Real Coinbase fees are 6x higher. Paper results overly optimistic.
  - Fix: Use EXCHANGE_FEES dict
- **[kelly]** `src/risk_management.py:202` — RiskManager Kelly inflates win_probability with spread_bonus and uses spread/costs as odds ratio producing unreasonably high fractions.
  - Fix: Use historical win rate data for probability estimation
- **[consistency]** `src/paper_trading.py:77` — Paper trading hardcodes 4-strategy weights {arb:0.4,fib:0.2,grid:0.2,dca:0.2} vs config 7-strategy weights. Inconsistent.
  - Fix: Load weights from trading_config.json
- **[consistency]** `src/paper_trading.py:67` — STRATEGIES list only has 4 strategies, missing mean_reversion, pairs_arbitrage, momentum.
  - Fix: Add all 7 strategies
- **[kelly]** `src/risk_management.py:300` — calculate_kelly_metrics EV formula dimensionally inconsistent. Does not account for actual dollar amounts at risk.
  - Fix: Use: EV = p*(spread-costs) - q*costs

## MEDIUM (6)
- **[consistency]** `src/risk_management.py:434` — check_stop_losses only handles buy-side. Sell positions stop/TP logic is inverted but not implemented.
  - Fix: Add side-aware stop loss matching TradingRiskManager
- **[fees]** `src/live_arbitrage_pipeline.py:699` — Fee calc uses flat 0.1% for both exchanges. Real exchange fees differ significantly.
  - Fix: Use per-exchange fee rates
- **[slippage]** `src/order_executor.py:315` — Partial fill hardcoded to 95%. Creates quantity mismatch between arb legs.
  - Fix: Check actual filled qty and adjust other leg
- **[rounding]** `src/capital_allocator.py:76` — rolling_sharpe uses sqrt(N trades) annualization instead of time-based. Incomparable across strategies.
  - Fix: Use sqrt(365/window_days)
- **[rounding]** `src/risk_management.py:865` — Sharpe ratio mixes per-trade returns with daily risk-free rate adjustments.
  - Fix: Match return frequency with risk-free rate period
- **[consistency]** `src/strategy_ensemble.py:371` — CrossExchangeScorer recomputes signals as simple average, losing confidence-weighted info.
  - Fix: Use weighted final_signal from EnsembleSignal

## LOW (2)
- **[slippage]** `src/order_executor.py:230` — Symmetric 0.1% slippage model. Real slippage is asymmetric.
  - Fix: Consider asymmetric model
- **[rounding]** `src/risk_management.py:186` — Min position check uses 0.001*avg_price regardless of pair. XRP min = $0.0005, effectively none.
  - Fix: Use pair-specific minimums from _ASSET_CONFIGS

## INFO (3)
- **[consistency]** `src/risk_management.py` — Two separate RiskManager classes with different Kelly, stop-loss, fee assumptions. Pipeline uses one, backtester the other.
  - Fix: Consolidate or document clearly
- **[hardcoded]** `config/trading_config.json:6` — min_spread_threshold=0.5 (50%) seems wrong. Should be 0.005 (0.5%)?
  - Fix: Verify value
- **[consistency]** `config/trading_config.json:14` — risk/reward ratio inverted: stop_loss=2%, take_profit=1%. Risk 2x of reward.
  - Fix: Set take_profit > stop_loss

## Top Recommendations
- FIX IMMEDIATELY: forward_windows dict missing 3 strategies - training will crash
- FIX IMMEDIATELY: Replace hardcoded $10k capital with config value
- FIX: Per-exchange fee schedules instead of flat 0.1%
- Consolidate or clearly separate the two RiskManager classes