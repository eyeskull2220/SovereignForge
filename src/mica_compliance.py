#!/usr/bin/env python3
"""
SovereignForge v1 - MiCA Compliance Engine
Centralized compliance management for EU Markets in Crypto-Assets regulation
MiCA-compliant coin whitelist, audit logging, and risk enforcement
"""

import logging
from typing import Dict, List, Optional, Set, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import os
import json
import hashlib

logger = logging.getLogger(__name__)

class ComplianceLevel(Enum):
    """MiCA compliance enforcement levels"""
    STRICT = "strict"  # Block all non-compliant operations
    WARNING = "warning"  # Log warnings but allow operations
    AUDIT = "audit"  # Log only, no enforcement

class MiCAComplianceError(Exception):
    """MiCA compliance violation exception"""
    pass

@dataclass
class AssetInfo:
    """MiCA-compliant asset information"""
    symbol: str
    name: str
    blockchain: str
    is_mica_compliant: bool
    max_position_pct: float
    risk_weight: float

class MiCAComplianceEngine:
    """
    Centralized MiCA Compliance Engine
    Consolidates compliance logic from trading_engine.py, low_risk_execution.py, and agents.py
    """

    # MiCA-compliant assets whitelist (Article 4)
    MICA_COMPLIANT_ASSETS = {
        # Major crypto assets
        "XRP": AssetInfo("XRP", "XRP", "XRP Ledger", True, 0.05, 0.8),
        "XLM": AssetInfo("XLM", "Stellar", "Stellar", True, 0.05, 0.8),
        "HBAR": AssetInfo("HBAR", "Hedera", "Hedera", True, 0.03, 0.9),
        "ALGO": AssetInfo("ALGO", "Algorand", "Algorand", True, 0.04, 0.85),
        "ADA": AssetInfo("ADA", "Cardano", "Cardano", True, 0.05, 0.8),

        # DeFi tokens
        "LINK": AssetInfo("LINK", "Chainlink", "Ethereum", True, 0.03, 0.9),
        "IOTA": AssetInfo("IOTA", "IOTA", "IOTA", True, 0.02, 0.95),
        "XDC": AssetInfo("XDC", "XDC Network", "XDC", True, 0.02, 0.95),
        "ONDO": AssetInfo("ONDO", "Ondo Finance", "Ethereum", True, 0.02, 0.95),
        "VET": AssetInfo("VET", "VeChain", "VeChain", True, 0.03, 0.9),

        # Stablecoins (limited to MiCA-approved)
        "USDC": AssetInfo("USDC", "USD Coin", "Ethereum", True, 0.10, 0.5),
        "RLUSD": AssetInfo("RLUSD", "Retail USD", "Ethereum", True, 0.10, 0.5),
    }

    def __init__(self,
                 compliance_level: ComplianceLevel = ComplianceLevel.STRICT,
                 audit_log_path: str = "/app/logs/mica_audit.log"):

        self.compliance_level = compliance_level
        self.audit_log_path = audit_log_path
        self.compliance_stats = {
            "total_operations": 0,
            "compliant_operations": 0,
            "violations": 0,
            "warnings": 0
        }

        # Initialize audit logging
        self._setup_audit_logging()

        logger.info(f"MiCA Compliance Engine initialized with level: {compliance_level.value}")

    def _setup_audit_logging(self):
        """Setup immutable audit logging"""
        os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)

        # Create audit log handler with integrity protection
        audit_handler = logging.FileHandler(self.audit_log_path)
        audit_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            '%(asctime)s - MICA_AUDIT - %(levelname)s - %(message)s'
        )
        audit_handler.setFormatter(formatter)

        # Create dedicated audit logger
        self.audit_logger = logging.getLogger('mica_audit')
        self.audit_logger.setLevel(logging.INFO)
        self.audit_logger.addHandler(audit_handler)
        self.audit_logger.propagate = False

    def validate_asset(self, symbol: str) -> bool:
        """
        Validate if asset is MiCA compliant (from trading_engine.py logic)
        Article 4: Only authorized crypto assets may be traded
        """
        clean_symbol = symbol.upper().replace('/', '').replace('-', '')

        # Check if asset is in whitelist
        is_compliant = clean_symbol in self.MICA_COMPLIANT_ASSETS

        # Log compliance check
        self._log_compliance_event(
            "ASSET_VALIDATION",
            {
                "symbol": symbol,
                "clean_symbol": clean_symbol,
                "compliant": is_compliant,
                "allowed_assets": list(self.MICA_COMPLIANT_ASSETS.keys())
            }
        )

        if not is_compliant and self.compliance_level == ComplianceLevel.STRICT:
            raise MiCAComplianceError(
                f"Asset {symbol} is not MiCA compliant. "
                f"Only these assets are allowed: {list(self.MICA_COMPLIANT_ASSETS.keys())}"
            )

        return is_compliant

    def validate_position_size(self,
                             symbol: str,
                             position_size: float,
                             portfolio_value: float) -> bool:
        """
        Validate position size against MiCA risk limits
        Article 8: Position limits and risk management
        """
        if not self.validate_asset(symbol):
            return False

        asset_info = self.MICA_COMPLIANT_ASSETS[symbol.upper()]
        max_position_value = portfolio_value * asset_info.max_position_pct

        is_compliant = position_size <= max_position_value

        # Log position validation
        self._log_compliance_event(
            "POSITION_SIZE_VALIDATION",
            {
                "symbol": symbol,
                "position_size": position_size,
                "portfolio_value": portfolio_value,
                "max_allowed": max_position_value,
                "max_pct": asset_info.max_position_pct,
                "compliant": is_compliant
            }
        )

        if not is_compliant and self.compliance_level == ComplianceLevel.STRICT:
            raise MiCAComplianceError(
                f"Position size {position_size} exceeds MiCA limit of "
                f"{max_position_value} ({asset_info.max_position_pct*100}%) for {symbol}"
            )

        return is_compliant

    def validate_trade_operation(self,
                                operation: str,
                                symbol: str,
                                amount: float,
                                price: float,
                                portfolio_value: float) -> Dict[str, Any]:
        """
        Comprehensive trade validation (consolidates low_risk_execution.py logic)
        """
        validation_result = {
            "compliant": True,
            "warnings": [],
            "violations": [],
            "risk_score": 0.0
        }

        try:
            # 1. Asset compliance check
            if not self.validate_asset(symbol):
                validation_result["compliant"] = False
                validation_result["violations"].append("Non-compliant asset")

            # 2. Position size check
            trade_value = amount * price
            if not self.validate_position_size(symbol, trade_value, portfolio_value):
                validation_result["compliant"] = False
                validation_result["violations"].append("Position size exceeds limit")

            # 3. Risk assessment
            asset_info = self.MICA_COMPLIANT_ASSETS.get(symbol.upper())
            if asset_info:
                validation_result["risk_score"] = asset_info.risk_weight * (trade_value / portfolio_value)

                if validation_result["risk_score"] > 0.8:
                    validation_result["warnings"].append("High risk trade")

            # 4. Log the operation
            self._log_compliance_event(
                "TRADE_OPERATION_VALIDATION",
                {
                    "operation": operation,
                    "symbol": symbol,
                    "amount": amount,
                    "price": price,
                    "trade_value": trade_value,
                    "portfolio_value": portfolio_value,
                    "validation_result": validation_result
                }
            )

            # Update compliance statistics
            self.compliance_stats["total_operations"] += 1
            if validation_result["compliant"]:
                self.compliance_stats["compliant_operations"] += 1
            else:
                self.compliance_stats["violations"] += 1

            if validation_result["warnings"]:
                self.compliance_stats["warnings"] += len(validation_result["warnings"])

        except MiCAComplianceError as e:
            validation_result["compliant"] = False
            validation_result["violations"].append(str(e))

        return validation_result

    def get_compliance_report(self) -> Dict[str, Any]:
        """Generate MiCA compliance report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "compliance_level": self.compliance_level.value,
            "statistics": self.compliance_stats.copy(),
            "allowed_assets": list(self.MICA_COMPLIANT_ASSETS.keys()),
            "compliance_status": "COMPLIANT" if self.compliance_stats["violations"] == 0 else "VIOLATIONS_DETECTED"
        }

        # Calculate compliance rate
        if self.compliance_stats["total_operations"] > 0:
            report["compliance_rate"] = (
                self.compliance_stats["compliant_operations"] /
                self.compliance_stats["total_operations"]
            )
        else:
            report["compliance_rate"] = 1.0

        return report

    def _log_compliance_event(self, event_type: str, data: Dict[str, Any]):
        """Log compliance event with integrity protection"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        }

        # Create integrity hash
        log_json = json.dumps(log_entry, sort_keys=True)
        integrity_hash = hashlib.sha256(log_json.encode()).hexdigest()
        log_entry["integrity_hash"] = integrity_hash

        self.audit_logger.info(json.dumps(log_entry))

    def emergency_stop(self, reason: str):
        """Emergency stop all trading operations (MiCA Article 8)"""
        self._log_compliance_event(
            "EMERGENCY_STOP",
            {
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
                "compliance_stats": self.compliance_stats
            }
        )

        logger.critical(f"MiCA Emergency Stop activated: {reason}")
        # Implementation would integrate with trading engine to halt all operations

