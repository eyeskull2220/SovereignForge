# SovereignForge — Enhancement Tracker

> **Last Updated**: 2026-03-12
> **Test Status**: 71/73 passing (97.3%)
> **Overall Health**: 75% production-ready

---

## BLOCKERS — Fix Before Live Testing

| # | Issue | Where | How to Fix |
|---|-------|-------|------------|
| B1 | Python deps not installed | `requirements.txt` | `pip install -r requirements.txt` |
| B2 | Exchange API keys empty | `config/api_keys.json` | Fill in real Binance/Coinbase/Kraken keys |

---

## OPEN BUGS — Fix Before Paper Trading

| # | Bug | File:Line | How to Fix |
|---|-----|-----------|------------|
| C3 | ADA/USDC model 76.9% (needs 80%) | `models/ADAUSDC_metadata.json` | Retrain: increase epochs, add data augmentation in `src/ml_trainer.py` |
| C4 | ETH/USDC model 79.5% (needs 80%) | `models/ETHUSDC_metadata.json` | Retrain: add LR warmup + cosine schedule in `src/ml_trainer.py` |
| C5 | XLM/USDC model 78.1% (needs 80%) | `models/XLMUSDC_metadata.json` | Retrain: tune dropout rate in `src/gpu_arbitrage_model.py` |
| C6 | IOTA/USDC model 79.8% (needs 80%) | `models/IOTAUSDC_metadata.json` | Retrain: only 0.2% gap, small LR bump should fix |
| C7 | VET/USDC has no model or metadata | `models/` (missing) | Fetch VET/USDC data via `src/data_fetcher.py`, train new model via `gpu_train.py` |
| C10 | MockInferenceService/MockDataService in prod pipeline | `src/live_arbitrage_pipeline.py:153,160,311,322` | Replace `MockDataService()` with `WebSocketConnector()`, replace `MockInferenceService()` with `RealtimeInferenceService()` |
| C13 | `asyncio.run()` crashes if called from async context | `src/main.py:738,802` | Replace with `await run_async_backtest()` or use `loop.run_until_complete()` |

---

## CLEANUP — Duplicate Files to Consolidate

| Files | Problem | Fix |
|-------|---------|-----|
| `src/risk_management.py` + `src/risk_manager.py` | Both implement risk mgmt (~1250 lines total) | Audit overlap, keep one, redirect imports |
| `src/compliance.py` + `src/mica_compliance.py` | Both implement MiCA compliance | Keep `compliance.py` (121 lines, cleaner), merge unique logic from `mica_compliance.py` |
| `src/cache.py` + `src/cache_layer.py` | Both implement caching | Keep `cache_layer.py` (newer, complete), delete `cache.py` |
| `src/sovereignforge_real.py` + `src/sovereignforge_working.py` | Thin ~70-80 line entry points | Delete both, `src/main.py` is the real entry point |
| 8 root `.tsx` files | Duplicates of `dashboard/src/components/*` | Delete: `AlertsPanel.tsx`, `Header.tsx`, `PnlChart.tsx`, `PositionsTable.tsx`, `RiskGauges.tsx`, `RiskMetrics.tsx`, `App.tsx`, `main.tsx` from repo root |

---

## MINOR ISSUES

| # | Issue | File:Line | How to Fix |
|---|-------|-----------|------------|
| A10 | `warm_start_state.json` is 18MB, loaded into memory | root | Lazy-load or paginate; consider `.gitignore`-ing it |
| A11 | `time.sleep(300)` blocks retraining loop | `src/model_retrainer.py:588` | Replace with `await asyncio.sleep(300)` or `threading.Event.wait(timeout=300)` |
| A12 | 3 tiny stub `.pth` files (not real models) | `models/strategies/dca_eth_usdc_coinbase.pth` (125B), `fib_btc_usdc_binance.pth` (116B), `grid_xrp_usdc_kraken.pth` (117B) | Train real strategy models or delete stubs |
| A14 | `monitoring/dashboard/` is dead Vite scaffold | `monitoring/dashboard/` | Either implement or `rm -rf monitoring/dashboard/` |
| M1 | `src/monitoring.py` has 2 `pass` stubs, not wired to main | `src/monitoring.py` | Implement stub methods, add `monitoring.setup()` call in `src/main.py` startup |
| M2 | `src/cache.py` has 2 `pass` stubs | `src/cache.py:286,292` | Implement `warm_market_data_cache()` and `warm_arbitrage_cache()` or delete file (see cleanup above) |

