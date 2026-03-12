# SovereignForge — Enhancement Tracker

> **Version**: v1.1.1
> **Last Updated**: March 12, 2026
> **Python Tests**: 331 passing, 80 skipped | **Dashboard Tests**: 32 passing
> **Overall Health**: 92%+ production-ready (blocked only on GPU training)

---

## BLOCKERS — Fix Before Live Testing

| # | Issue | Where | How to Fix |
|---|-------|-------|------------|
| B1 | Python deps not installed | `requirements.txt` | `pip install -r requirements.txt` |
| B2 | Exchange API keys empty | `config/api_keys.json` | Fill in real Binance/Coinbase/Kraken keys |

---

## OPEN — Needs GPU

| # | Issue | File | How to Fix |
|---|-------|------|------------|
| C3 | ADA/USDC model 76.9% (needs 80%) | `models/ADAUSDC_metadata.json` | Retrain: increase epochs, add data augmentation |
| C4 | ETH/USDC model 79.5% (needs 80%) | `models/ETHUSDC_metadata.json` | Retrain: add LR warmup + cosine schedule |
| C5 | XLM/USDC model 78.1% (needs 80%) | `models/XLMUSDC_metadata.json` | Retrain: tune dropout rate |
| C6 | IOTA/USDC model 79.8% (needs 80%) | `models/IOTAUSDC_metadata.json` | Retrain: only 0.2% gap, small LR bump |
| C7 | VET/USDC has no model | `models/` (missing) | Fetch data via `src/data_fetcher.py`, train via `gpu_train.py` |

---

## ENHANCEMENTS — Prioritized Backlog

### HIGH — Next Up (After GPU Training)

| Task | Details |
|------|---------|
| Wire real services | Replace mocks in `live_arbitrage_pipeline.py` with real inference + data services |
| K8s image tags | Update `k8s/sovereignforge-deployment.yaml` to use commit-SHA tags instead of `latest` |
| MCP server | Implement `src/mcp_server.py` with tools: `get_opportunities`, `execute_trade`, `get_portfolio` |

### MEDIUM — Wave 3-4

| Task | Details |
|------|---------|
| Dashboard polish | Add candlestick charts (lightweight-charts), technical indicators (RSI, MACD, Bollinger) |
| Performance | Profile arbitrage hot path (<10ms target), add `__slots__` on hot paths |
| Security | Move secrets from `config/api_keys.json` to env vars/vault, encrypt `.pth` files at rest |
| Multi-asset | Add SOL/USDC, MATIC/USDC, DOT/USDC, AVAX/USDC (update `compliance.py` whitelist) |

### LOW — Wave 4+

| Task | Details |
|------|---------|
| Self-healing | Auto-restart dead components, auto-retrain when accuracy <78% for 24h |
| Documentation | `docs/architecture.md` diagram, `docs/api.md` endpoints |
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

## COMPLETED (All Resolved)

- [x] B3-B7: Model paths, Dockerfile CMD, ComplianceEngine alias, shebang fix
- [x] C1-C2: Dashboard App.tsx rewritten, components moved to `dashboard/src/components/`
- [x] C8-C9: LINK/IOTA checksums fixed, test_wave2.py created
- [x] C10: Mock services → pipeline has mode config (production/development)
- [x] C11: `torch.load` changed to `weights_only=True` in 3 files
- [x] C12: All 60+ USDT references removed from src/
- [x] C13: `asyncio.run()` crash fixed
- [x] C14: `gpu_max_test.py` return value bug fixed
- [x] A1-A15: USDT purge, Windows paths, import guards, port conflict, useWebSocket, main.py defaults
- [x] M1-M2: monitoring.py wired, cache.py deleted (cache_layer.py is canonical)
- [x] CI/CD: All 3 GitHub Actions workflows created + hardened (test, lint, build)
- [x] Phase 9-12: Paper trading, dashboard, strategy optimization, risk management, SMC integration
- [x] Multi-strategy training pipeline: 4 architectures, collective brain ensemble
- [x] Performance optimization: mixed precision, DataLoader, async gather, concurrent execution
- [x] Test coverage: 363 tests (331 Python + 32 dashboard)
- [x] risk_manager.py consolidated into risk_management.py
- [x] 75 stale files deleted (root scripts, dead docs, orphaned .tsx)
- [x] Dashboard tests: 7 test suites, 32 tests, all passing
- [x] CI test workflow: removed `|| true`, installed all deps
