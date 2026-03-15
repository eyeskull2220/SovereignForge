# SovereignForge — Agent Operating Rules

## Session Start

1. Read `CLAUDE.md` — project structure, 7 strategies, 7 exchanges, commands
2. Check memory files in `C:\Users\Gino\.claude\projects\C--Users-Gino\memory/` for context
3. `git status` — check branch and uncommitted changes
4. `PYTHONPATH=src python -m pytest tests/test_integration.py -v` — verify tests pass

## MiCA Compliance — NEVER VIOLATE

**Allowed pairs only:**
- XRP/USDC, XLM/USDC, HBAR/USDC, ALGO/USDC, ADA/USDC
- LINK/USDC, IOTA/USDC, VET/USDC, XDC/USDC, ONDO/USDC
- BTC/USDC, ETH/USDC (personal deployment)
- XRP/RLUSD, XLM/RLUSD, ADA/RLUSD

**Forbidden:**
- No USDT pairs anywhere (not MiCA compliant)
- No DOGE (removed from compliance engine)
- No external custody, no public offering

## Using Personality Subagents

The user prefers using Claude Code subagents with personalities for parallel work. Pattern:

```
# Launch agents in parallel
Agent("Risk Auditor fixes", "You are a RISK MANAGEMENT OFFICER...", run_in_background=true)
Agent("Compliance fixes", "You are a MiCA COMPLIANCE OFFICER...", run_in_background=true)
Agent("Performance fixes", "You are a PERFORMANCE ENGINEER...", run_in_background=true)
```

**Key rules for subagents:**
- Each agent works on NON-OVERLAPPING files to avoid conflicts
- Use `run_in_background=true` for parallel execution
- Always specify "Read each file before editing"
- Add "CRITICAL: Do NOT touch src/multi_strategy_training.py" if training is running
- Report results as they complete, verify with tests after all finish

### Available Agent Personalities (10 total)

**6 Audit Agents** (`src/agents/audit_*.py`):
- **SecurityAuditor** (red_team) — 15 years breaking financial systems, paranoid about API keys and injection
- **PerformanceAnalyst** (latency_hunter) — microsecond obsessive, GPU batching, async patterns
- **TradingLogicReviewer** (burned_quant) — lost money to rounding errors, fee blindness, signal lag
- **RiskAuditor** (crash_survivor) — survived 2008, 2020, 2022, paranoid about drawdowns
- **MiCAComplianceChecker** (eu_regulator) — zero tolerance, former ESMA official
- **CodeQualityGuardian** (senior_architect) — 20+ years, hates bare excepts and duplication

**3 Research Agents** (`src/agents/research_*.py`):
- **MarketSentimentAgent** — fear/greed, momentum, volume trends
- **TechnicalAnalysisAgent** — RSI, Bollinger, MACD, signal strength
- **StrategyPerformanceAgent** — per-strategy win rates, weight recommendations

**4 Additional Personalities** (used via Claude Code subagents, not code-based):
- **ChaosEngineer** (stress_tester) — breaks systems, finds failure modes
- **ForensicAccountant** (money_flow) — traces every dollar, catches P&L errors
- **DevOps** (infra_ops) — monitoring, graceful shutdown, process management
- **DataScientist** (model_quality) — overfitting, data leakage, feature quality

### Runner Commands
```bash
cd E:\Users\Gino\Downloads\SovereignForge\src
python -m agents.runner list                    # Show all agents
python -m agents.runner audit --all             # Dispatch 6 audit agents
python -m agents.runner research                # Run 3 research agents
python -m agents.runner synthesize              # Consolidate reports
python -m agents.runner readiness               # Paper trading go/no-go gate
```

## Trading Oracle (Collective Brain)

**File:** `src/trading_oracle.py` — aggregates all signal sources into ranked recommendations.

**Signal flow:**
1. Paper trading generates 7-strategy ensemble signals
2. Oracle normalizes (rank-percentile), resolves contradictions (regime-aware)
3. Integrates research agents (TA + sentiment, time-decayed)
4. Computes composite score (additive) + confidence (weighted additive)
5. Applies 7 safety gates: fee viability, anti-herding, circuit breaker, drawdown cascade, research vetoes, time safety, confidence floor
6. Outputs ranked OracleRecommendation with position sizing

**Key thresholds:**
- HOLD_THRESHOLD: 0.12 (composite score minimum)
- CONFIDENCE_FLOOR: 0.20
- FEE_COVERAGE_MULTIPLIER: 2.0x
- MIN_CONSENSUS_FOR_TRADE: 3/7 strategies must agree
- MAX_TRADES_PER_HOUR: 6, MAX_TRADES_PER_DAY: 20

**Dashboard endpoints:**
- GET /api/oracle/opportunities — ranked recommendations
- GET /api/oracle/status — oracle health and accuracy

## Current System State (2026-03-15)

### What's Working
- 7 exchanges integrated (Binance, Coinbase, Kraken, KuCoin, OKX, Bybit, Gate)
- 7 strategies trained (arbitrage, fibonacci, grid, dca, mean_reversion, pairs_arbitrage, momentum)
- **219+ models** across 4 exchanges (v1.0.53)
- Trading Oracle with 10 safety gates
- Paper trading at $300 with Oracle integration
- 15 dashboard pages with dark theme (localhost:3000)
- 10 agent personalities (6 audit + 3 research + 4 Claude Code)
- 3 optimization tools (Optuna, autotuner, swarm optimizer)
- Readiness gate (`python -m agents.runner readiness`)
- Windows auto-start scripts (setup_autostart.ps1)
- Centralized fee constants (src/fee_constants.py)

### What Needs Doing (Priority Order)
1. **Monitor paper trading** for 2 weeks (target: win rate > 52%)
2. **Run swarm optimizer** overnight for parameter optimization
3. **Fix 6 critical findings** in live pipeline (synthesis score 42/100)
4. **Install GitNexus** for code intelligence: `npx gitnexus analyze`
5. **Register Windows autostart**: `.\setup_autostart.ps1` (PowerShell Admin)
6. **MEV integration**: DEFERRED until $5,000+ portfolio

### Key Config Values
- Initial capital: $300 (config/trading_config.json)
- Target: $5,000
- Kelly fraction: 0.25 (quarter-Kelly)
- Stop loss: 2%, Take profit: 3%
- Max daily loss: 5%
- Capital floor: $150 (raised from $50)
- MICRO tier: 4% max position (lowered from 10%), max 2 positions
- Strategy diversification cap: max 60% same strategy

## Code Standards

- **Async ccxt**: All exchange operations use `ccxt.async_support`
- **Type hints**: Annotate all function signatures
- **Error handling**: try/except with specific exception types. No bare `except:`
- **Security**: No hardcoded secrets. API key auth on POST endpoints
- **No USDT**: Zero tolerance. Multi-layer enforcement (Oracle, API, executor)
- **Atomic writes**: State files use write-to-temp-then-rename pattern
- **Log rotation**: RotatingFileHandler(maxBytes=100MB, backupCount=5)
- **Fee constants**: Single source of truth in `src/fee_constants.py`
- **Oracle modular gates**: Each safety gate is a separate method

## Testing

```bash
PYTHONPATH=src python -m pytest tests/test_integration.py tests/test_risk_management.py -v
```
