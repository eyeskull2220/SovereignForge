# Code Quality Guardian Audit Report
**Type:** audit | **Score:** 38.0/100 | **Time:** 151.0s
**Files Scanned:** 9 | **Findings:** 10

## Summary
2 critical: VECHAIN/VET mismatch, method outside class body. Major duplication across 5 whitelists, 2 risk managers, copy-pasted features.

## CRITICAL (1)
- **[organization]** `src/live_arbitrage_pipeline.py:812` — _cache_opportunity_bg outside class body. Runtime NameError
  - Fix: Move inside class

## HIGH (6)
- **[duplication]** `src/risk_management.py:67` — Two risk manager classes with overlapping 830 lines
  - Fix: Consolidate
- **[duplication]** `src/paper_trading.py:69` — STRATEGY_MODELS duplicated, only 4 of 7 strategies
  - Fix: Import from canonical source
- **[duplication]** `src/paper_trading.py:144` — 130 lines feature engineering copy-pasted
  - Fix: Delete, import instead
- **[duplication]** `src/` — MiCA whitelist in 5 files with inconsistent contents
  - Fix: Single source in compliance.py
- **[sys_path]** `src/` — sys.path.insert in 12 files. No proper package structure
  - Fix: Add __init__.py
- **[singleton]** `src/risk_management.py:580` — Mutable singletons not thread-safe
  - Fix: Use dependency injection

## MEDIUM (2)
- **[error_handling]** `src/order_executor.py:532` — PaperTrading super().__init__ tries load_markets with empty configs
  - Fix: Override _init_exchanges
- **[types]** `src/strategy_ensemble.py` — predict() no shape validation on input
  - Fix: Add shape check

## LOW (1)
- **[todo]** `src/dashboard_api.py:71` — Stale TODO for rate limiting
  - Fix: Implement or track

## Top Recommendations
- Fix _cache_opportunity_bg placement
- Consolidate whitelists
- Add src/__init__.py
- Remove duplicated feature engineering