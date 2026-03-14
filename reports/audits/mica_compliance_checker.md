# MiCA Compliance Checker Audit Report
**Type:** audit | **Score:** 38.0/100 | **Time:** 136.0s
**Files Scanned:** 24 | **Findings:** 10

## Summary
5 critical: DOGE in compliance, VECHAIN/VET mismatch, missing LINK/IOTA, USDT in K8s and training data. 11 divergent whitelists.

## CRITICAL (5)
- **[usdt]** `src/compliance.py:29` — DOGE in compliant_assets - unauthorized meme coin
  - Fix: Remove DOGE
- **[inconsistency]** `src/compliance.py:30` — VECHAIN ticker but all files use VET. VET/USDC fails checks
  - Fix: Change to VET
- **[inconsistency]** `src/compliance.py:30` — Missing LINK and IOTA from compliant_assets
  - Fix: Add LINK, IOTA, VET
- **[usdt]** `k8s/sovereignforge-configmap.yaml:20` — K8s ConfigMap has ALL USDT pairs
  - Fix: Replace with USDC
- **[usdt]** `models/training_results_20260306_154016.json:2` — Training results contain USDT pair data
  - Fix: Retrain on USDC only

## HIGH (4)
- **[btc_eth]** `config/trading_config.json:3` — BTC/USDC and ETH/USDC enabled. Flagged for personal deployment
  - Fix: Evaluate compliance
- **[inconsistency]** `src/risk_management.py:676` — _ASSET_CONFIGS missing 5 pairs: LINK,IOTA,VET,XDC,ONDO
  - Fix: Add missing configs
- **[inconsistency]** `src/data_integration_service.py:161` — WebSocket pairs missing XDC/USDC and ONDO/USDC
  - Fix: Add missing pairs
- **[whitelist]** `tests/test_integration.py:247` — Test asserts DOGE/USDC is compliant. Wrong.
  - Fix: Fix after removing DOGE

## MEDIUM (1)
- **[stale]** `src/compliance.py:104` — last_updated hardcoded 2024-01-01
  - Fix: Use dynamic timestamp

## Top Recommendations
- Fix compliance.py assets
- Replace USDT in K8s
- Retrain USDT models
- Single whitelist source