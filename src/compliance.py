#!/usr/bin/env python3
"""
SovereignForge - MiCA Compliance Engine
Ensures all trading activities comply with EU MiCA regulations
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ComplianceViolationError(Exception):
    """Exception raised when MiCA compliance is violated"""
    violation: str

class MiCAComplianceEngine:
    """
    MiCA (Markets in Crypto-Assets) Regulation Compliance Engine
    Ensures SovereignForge operates within EU regulatory framework
    """

    def __init__(self):
        # MiCA compliant crypto assets (Article 3)
        self.compliant_assets = {
            'BTC', 'ETH', 'XRP', 'ADA', 'XLM', 'HBAR', 'ALGO', 'VECHAIN', 'ONDO', 'XDC', 'DOGE'
        }

        # MiCA compliant stablecoins (Article 5)
        self.compliant_stablecoins = {
            'USDC', 'RLUSD'
        }

        # MiCA compliant trading pairs
        self.compliant_pairs = set()
        self._build_compliant_pairs()

        logger.info(f"MiCA Compliance Engine initialized with {len(self.compliant_pairs)} compliant pairs")

    def _build_compliant_pairs(self):
        """Build set of MiCA compliant trading pairs"""
        # Crypto-to-crypto pairs
        for base in self.compliant_assets:
            for quote in self.compliant_assets:
                if base != quote:
                    self.compliant_pairs.add(f"{base}/{quote}")

        # Crypto-to-stablecoin pairs
        for base in self.compliant_assets:
            for quote in self.compliant_stablecoins:
                self.compliant_pairs.add(f"{base}/{quote}")

        # Stablecoin-to-stablecoin pairs
        for base in self.compliant_stablecoins:
            for quote in self.compliant_stablecoins:
                if base != quote:
                    self.compliant_pairs.add(f"{base}/{quote}")

    def is_asset_compliant(self, asset: str) -> bool:
        """Check if an asset is MiCA compliant"""
        return asset.upper() in self.compliant_assets or asset.upper() in self.compliant_stablecoins

    def is_pair_compliant(self, pair: str) -> bool:
        """Check if a trading pair is MiCA compliant"""
        return pair.upper() in self.compliant_pairs

    def filter_compliant_pairs(self, pairs: List[str]) -> List[str]:
        """Filter list to only include MiCA compliant pairs"""
        compliant = []
        for pair in pairs:
            if self.is_pair_compliant(pair):
                compliant.append(pair)
            else:
                self._log_violation(f"Non-compliant pair filtered: {pair}")
        return compliant

    def validate_opportunity(self, opportunity: Dict[str, Any]) -> bool:
        """Validate arbitrage opportunity for MiCA compliance"""
        pair = opportunity.get('pair', '')

        if not self.is_pair_compliant(pair):
            self._log_violation(f"Non-compliant opportunity: {pair}")
            raise ComplianceViolationError(f"Non-compliant opportunity: {pair}")

        return True

    def get_compliance_report(self) -> Dict[str, Any]:
        """Generate MiCA compliance report"""
        return {
            'compliant_assets': len(self.compliant_assets),
            'compliant_stablecoins': len(self.compliant_stablecoins),
            'compliant_pairs': len(self.compliant_pairs),
            'mica_version': 'EU_2023_1114',
            'last_updated': '2024-01-01',
            'status': 'ACTIVE'
        }

    def _log_violation(self, violation: str):
        """Log compliance violation"""
        logger.warning(f"🚫 MiCA COMPLIANCE VIOLATION: {violation}")

# Global compliance engine instance
_compliance_engine = None

def get_compliance_engine() -> MiCAComplianceEngine:
    """Get or create global compliance engine instance"""
    global _compliance_engine

    if _compliance_engine is None:
        _compliance_engine = MiCAComplianceEngine()

    return _compliance_engine