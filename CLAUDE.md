# CLAUDE.md — SovereignForge

## Project Overview

SovereignForge is a GPU-accelerated cryptocurrency arbitrage detection system with real-time monitoring, AI-powered opportunity filtering, and MiCA compliance enforcement. It is a hybrid Python/TypeScript monorepo combining a Python ML/trading backend with a React dashboard frontend.

**Status**: Production-ready (Phase 12 complete, 92%+ completion).

---

## Repository Structure

```
SovereignForge/
├── src/                    # Python backend (43 modules) — core trading, ML, compliance
├── dashboard/              # React TypeScript frontend (trading dashboard)
│   └── src/components/     # PositionsTable, RiskMetrics, PnlChart, AlertsPanel, etc.
├── tests/                  # pytest test suite (9 files, 71/73 passing)
├── models/                 # Trained PyTorch model checkpoints (.pth) and metadata
│   ├── strategies/         # Per-strategy models (arbitrage, DCA, grid, fibonacci)
│   └── registry/           # Model metadata registry
├── config/                 # Application configuration (trading, deployment, risk, API keys)
├── k8s/                    # Kubernetes manifests (deployment, service, configmap, secrets, PVC, RBAC)
├── docker/                 # Docker build/run scripts
├── monitoring/             # Prometheus/Grafana dashboards and system monitoring
├── data/                   # Historical and processed market data
├── .github/workflows/      # CI/CD: test.yml, build.yml, lint.yml
├── crewai_agents/          # CrewAI agent definitions
├── litserve_api/           # LitServe model serving API
├── mcp_server/             # Model Context Protocol server
└── core/                   # Core utilities and config
```

### Key Entry Points

| Purpose | Path |
|---------|------|
| Backend CLI | `src/main.py` (production entry: `python3 src/main.py production`) |
| Dashboard | `dashboard/src/App.tsx` |
| GPU Training | `gpu_train.py` |
| Tests | `python -m pytest tests/ -v` |
| Docker dev | `docker-compose up` |
| K8s deploy | `kubectl apply -f k8s/` |

---

## Tech Stack

### Backend (Python 3.10+)
- **Framework**: FastAPI + Uvicorn (async)
- **ML/AI**: PyTorch 2.0+ (CUDA 12.1), Hugging Face transformers (163M-param models)
- **Data**: pandas, numpy, scikit-learn
- **Exchange connectivity**: CCXT (Binance, Coinbase, Kraken)
- **Real-time**: WebSockets, aiohttp, asyncio
- **Database**: aiosqlite (SQLite), asyncpg (PostgreSQL optional)
- **Caching**: Redis (async), in-memory fallback
- **Monitoring**: Prometheus, structlog
- **Alerts**: python-telegram-bot, twilio (SMS)

### Frontend (TypeScript/React)
- **Framework**: React 19, TypeScript 4.9, Create React App
- **UI**: Tailwind CSS 3.4, Lucide React icons
- **Charts**: Chart.js 4.5, Recharts 2.8
- **Real-time**: Custom WebSocket hook (`useWebSocket.ts`)

### DevOps
- **Containers**: Docker (multi-stage, CUDA 12.1 base), Docker Compose
- **Orchestration**: Kubernetes (11 manifests)
- **CI/CD**: GitHub Actions (3 workflows)
- **GPU**: NVIDIA CUDA 12.1, RTX 4060 Ti optimized

---

## Build & Development Commands

### Python Backend
```bash
# Install dependencies
pip install -r requirements.txt          # CPU
pip install -r requirements-gpu.txt      # GPU (CUDA 12.1)

# Run production server
python3 src/main.py production

# Run tests
python -m pytest tests/ -v --tb=short

# Run specific test suites
python -m pytest tests/test_compliance_models.py -v
python -m pytest tests/test_arbitrage_detector.py -v
python -m pytest tests/test_integration.py -v

# GPU tests (requires NVIDIA GPU)
python test_cuda.py
python gpu_status_check.py

# Linting
ruff check src/ --select E,W,F,I --ignore E501,W503,F401,E402,F841,E741
ruff check tests/ --select E,W,F,I --ignore E501,W503,F401,E402
```

### Dashboard (React)
```bash
cd dashboard
npm ci                  # Install dependencies
npm start               # Dev server
npm run build           # Production build
npm test                # Run tests
npx tsc --noEmit        # Type checking
```

### Docker
```bash
docker-compose up                              # Full stack (app + Redis + Prometheus + Grafana)
docker build -t sovereignforge .               # Build image
docker build --target runtime -t sovereignforge .  # Runtime-only stage
```

---

## CI/CD Workflows

### test.yml — Python Tests
- **Triggers**: Push to any branch, PRs to main/master
- **Environment**: Python 3.11, CPU-only PyTorch
- **Runs**: `pytest tests/` (excluding GPU, network, slow tests; 60s timeout)
- **MiCA compliance check**: Scans `src/` for USDT references — fails if any found
- **PYTHONPATH**: Set to `src/` in CI

### lint.yml — Code Quality
- **Linter**: ruff (E, W, F, I rules)
- **Checks**: CRLF detection, hardcoded Windows paths (`E:\\`), model metadata path validation
- **Status**: Advisory-only (non-blocking)

