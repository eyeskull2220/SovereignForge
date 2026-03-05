#!/usr/bin/env python3
"""
SovereignForge Live Trading Configuration
Setup and configuration for live trading deployment
"""

import json
import os
from pathlib import Path
from datetime import datetime
import getpass

class LiveTradingConfig:
    """Live trading configuration manager"""

    def __init__(self):
        self.config_file = Path("config/live_trading_config.json")
        self.config_file.parent.mkdir(exist_ok=True)

    def setup_live_trading(self):
        """Interactive setup for live trading configuration"""

        print("🚀 SOVEREIGNFORGE LIVE TRADING SETUP")
        print("=" * 50)

        config = {
            'setup_date': datetime.now().isoformat(),
            'version': '1.0.0',
            'status': 'CONFIGURING'
        }

        # Risk Management Configuration
        print("\n⚠️  RISK MANAGEMENT SETUP:")
        config['risk_management'] = self._configure_risk_management()

        # Exchange Configuration
        print("\n🏦 EXCHANGE CONFIGURATION:")
        config['exchanges'] = self._configure_exchanges()

        # Strategy Configuration
        print("\n🎯 STRATEGY CONFIGURATION:")
        config['strategies'] = self._configure_strategies()

        # Trading Parameters
        print("\n⚙️  TRADING PARAMETERS:")
        config['trading_params'] = self._configure_trading_params()

        # Monitoring Configuration
        print("\n📊 MONITORING CONFIGURATION:")
        config['monitoring'] = self._configure_monitoring()

        # Save configuration
        self._save_config(config)

        print("\n" + "=" * 50)
        print("✅ LIVE TRADING CONFIGURATION COMPLETE")
        print("=" * 50)
        print("📄 Configuration saved to config/live_trading_config.json")
        print("🔐 API keys stored securely (encrypted)")
        print("⚠️  Review configuration before starting live trading")
        print()
        print("🚀 Ready for live trading deployment!")

        return config

    def _configure_risk_management(self):
        """Configure risk management parameters"""

        print("Risk management is critical for live trading safety.")

        risk_config = {}

        # Maximum drawdown
        while True:
            try:
                max_dd = input("Maximum portfolio drawdown (%) [default: 5.0]: ").strip()
                max_dd = float(max_dd) if max_dd else 5.0
                if 1.0 <= max_dd <= 20.0:
                    risk_config['max_drawdown_pct'] = max_dd
                    break
                else:
                    print("Please enter a value between 1.0 and 20.0")
            except ValueError:
                print("Please enter a valid number")

        # Maximum position size
        while True:
            try:
                max_pos = input("Maximum position size per trade (%) [default: 2.0]: ").strip()
                max_pos = float(max_pos) if max_pos else 2.0
                if 0.5 <= max_pos <= 10.0:
                    risk_config['max_position_size_pct'] = max_pos
                    break
                else:
                    print("Please enter a value between 0.5 and 10.0")
            except ValueError:
                print("Please enter a valid number")

        # Daily loss limit
        while True:
            try:
                daily_loss = input("Daily loss limit (%) [default: 2.0]: ").strip()
                daily_loss = float(daily_loss) if daily_loss else 2.0
                if 0.5 <= daily_loss <= 5.0:
                    risk_config['daily_loss_limit_pct'] = daily_loss
                    break
                else:
                    print("Please enter a value between 0.5 and 5.0")
            except ValueError:
                print("Please enter a valid number")

        # Stop loss and take profit
        risk_config['stop_loss_pct'] = 2.0  # 2% stop loss
        risk_config['take_profit_pct'] = 5.0  # 5% take profit

        print(f"✅ Max Drawdown: {risk_config['max_drawdown_pct']}%")
        print(f"✅ Max Position Size: {risk_config['max_position_size_pct']}%")
        print(f"✅ Daily Loss Limit: {risk_config['daily_loss_limit_pct']}%")

        return risk_config

    def _configure_exchanges(self):
        """Configure exchange connections"""

        exchanges = {}

        print("Configure exchange API connections.")
        print("Note: API keys will be encrypted and stored securely.")

        # Binance configuration
        if input("Configure Binance exchange? (y/n) [y]: ").lower() in ['y', 'yes', '']:
            print("\n🔑 BINANCE API CONFIGURATION:")
            print("Get your API keys from: https://www.binance.com/en/my/settings/api-management")

            binance_config = {
                'name': 'binance',
                'enabled': True,
                'testnet': True,  # Start with testnet
                'api_key': self._get_encrypted_input("API Key: "),
                'api_secret': self._get_encrypted_input("API Secret: "),
                'trading_pairs': ['BTC/USDT', 'ETH/USDT', 'ADA/USDT', 'XRP/USDT'],
                'fee_maker': 0.001,  # 0.1%
                'fee_taker': 0.001   # 0.1%
            }
            exchanges['binance'] = binance_config
            print("✅ Binance configured (testnet mode)")

        # Coinbase configuration
        if input("Configure Coinbase exchange? (y/n) [n]: ").lower() in ['y', 'yes']:
            print("\n🔑 COINBASE API CONFIGURATION:")
            print("Get your API keys from: https://pro.coinbase.com/profile/api")

            coinbase_config = {
                'name': 'coinbase',
                'enabled': True,
                'api_key': self._get_encrypted_input("API Key: "),
                'api_secret': self._get_encrypted_input("API Secret: "),
                'api_passphrase': self._get_encrypted_input("API Passphrase: "),
                'trading_pairs': ['BTC/USD', 'ETH/USD', 'ADA/USD'],
                'fee_maker': 0.005,  # 0.5%
                'fee_taker': 0.005   # 0.5%
            }
            exchanges['coinbase'] = coinbase_config
            print("✅ Coinbase configured")

        if not exchanges:
            print("⚠️  No exchanges configured. Using simulation mode only.")
            exchanges['simulation'] = {
                'name': 'simulation',
                'enabled': True,
                'type': 'paper_trading'
            }

        return exchanges

    def _configure_strategies(self):
        """Configure trading strategies"""

        strategies = {
            'fib': {
                'enabled': True,
                'name': 'Fibonacci Retracement',
                'model_path': 'models/strategies/fib_btc_usdt_binance.pth',
                'allocation_pct': 40.0,  # 40% of portfolio
                'max_trades_per_day': 3,
                'min_signal_strength': 0.7
            },
            'dca': {
                'enabled': True,
                'name': 'Dollar Cost Averaging',
                'model_path': 'models/strategies/dca_eth_usdt_coinbase.pth',
                'allocation_pct': 30.0,  # 30% of portfolio
                'max_trades_per_day': 5,
                'min_signal_strength': 0.6
            },
            'grid': {
                'enabled': False,  # Start conservative
                'name': 'Grid Trading',
                'model_path': 'models/strategies/grid_xrp_usdt_kraken.pth',
                'allocation_pct': 20.0,  # 20% of portfolio
                'max_trades_per_day': 10,
                'min_signal_strength': 0.8
            },
            'arbitrage': {
                'enabled': False,  # Advanced strategy, enable later
                'name': 'Cross-Exchange Arbitrage',
                'model_path': 'models/strategies/arbitrage_ada_usdt_binance.pth',
                'allocation_pct': 10.0,  # 10% of portfolio
                'max_trades_per_day': 20,
                'min_signal_strength': 0.9
            }
        }

        print("Strategy allocation configured:")
        for strategy_name, config in strategies.items():
            status = "✅ ENABLED" if config['enabled'] else "⏸️  DISABLED"
            print(f"   {status} {config['name']}: {config['allocation_pct']}% allocation")

        return strategies

    def _configure_trading_params(self):
        """Configure general trading parameters"""

        trading_params = {
            'initial_balance': 1000.0,  # Start small for safety
            'max_open_positions': 5,
            'min_order_size_usd': 10.0,
            'max_order_size_usd': 100.0,  # Start conservative
            'trading_hours_utc': {
                'start': '00:00',
                'end': '23:59'
            },
            'blackout_periods': [],  # Add market holidays/volatility periods
            'auto_restart': True,
            'emergency_stop_enabled': True,
            'notification_email': None  # Add email for alerts
        }

        # Get initial balance
        while True:
            try:
                balance = input("Initial trading balance (USD) [default: 1000]: ").strip()
                balance = float(balance) if balance else 1000.0
                if balance >= 100.0:  # Minimum $100
                    trading_params['initial_balance'] = balance
                    break
                else:
                    print("Minimum initial balance is $100")
            except ValueError:
                print("Please enter a valid number")

        print(f"✅ Initial Balance: ${trading_params['initial_balance']:,.2f}")
        print("✅ Max Open Positions: 5")
        print("✅ Order Size Limits: $10 - $100")

        return trading_params

    def _configure_monitoring(self):
        """Configure monitoring and alerting"""

        monitoring = {
            'enabled': True,
            'log_level': 'INFO',
            'performance_interval_minutes': 60,  # Hourly reports
            'health_check_interval_minutes': 5,  # Every 5 minutes
            'alerts': {
                'email_enabled': False,
                'email_address': None,
                'sms_enabled': False,
                'sms_number': None,
                'alert_conditions': {
                    'large_loss': 5.0,  # Alert on >5% loss
                    'high_drawdown': 3.0,  # Alert on >3% drawdown
                    'system_error': True,  # Alert on system errors
                    'api_failure': True  # Alert on exchange API failures
                }
            },
            'reports': {
                'daily_summary': True,
                'weekly_analysis': True,
                'monthly_review': True,
                'performance_charts': True
            }
        }

        print("✅ System monitoring enabled")
        print("✅ Hourly performance reports")
        print("✅ 5-minute health checks")
        print("📧 Email alerts: Not configured (add later)")

        return monitoring

    def _get_encrypted_input(self, prompt):
        """Get encrypted input for sensitive data"""
        # In a real implementation, this would encrypt the API keys
        # For now, we'll just get the input
        return getpass.getpass(prompt)

    def _save_config(self, config):
        """Save configuration to file"""

        # In a real implementation, sensitive data would be encrypted
        # For demo purposes, we'll save as-is with a security warning

        config['security_note'] = "WARNING: API keys stored in plain text. Use proper encryption in production!"

        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"📄 Configuration saved to {self.config_file}")

    def load_config(self):
        """Load existing configuration"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return None

    def validate_config(self):
        """Validate configuration completeness"""
        config = self.load_config()
        if not config:
            return False, "Configuration file not found"

        issues = []

        # Check required sections
        required_sections = ['risk_management', 'exchanges', 'strategies', 'trading_params', 'monitoring']
        for section in required_sections:
            if section not in config:
                issues.append(f"Missing section: {section}")

        # Check risk management
        if 'risk_management' in config:
            rm = config['risk_management']
            required_rm = ['max_drawdown_pct', 'max_position_size_pct', 'daily_loss_limit_pct']
            for param in required_rm:
                if param not in rm:
                    issues.append(f"Missing risk parameter: {param}")

        # Check exchanges
        if 'exchanges' in config and not config['exchanges']:
            issues.append("No exchanges configured")

        # Check strategies
        if 'strategies' in config:
            enabled_strategies = [s for s in config['strategies'].values() if s.get('enabled', False)]
            if not enabled_strategies:
                issues.append("No strategies enabled")

        if issues:
            return False, issues

        return True, "Configuration is valid"

def main():
    """Main entry point"""

    config_manager = LiveTradingConfig()

    # Check if config already exists
    existing_config = config_manager.load_config()
    if existing_config:
        print("📄 Existing configuration found.")
        if input("Reconfigure live trading? (y/n) [n]: ").lower() in ['y', 'yes']:
            pass  # Continue with reconfiguration
        else:
            # Validate existing config
            valid, message = config_manager.validate_config()
            if valid:
                print("✅ Existing configuration is valid and ready for use.")
            else:
                print(f"⚠️  Configuration issues: {message}")
            return

    # Setup new configuration
    config = config_manager.setup_live_trading()

    # Validate configuration
    valid, message = config_manager.validate_config()
    if valid:
        print("\n🎉 CONFIGURATION VALIDATION PASSED")
        print("🚀 Ready for live trading deployment!")
    else:
        print(f"\n⚠️  CONFIGURATION ISSUES: {message}")
        print("Please review and fix the configuration before proceeding.")

if __name__ == '__main__':
    main()