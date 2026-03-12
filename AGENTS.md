# SovereignForge — Agent Operating Rules

## Version: v1.1.1

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
- Prefix: `feat:`, `fix:`, `perf:`, `docs:`, `test:`, `refactor:`, `chore:`
- Tests must pass before committing
- Update `WORKING.md` after significant changes

## Known Open Issues

### BLOCKERS (system won't run without these)

| Problem | Where | Fix |
|---------|-------|-----|
| Deps not installed | `requirements.txt` | `pip install -r requirements.txt` |
| API keys empty | `config/api_keys.json` | Fill real exchange keys |

### GPU-DEPENDENT (cannot fix without GPU)

| Problem | Where | Fix |
|---------|-------|-----|
| 4 models below 80% accuracy | `models/` metadata JSONs | Retrain via `gpu_train.py` |
| VET/USDC model missing | `models/` | Fetch data + train new model |
| Mock services in pipeline | `src/live_arbitrage_pipeline.py` | Needs torch for real inference |

### ALL RESOLVED

| Problem | Resolution |
|---------|-----------|
| Mock services in prod pipeline | `bd53da6` — Pipeline has `mode` config: production requires real services |
| asyncio event loop in sync methods | `93ed347` — Replaced with `asyncio.run()` |
| Model weights not loaded | `2db7c3d` — `AdvancedArbitrageDetector` with `strict=False` |
| No pre-trade balance check | `2db7c3d` — `_check_sufficient_balance()` added |
| `risk_manager.py` + `risk_management.py` | `0a10a9a` — Consolidated into `risk_management.py` |
| `compliance.py` + `mica_compliance.py` | `5e12b8b` — `mica_compliance.py` deleted |
| `cache.py` + `cache_layer.py` | `5e12b8b` — `cache.py` deleted |
| 8 root `.tsx` files | `cf7a50a` — Deleted |
| 3 stub `.pth` files | `5e12b8b` — Deleted |
| `monitoring/dashboard/` scaffold | `5e12b8b` — Deleted |
| `warm_start_state.json` (18MB) | `.gitignore` — Untracked |
| `time.sleep(300)` blocking | `93ed347` — `threading.Event.wait(timeout=300)` |
| CI `|| true` on test steps | `ccd6038` — Removed, tests now fail the build |
| Stale CRA test (dashboard) | `eb24c6a` — Replaced with 32 real component tests |

## Testing

```bash
# Python tests (363 total: 331 passing + 80 skipped)
PYTHONPATH=src python -m pytest tests/ -v --tb=short \
  --ignore=tests/test_websocket_integration.py \
  --ignore=tests/test_integration.py

# Dashboard tests (32 passing)
cd dashboard && CI=true npm test -- --watchAll=false

# Lint
ruff check src/ --select E,W,F,I --ignore E501,F401,E402,F841,E741
ruff check tests/ --select E,W,F,I --ignore E501,F401,E402

# TypeScript
cd dashboard && npx tsc --noEmit
```

Test markers (skipped in CI): `@pytest.mark.gpu`, `@pytest.mark.network`, `@pytest.mark.slow`

## Architecture Notes

- Entry point: `src/main.py production`
- Dashboard: `dashboard/` (React 19, TypeScript, 6 components, 7 test suites)
- Models: `models/strategies/arbitrage_*_usdc_binance.pth` (73MB each, PyTorch)
- Config: `config/` (trading, risk, deployment, API keys)
- Docker: `docker-compose.yml` (app + Redis + Prometheus + Grafana)
- K8s: `k8s/` (11 manifests)
- CI: `.github/workflows/` (test, lint, build)
- Source: `src/` (40 Python modules)
- Tests: `tests/` (12 Python test files) + `dashboard/src/` (7 TypeScript test files)
