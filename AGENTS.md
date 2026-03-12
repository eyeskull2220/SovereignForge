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
| asyncio.run() in async context | `src/main.py:738` | Change `results = asyncio.run(run_async_backtest())` to `results = await run_async_backtest()` |
| asyncio.run() in async context | `src/main.py:802` | Change `trade_result = asyncio.run(self.order_executor.execute_arbitrage_trade(opportunity))` to use await |
| 4 models below 80% accuracy | `models/` metadata JSONs | Retrain via `gpu_train.py` with tuned hyperparams (see TODO_ENHANCEMENTS.md C3-C6) |
| VET/USDC model missing entirely | `models/` | Fetch data with `src/data_fetcher.py`, train with `gpu_train.py` |
| time.sleep(300) blocks thread | `src/model_retrainer.py:588` | Replace with `await asyncio.sleep(300)` |
| monitoring.py not wired to app | `src/monitoring.py` | Has 2 `pass` stubs. Implement them, call from `src/main.py` startup |
| cache.py has empty methods | `src/cache.py:286,292` | `warm_market_data_cache()` and `warm_arbitrage_cache()` are `pass`. Implement or delete file (duplicate of cache_layer.py) |

### CLEANUP (duplicates to consolidate)

| Duplicate Pair | Keep | Delete/Merge |
|---------------|------|-------------|
| ~~`risk_management.py` + `risk_manager.py`~~ | **RESOLVED** | Consolidated into `risk_management.py`, `risk_manager.py` deleted |
| `compliance.py` + `mica_compliance.py` | `compliance.py` | Merge unique logic from `mica_compliance.py` |
| `cache.py` + `cache_layer.py` | `cache_layer.py` | Delete `cache.py`, update imports |
| `sovereignforge_real.py` + `sovereignforge_working.py` | Neither (use `main.py`) | Delete both |
| 8 root `.tsx` files | `dashboard/src/components/*` | Delete root copies |
| ~~3 stub `.pth` files (<200B)~~ | **RESOLVED** | Deleted + added to `.gitignore` |
| `monitoring/dashboard/` scaffold | None | Delete dead Vite project |
| `warm_start_state.json` (18MB) | Consider .gitignore | Lazy-load or compress |

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

**Current: 155+ tests passing**

Test markers (skipped in CI): `@pytest.mark.gpu`, `@pytest.mark.network`, `@pytest.mark.slow`

## Architecture Notes

- Entry point: `src/main.py production`
- Dashboard: `dashboard/` (React 19, Tailwind, WebSocket to backend)
- Models: `models/strategies/arbitrage_*_usdc_binance.pth` (73MB each, PyTorch)
- Config: `config/` (trading, risk, deployment, API keys)
- Docker: `docker-compose.yml` (app + Redis + Prometheus + Grafana)
- K8s: `k8s/` (11 manifests)
- CI: `.github/workflows/` (test, lint, build)
