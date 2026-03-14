#!/usr/bin/env python3
"""
SovereignForge v1 - Trading Configuration
Configuration management for trading parameters and settings
"""

import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
import os

logger = logging.getLogger(__name__)

class TradingConfig:
    """Configuration management for SovereignForge trading parameters"""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "sovereignforge_config.json"
        self.config_path = Path(__file__).parent.parent / self.config_file

        # Default configuration
        self._config = self._get_default_config()

        # Load existing configuration if available
        self.load_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values"""
        return {
            "version": "1.0.0",
            "trading": {
                "enabled_coins": ["XRP", "XLM", "HBAR", "ALGO", "ADA", "LINK", "IOTA", "XDC", "ONDO", "VET"],
                "stable_coins": ["USDC", "RLUSD"],
                "forbidden_coins": ["BTC", "ETH", "USDT", "BNB", "SOL", "DOT", "AVAX", "MATIC"],
                "supported_exchanges": ["binance", "kraken", "coinbase", "okx"],
                "min_spread_threshold": 0.5,  # Minimum 0.5% spread to consider
                "max_spread_threshold": 5.0,  # Maximum 5% spread to avoid outliers
                "min_volume_threshold": 1000,  # Minimum volume for consideration
                "max_age_seconds": 30,  # Maximum age of price data in seconds
            },
            "risk_management": {
                "max_position_size_pct": 0.02,  # Max 2% of portfolio per position
                "max_daily_loss_pct": 0.05,     # Max 5% daily loss
                "max_slippage_pct": 0.005,      # Max 0.5% slippage
                "max_concurrent_trades": 3,     # Max 3 concurrent arbitrage trades
                "emergency_stop_enabled": True,
                "circuit_breaker_enabled": True,
                "circuit_breaker_threshold": 0.03,  # 3% loss triggers circuit breaker
            },
            "execution": {
                "mode": "simulation",  # simulation, paper_trading, live_trading
                "risk_level": "conservative",  # conservative, moderate, aggressive
                "max_execution_time_seconds": 300,  # 5 minutes max execution time
                "retry_attempts": 3,
                "retry_delay_seconds": 5,
            },
            "market_data": {
                "update_interval_seconds": 5,
                "cache_size": 1000,  # Max cached price points
                "data_retention_days": 30,
                "price_sources": ["exchange_api", "websocket"],
            },
            "ui": {
                "theme": "finn_no",  # finn_no, dark, light
                "refresh_interval_seconds": 1,
                "max_chart_points": 100,
                "default_timeframe": "1m",
                "notifications_enabled": True,
            },
            "logging": {
                "level": "INFO",
                "max_log_size_mb": 100,
                "max_log_files": 5,
                "log_trades": True,
                "log_risk_events": True,
                "log_compliance": True,
            },
            "compliance": {
                "mica_compliance_enabled": True,
                "audit_trail_enabled": True,
                "data_encryption_enabled": False,  # Not implemented yet
                "session_restrictions_enabled": True,
                "allowed_sessions": ["london", "ny"],  # Conservative default
            },
            "performance": {
                "gpu_acceleration_enabled": False,  # Not implemented yet
                "parallel_processing_enabled": True,
                "max_workers": 4,
                "memory_limit_mb": 1024,
            },
            "backtesting": {
                "enabled": False,  # Not implemented yet
                "historical_data_days": 365,
                "commission_model": "percentage",  # percentage, fixed, tiered
                "commission_rate": 0.001,  # 0.1%
                "slippage_model": "fixed",  # fixed, volume_based, time_based
                "slippage_rate": 0.0005,  # 0.05%
            },
            "ai_ml": {
                "enabled": False,  # Not implemented yet
                "model_update_interval_hours": 24,
                "prediction_horizon_minutes": 60,
                "confidence_threshold": 0.7,
                "feature_engineering_enabled": True,
            },
            "mcp_knowledge_graph": {
                "enabled": False,  # Not implemented yet
                "local_only": True,
                "network_disabled": True,
                "data_retention_days": 90,
                "ceo_gated_access": True,
            }
        }

    def load_config(self) -> bool:
        """Load configuration from file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)

                # Deep merge loaded config with defaults
                self._deep_merge(self._config, loaded_config)

                logger.info(f"Configuration loaded from {self.config_path}")
                return True
            else:
                logger.info("No existing configuration found, using defaults")
                return False

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return False

    def save_config(self) -> bool:
        """Save current configuration to file"""
        try:
            # Create backup if file exists
            if self.config_path.exists():
                backup_path = self.config_path.with_suffix('.backup.json')
                self.config_path.rename(backup_path)
                logger.info(f"Created backup: {backup_path}")

            # Save configuration
            with open(self.config_path, 'w') as f:
                json.dump(self._config, f, indent=2, default=str)

            logger.info(f"Configuration saved to {self.config_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False

    def _deep_merge(self, base: Dict[str, Any], update: Dict[str, Any]) -> None:
        """Deep merge update dictionary into base dictionary"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-separated key"""
        keys = key.split('.')
        value = self._config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any) -> None:
        """Set configuration value by dot-separated key"""
        keys = key.split('.')
        config = self._config

        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        # Set the value
        config[keys[-1]] = value

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire configuration section"""
        return self._config.get(section, {})

    def update_section(self, section: str, updates: Dict[str, Any]) -> None:
        """Update entire configuration section"""
        if section not in self._config:
            self._config[section] = {}

        self._deep_merge(self._config[section], updates)

    def validate_config(self) -> List[str]:
        """Validate configuration for consistency and safety"""
        errors = []

        # Trading validation
        trading = self._config.get("trading", {})
        enabled_coins = set(trading.get("enabled_coins", []))
        forbidden_coins = set(trading.get("forbidden_coins", []))

        # Check for overlap between enabled and forbidden coins
        overlap = enabled_coins & forbidden_coins
        if overlap:
            errors.append(f"Coins cannot be both enabled and forbidden: {overlap}")

        # Risk management validation
        risk = self._config.get("risk_management", {})
        max_position = risk.get("max_position_size_pct", 0)
        max_daily_loss = risk.get("max_daily_loss_pct", 0)

        if max_position > 0.1:  # 10% max
            errors.append(f"Max position size too high: {max_position:.1%}")

        if max_daily_loss > 0.1:  # 10% max
            errors.append(f"Max daily loss too high: {max_daily_loss:.1%}")

        # Execution validation
        execution = self._config.get("execution", {})
        mode = execution.get("mode", "")
        risk_level = execution.get("risk_level", "")

        valid_modes = ["simulation", "paper_trading", "live_trading"]
        if mode not in valid_modes:
            errors.append(f"Invalid execution mode: {mode}. Must be one of {valid_modes}")

        valid_risk_levels = ["conservative", "moderate", "aggressive"]
        if risk_level not in valid_risk_levels:
            errors.append(f"Invalid risk level: {risk_level}. Must be one of {valid_risk_levels}")

        # Compliance validation
        compliance = self._config.get("compliance", {})
        if not compliance.get("mica_compliance_enabled", False):
            errors.append("MiCA compliance must be enabled")

        return errors

    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults"""
        self._config = self._get_default_config()
        logger.info("Configuration reset to defaults")

    def get_summary(self) -> str:
        """Get configuration summary"""
        summary = []
        summary.append("SovereignForge Configuration Summary")
        summary.append("=" * 40)

        # Key settings
        summary.append(f"Version: {self._config.get('version', 'unknown')}")
        summary.append(f"Execution Mode: {self._config.get('execution', {}).get('mode', 'unknown')}")
        summary.append(f"Risk Level: {self._config.get('execution', {}).get('risk_level', 'unknown')}")
        summary.append(f"Enabled Coins: {len(self._config.get('trading', {}).get('enabled_coins', []))}")
        summary.append(f"Supported Exchanges: {len(self._config.get('trading', {}).get('supported_exchanges', []))}")

        # Risk settings
        risk = self._config.get('risk_management', {})
        summary.append(f"Max Position Size: {risk.get('max_position_size_pct', 0):.1%}")
        summary.append(f"Max Daily Loss: {risk.get('max_daily_loss_pct', 0):.1%}")
        summary.append(f"Max Slippage: {risk.get('max_slippage_pct', 0):.1%}")

        # Compliance
        compliance = self._config.get('compliance', {})
        mica_status = "✓ Enabled" if compliance.get('mica_compliance_enabled') else "❌ Disabled"
        summary.append(f"MiCA Compliance: {mica_status}")

        return "\n".join(summary)

    def __str__(self) -> str:
        """String representation"""
        return self.get_summary()

    def __repr__(self) -> str:
        """Representation"""
        return f"TradingConfig(version={self._config.get('version', 'unknown')})"