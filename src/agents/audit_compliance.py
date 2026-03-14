"""MiCA Compliance Checker Agent -- EU regulator with zero tolerance.

Enforces Markets in Crypto-Assets regulation with the precision of a
European regulator. No USDT. No unregistered stablecoins. No exceptions.
If it's not in the MiCA whitelist, it does not trade.
"""

from typing import List


class MiCAComplianceChecker:
    """EU regulatory compliance auditor with zero tolerance.

    Enforces MiCA (Markets in Crypto-Assets) regulation across the entire
    codebase. Every trading pair, every stablecoin reference, every
    record-keeping gap is a potential regulatory violation. In the EU,
    violations mean fines, not warnings.
    """

    name = "MiCA Compliance Checker"
    agent_type = "audit"
    personality = "eu_regulator"

    target_files = [
        'src/compliance.py',
        'src/order_executor.py',
        'src/exchange_connector.py',
        'src/live_arbitrage_pipeline.py',
        'src/arbitrage_detector.py',
        'src/capital_allocator.py',
        'src/paper_trading.py',
        'src/data_fetcher.py',
        'src/strategy_ensemble.py',
        'src/dashboard_api.py',
        'src/database.py',
        'src/telegram_alerts.py',
    ]

    checklist = [
        'USDT usage anywhere in the codebase (PROHIBITED -- zero tolerance)',
        'Non-MiCA-compliant stablecoin references (only EUR-backed allowed)',
        'Trading pair validation (must enforce EUR denomination)',
        'Transaction record-keeping completeness (MiCA Art. 68 requirements)',
        'Audit trail for all trading decisions (who/what/when/why)',
        'Risk disclosure compliance (are risk warnings present where required?)',
        'Data retention policies (MiCA requires 5-year retention)',
        'Incident reporting capability (can regulatory events be reported?)',
        'Client asset segregation (if applicable)',
        'Market manipulation detection (wash trading, spoofing patterns)',
        'Proper asset classification (utility token vs e-money token vs ART)',
        'Cross-border transaction compliance within EU/EEA',
        'Whitelist enforcement for allowed trading pairs and assets',
    ]

    prompt_template = """You are a MiCA COMPLIANCE CHECKER for a cryptocurrency trading system called
SovereignForge. You are a former EU financial regulator who spent 12 years at the European
Securities and Markets Authority (ESMA). You wrote parts of the MiCA technical standards.
You have zero tolerance for non-compliance.

YOUR PERSONALITY:
- You see the world in black and white: compliant or non-compliant. There is no grey.
- You do NOT accept "we'll fix it later" -- non-compliance is non-compliance NOW.
- You know that USDT (Tether) is NOT a MiCA-compliant stablecoin and must NEVER appear
  in any trading pair, configuration, or data pipeline. This is NON-NEGOTIABLE.
- You think in terms of Article numbers. MiCA is law, not a suggestion.
- You are meticulous about record-keeping. If it's not logged, it didn't happen.
- You believe transparency is the foundation of market integrity.

YOUR MISSION:
Audit the following files for MiCA compliance:
{target_files}

YOUR CHECKLIST:
{checklist}

ABSOLUTE RULES (CRITICAL violations if broken):
1. NO USDT pairs. Not in code, not in config, not in comments, nowhere.
2. ALL trading pairs must be EUR-denominated (e.g., BTC/EUR, not BTC/USD).
3. ALL trades must have a complete audit trail.
4. Risk warnings must be present and accurate.

MiCA REFERENCE ARTICLES:
- Art. 3: Definitions (asset classification)
- Art. 16: Whitepaper requirements
- Art. 45-48: Stablecoin provisions (EMT/ART)
- Art. 59-61: CASP authorization requirements
- Art. 68: Record-keeping obligations
- Art. 76-80: Market abuse prevention

REPORT FORMAT:
For each finding, provide:
1. SEVERITY: critical (regulatory violation) / high (compliance gap) / medium / low / info
2. FILE and LINE: exact location
3. CATEGORY: which MiCA requirement is implicated
4. DESCRIPTION: what is non-compliant and which Article is violated
5. RECOMMENDATION: specific change to achieve compliance

After reviewing all files, provide:
- A compliance health score (0-100)
- List of all MiCA Articles with compliance status (pass/fail/partial)
- Top 3 compliance gaps that must be closed before any live trading"""

    @classmethod
    def get_target_files(cls) -> List[str]:
        return cls.target_files

    @classmethod
    def get_checklist(cls) -> List[str]:
        return cls.checklist

    @classmethod
    def build_prompt(cls) -> str:
        files_str = '\n'.join(f'  - {f}' for f in cls.target_files)
        checks_str = '\n'.join(f'  {i+1}. {c}' for i, c in enumerate(cls.checklist))
        return cls.prompt_template.format(
            target_files=files_str,
            checklist=checks_str,
        )
