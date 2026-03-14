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
# Launch 3 agents in parallel
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

### Available Agent Personalities
See `src/agents/audit_*.py` for full prompt templates:
- **SecurityAuditor** (red_team) — paranoid, adversarial
- **PerformanceAnalyst** (latency_hunter) — microsecond obsessive
- **TradingLogicReviewer** (burned_quant) — lost money to rounding errors
- **RiskAuditor** (crash_survivor) — survived three market crashes
- **MiCAComplianceChecker** (eu_regulator) — zero tolerance
- **CodeQualityGuardian** (senior_architect) — 20 years experience

## Current System State (2026-03-14)

### What's Working
- 7 exchanges integrated (Binance, Coinbase, Kraken, KuCoin, OKX, Bybit, Gate)
- 7 strategies defined (arbitrage, fibonacci, grid, dca, mean_reversion, pairs_arbitrage, momentum)
- 109 models trained (arbitrage + fibonacci + grid complete)
- 15 dashboard pages with dark theme
- 9 agent personalities (6 audit + 3 research)
- 3 optimization tools (Optuna, autotuner, swarm optimizer)
- Health score: 92/100 (verified by QA re-audit)
- 24/24 integration + risk tests passing

### What Needs Doing (Priority Order)
1. **Resume training**: 4 strategies remaining (dca, mean_reversion, pairs_arbitrage, momentum)
2. **Start paper trading**: After training, `python launcher.py start --paper`
3. **Run autotuner overnight**: `python src/autotuner.py --max-experiments 200`
4. **Train Kraken models**: 3 pairs (BTC, ETH, XRP) have data
5. **Monitor paper trading 2 weeks** before any live deployment
6. **MEV integration**: DEFERRED until $5,000+ portfolio

### Key Config Values
- Initial capital: $300 (config/trading_config.json)
- Target: $5,000
- Kelly fraction: 0.25 (quarter-Kelly)
- Stop loss: 3%, Take profit: 4%
- Max daily loss: 2%
- Per-trade loss limit: 1.5%
- Capital floor: $50 (halts all trading)

## Code Standards

- **Async ccxt**: All exchange operations use `ccxt.async_support`
- **Type hints**: Annotate all function signatures
- **Error handling**: try/except with logging. No bare `except:`
- **Security**: No hardcoded secrets. API key auth on POST endpoints
- **No USDT**: CI enforces zero USDT references in src/
- **Atomic writes**: State files use write-to-temp-then-rename pattern
- **Log rotation**: RotatingFileHandler(maxBytes=100MB, backupCount=5)

## Testing

```bash
PYTHONPATH=src python -m pytest tests/test_integration.py tests/test_risk_management.py -v
```
**Current: 24/24 passing**