### build.yml — Docker & Dashboard
- **Triggers**: Push to master/main, version tags (`v*`)
- **Docker**: Multi-stage build with BuildKit caching
- **Dashboard**: Node 20, `npm ci`, TypeScript check, `npm run build`

---

## MiCA Compliance — CRITICAL RULES

**MiCA compliance is the top priority. Never violate these rules.**

### Allowed Trading Pairs (Whitelist)
- XRP/USDC, XLM/USDC, HBAR/USDC, ALGO/USDC, ADA/USDC
- LINK/USDC, IOTA/USDC, XDC/USDC, ONDO/USDC, VET/USDC
- XRP/RLUSD, XLM/RLUSD, ADA/RLUSD

### Forbidden
- **No USDT pairs** — USDT is not MiCA-compliant
- **No BTC/ETH in personal deployment** — institutional only
- **No external custody** — local-only execution
- **No public offering** — individual use only

### Compliance Verification
Before committing, verify zero USDT references in `src/`:
```bash
grep -rn "USDT" src/ --include="*.py" | grep -v "NO USDT\|USDT ALLOWED\|USDT PAIRS\|compliance.py:3[89]\|gpu_accelerated"
```
This check runs in CI and **will fail the build** if violations are found.

---

## Code Conventions

### Python
- **Async-first**: All I/O operations must use async/await
- **Type hints**: Full annotation coverage expected
- **Error handling**: Comprehensive try/except with structured logging (structlog)
- **Security**: Non-root containers, secrets via env vars, no hardcoded credentials
- **Performance**: GPU optimization, memory bounds, gradient accumulation
- **Imports**: isort-compatible ordering (enforced by ruff I rules)

### TypeScript/React
- **Strict mode**: Enabled in tsconfig.json
- **Styling**: Tailwind CSS utility classes
- **State management**: React hooks, WebSocket hook for real-time data
- **Target**: ES5, esnext modules, react-jsx

### Commit Messages
Use conventional commit prefixes:
- `feat:` — new feature
- `fix:` — bug fix
- `perf:` — performance improvement
- `docs:` — documentation
- `test:` — test additions/changes
- `refactor:` — code restructuring

Small, single-purpose commits preferred.

---

## Testing

### Test Suite Overview
| File | Coverage |
|------|----------|
| `test_compliance_models.py` | MiCA whitelist enforcement |
| `test_wave2.py` | Wave 2 feature validation |
| `test_arbitrage_detector.py` | Arbitrage detection engine |
| `test_risk_management.py` | Risk control validation |
| `test_telegram_alerts.py` | Alert delivery |
| `test_websocket_integration.py` | Real-time data (skipped in CI) |
| `test_ml_models.py` | ML model validation (skipped in CI) |
| `test_integration.py` | End-to-end integration |

### Test Markers
- `@pytest.mark.gpu` — requires NVIDIA GPU (skipped in CI)
- `@pytest.mark.network` — requires network access (skipped in CI)
- `@pytest.mark.slow` — long-running tests (skipped in CI)

### Current Status
- **71/73 tests passing** (97.3%)
- **Coverage**: ~74%

---

## Configuration

### Environment Variables
Copy `.env.example` to `.env` and configure. Key sections:
- **Database**: PostgreSQL connection, pool settings
- **Cache**: Redis URL and password
- **Trading**: Symbol pairs, exchanges, risk limits
- **Exchange API keys**: Binance, Coinbase, Kraken
- **Monitoring**: Prometheus, Sentry
- **Security**: Encryption keys, JWT secrets

### Config Files (`config/`)
- `trading_config.json` — enabled pairs, position sizes, spreads, dry-run mode
- `deployment_config.json` — Docker registry, K8s replicas, resource limits
- `risk_limits.json` — portfolio risk %, position risk %, Kelly fraction
- `api_keys.json` — exchange API credential template

---

## Session Workflow for AI Agents

### Session Start
1. Read this file (`CLAUDE.md`) for project conventions
2. Read `WORKING.md` for current priorities and known issues
3. Read `AGENTS.md` for detailed operating rules and guardrails
4. Check `git status` for branch state and uncommitted changes
5. Verify tests pass before making changes

### During Development
- Run tests before and after changes: `python -m pytest tests/ -v --tb=short`
- Verify MiCA compliance (no USDT references in `src/`)
- Update `WORKING.md` after significant changes
- Keep commits small and focused

### Pre-Commit Checklist
- [ ] Tests pass
- [ ] MiCA compliance verified (no USDT)
- [ ] Type hints included for new code
- [ ] Error handling is comprehensive
- [ ] No hardcoded secrets or Windows paths
- [ ] WORKING.md updated if needed

---

## Architecture Notes

- **Async everywhere**: The entire backend is async — never use blocking I/O
- **Circuit breakers**: Exchange API calls use exponential backoff with jitter
- **GPU inference**: 163M-parameter transformer models with mixed precision (FP16/FP32)
- **Multi-exchange**: Concurrent data from Binance, Coinbase, Kraken via CCXT
- **WebSocket streaming**: Real-time price feeds with auto-reconnect
- **Horizontal scaling**: Stateless services behind K8s, ready for replica scaling
- **Monitoring**: Prometheus metrics on port 9090, Grafana dashboards on port 3000
