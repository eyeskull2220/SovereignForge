# SovereignForge — Agent Operating Rules

## Session Start

1. Read `CLAUDE.md` — project structure, commands, conventions
2. Read `WORKING.md` — current priorities, blockers, what's broken
3. Read `TODO_ENHANCEMENTS.md` — open bugs with exact file:line locations
4. `git status` — check branch, uncommitted changes
5. `python -m pytest tests/ -v --tb=short` — verify tests pass before touching code

## MiCA Compliance — NEVER VIOLATE

**Allowed pairs only:**
- XRP/USDC, XLM/USDC, HBAR/USDC, ALGO/USDC, ADA/USDC
- LINK/USDC, IOTA/USDC, XDC/USDC, ONDO/USDC, VET/USDC
- XRP/RLUSD, XLM/RLUSD, ADA/RLUSD

**Forbidden:**
- No USDT pairs anywhere (not MiCA compliant)
- No BTC/ETH in personal deployment (institutional only)
- No external custody, no public offering

**Before every commit, verify:**
```bash
grep -rn "USDT" src/ --include="*.py" | grep -v "NO USDT\|USDT ALLOWED\|USDT PAIRS\|compliance.py:3[89]\|gpu_accelerated"
```
Must return zero results. CI enforces this.

## Code Standards

- **Async-first**: All I/O uses async/await. Never block the event loop.
- **Type hints**: Annotate all function signatures.
- **Error handling**: try/except with structlog logging. No bare `except:`.
- **Security**: No hardcoded secrets. No `weights_only=False` in torch.load.
- **No Windows paths**: No `E:\\` or backslashes in file paths.

## Commit Rules

- Small, single-purpose commits
- Prefix: `feat:`, `fix:`, `perf:`, `docs:`, `test:`, `refactor:`
- Tests must pass before committing
- Update `WORKING.md` after significant changes

## Known Problems Quick Reference

Concise guide to every open issue. Fix these in priority order.

### BLOCKERS (system won't run)

| Problem | Where | Fix |
|---------|-------|-----|
| Deps not installed | `requirements.txt` | `pip install -r requirements.txt` |
| API keys empty | `config/api_keys.json` | Fill real exchange keys |

### BUGS (incorrect behavior)

| Problem | Where | Fix |
|---------|-------|-----|
| ~~Mock services in prod pipeline~~ | `src/live_arbitrage_pipeline.py` | **RESOLVED** — Pipeline now has `mode` config: `"production"` requires real services (raises `ServiceInitError`), `"development"` allows mocks with warnings. Added `start()`/`stop()` lifecycle and `get_readiness_check()`. |
| ~~asyncio event loop in sync methods~~ | `src/main.py` | **RESOLVED** — Replaced `new_event_loop()` / `run_until_complete()` with `asyncio.run()` in `run_backtest()` and `run_paper_trading()` |
| ~~Model weights not loaded~~ | `src/realtime_inference.py:233` | **RESOLVED** — `_create_model_from_metadata()` now imports `AdvancedArbitrageDetector` (LSTM+attention) matching trained `.pth` files. `load_state_dict()` uncommented with `strict=False` + error handling. `_weights_status` dict tracks which models have real vs random weights. |
| ~~No pre-trade balance check~~ | `src/order_executor.py` | **RESOLVED** — Added `_check_sufficient_balance()` that verifies quote currency on buy exchange and base currency on sell exchange before placing orders. `PaperTradingExecutor` overrides with paper balance checks. Post-trade balance audit logging added. |
| 4 models below 80% accuracy | `models/` metadata JSONs | Retrain via `gpu_train.py` with tuned hyperparams (see TODO_ENHANCEMENTS.md C3-C6) |
| VET/USDC model missing entirely | `models/` | Fetch data with `src/data_fetcher.py`, train with `gpu_train.py` |
| ~~time.sleep(300) blocks thread~~ | `src/model_retrainer.py` | **NOT A BUG** — `_stop_event.wait(timeout=300)` in daemon thread is correct; interruptible via `stop_monitoring()` |
| ~~monitoring.py not wired to app~~ | `src/monitoring.py` | **RESOLVED** — `MetricsCollector` already wired via `_create_metrics_collector()` in main.py. `AlertManager` used independently; main.py has its own `_NoOpAlertManager` wrapping `multi_channel_alerts`. |
| ~~cache.py has empty methods~~ | `src/cache.py` | **RESOLVED** — `cache.py` was deleted in previous cleanup. `cache_layer.py` is the sole cache implementation. |

### CLEANUP (duplicates to consolidate)

| Duplicate Pair | Keep | Delete/Merge |
|---------------|------|-------------|
| ~~`risk_management.py` + `risk_manager.py`~~ | **RESOLVED** | Consolidated into `risk_management.py`, `risk_manager.py` deleted |
| ~~`compliance.py` + `mica_compliance.py`~~ | **RESOLVED** | `mica_compliance.py` deleted in previous cleanup |
| ~~`cache.py` + `cache_layer.py`~~ | **RESOLVED** | `cache.py` deleted, `cache_layer.py` is sole implementation |
| ~~`sovereignforge_real.py` + `sovereignforge_working.py`~~ | **RESOLVED** | Both deleted in previous cleanup |
| ~~8 root `.tsx` files~~ | **RESOLVED** | All deleted in previous cleanup |
| ~~3 stub `.pth` files (<200B)~~ | **RESOLVED** | Deleted + added to `.gitignore` |
| ~~`monitoring/dashboard/` scaffold~~ | **RESOLVED** | Deleted in previous cleanup |
| ~~`warm_start_state.json` (18MB)~~ | **RESOLVED** | Added to `.gitignore` |

## Testing

```bash
# All tests
python -m pytest tests/ -v --tb=short

# Specific suites
python -m pytest tests/test_compliance_models.py -v
python -m pytest tests/test_arbitrage_detector.py -v
python -m pytest tests/test_integration.py -v

# GPU tests (needs NVIDIA GPU)
python test_cuda.py
```

**Current: 170+ tests passing**

Test markers (skipped in CI): `@pytest.mark.gpu`, `@pytest.mark.network`, `@pytest.mark.slow`

## Architecture Notes

- Entry point: `src/main.py production`
- Dashboard: `dashboard/` (React 19, Tailwind, WebSocket to backend)
- Models: `models/strategies/arbitrage_*_usdc_binance.pth` (73MB each, PyTorch)
- Config: `config/` (trading, risk, deployment, API keys)
- Docker: `docker-compose.yml` (app + Redis + Prometheus + Grafana)
- K8s: `k8s/` (11 manifests)
- CI: `.github/workflows/` (test, lint, build)