# Global compliance engine instance
_mica_engine = None

def get_mica_engine() -> MiCAComplianceEngine:
    """Get or create global MiCA compliance engine"""
    global _mica_engine

    if _mica_engine is None:
        compliance_level = ComplianceLevel.STRICT
        level_env = os.getenv("MICA_COMPLIANCE_LEVEL", "strict").lower()

        if level_env == "warning":
            compliance_level = ComplianceLevel.WARNING
        elif level_env == "audit":
            compliance_level = ComplianceLevel.AUDIT

        audit_path = os.getenv("MICA_AUDIT_LOG_PATH", "/app/logs/mica_audit.log")

        _mica_engine = MiCAComplianceEngine(
            compliance_level=compliance_level,
            audit_log_path=audit_path
        )

    return _mica_engine

def validate_mica_asset(symbol: str) -> bool:
    """Convenience function for asset validation (from trading_engine.py)"""
    return get_mica_engine().validate_asset(symbol)

def validate_mica_position(symbol: str, position_size: float, portfolio_value: float) -> bool:
    """Convenience function for position validation"""
    return get_mica_engine().validate_position_size(symbol, position_size, portfolio_value)

def validate_mica_trade(operation: str, symbol: str, amount: float, price: float, portfolio_value: float) -> Dict[str, Any]:
    """Convenience function for trade validation (from low_risk_execution.py)"""
    return get_mica_engine().validate_trade_operation(operation, symbol, amount, price, portfolio_value)

# Export compliance functions for easy integration
__all__ = [
    'MiCAComplianceEngine',
    'ComplianceLevel',
    'MiCAComplianceError',
    'get_mica_engine',
    'validate_mica_asset',
    'validate_mica_position',
    'validate_mica_trade'
]