---

## ENHANCEMENTS — Prioritized Backlog

### HIGH — Next Up

| Task | Details |
|------|---------|
| Dashboard polish | Add candlestick charts (lightweight-charts), technical indicators (RSI, MACD, Bollinger), backtesting view |
| Test coverage | Write tests for: `main.py`, `order_executor.py`, `backtester.py`, `performance_analyzer.py`, `data_integration_service.py`. Add `conftest.py` with shared fixtures. Target >85% |
| K8s image tags | Update `k8s/sovereignforge-deployment.yaml` to use commit-SHA tags instead of `latest` |
| Wire monitoring | Connect `src/monitoring.py` to `src/main.py` startup, expose `/metrics` Prometheus endpoint |

### MEDIUM — Wave 3-4

| Task | Details |
|------|---------|
| MCP server | Implement `src/mcp_server.py` with tools: `get_opportunities`, `execute_trade`, `get_portfolio`, `run_backtest` |
| Performance | Profile arbitrage hot path (<10ms target), add `__slots__` on hot paths, Redis Streams for order bus |
| Security | Move secrets from `config/api_keys.json` to env vars/vault, encrypt `.pth` files at rest, add audit log |
| Multi-asset | Add SOL/USDC, MATIC/USDC, DOT/USDC, AVAX/USDC (update `compliance.py` whitelist) |

### LOW — Wave 4+

| Task | Details |
|------|---------|
| Self-healing | Auto-restart dead components, auto-retrain when accuracy <78% for 24h |
| Documentation | `docs/architecture.md` diagram, `docs/api.md` endpoints, `docs/compliance.md` legal |
| Dependency scanning | Add Dependabot or pip-audit to CI |
| Blue-green deploy | Automatic rollback on health check failure |

---

## MODEL ACCURACY STATUS

| Pair | Accuracy | Status | Model File |
|------|----------|--------|------------|
| BTC/USDC | 82.7% | PASS | `models/strategies/arbitrage_btc_usdc_binance.pth` |
| XRP/USDC | 82.6% | PASS | `models/strategies/arbitrage_xrp_usdc_binance.pth` |
| HBAR/USDC | 81.6% | PASS | `models/strategies/arbitrage_hbar_usdc_binance.pth` |
| LINK/USDC | 81.3% | PASS | `models/strategies/arbitrage_link_usdc_binance.pth` |
| ALGO/USDC | 80.5% | PASS | `models/strategies/arbitrage_algo_usdc_binance.pth` |
| IOTA/USDC | 79.8% | FAIL (-0.2%) | `models/strategies/arbitrage_iota_usdc_binance.pth` |
| ETH/USDC | 79.5% | FAIL (-0.5%) | `models/strategies/arbitrage_eth_usdc_binance.pth` |
| XLM/USDC | 78.1% | FAIL (-1.9%) | `models/strategies/arbitrage_xlm_usdc_binance.pth` |
| ADA/USDC | 76.9% | FAIL (-3.1%) | `models/strategies/arbitrage_ada_usdc_binance.pth` |
| VET/USDC | N/A | MISSING | No model or metadata exists |

**5/10 passing 80% threshold. 4 need retraining, 1 needs fresh training.**

---

## COMPLETED (Reference)

- [x] B3-B7: Model paths, Dockerfile CMD, ComplianceEngine alias, shebang fix
- [x] C1-C2: Dashboard App.tsx rewritten, components moved to `dashboard/src/components/`
- [x] C8-C9: LINK/IOTA checksums fixed, test_wave2.py created
- [x] C11: `torch.load` changed to `weights_only=True` in 3 files
- [x] C12: All 60+ USDT references removed from src/
- [x] C14: `gpu_max_test.py` return value bug fixed
- [x] A1-A9, A13, A15: USDT purge, Windows paths, import guards, port conflict, useWebSocket, main.py defaults
- [x] CI/CD: All 3 GitHub Actions workflows created (test, lint, build)
- [x] Phase 9-12: Paper trading, dashboard, strategy optimization, risk management, SMC integration, personal CLI
