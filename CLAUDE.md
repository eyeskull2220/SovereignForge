# CLAUDE.md — SovereignForge

## Project Overview

SovereignForge is a GPU-accelerated cryptocurrency arbitrage detection system with real-time monitoring, AI-powered opportunity filtering, MiCA compliance enforcement, and multi-personality agent auditing. Hybrid Python/TypeScript monorepo.

**Status**: 7 strategies, 7 exchanges, 15 dashboard pages, 9 agent personalities, 3 optimization tools. Health score: 92/100.

---

## Repository Structure

```
SovereignForge/
├── src/                    # Python backend (51+ modules)
│   ├── agents/             # 6 audit + 3 research agent personalities
│   ├── multi_strategy_training.py  # 7-strategy ML training pipeline
│   ├── live_arbitrage_pipeline.py  # Real-time execution with risk gates
│   ├── strategy_ensemble.py        # Confidence-weighted ensemble with regime detection
│   ├── order_executor.py           # Async ccxt exchange execution
│   ├── capital_allocator.py        # Tier-based capital allocation ($300→$5000)
│   ├── regime_detector.py          # Market regime classification
│   ├── cointegration_detector.py   # Statistical pairs arbitrage detection
│   ├── autotuner.py                # Karpathy-style overnight param optimization
│   ├── swarm_optimizer.py          # Evolutionary optimizer with Research DAG
│   ├── hyperparameter_tuner.py     # Optuna Bayesian optimization
│   ├── model_backup.py             # Model backup/restore utility
│   └── dashboard_api.py            # FastAPI backend (20+ endpoints)
├── dashboard/              # React 19 frontend (15 pages)
│   └── src/components/     # Audit, Exchanges, Capital, Research, Cointegration, etc.
├── tests/                  # pytest suite (24/24 passing)
├── models/strategies/      # 109+ trained PyTorch models (.pth + _meta.json)
├── config/                 # trading_config.json, api_keys.json
├── data/historical/        # OHLCV data (7 exchanges × 12 pairs)
├── reports/audits/         # Agent audit reports (JSON + Markdown)
├── health_watchdog.py      # Production health check daemon
├── setup_telegram.py       # Interactive Telegram alert setup
├── refresh_training_data.py # Multi-exchange OHLCV data fetcher
└── gpu_train.py            # GPU training CLI (7 strategies)
```

---

## Quick Reference Commands

```bash
# Training (resume remaining 4 strategies)
python gpu_train.py --strategy dca --all-pairs --exchanges binance okx kucoin bybit --epochs 200 --batch-size 64 --learning-rate 8e-5 --memory-fraction 0.88 --mixed-precision --gpu-monitor

# Paper trading
python launcher.py start --paper

# Optimization (run overnight)
python src/autotuner.py --max-experiments 200
python src/swarm_optimizer.py "maximize Sharpe ratio" --generations 50
python src/hyperparameter_tuner.py --optuna --strategy momentum --trials 50

# Agents
python src/agents/runner.py list              # Show all 9 agents
python src/agents/runner.py audit --all       # Run 6 audit agents
python src/agents/runner.py research          # Run 3 research agents
python src/agents/runner.py synthesize        # Consolidate reports

# Data refresh
python refresh_training_data.py               # All 7 exchanges
python refresh_training_data.py --exchanges kraken --force  # Kraken trades workaround

# Dashboard
cd dashboard && npm start                     # Dev server on :3000
# API on :8420 (bound to 127.0.0.1, API key auth on POST endpoints)

# Tests
PYTHONPATH=src python -m pytest tests/test_integration.py tests/test_risk_management.py -v

# Health monitoring
python health_watchdog.py                     # Polls /api/health every 30s

# Telegram setup
python setup_telegram.py                      # Interactive bot configuration

# Model backup
python -c "from model_backup import backup_models; backup_models('pre_training')"
```

---

## 7 Trading Strategies

