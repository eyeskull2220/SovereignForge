#!/usr/bin/env python3
"""
SovereignForge Personal Configuration
Local configuration management for personal trading system
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class PersonalConfig:
    """Personal configuration for SovereignForge"""

    # Trading Configuration
    trading_pairs: list = None
    base_currency: str = "USDT"
    quote_currencies: list = None

    # Exchange Configuration
    exchanges: list = None
    api_keys: Dict[str, Dict[str, str]] = None

    # Database Configuration (Local SQLite)
    database_path: str = "data/sovereignforge.db"
    backup_database: bool = True
    backup_interval_hours: int = 24

    # Model Configuration
    model_save_path: str = "models"
    checkpoint_frequency: int = 10
    max_models_per_pair: int = 5

    # Training Configuration
    default_epochs: int = 50
    default_batch_size: int = 32
    learning_rate: float = 1e-4
    validation_split: float = 0.2

    # GPU Configuration
    use_gpu: bool = True
    gpu_memory_fraction: float = 0.8
    gpu_device: int = 0

    # Data Configuration
    data_cache_path: str = "data/cache"
    historical_data_days: int = 365
    update_frequency_minutes: int = 60

    # Risk Management
    max_position_size: float = 0.1  # 10% of portfolio
    max_daily_loss: float = 0.05    # 5% daily loss limit
    stop_loss_percentage: float = 0.02  # 2% stop loss
    take_profit_percentage: float = 0.05  # 5% take profit

    # Logging Configuration
    log_level: str = "INFO"
    log_file: str = "logs/sovereignforge.log"
    max_log_size_mb: int = 100
    backup_logs: bool = True

    # UI Configuration
    enable_web_interface: bool = True
    web_port: int = 8080
    enable_dark_mode: bool = True
    chart_theme: str = "dark"

    # Notification Configuration
    enable_notifications: bool = True
    notification_sound: bool = True
    email_notifications: bool = False
    email_address: str = ""

    def __post_init__(self):
        # Set defaults if None
        if self.trading_pairs is None:
            self.trading_pairs = [
                'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT',
                'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT'
            ]

        if self.quote_currencies is None:
            self.quote_currencies = ['USDT', 'BTC', 'ETH']

        if self.exchanges is None:
            self.exchanges = ['binance', 'coinbase', 'kraken']

        if self.api_keys is None:
            self.api_keys = {
                'binance': {'api_key': '', 'secret_key': ''},
                'coinbase': {'api_key': '', 'secret_key': ''},
                'kraken': {'api_key': '', 'secret_key': ''}
            }

class ConfigManager:
    """Manages personal configuration loading and saving"""

    def __init__(self, config_file: str = "config/personal_config.json"):
        self.config_file = Path(config_file)
        self.config = None
        self.load_config()

    def load_config(self) -> PersonalConfig:
        """Load configuration from file or create default"""

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                self.config = PersonalConfig(**data)
                print("✅ Loaded personal configuration")
            except Exception as e:
                print(f"⚠️  Error loading config: {e}, using defaults")
                self.config = PersonalConfig()
        else:
            print("📝 Creating default personal configuration")
            self.config = PersonalConfig()
            self.save_config()

        return self.config

    def save_config(self):
        """Save current configuration to file"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(asdict(self.config), f, indent=2)
            print(f"💾 Configuration saved to {self.config_file}")
        except Exception as e:
            print(f"❌ Error saving config: {e}")

    def update_config(self, updates: Dict[str, Any]):
        """Update configuration with new values"""
        for key, value in updates.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
            else:
                print(f"⚠️  Unknown config key: {key}")

        self.save_config()

    def get_config(self) -> PersonalConfig:
        """Get current configuration"""
        return self.config

    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self.config = PersonalConfig()
        self.save_config()
        print("🔄 Configuration reset to defaults")

# Global config manager instance
config_manager = None

def get_config() -> PersonalConfig:
    """Get global configuration instance"""
    global config_manager
    if config_manager is None:
        config_manager = ConfigManager()
    return config_manager.get_config()

def update_config(updates: Dict[str, Any]):
    """Update global configuration"""
    global config_manager
    if config_manager is None:
        config_manager = ConfigManager()
    config_manager.update_config(updates)

def save_config():
    """Save current configuration"""
    global config_manager
    if config_manager:
        config_manager.save_config()

def reset_config():
    """Reset configuration to defaults"""
    global config_manager
    if config_manager:
        config_manager.reset_to_defaults()
    else:
        config_manager = ConfigManager()

# Utility functions for common operations
def get_trading_pairs() -> list:
    """Get configured trading pairs"""
    return get_config().trading_pairs

def get_exchanges() -> list:
    """Get configured exchanges"""
    return get_config().exchanges

