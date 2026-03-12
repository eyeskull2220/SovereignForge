# SovereignForge — Working Context

## Current Date: March 12, 2026

## Current Status

- **Tests**: 71/73 passing (97.3%)
- **MiCA Compliance**: Clean — 0 USDT violations in src/
- **Models**: 5/10 above 80% accuracy threshold, 4 need retraining, 1 missing (VET/USDC)
- **Dashboard**: Functional — 6 components wired in `dashboard/src/components/`
- **CI/CD**: 3 workflows active (test, lint, build)
- **Infrastructure**: Docker/K8s manifests ready, deps not installed in current env

## What's Broken

### Must Fix

| Issue | Location | Quick Fix |
|-------|----------|-----------|
| Mock services in production pipeline | `src/live_arbitrage_pipeline.py:153,160` | Wire real `WebSocketConnector` and `RealtimeInferenceService` instead of mocks |
| `asyncio.run()` in async context | `src/main.py:738,802` | Replace with `await` calls |
| 4 models below 80% threshold | ADA 76.9%, XLM 78.1%, ETH 79.5%, IOTA 79.8% | Retrain with tuned hyperparams via `gpu_train.py` |
| VET/USDC model missing | `models/` — no file or metadata | Fetch data, train fresh model |
| `time.sleep(300)` blocking | `src/model_retrainer.py:588` | Use `asyncio.sleep(300)` |
| monitoring.py has pass stubs | `src/monitoring.py` | Implement stubs, wire into `src/main.py` |

### Should Fix (Cleanup)

| Issue | Location |
|-------|----------|
| 5 duplicate file pairs in src/ | See AGENTS.md cleanup table |
| 8 orphaned .tsx files in repo root | Delete — real copies exist in `dashboard/src/components/` |
| 3 stub .pth files (<200 bytes) | `models/strategies/dca_*`, `fib_*`, `grid_*` — not real models |
| Dead Vite project | `monitoring/dashboard/` — scaffolded, no real code |
| 18MB `warm_start_state.json` | Consider .gitignore or lazy-loading |

### Not Broken (Confirmed Working)

- Dashboard `App.tsx` — real implementation, not CRA stub
- `useWebSocket.ts` — full hook with reconnect/backoff
- All 6 dashboard components — in correct location
- CI workflows — all 3 exist and functional
- `tests/test_wave2.py` — exists in tests/
- MiCA compliance — zero USDT violations, CI enforced
- 9 real arbitrage models (73MB each) in `models/strategies/`

## Completed Phases

| Phase | Status |
|-------|--------|
| Phase 2: Infrastructure | Done — model loading, WebSocket, risk alerts |
| Phase 3: Performance | Done — GPU fixes, rate limiting, circuit breaker, batching |
| Phase 6: Production | Done — Docker hardening, dashboard, CLI, installer |
| Phase 9: Strategy | Done — paper trading, dashboard, risk management |
| Phase 10: Deployment | Done — live testing, Docker Compose, monitoring, docs |
| Phase 11: Personal Use | Done — CLI wrapper, auto-recovery, Windows compat |
| Phase 12: Smart Money | Done — SMC library, enhanced arbitrage, Kraken support |

## Next Priorities

1. **Fix mock services** in `src/live_arbitrage_pipeline.py` — replace with real inference/data services
2. **Fix asyncio.run()** in `src/main.py:738,802` — use await
3. **Retrain failing models** — IOTA (0.2% gap), ETH (0.5%), XLM (1.9%), ADA (3.1%)
4. **Train VET/USDC** model from scratch
5. **Consolidate duplicates** — merge risk_management/risk_manager, compliance/mica_compliance, cache/cache_layer
6. **Delete orphaned files** — root .tsx copies, dead monitoring/dashboard, stub .pth files
7. **Wire monitoring** — implement pass stubs, connect to main.py
8. **Expand test coverage** — write tests for main.py, order_executor, backtester (target >85%)

## Test Commands

```bash
# All tests
python -m pytest tests/ -v --tb=short

# MiCA compliance check
grep -rn "USDT" src/ --include="*.py" | grep -v "NO USDT\|USDT ALLOWED\|USDT PAIRS\|compliance.py:3[89]\|gpu_accelerated"

# Dashboard build
cd dashboard && npm run build

# Docker
docker-compose up
```

## Guardrails

- **MiCA**: Only USDC/RLUSD pairs. No USDT. No BTC/ETH in personal deployment.
- **Async**: Never use blocking I/O. No `time.sleep()` in async code.
- **Security**: No hardcoded secrets. `weights_only=True` in all torch.load calls.
- **Tests**: Must pass before committing. Update this file after changes.
