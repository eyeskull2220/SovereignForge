# SovereignForge — Working Context

## Current Date: March 12, 2026

## Current Status

- **Version**: v1.1.1
- **Python Tests**: 331 passing, 80 skipped (GPU/torch/scipy/prometheus markers)
- **Dashboard Tests**: 32 passing (7 test suites — App + 6 components)
- **Total Tests**: 363 across 12 test files + 7 dashboard test files
- **Lint**: Clean — ruff passes on both src/ and tests/
- **TypeScript**: Clean — `tsc --noEmit` passes for dashboard
- **MiCA Compliance**: Clean — 0 USDT violations in src/
- **Models**: 5/10 above 80% accuracy threshold, 4 need retraining, 1 missing (VET/USDC)
- **Dashboard**: 6 components, 32 tests, TypeScript clean
- **CI/CD**: 3 workflows active (test, lint, build) — test workflow hardened, no `|| true`
- **Infrastructure**: Docker/K8s manifests ready

## What's Left

### Must Fix (Needs GPU)

| Issue | Location | Fix |
|-------|----------|-----|
| 4 models below 80% threshold | ADA 76.9%, XLM 78.1%, ETH 79.5%, IOTA 79.8% | Retrain via `gpu_train.py` |
| VET/USDC model missing | `models/` | Fetch data with `src/data_fetcher.py`, train with `gpu_train.py` |

### Should Fix

| Issue | Location | Fix |
|-------|----------|-----|
| Mock services in production pipeline | `src/live_arbitrage_pipeline.py` | Ensemble wired — mocks only used when deps missing (e.g. no torch) |

## Commit History (Recent)

| Commit | Description |
|--------|-------------|
| `458117d` | chore: update dashboard package-lock.json |
| `eb24c6a` | test: add 32 dashboard tests — App + 6 component test suites |
| `ccd6038` | fix: harden CI test workflow + clean up WORKING.md |
| `1d2daf2` | test: add 102 tests for 8 more untested modules |
| `56ef916` | test: add 88 tests for 5 previously untested modules |
| `18ddd2e` | feat: wire StrategyEnsemble into live pipeline as collective brain |
| `3d98318` | perf: optimize training, inference, data pipeline, and execution |
| `7d418a2` | feat: multi-strategy training pipeline + collective brain ensemble |
| `9c5a8d6` | test: add 21 data integration tests + balance check edge case + cleanup |
| `2db7c3d` | fix: load trained ML weights + add pre-trade balance validation |
| `bd53da6` | feat: production/development mode pipeline + readiness checks |
| `5e12b8b` | refactor: major cleanup — delete 75 stale files, add 81 new tests |

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
| Performance Optimization | Done — mixed precision, DataLoader, async gather, concurrent execution |
| Multi-Strategy Pipeline | Done — 4 architectures, collective brain ensemble, strategy config |
| Test Coverage Expansion | Done — 363 tests across Python + dashboard |
| CI Hardening | Done — no `|| true`, full deps, single test step |

## Next Priorities

1. **Train all strategies on GPU** — `python gpu_train.py --strategy all --all-pairs --epochs 100 --gpu-monitor`
2. **Retrain failing models** — IOTA (0.2% gap), ETH (0.5%), XLM (1.9%), ADA (3.1%) — needs GPU
3. **Train VET/USDC** model from scratch — needs GPU
4. **Wire real services** in `src/live_arbitrage_pipeline.py` — replace mocks with real inference/data

## Test Commands

```bash
# Python tests (full suite, excluding network-dependent)
PYTHONPATH=src python -m pytest tests/ -v --tb=short \
  --ignore=tests/test_websocket_integration.py \
  --ignore=tests/test_integration.py

# Dashboard tests
cd dashboard && CI=true npm test -- --watchAll=false

# TypeScript type check
cd dashboard && npx tsc --noEmit

# MiCA compliance check
grep -rn "USDT" src/ --include="*.py" | grep -v "NO USDT\|USDT ALLOWED\|USDT PAIRS\|compliance.py:3[89]\|gpu_accelerated"

# Lint
ruff check src/ --select E,W,F,I --ignore E501,F401,E402,F841,E741
ruff check tests/ --select E,W,F,I --ignore E501,F401,E402
```

## Guardrails

- **MiCA**: Only USDC/RLUSD pairs. No USDT. No BTC/ETH in personal deployment.
- **Async**: Never use blocking I/O. No `time.sleep()` in async code.
- **Security**: No hardcoded secrets. `weights_only=True` in all torch.load calls.
- **Tests**: Must pass before committing. Update this file after changes.
