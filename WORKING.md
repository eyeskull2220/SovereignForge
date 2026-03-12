# SovereignForge — Working Context

## Current Date: March 12, 2026

## Current Status

- **Tests**: 193 passing, 2 skipped (GPU markers)
- **Lint**: Clean — ruff passes on both src/ and tests/
- **MiCA Compliance**: Clean — 0 USDT violations in src/
- **Models**: 5/10 above 80% accuracy threshold, 4 need retraining, 1 missing (VET/USDC)
- **Dashboard**: Functional — 6 components wired in `dashboard/src/components/`
- **CI/CD**: 3 workflows active (test, lint, build) — lint workflow fixed (W503 removed)
- **Infrastructure**: Docker/K8s manifests ready, deps not installed in current env

## What's Left

### Must Fix (Needs GPU)

| Issue | Location | Fix |
|-------|----------|-----|
| 4 models below 80% threshold | ADA 76.9%, XLM 78.1%, ETH 79.5%, IOTA 79.8% | Retrain via `gpu_train.py` |
| VET/USDC model missing | `models/` | Fetch data with `src/data_fetcher.py`, train with `gpu_train.py` |

### Should Fix

| Issue | Location | Fix |
|-------|----------|-----|
| Mock services in production pipeline | `src/live_arbitrage_pipeline.py` | Already wired — mocks only used when deps missing (e.g. no torch) |
| ~~3 stub .pth files~~ | ~~`models/strategies/`~~ | Resolved — no stub files remain |
| ~~18MB `warm_start_state.json`~~ | ~~repo root~~ | Resolved — in .gitignore, removed from tracking |

### Recently Fixed

| Fix | Commit |
|-----|--------|
| `asyncio.run()` in async context | `93ed347` — replaced with `loop.run_until_complete()` |
| `time.sleep(300)` blocking | `93ed347` — replaced with `threading.Event.wait(timeout=300)` |
| Monitoring wired into main.py | `93ed347` — factory function with no-op fallback |
| Test suite rewritten (41 tests) | `93ed347` — fixed all async/API mismatches |
| Orphaned .tsx, .py, dead scaffolds deleted | `cf7a50a` — 10 root files + dead dirs |
| risk_manager.py consolidated into risk_management.py | `0a10a9a` — single canonical module |
| All CI lint errors fixed (100+ issues) | `2f94fbe` — imports, newlines, bare except, Windows paths |
| Lint workflow W503 bug fixed | `68739a8` — invalid ruff rule removed |
| 59 root-level .py scripts deleted | pending commit — shadowing duplicates + old scripts |
| 16 stale docs deleted | pending commit — PHASE2_*, handoffs, clinerules, etc. |
| 81 new tests added | pending commit — compliance, monitoring, risk, pipeline, executor |
| test_risk_management.py rewritten | pending commit — matched to actual RiskManager API |
| ML weight loading fixed | `2db7c3d` — inference uses trained AdvancedArbitrageDetector weights |
| Pre-trade balance validation | `2db7c3d` — OrderExecutor checks funds before placing orders |
| Data integration service tests | pending commit — 21 new tests for HybridDataIntegrationService |
| warm_start_state.json untracked | pending commit — removed from git tracking (already in .gitignore) |

### Not Broken (Confirmed Working)

- Dashboard `App.tsx` — real implementation, not CRA stub
- `useWebSocket.ts` — full hook with reconnect/backoff
- All 6 dashboard components — in correct location
- CI workflows — all 3 exist and functional
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

1. **Retrain failing models** — IOTA (0.2% gap), ETH (0.5%), XLM (1.9%), ADA (3.1%) — needs GPU
2. **Train VET/USDC** model from scratch — needs GPU
3. **Wire real services** in `src/live_arbitrage_pipeline.py` — replace mocks with real inference/data
4. **Continue expanding test coverage** — target >85%

## Test Commands

```bash
# All tests (excluding torch-dependent)
PYTHONPATH=src python -m pytest tests/ -v --tb=short \
  --ignore=tests/test_compliance_models.py \
  --ignore=tests/test_ml_models.py \
  --ignore=tests/test_integration.py \
  --ignore=tests/test_websocket_integration.py

# MiCA compliance check
grep -rn "USDT" src/ --include="*.py" | grep -v "NO USDT\|USDT ALLOWED\|USDT PAIRS\|compliance.py:3[89]\|gpu_accelerated"

# Lint
ruff check src/ --select E,W,F,I --ignore E501,F401,E402,F841,E741
ruff check tests/ --select E,W,F,I --ignore E501,F401,E402

# Dashboard build
cd dashboard && npm run build
```

## Guardrails

- **MiCA**: Only USDC/RLUSD pairs. No USDT. No BTC/ETH in personal deployment.
- **Async**: Never use blocking I/O. No `time.sleep()` in async code.
- **Security**: No hardcoded secrets. `weights_only=True` in all torch.load calls.
- **Tests**: Must pass before committing. Update this file after changes.