def get_api_key(exchange: str) -> Optional[Dict[str, str]]:
    """Get API keys for exchange"""
    config = get_config()
    return config.api_keys.get(exchange)

def set_api_key(exchange: str, api_key: str, secret_key: str):
    """Set API keys for exchange"""
    config = get_config()
    if exchange not in config.api_keys:
        config.api_keys[exchange] = {}
    config.api_keys[exchange]['api_key'] = api_key
    config.api_keys[exchange]['secret_key'] = secret_key
    save_config()

def get_database_path() -> str:
    """Get database path"""
    return get_config().database_path

def get_model_path() -> str:
    """Get model save path"""
    return get_config().model_save_path

def is_gpu_enabled() -> bool:
    """Check if GPU is enabled"""
    return get_config().use_gpu

def get_risk_limits() -> Dict[str, float]:
    """Get risk management limits"""
    config = get_config()
    return {
        'max_position_size': config.max_position_size,
        'max_daily_loss': config.max_daily_loss,
        'stop_loss_percentage': config.stop_loss_percentage,
        'take_profit_percentage': config.take_profit_percentage
    }

# Configuration validation
def validate_config() -> list:
    """Validate current configuration and return issues"""
    issues = []
    config = get_config()

    # Check required directories
    required_dirs = [
        Path(config.database_path).parent,
        Path(config.model_save_path),
        Path(config.data_cache_path),
        Path(config.log_file).parent
    ]

    for dir_path in required_dirs:
        if not dir_path.exists():
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                issues.append(f"Cannot create directory {dir_path}: {e}")

    # Check API keys (warn if empty)
    for exchange, keys in config.api_keys.items():
        if not keys.get('api_key') or not keys.get('secret_key'):
            issues.append(f"API keys not configured for {exchange}")

    # Check GPU settings
    if config.use_gpu and config.gpu_memory_fraction > 1.0:
        issues.append("GPU memory fraction cannot exceed 1.0")

    return issues

def setup_initial_config():
    """Setup initial configuration with user prompts"""
    print("🎯 SovereignForge Personal Configuration Setup")
    print("=" * 50)

    config = get_config()

    # Trading pairs
    print(f"\n📊 Current trading pairs: {config.trading_pairs}")
    change_pairs = input("Change trading pairs? (y/N): ").lower().strip()
    if change_pairs == 'y':
        pairs_input = input("Enter trading pairs (comma-separated): ")
        config.trading_pairs = [p.strip() for p in pairs_input.split(',') if p.strip()]

    # Exchanges
    print(f"\n🏦 Current exchanges: {config.exchanges}")
    change_exchanges = input("Change exchanges? (y/N): ").lower().strip()
    if change_exchanges == 'y':
        exchanges_input = input("Enter exchanges (comma-separated): ")
        config.exchanges = [e.strip() for e in exchanges_input.split(',') if e.strip()]

    # API Keys
    print("
🔑 API Key Configuration:"    for exchange in config.exchanges:
        current_keys = config.api_keys.get(exchange, {})
        has_keys = bool(current_keys.get('api_key') and current_keys.get('secret_key'))

        if not has_keys:
            setup_keys = input(f"Setup API keys for {exchange}? (y/N): ").lower().strip()
            if setup_keys == 'y':
                api_key = input(f"Enter {exchange} API key: ").strip()
                secret_key = input(f"Enter {exchange} secret key: ").strip()
                set_api_key(exchange, api_key, secret_key)
                print(f"✅ API keys configured for {exchange}")
        else:
            print(f"✅ API keys already configured for {exchange}")

    # Risk settings
    print("
⚠️  Risk Management Settings:"    print(f"Max position size: {config.max_position_size*100}%")
    print(f"Max daily loss: {config.max_daily_loss*100}%")
    print(f"Stop loss: {config.stop_loss_percentage*100}%")
    print(f"Take profit: {config.take_profit_percentage*100}%")

    change_risk = input("Change risk settings? (y/N): ").lower().strip()
    if change_risk == 'y':
        try:
            config.max_position_size = float(input("Max position size (0.01-1.0): ")) / 100
            config.max_daily_loss = float(input("Max daily loss (0.01-0.5): ")) / 100
            config.stop_loss_percentage = float(input("Stop loss % (0.005-0.1): ")) / 100
            config.take_profit_percentage = float(input("Take profit % (0.01-0.2): ")) / 100
        except ValueError:
            print("❌ Invalid input, keeping current settings")

    # Save configuration
    save_config()
    print("
💾 Configuration saved!"    # Validate configuration
    issues = validate_config()
    if issues:
        print("
⚠️  Configuration Issues:"        for issue in issues:
            print(f"  - {issue}")
    else:
        print("
✅ Configuration is valid!"if __name__ == "__main__":
    setup_initial_config()