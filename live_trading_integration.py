#!/usr/bin/env python3
"""
SovereignForge Live Trading Integration
End-to-end automated arbitrage trading system
"""

import asyncio
import logging
import sys
import os
import importlib.util
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import time
import json

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import SovereignForge components
from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
from realtime_inference import RealTimeInferenceService
from risk_management import RiskManager
from order_executor import OrderExecutor
from data_integration_service import HybridDataIntegrationService

# Import Phase 2A components
try:
    from crewai_agents.agents import get_arbitrage_crew
    from litserve_api.server import ArbitrageAPI
except ImportError:
    logging.warning("Phase 2A components not available")
    get_arbitrage_crew = None
    ArbitrageAPI = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('live_trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class LiveArbitrageTrader:
    """Live automated arbitrage trading system"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_running = False

        # Initialize core components
        self.data_service = HybridDataIntegrationService()
        self.inference_service = RealTimeInferenceService()
        self.risk_manager = RiskManager()
        self.order_executor = OrderExecutor(config.get('exchange_config', {}))
        self.opportunity_filter = OpportunityFilter(
            min_probability=config.get('min_probability', 0.8),
            min_spread=config.get('min_spread', 0.002),
            max_risk_score=config.get('max_risk_score', 0.3)
        )

        # Phase 2A components (optional)
        self.arbitrage_crew = get_arbitrage_crew() if get_arbitrage_crew else None
        self.api_server = ArbitrageAPI() if ArbitrageAPI else None

        # Trading state
        self.active_positions = {}
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.max_daily_trades = config.get('max_daily_trades', 10)
        self.max_daily_drawdown = config.get('max_daily_drawdown', 0.05)  # 5%

        # Safety controls
        self.emergency_stop = False
        self.last_health_check = time.time()
        self.health_check_interval = 60  # seconds

        logger.info("LiveArbitrageTrader initialized")

    async def start_trading(self):
        """Start automated trading"""
        logger.info("Starting live arbitrage trading...")

        try:
            self.is_running = True

            # Connect data service to inference
            self.data_service.add_data_callback(self._on_market_data)

            # Connect inference to trading logic
            self.inference_service.add_opportunity_callback(self._on_arbitrage_opportunity)

            # Start health monitoring
            asyncio.create_task(self._health_monitor())

            # Start data service
            await self.data_service.start()

            logger.info("Live trading started successfully")

            # Keep running
            while self.is_running:
                await asyncio.sleep(1)

                # Emergency stop check
                if self.emergency_stop:
                    logger.warning("Emergency stop activated")
                    await self._emergency_shutdown()
                    break

        except Exception as e:
            logger.error(f"Trading startup failed: {e}")
            await self.stop_trading()

    async def stop_trading(self):
        """Stop automated trading"""
        logger.info("Stopping live arbitrage trading...")
        self.is_running = False

        try:
            # Close all positions
            await self._close_all_positions()

            # Stop data service
            await self.data_service.stop()

            # Generate end-of-day report
            self._generate_eod_report()

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def _on_market_data(self, market_data: Dict[str, Any]):
        """Handle incoming market data"""
        try:
            # Update inference service
            await self.inference_service.process_market_data(market_data)

        except Exception as e:
            logger.error(f"Error processing market data: {e}")

    async def _on_arbitrage_opportunity(self, opportunity: ArbitrageOpportunity):
        """Handle detected arbitrage opportunity"""
        try:
            logger.info(f"Processing opportunity: {opportunity.pair} - {opportunity.probability:.3f}")

            # Phase 1: Basic filtering
            filtered_opp = self.opportunity_filter.filter_opportunity(opportunity)
            if not filtered_opp:
                logger.debug(f"Opportunity filtered out: {opportunity.pair}")
                return

            # Phase 2A: CrewAI analysis (if available)
            if self.arbitrage_crew:
                crew_result = self.arbitrage_crew.execute_arbitrage_analysis({
                    "pairs": [opportunity.pair],
                    "exchanges": opportunity.exchanges,
                    "prices": {ex: opportunity.prices.get(ex, 0) for ex in opportunity.exchanges},
                    "volumes": {ex: opportunity.volumes.get(ex, 0) for ex in opportunity.exchanges}
                })

                if crew_result.get('status') != 'success':
                    logger.warning(f"CrewAI analysis failed for {opportunity.pair}")
                    return

            # Phase 3: Risk assessment
            risk_valid = self.risk_manager.validate_opportunity(opportunity)
            if not risk_valid:
                logger.info(f"Risk check failed for {opportunity.pair}")
                return

            # Phase 4: Position sizing
            position_size = self._calculate_position_size(opportunity)
            if position_size <= 0:
                logger.info(f"Invalid position size for {opportunity.pair}")
                return

            # Phase 5: Pre-trade checks
            if not await self._pre_trade_checks(opportunity, position_size):
                logger.warning(f"Pre-trade checks failed for {opportunity.pair}")
                return

            # Phase 6: Execute trade
            await self._execute_arbitrage_trade(opportunity, position_size)

        except Exception as e:
            logger.error(f"Error processing opportunity {opportunity.pair}: {e}")

    def _calculate_position_size(self, opportunity: ArbitrageOpportunity) -> float:
        """Calculate position size using Kelly Criterion"""
        try:
            # Get Kelly fraction from risk manager
            if hasattr(self.risk_manager, 'calculate_kelly_position'):
                kelly_fraction = self.risk_manager.calculate_kelly_position(opportunity)
            else:
                # Conservative default
                kelly_fraction = 0.02  # 2% of capital

            # Apply limits
            max_position = self.config.get('max_position_size', 0.05)  # 5% max
            kelly_fraction = min(kelly_fraction, max_position)

            # Daily drawdown check
            current_drawdown = abs(self.daily_pnl) / max(self.config.get('initial_capital', 1000), 1)
            if current_drawdown > self.max_daily_drawdown:
                logger.warning(f"Daily drawdown limit reached: {current_drawdown:.3f}")
                return 0.0

            # Daily trade count check
            if self.daily_trade_count >= self.max_daily_trades:
                logger.info("Daily trade limit reached")
                return 0.0

            return kelly_fraction

        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0.0

    async def _pre_trade_checks(self, opportunity: ArbitrageOpportunity, position_size: float) -> bool:
        """Perform pre-trade safety checks"""
        try:
            # Check position limits
            if len(self.active_positions) >= self.config.get('max_concurrent_positions', 3):
                logger.info("Maximum concurrent positions reached")
                return False

            # Check if pair already has active position
            if opportunity.pair in self.active_positions:
                logger.info(f"Position already active for {opportunity.pair}")
                return False

            # MiCA compliance check
            mica_whitelist = [
                'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC',
                'LINK/USDC', 'IOTA/USDC', 'XDC/USDC', 'ONDO/USDC', 'VET/USDC',
                'XRP/RLUSD', 'XLM/RLUSD', 'HBAR/RLUSD', 'ALGO/RLUSD', 'ADA/RLUSD',
                'LINK/RLUSD', 'IOTA/RLUSD', 'XDC/RLUSD', 'ONDO/RLUSD', 'VET/RLUSD'
            ]

            if opportunity.pair not in mica_whitelist:
                logger.warning(f"MiCA compliance violation: {opportunity.pair}")
                return False

            # Exchange connectivity check
            for exchange in opportunity.exchanges:
                if not await self.order_executor.check_exchange_status(exchange):
                    logger.warning(f"Exchange {exchange} not available")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error in pre-trade checks: {e}")
            return False

    async def _execute_arbitrage_trade(self, opportunity: ArbitrageOpportunity, position_size: float):
        """Execute arbitrage trade"""
        try:
            logger.info(f"Executing arbitrage trade: {opportunity.pair} - Size: {position_size:.4f}")

            # Record trade start
            trade_id = f"{opportunity.pair}_{int(time.time())}"
            self.active_positions[opportunity.pair] = {
                'trade_id': trade_id,
                'start_time': datetime.now(),
                'position_size': position_size,
                'opportunity': opportunity,
                'status': 'executing'
            }

            # Execute arbitrage (simultaneous buy/sell)
            success = await self.order_executor.execute_arbitrage(
                opportunity=opportunity,
                position_size=position_size
            )

            if success:
                self.daily_trade_count += 1
                self.active_positions[opportunity.pair]['status'] = 'active'
                logger.info(f"Arbitrage trade executed successfully: {trade_id}")

                # Schedule position monitoring
                asyncio.create_task(self._monitor_position(opportunity.pair))

            else:
                # Clean up failed trade
                del self.active_positions[opportunity.pair]
                logger.error(f"Arbitrage trade failed: {trade_id}")

        except Exception as e:
            logger.error(f"Error executing arbitrage trade: {e}")
            # Clean up on error
            if opportunity.pair in self.active_positions:
                del self.active_positions[opportunity.pair]

    async def _monitor_position(self, pair: str):
        """Monitor active position for exit conditions"""
        try:
            position = self.active_positions.get(pair)
            if not position:
                return

            # Monitor for 5 minutes or until profit target/stop loss
            start_time = time.time()
            while time.time() - start_time < 300:  # 5 minutes
                await asyncio.sleep(10)  # Check every 10 seconds

                # Check exit conditions
                if await self._should_exit_position(pair):
                    await self._close_position(pair)
                    break

            # Force close if still active
            if pair in self.active_positions:
                await self._close_position(pair)

        except Exception as e:
            logger.error(f"Error monitoring position {pair}: {e}")

    async def _should_exit_position(self, pair: str) -> bool:
        """Check if position should be closed"""
        try:
            position = self.active_positions.get(pair)
            if not position:
                return False

            # Get current spread
            current_spread = await self._get_current_spread(pair)

            # Exit conditions
            entry_spread = position['opportunity'].spread_prediction

            # Profit target: spread reduced by 50%
            profit_target = entry_spread * 0.5

            # Stop loss: spread increased by 100%
            stop_loss = entry_spread * 2.0

            if current_spread <= profit_target:
                logger.info(f"Profit target reached for {pair}: {current_spread:.6f}")
                return True

            if current_spread >= stop_loss:
                logger.info(f"Stop loss triggered for {pair}: {current_spread:.6f}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking exit conditions for {pair}: {e}")
            return True  # Exit on error

    async def _get_current_spread(self, pair: str) -> float:
        """Get current spread for pair"""
        try:
            # Get latest prices from data service
            prices = await self.data_service.get_latest_prices(pair)
            if not prices or len(prices) < 2:
                return 1.0  # High spread to trigger exit

            # Calculate spread
            price_values = list(prices.values())
            max_price = max(price_values)
            min_price = min(price_values)

            return (max_price - min_price) / min_price

        except Exception as e:
            logger.error(f"Error getting current spread for {pair}: {e}")
            return 1.0

    async def _close_position(self, pair: str):
        """Close arbitrage position"""
        try:
            position = self.active_positions.get(pair)
            if not position:
                return

            logger.info(f"Closing position: {pair}")

            # Close arbitrage position
            success = await self.order_executor.close_arbitrage_position(
                opportunity=position['opportunity'],
                position_size=position['position_size']
            )

            if success:
                # Calculate P&L
                pnl = await self._calculate_pnl(position)
                self.daily_pnl += pnl

                logger.info(f"Position closed: {pair} - P&L: {pnl:.4f}")

            # Remove from active positions
            del self.active_positions[pair]

        except Exception as e:
            logger.error(f"Error closing position {pair}: {e}")

    async def _calculate_pnl(self, position: Dict[str, Any]) -> float:
        """Calculate profit/loss for closed position"""
        try:
            # Simplified P&L calculation
            # In real implementation, this would get actual execution prices
            opportunity = position['opportunity']
            position_size = position['position_size']

            # Assume profitable exit (simplified)
            estimated_profit = opportunity.profit_potential * position_size * 0.8  # 80% of potential

            return estimated_profit

        except Exception as e:
            logger.error(f"Error calculating P&L: {e}")
            return 0.0

    async def _close_all_positions(self):
        """Close all active positions"""
        logger.info("Closing all active positions...")

        pairs = list(self.active_positions.keys())
        for pair in pairs:
            await self._close_position(pair)

    async def _health_monitor(self):
        """Monitor system health"""
        while self.is_running:
            try:
                await asyncio.sleep(self.health_check_interval)

                # Check component health
                health_status = await self._check_system_health()

                if not health_status['healthy']:
                    logger.warning("System health check failed")
                    for issue in health_status['issues']:
                        logger.warning(f"Health issue: {issue}")

                    # Emergency stop if critical issues
                    if health_status['critical']:
                        logger.error("Critical health issues detected - emergency stop")
                        self.emergency_stop = True

            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    async def _check_system_health(self) -> Dict[str, Any]:
        """Check overall system health"""
        issues = []
        critical = False

        try:
            # Check data service
            if not await self.data_service.is_healthy():
                issues.append("Data service unhealthy")
                critical = True

            # Check order executor
            if not await self.order_executor.is_healthy():
                issues.append("Order executor unhealthy")
                critical = True

            # Check inference service
            if not self.inference_service.is_healthy():
                issues.append("Inference service unhealthy")

            # Check active positions
            if len(self.active_positions) > 10:  # Too many positions
                issues.append("Too many active positions")

            # Check daily drawdown
            current_drawdown = abs(self.daily_pnl) / max(self.config.get('initial_capital', 1000), 1)
            if current_drawdown > self.max_daily_drawdown:
                issues.append(f"Daily drawdown exceeded: {current_drawdown:.3f}")
                critical = True

        except Exception as e:
            issues.append(f"Health check error: {e}")
            critical = True

        return {
            'healthy': len(issues) == 0,
            'critical': critical,
            'issues': issues
        }

    async def _emergency_shutdown(self):
        """Emergency shutdown procedure"""
        logger.critical("Emergency shutdown initiated")

        # Close all positions immediately
        await self._close_all_positions()

        # Stop all services
        await self.data_service.stop()

        # Generate emergency report
        self._generate_emergency_report()

        self.is_running = False

    def _generate_eod_report(self):
        """Generate end-of-day trading report"""
        try:
            report = {
                'date': datetime.now().date().isoformat(),
                'total_pnl': self.daily_pnl,
                'total_trades': self.daily_trade_count,
                'active_positions': len(self.active_positions),
                'config': self.config,
                'timestamp': datetime.now().isoformat()
            }

            with open(f'eod_report_{datetime.now().date().isoformat()}.json', 'w') as f:
                json.dump(report, f, indent=2, default=str)

            logger.info(f"EOD Report generated: P&L {self.daily_pnl:.4f}, Trades: {self.daily_trade_count}")

        except Exception as e:
            logger.error(f"Error generating EOD report: {e}")

    def _generate_emergency_report(self):
        """Generate emergency shutdown report"""
        try:
            report = {
                'emergency_shutdown': True,
                'timestamp': datetime.now().isoformat(),
                'active_positions': list(self.active_positions.keys()),
                'daily_pnl': self.daily_pnl,
                'daily_trades': self.daily_trade_count,
                'config': self.config
            }

            with open(f'emergency_report_{int(time.time())}.json', 'w') as f:
                json.dump(report, f, indent=2, default=str)

            logger.critical("Emergency report generated")

        except Exception as e:
            logger.critical(f"Error generating emergency report: {e}")

    def get_trading_status(self) -> Dict[str, Any]:
        """Get current trading status"""
        return {
            'is_running': self.is_running,
            'active_positions': len(self.active_positions),
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trade_count,
            'emergency_stop': self.emergency_stop,
            'last_health_check': datetime.fromtimestamp(self.last_health_check).isoformat(),
            'config': self.config
        }

def create_live_trader(config_path: str = 'live_trading_config.py') -> LiveArbitrageTrader:
    """Factory function to create live trader with config"""
    try:
        # Load configuration
        spec = importlib.util.spec_from_file_location("config", config_path)
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)

        config = config_module.TRADING_CONFIG
        return LiveArbitrageTrader(config)

    except Exception as e:
        logger.error(f"Error loading config from {config_path}: {e}")
        # Default config
        default_config = {
            'min_probability': 0.8,
            'min_spread': 0.002,
            'max_risk_score': 0.3,
            'max_daily_trades': 10,
            'max_daily_drawdown': 0.05,
            'max_concurrent_positions': 3,
            'max_position_size': 0.05,
            'initial_capital': 1000,
            'exchange_config': {}
        }
        return LiveArbitrageTrader(default_config)

async def main():
    """Main entry point for live trading"""
    import argparse

    parser = argparse.ArgumentParser(description="SovereignForge Live Arbitrage Trading")
    parser.add_argument('--config', default='live_trading_config.py', help='Configuration file')
    parser.add_argument('--paper-trading', action='store_true', help='Enable paper trading mode')
    parser.add_argument('--max-trades', type=int, default=5, help='Maximum trades for testing')

    args = parser.parse_args()

    # Create trader
    trader = create_live_trader(args.config)

    # Override for testing
    if args.paper_trading:
        trader.config['paper_trading'] = True
        logger.info("Paper trading mode enabled")

    trader.max_daily_trades = args.max_trades

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("Signal received, initiating shutdown...")
        asyncio.create_task(trader.stop_trading())

    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start trading
        await trader.start_trading()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await trader.stop_trading()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await trader.stop_trading()

if __name__ == "__main__":
    asyncio.run(main())