| Strategy | Architecture | Forward Window | Best For |
|----------|-------------|---------------|----------|
| arbitrage | LSTM | 6 candles (30m) | Cross-exchange spread detection |
| fibonacci | Transformer | 18 candles (90m) | Fib retracement patterns |
| grid | GRU | 12 candles (1h) | Mean-reversion in ranging markets |
| dca | LSTM | 48 candles (4h) | Optimal DCA entry timing |
| mean_reversion | GRU | 12 candles (1h) | Bollinger Band + RSI oversold/overbought |
| pairs_arbitrage | LSTM | 15 candles (75m) | Cointegrated pair spread trading |
| momentum | Transformer | 36 candles (3h) | Trend continuation with ADX confirmation |

Ensemble weights (from config): arb=0.20, fib=0.10, grid=0.18, dca=0.10, mr=0.17, pairs=0.12, mom=0.13

---

## 7 Exchanges

| Exchange | Fee | WebSocket | Status |
|----------|-----|-----------|--------|
| Binance | 0.1% | BinanceWebSocket | Full support |
| Coinbase | 0.4% | CoinbaseWebSocket | Full support |
| Kraken | 0.26% | KrakenWebSocket | Full support (OHLCV limited to 720 candles) |
| KuCoin | 0.1% | KuCoinWebSocket | Full support |
| OKX | 0.1% | OKXWebSocket | Full support |
| Bybit | 0.1% | BybitWebSocket | Full support (MiCA licensed, Austria) |
| Gate.io | 0.2% | GateWebSocket | Full support (MiCA licensed, Malta) |

---

## MiCA Compliance — CRITICAL RULES

**NEVER use USDT. Only USDC and RLUSD stablecoins.**

### Allowed Pairs
- XRP/USDC, XLM/USDC, HBAR/USDC, ALGO/USDC, ADA/USDC
- LINK/USDC, IOTA/USDC, VET/USDC, XDC/USDC, ONDO/USDC
- BTC/USDC, ETH/USDC (personal deployment)

### Compliance verification
```bash
grep -rn "USDT" src/ --include="*.py" | grep -v "NO USDT\|USDT ALLOWED\|compliance"
```

---

## Agent System (9 personalities)

### 6 Audit Agents
| Agent | Personality | Focus |
|-------|------------|-------|
| SecurityAuditor | Red teamer | OWASP, auth, secrets, injection |
| PerformanceAnalyst | Latency hunter | Blocking I/O, memory, async |
| TradingLogicReviewer | Burned quant | Fees, spreads, Kelly, rounding |
| RiskAuditor | Crash survivor | Limits, drawdown, emergency stop |
| MiCAComplianceChecker | EU regulator | USDT scan, whitelist consistency |
| CodeQualityGuardian | Senior architect | Dead code, duplication, types |

### 3 Research Agents
| Agent | Focus |
|-------|-------|
| MarketSentimentAgent | Fear/greed, news sentiment |
| TechnicalAnalysisAgent | RSI, BB, MACD per pair via ccxt |
| StrategyPerformanceAgent | Weight rebalancing recommendations |

---

## Production Safety

- **API auth**: API key on all POST endpoints (set `SOVEREIGNFORGE_API_KEY` env var)
- **Localhost binding**: Dashboard API on 127.0.0.1:8420 only
- **Atomic state writes**: paper_trading_state.json uses write-to-temp-then-rename
- **Log rotation**: 100MB max, 5 backups
- **Multi-layer safety gate**: Both env var AND config must agree to go live
- **Model backup**: `backup_models()` before retraining, keeps last 3
- **Health watchdog**: Polls /api/health, restarts on 3 consecutive failures
- **WebSocket limit**: Max 10 concurrent connections
- **Quarter-Kelly**: Conservative position sizing (0.25 fraction)
- **$50 capital floor**: Halts all trading if breached

---

## Architecture Notes

- **Async ccxt**: Exchange operations use `ccxt.async_support` with lazy initialization
- **RegimeDetector**: Classifies market as trending/ranging/volatile, adjusts strategy weights
- **CointegrationDetector**: ADF test + z-score for pairs arbitrage
- **DynamicRiskAdjustment**: VaR/ES circuit breakers wired into pipeline
- **Capital tiers**: micro ($0-500), small ($500-2k), medium ($2k-5k), standard ($5k+)
- **Training improvements**: Embargo gap, noise injection, SWA, temporal dropout, Huber beta=0.1
