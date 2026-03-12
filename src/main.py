#!/usr/bin/env python3
"""
SovereignForge Main CLI - Wave 6 Production
Production-ready arbitrage trading system with monitoring, database, and async processing
"""

import argparse
import asyncio
import time
import logging
from datetime import datetime, timedelta
import json
import os
import sys
import signal
import threading
from typing import Optional, Dict, Any
import numpy as np

# Add src directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Optional production imports — degrade gracefully if missing
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on environment variables

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

try:
    import structlog
    _STRUCTLOG_AVAILABLE = True
except ImportError:
    _STRUCTLOG_AVAILABLE = False

# Core application imports
from arbitrage_detector import ArbitrageDetector, LocalDatabase, create_sample_data
from exchange_connector import create_demo_connector
from risk_management import create_default_risk_manager, ArbitrageRiskAssessor
from order_executor import create_demo_executor
from backtester import ArbitrageBacktester, BacktestDataProvider
from performance_analyzer import create_performance_analyzer

# Production persistence — use SQLite via aiosqlite (zero-config fallback)
# Redis cache via cache_layer (falls back to in-memory LRU automatically)
try:
    from cache_layer import CacheManager, get_cache, init_cache
    _CACHE_AVAILABLE = True
except ImportError:
    _CACHE_AVAILABLE = False

# Configure structured logging (optional — only if structlog is installed)
if _STRUCTLOG_AVAILABLE and os.getenv('STRUCTLOG_ENABLED', 'false').lower() == 'true':
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# Configure logging
log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper())
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lightweight in-process stubs for optional production services
# ---------------------------------------------------------------------------

class _NoOpDB:
    """SQLite-backed persistence stub using aiosqlite, or pure no-op if unavailable."""

    def __init__(self):
        self._db_path = os.getenv("SQLITE_DB_PATH", "sovereignforge.db")
        self._conn = None

    async def initialize(self):
        try:
            import aiosqlite
            self._conn = await aiosqlite.connect(self._db_path)
            await self._conn.execute(
                "CREATE TABLE IF NOT EXISTS arbitrage_opportunities "
                "(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, ts REAL)"
            )
            await self._conn.execute(
                "CREATE TABLE IF NOT EXISTS trade_executions "
                "(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, ts REAL)"
            )
            await self._conn.commit()
            logger.info(f"SQLite database initialised at {self._db_path}")
        except ImportError:
            logger.warning("aiosqlite not installed — persistence disabled")

    async def store_arbitrage_opportunity(self, result: dict, market_data: dict):
        if self._conn is None:
            return
        try:
            import json as _json
            payload = _json.dumps({"result": result, "market": market_data}, default=str)
            await self._conn.execute(
                "INSERT INTO arbitrage_opportunities (data, ts) VALUES (?, ?)",
                (payload, time.time()),
            )
            await self._conn.commit()
        except Exception:
            pass

    async def store_trade_execution(self, trade_result: dict):
        if self._conn is None:
            return
        try:
            import json as _json
            await self._conn.execute(
                "INSERT INTO trade_executions (data, ts) VALUES (?, ?)",
                (_json.dumps(trade_result, default=str), time.time()),
            )
            await self._conn.commit()
        except Exception:
            pass

    async def health_check(self) -> bool:
        return self._conn is not None

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None


class _NoOpMetrics:
    """No-op metrics collector — logs metrics at DEBUG level.
    Falls back to real MetricsCollector from monitoring.py when available."""

    async def initialize(self):
        pass

    async def record_metric(self, name: str, value, labels: dict = None):
        logger.debug(f"metric {name}={value} labels={labels}")

    def get_metrics_text(self) -> str:
        return ""

    async def close(self):
        pass


def _create_metrics_collector():
    """Create the best available metrics collector."""
    try:
        from monitoring import MetricsCollector
        return MetricsCollector()
    except (ImportError, Exception) as e:
        logger.info(f"MetricsCollector not available ({e}), using no-op metrics")
        return _NoOpMetrics()


class _NoOpAlertManager:
    """Alert manager backed by multi_channel_alerts when available."""

    async def initialize(self):
        try:
            from multi_channel_alerts import get_alert_router
            self._router = get_alert_router()
        except ImportError:
            self._router = None

    async def send_alert(self, level: str, title: str, message: str):
        if self._router is None:
            logger.warning(f"ALERT [{level.upper()}] {title}: {message}")
            return
        try:
            from multi_channel_alerts import AlertPriority, Alert
            pmap = {
                "critical": AlertPriority.CRITICAL,
                "error": AlertPriority.HIGH,
                "warning": AlertPriority.MEDIUM,
                "info": AlertPriority.LOW,
            }
            priority = pmap.get(level.lower(), AlertPriority.LOW)
            await self._router.send(Alert(title=title, message=message, priority=priority))
        except Exception as e:
            logger.error(f"Alert send failed: {e}")


class _NoOpCacheManager:
    """CacheManager wrapper — uses cache_layer if available, else no-op."""

    def __init__(self):
        self._cache = None

    async def initialize(self):
        if _CACHE_AVAILABLE:
            from cache_layer import init_cache
            self._cache = await init_cache()
            logger.info("CacheManager (cache_layer) initialised")
        else:
            logger.warning("cache_layer not available — caching disabled")

    async def get(self, key: str):
        if self._cache is None:
            return None
        # cache_layer.get takes (domain, key) — split on first ':'
        parts = key.split(":", 1)
        domain, k = (parts[0], parts[1]) if len(parts) == 2 else ("default", key)
        return await self._cache.get(domain, k)

    async def set(self, key: str, value, ttl: int = 30):
        if self._cache is None:
            return
        parts = key.split(":", 1)
        domain, k = (parts[0], parts[1]) if len(parts) == 2 else ("default", key)
        await self._cache.set(domain, k, value, ttl=ttl)

    async def health_check(self) -> bool:
        return self._cache is not None

    async def close(self):
        if self._cache is not None:
            await self._cache.disconnect()


# ---------------------------------------------------------------------------
# MiCA-compliant asset configs (USDC pairs only)
# ---------------------------------------------------------------------------
_MICA_ASSET_CONFIGS = {
    'BTC/USDC': {'volatility': 0.03, 'min_order_size': 0.0001, 'volatility_multiplier': 1.0},
    'ETH/USDC': {'volatility': 0.04, 'min_order_size': 0.001,  'volatility_multiplier': 1.0},
    'XRP/USDC': {'volatility': 0.08, 'min_order_size': 1,      'volatility_multiplier': 1.5},
    'XLM/USDC': {'volatility': 0.07, 'min_order_size': 1,      'volatility_multiplier': 1.4},
    'HBAR/USDC': {'volatility': 0.09, 'min_order_size': 10,    'volatility_multiplier': 1.6},
    'ALGO/USDC': {'volatility': 0.10, 'min_order_size': 1,     'volatility_multiplier': 1.7},
    'ADA/USDC':  {'volatility': 0.06, 'min_order_size': 1,     'volatility_multiplier': 1.2},
    'LINK/USDC': {'volatility': 0.07, 'min_order_size': 0.1,   'volatility_multiplier': 1.3},
    'IOTA/USDC': {'volatility': 0.09, 'min_order_size': 1,     'volatility_multiplier': 1.5},
    'VET/USDC':  {'volatility': 0.08, 'min_order_size': 10,    'volatility_multiplier': 1.4},
}


class ProductionArbitrageSystem:
    """Production-ready arbitrage trading system with monitoring and async processing"""

    def __init__(self):
        self.running = False
        self.shutdown_event = asyncio.Event()

        # Initialize core components
        self.detector = ArbitrageDetector()
        self.connector = create_demo_connector()
        self.risk_manager = create_default_risk_manager()
        self.order_executor = create_demo_executor(self.risk_manager)
        self.performance_analyzer = create_performance_analyzer(self.risk_manager, None)

        # Production components (graceful no-ops when services unavailable)
        self.db_manager = _NoOpDB()
        self.cache_manager = _NoOpCacheManager()
        self.metrics_collector = _create_metrics_collector()
        self.alert_manager = _NoOpAlertManager()

        # Trading state
        self.active_opportunities = {}
        self.last_health_check = datetime.now()

    async def initialize(self):
        """Initialize production system components — non-fatal if any service is down."""
        errors = []
        for name, component in [
            ("database", self.db_manager),
            ("cache", self.cache_manager),
            ("metrics", self.metrics_collector),
            ("alerts", self.alert_manager),
        ]:
            try:
                await component.initialize()
            except Exception as e:
                errors.append(f"{name}: {e}")
                logger.warning(f"Production component '{name}' failed to initialise: {e}")

        if errors:
            logger.warning(f"System started with degraded components: {errors}")
        else:
            logger.info("Production system initialized successfully")
        return True  # Always return True — partial init is acceptable

    async def shutdown(self):
        """Gracefully shutdown the system"""
        logger.info("Shutting down production system...")
        self.running = False
        self.shutdown_event.set()

        for component in [self.db_manager, self.cache_manager, self.metrics_collector]:
            try:
                await component.close()
            except Exception:
                pass

        logger.info("Production system shutdown complete")

    async def run_arbitrage_detection(self, symbols: list = None, interval: int = 60):
        """Run continuous arbitrage detection with production features"""
        if symbols is None:
            symbols = os.getenv(
                'TRADING_SYMBOLS',
                'BTC/USDC,ETH/USDC,XRP/USDC,XLM/USDC,HBAR/USDC,ALGO/USDC,ADA/USDC,LINK/USDC,IOTA/USDC,VET/USDC'
            ).split(',')

        logger.info(f"Starting arbitrage detection for symbols: {symbols}")

        self.running = True

        try:
            while self.running and not self.shutdown_event.is_set():
                start_time = time.time()

                # Process each symbol concurrently
                tasks = []
                for symbol in symbols:
                    task = asyncio.create_task(self._process_symbol(symbol.strip()))
                    tasks.append(task)

                # Wait for all symbols to be processed
                await asyncio.gather(*tasks, return_exceptions=True)

                # Update metrics
                processing_time = time.time() - start_time
                await self.metrics_collector.record_metric(
                    'detection_cycle_duration',
                    processing_time,
                    {'cycle_type': 'full'}
                )

                # Health check
                await self._perform_health_check()

                # Wait for next cycle
                await asyncio.sleep(interval)

        except Exception as e:
            logger.error(f"Arbitrage detection failed: {e}")
            await self.alert_manager.send_alert(
                'critical',
                'Arbitrage Detection Failed',
                f"Arbitrage detection encountered an error: {e}"
            )

    async def _process_symbol(self, symbol: str):
        """Process arbitrage detection for a single symbol"""
        try:
            # Check cache first
            cache_key = f"market_data:{symbol}"
            cached_data = await self.cache_manager.get(cache_key)

            if cached_data:
                market_data = cached_data
            else:
                # Get fresh market data
                market_data = await asyncio.get_event_loop().run_in_executor(
                    None, self.connector.get_market_data, symbol
                )

                # Cache the data
                await self.cache_manager.set(cache_key, market_data, ttl=30)

            if not market_data.get('exchanges'):
                # Use sample data for demo
                market_data = create_sample_data()

            # Add price history
            market_data['price_history'] = await asyncio.get_event_loop().run_in_executor(
                None, self.connector.get_price_history, symbol
            )

            # Detect opportunities
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.detector.detect_opportunity, market_data
            )

            # Store in database
            await self._store_detection_result(result, market_data)

            # Check for trading opportunity
            if result['opportunity_detected']:
                await self._handle_arbitrage_opportunity(result, market_data)

            # Update metrics
            await self.metrics_collector.record_metric(
                'arbitrage_signal',
                result['arbitrage_signal'],
                {'symbol': symbol}
            )

            await self.metrics_collector.record_metric(
                'detection_confidence',
                result['confidence'],
                {'symbol': symbol}
            )

        except Exception as e:
            logger.error(f"Failed to process symbol {symbol}: {e}")
            await self.metrics_collector.record_metric(
                'detection_errors_total',
                1,
                {'symbol': symbol, 'error_type': type(e).__name__}
            )

    async def _store_detection_result(self, result: dict, market_data: dict):
        """Store detection result in database"""
        try:
            await self.db_manager.store_arbitrage_opportunity(result, market_data)
        except Exception as e:
            logger.error(f"Failed to store detection result: {e}")

    async def _handle_arbitrage_opportunity(self, result: dict, market_data: dict):
        """Handle detected arbitrage opportunity"""
        try:
            exchanges = list(market_data['exchanges'].keys())
            if len(exchanges) < 2:
                return

            symbol = result.get('symbol', 'BTC/USDC')
            opportunity_id = f"{symbol}_{result['timestamp']}"

            # Check if already processing this opportunity
            if opportunity_id in self.active_opportunities:
                return

            self.active_opportunities[opportunity_id] = datetime.now()

            # Calculate position size with asset-specific configuration
            asset_config = self._get_asset_config(symbol)
            position_calc = self.risk_manager.calculate_position_size({
                'spread_percentage': result['arbitrage_signal'],
                'confidence': result['confidence'],
                'entry_price': market_data['exchanges'][exchanges[0]]['ask'],
                'symbol': symbol
            }, asset_config)

            if not position_calc['approved']:
                logger.info(f"Opportunity rejected by risk manager: {opportunity_id}")
                return

            # Execute trade
            opportunity = {
                'symbol': symbol,
                'buy_exchange': exchanges[0],
                'sell_exchange': exchanges[1],
                'spread_percentage': result['arbitrage_signal'],
                'quantity': position_calc['quantity'],
                'buy_price': market_data['exchanges'][exchanges[0]]['ask'],
                'sell_price': market_data['exchanges'][exchanges[1]]['bid']
            }

            trade_result = await self.order_executor.execute_arbitrage_trade(opportunity)

            # Store trade result
            await self.db_manager.store_trade_execution(trade_result)

            # Update metrics
            await self.metrics_collector.record_metric(
                'trades_total',
                1,
                {'symbol': symbol, 'status': 'success' if trade_result['success'] else 'failed'}
            )

            # Send alert for successful trades
            if trade_result['success']:
                await self.alert_manager.send_alert(
                    'info',
                    'Arbitrage Trade Executed',
                    f"Executed arbitrage trade for {symbol}: P&L ${trade_result['pnl']:.2f}"
                )

            # Clean up
            if opportunity_id in self.active_opportunities:
                del self.active_opportunities[opportunity_id]

        except Exception as e:
            logger.error(f"Failed to handle arbitrage opportunity: {e}")

    async def _perform_health_check(self):
        """Perform system health check"""
        try:
            now = datetime.now()
            if (now - self.last_health_check).seconds < 60:  # Check every minute
                return

            self.last_health_check = now

            # Check database connectivity
            db_healthy = await self.db_manager.health_check()

            # Check cache connectivity
            cache_healthy = await self.cache_manager.health_check()

            # Check exchange connectivity
            exchange_healthy = len(self.connector.get_market_data('BTC/USDC').get('exchanges', {})) > 0

            # Record health metrics
            await self.metrics_collector.record_metric(
                'health_check_db',
                1 if db_healthy else 0,
                {'component': 'database'}
            )

            await self.metrics_collector.record_metric(
                'health_check_cache',
                1 if cache_healthy else 0,
                {'component': 'cache'}
            )

            await self.metrics_collector.record_metric(
                'health_check_exchange',
                1 if exchange_healthy else 0,
                {'component': 'exchange'}
            )

            # System resource metrics (requires psutil)
            system_metrics = {}
            if _PSUTIL_AVAILABLE:
                system_metrics = {
                    'cpu_percent': psutil.cpu_percent(interval=1),
                    'memory_percent': psutil.virtual_memory().percent,
                    'disk_usage_percent': psutil.disk_usage('/').percent
                }

            for metric_name, value in system_metrics.items():
                await self.metrics_collector.record_metric(
                    f'system_{metric_name}',
                    value,
                    {'hostname': os.getenv('HOSTNAME', 'localhost')}
                )

        except Exception as e:
            logger.error(f"Health check failed: {e}")

    def _get_asset_config(self, symbol: str) -> Dict:
        """Get asset-specific configuration parameters (MiCA USDC pairs)."""
        return _MICA_ASSET_CONFIGS.get(symbol, {
            'volatility': 0.05,
            'min_order_size': 0.001,
            'volatility_multiplier': 1.0,
        })

class ArbitrageCLI:
    """Command-line interface for arbitrage detection"""

    def __init__(self):
        self.detector = ArbitrageDetector()
        self.database = LocalDatabase()
        self.connector = create_demo_connector()

        # Wave 3 components
        self.risk_manager = create_default_risk_manager()
        self.order_executor = create_demo_executor(self.risk_manager)
        self.backtester = None  # Initialize lazily for backtesting

        # Wave 4 components
        self.performance_analyzer = create_performance_analyzer(self.risk_manager, self.backtester)

    def run_detection(self, symbol: str = 'BTC/USDC', continuous: bool = False, interval: int = 60):
        """Run arbitrage detection"""
        print(f"SovereignForge Arbitrage Detector - Wave 1")
        print(f"Symbol: {symbol}")
        print(f"Continuous mode: {continuous}")
        if continuous:
            print(f"Check interval: {interval} seconds")
        print("-" * 50)

        try:
            while True:
                # Get market data
                market_data = self.connector.get_market_data(symbol)

                if not market_data['exchanges']:
                    print("No market data available, using sample data...")
                    market_data = create_sample_data()

                # Add price history
                market_data['price_history'] = self.connector.get_price_history(symbol)

                # Detect opportunities
                result = self.detector.detect_opportunity(market_data)

                # Display results
                timestamp = datetime.fromisoformat(result['timestamp'])
                print(f"[{timestamp.strftime('%H:%M:%S')}] Signal: {result['arbitrage_signal']:.6f}, "
                      f"Confidence: {result['confidence']:.2f}, "
                      f"Opportunity: {'YES' if result['opportunity_detected'] else 'NO'}")

                # Save to database
                self.database.save_opportunity(result, market_data)

                if not continuous:
                    break

                # Wait for next check
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\nStopping detection...")
        except Exception as e:
            logger.error(f"Detection failed: {e}")

    def show_history(self, limit: int = 10):
        """Show detection history"""
        print(f"Recent Arbitrage Detection Results (last {limit})")
        print("-" * 60)

        opportunities = self.database.get_recent_opportunities(limit)

        if not opportunities:
            print("No detection history found.")
            return

        for opp in opportunities:
            timestamp = datetime.fromisoformat(opp['timestamp'])
            print(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
                  f"Signal: {opp['arbitrage_signal']:.6f} | "
                  f"Confidence: {opp['confidence']:.2f} | "
                  f"Opportunity: {'YES' if opp['opportunity_detected'] else 'NO'} | "
                  f"Exchanges: {', '.join(opp['exchanges'])}")

    def show_stats(self):
        """Show detection statistics"""
        print("Arbitrage Detection Statistics")
        print("-" * 40)

        opportunities = self.database.get_recent_opportunities(1000)  # Last 1000

        if not opportunities:
            print("No data available.")
            return

        total = len(opportunities)
        opportunities_found = sum(1 for opp in opportunities if opp['opportunity_detected'])
        avg_confidence = sum(opp['confidence'] for opp in opportunities) / total
        avg_signal = sum(opp['arbitrage_signal'] for opp in opportunities) / total

        print(f"Total detections: {total}")
        print(f"Opportunities found: {opportunities_found}")
        print(f"Success rate: {opportunities_found/total*100:.1f}%")
        print(f"Average confidence: {avg_confidence:.3f}")
        print(f"Average signal: {avg_signal:.6f}")

    def test_system(self):
        """Run system tests"""
        print("Running SovereignForge System Tests")
        print("-" * 40)

        # Test detector
        print("Testing arbitrage detector...")
        sample_data = create_sample_data()
        result = self.detector.detect_opportunity(sample_data)
        print(f"[OK] Detector working: {result['arbitrage_signal']:.6f}")

        # Test database
        print("Testing database...")
        self.database.save_opportunity(result, sample_data)
        recent = self.database.get_recent_opportunities(1)
        print(f"[OK] Database working: {len(recent)} records")

        # Test exchange connector
        print("Testing exchange connector...")
        market_data = self.connector.get_market_data('BTC/USDC')
        if market_data['exchanges']:
            print(f"[OK] Exchange connector working: {len(market_data['exchanges'])} exchanges")
        else:
            print("[WARN] Exchange connector returned no data (may be normal for demo)")

        # Test risk manager
        print("Testing risk manager...")
        position_calc = self.risk_manager.calculate_position_size({
            'spread_percentage': 0.003,
            'confidence': 0.8,
            'entry_price': 45000
        })
        print(f"[OK] Risk manager working: {position_calc['approved']}")

        # Test order executor
        print("Testing order executor...")
        balance = self.order_executor.get_paper_balance('binance')
        print(f"[OK] Order executor working: ${balance.get('USDC', 0):.2f} balance")

        print("System tests completed!")

    def show_risk_status(self):
        """Show risk management status"""
        print("Risk Management Status")
        print("-" * 30)

        metrics = self.risk_manager.get_risk_metrics()

        print(f"Portfolio Value: ${metrics['portfolio_value']:.2f}")
        print(f"Daily P&L: ${metrics['daily_pnl']:.2f}")
        print(f"Open Positions: {metrics['open_positions']}")
        print(f"Total Trades: {metrics['total_trades']}")
        print(f"Current Drawdown: {metrics['current_drawdown']:.4f}")
        print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.3f}")
        print(f"Win Rate: {metrics['win_rate']:.1f}")

        print(f"\nRisk Limits:")
        limits = metrics['risk_limits']
        print(f"Daily Loss Limit: ${limits['daily_loss_limit']:.2f}")
        print(f"Single Trade Limit: ${limits['single_trade_limit']:.2f}")
        print(f"Drawdown Limit: {limits['drawdown_limit']:.1f}")

    def run_backtest(self, symbols: str = 'BTC/USDC,ETH/USDC', days: int = 30):
        """Run backtest"""
        print("SovereignForge Backtester - Wave 3")
        print("-" * 35)

        # Initialize backtester
        data_provider = BacktestDataProvider()
        self.backtester = ArbitrageBacktester(data_provider, self.risk_manager)

        # Parse symbols
        symbol_list = [s.strip() for s in symbols.split(',')]

        # Run backtest
        from datetime import timedelta
        start_date = datetime.now() - timedelta(days=days)
        end_date = datetime.now()

        print(f"Backtesting {symbol_list}")
        print(f"Period: {start_date.date()} to {end_date.date()}")

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(
                self.backtester.run_backtest(symbol_list, start_date, end_date)
            )
        finally:
            loop.close()

        # Display results
        print("\nBacktest Results:")
        print("-" * 20)

        if 'error' in results:
            print(f"Error: {results['error']}")
            print(f"Final Portfolio Value: ${self.backtester.portfolio_value:.2f}")
            print("No trades were executed during the backtest period.")
            return results

        print(f"Final Portfolio Value: ${results['final_portfolio_value']:.2f}")
        print(f"Total Return: {results['total_return_pct']:.2f}%")
        print(f"Total Trades: {results['total_trades']}")
        print(f"Win Rate: {results['win_rate_pct']:.1f}%")
        print(f"Sharpe Ratio: {results['sharpe_ratio']:.3f}")
        print(f"Max Drawdown: {results['max_drawdown_pct']:.2f}%")
        print(f"Average Trade P&L: ${results['avg_trade_pnl']:.2f}")

        return results

    def run_paper_trading(self, symbol: str = 'BTC/USDC', continuous: bool = False, interval: int = 60):
        """Run paper trading simulation"""
        print("SovereignForge Paper Trading - Wave 3")
        print("-" * 38)
        print(f"Symbol: {symbol}")
        print(f"Continuous mode: {continuous}")
        if continuous:
            print(f"Check interval: {interval} seconds")
        print("-" * 50)

        try:
            while True:
                # Get market data
                market_data = self.connector.get_market_data(symbol)

                if not market_data['exchanges']:
                    print("No market data available, using sample data...")
                    market_data = create_sample_data()

                # Detect opportunities
                result = self.detector.detect_opportunity(market_data)

                # Check for arbitrage opportunity
                if result['opportunity_detected']:
                    # Create arbitrage opportunity
                    exchanges = list(market_data['exchanges'].keys())
                    if len(exchanges) >= 2:
                        buy_exch = exchanges[0]
                        sell_exch = exchanges[1]

                        opportunity = {
                            'symbol': symbol,
                            'buy_exchange': buy_exch,
                            'sell_exchange': sell_exch,
                            'spread_percentage': result['arbitrage_signal'],
                            'quantity': 0.01,  # Fixed small quantity for demo
                            'buy_price': market_data['exchanges'][buy_exch]['ask'],
                            'sell_price': market_data['exchanges'][sell_exch]['bid']
                        }

                        # Execute paper trade
                        loop = asyncio.new_event_loop()
                        try:
                            trade_result = loop.run_until_complete(
                                self.order_executor.execute_arbitrage_trade(opportunity)
                            )
                        finally:
                            loop.close()

                        timestamp = datetime.fromisoformat(result['timestamp'])
                        print(f"[{timestamp.strftime('%H:%M:%S')}] PAPER TRADE: "
                              f"P&L ${trade_result['pnl']:.2f}, "
                              f"Success: {trade_result['success']}")

                        # Show updated balances
                        for exchange in ['binance', 'coinbase']:
                            balance = self.order_executor.get_paper_balance(exchange)
                            usdc = balance.get('USDC', 0)
                            print(f"  {exchange}: ${usdc:.2f} USDC")

                else:
                    timestamp = datetime.fromisoformat(result['timestamp'])
                    print(f"[{timestamp.strftime('%H:%M:%S')}] No opportunity detected")

                if not continuous:
                    break

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\nStopping paper trading...")
        except Exception as e:
            logger.error(f"Paper trading failed: {e}")

    def run_analytics(self, days: int = 30, format: str = 'text'):
        """Run performance analytics"""
        print("SovereignForge Performance Analytics - Wave 4")
        print("-" * 45)

        # Get trades from risk manager (if available)
        trades = []
        if hasattr(self.risk_manager, 'position_history') and self.risk_manager.position_history:
            # Convert position history to trade format
            for position in self.risk_manager.position_history:
                trade = {
                    'timestamp': position.get('timestamp', datetime.now()),
                    'symbol': position.get('symbol', 'BTC/USDC'),
                    'buy_exchange': 'binance',  # Default
                    'sell_exchange': 'coinbase',  # Default
                    'quantity': position.get('quantity', 0),
                    'buy_price': position.get('entry_price', 0),
                    'sell_price': position.get('entry_price', 0) * 1.001,  # Assume small profit
                    'pnl': position.get('pnl', 0),
                    'fees': 0.0
                }
                trades.append(trade)

        # If no trades from risk manager, create sample data for demo
        if not trades:
            print("No trading history found. Generating sample analytics...")
            trades = self._create_sample_trades(days)

        # Filter by date range
        cutoff_date = datetime.now() - timedelta(days=days)
        filtered_trades = [t for t in trades if t['timestamp'] >= cutoff_date]

        if not filtered_trades:
            print(f"No trades found in the last {days} days.")
            return

        # Run analysis
        analysis = self.performance_analyzer.analyze_portfolio_performance(filtered_trades)

        if 'error' in analysis:
            print(f"Analysis error: {analysis['error']}")
            return

        # Display results based on format
        if format == 'text':
            report = self.performance_analyzer.generate_performance_report(filtered_trades, 'text')
            print(report)
        elif format == 'json':
            report = self.performance_analyzer.generate_performance_report(filtered_trades, 'json')
            print(report)
        elif format == 'html':
            report = self.performance_analyzer.generate_performance_report(filtered_trades, 'html')
            # Save HTML report
            filepath = self.performance_analyzer.save_report(analysis, f'analytics_report_{datetime.now().strftime("%Y%m%d")}.html', 'html')
            print(f"HTML report saved to: {filepath}")
            print("Open the file in a web browser to view the interactive report.")
        else:
            print("Invalid format. Use 'text', 'json', or 'html'.")

    def _create_sample_trades(self, days: int):
        """Create sample trades for demonstration"""
        trades = []
        base_date = datetime.now() - timedelta(days=days)

        # Generate realistic sample trades
        np.random.seed(42)  # For reproducible results

        for i in range(50):  # 50 sample trades
            trade_date = base_date + timedelta(days=np.random.randint(0, days))

            # Random symbol (MiCA-compliant USDC pairs)
            symbols = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC']
            symbol = np.random.choice(symbols)

            # Random P&L with realistic distribution
            pnl = np.random.normal(0.5, 2.0)  # Mean $0.50, std $2.00

            trade = {
                'timestamp': trade_date,
                'symbol': symbol,
                'buy_exchange': 'binance',
                'sell_exchange': 'coinbase',
                'quantity': np.random.uniform(0.001, 0.1),
                'buy_price': 45000 if symbol == 'BTC/USDC' else 3000 if symbol == 'ETH/USDC' else 0.45,
                'sell_price': 45050 if symbol == 'BTC/USDC' else 3005 if symbol == 'ETH/USDC' else 0.451,
                'pnl': pnl,
                'fees': abs(pnl) * 0.001  # 0.1% fees
            }
            trades.append(trade)

        return trades

async def run_production_system(interval: int = 60):
    """Run the production arbitrage system"""
    system = ProductionArbitrageSystem()

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(system.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize system
        if not await system.initialize():
            logger.error("Failed to initialize production system")
            return

        # Run arbitrage detection
        await system.run_arbitrage_detection(interval=interval)

    except Exception as e:
        logger.error(f"Production system failed: {e}")
    finally:
        await system.shutdown()

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description='SovereignForge Arbitrage Trading System - Wave 6 Production')
    parser.add_argument('command', choices=['detect', 'history', 'stats', 'test', 'risk', 'backtest', 'paper', 'analytics', 'production', 'health', 'gpu-train', 'gpu-status'],
                       help='Command to run')
    parser.add_argument('--symbol', default='BTC/USDC',
                       help='Trading symbol (default: BTC/USDC)')
    parser.add_argument('--symbols', default='BTC/USDC,ETH/USDC,XRP/USDC,XLM/USDC,HBAR/USDC,ALGO/USDC,ADA/USDC,LINK/USDC,IOTA/USDC,VET/USDC',
                       help='Trading symbols for backtest (comma-separated)')
    parser.add_argument('--continuous', action='store_true',
                       help='Run continuous detection/trading')
    parser.add_argument('--interval', type=int, default=60,
                       help='Check interval in seconds (default: 60)')
    parser.add_argument('--limit', type=int, default=10,
                       help='Number of records to show (default: 10)')
    parser.add_argument('--days', type=int, default=30,
                       help='Number of days for backtest/analytics (default: 30)')
    parser.add_argument('--format', choices=['text', 'json', 'html'], default='text',
                       help='Output format for analytics (default: text)')

    args = parser.parse_args()

    # Check environment
    environment = os.getenv('ENVIRONMENT', 'development')
    logger.info(f"Starting SovereignForge in {environment} mode")

    # Execute command
    if args.command == 'production':
        # Run production system
        logger.info("Starting production arbitrage system...")
        asyncio.run(run_production_system(args.interval))

    elif args.command == 'health':
        # Run health check
        print("SovereignForge Health Check")
        print("-" * 30)

        # Basic health checks
        checks = {
            'Environment': environment,
            'Python Version': sys.version.split()[0],
            'Working Directory': os.getcwd(),
            'Log Level': os.getenv('LOG_LEVEL', 'INFO'),
            'Database URL': 'Configured' if os.getenv('DATABASE_URL') else 'Not configured',
            'Redis URL': 'Configured' if os.getenv('REDIS_URL') else 'Not configured',
        }

        for check, status in checks.items():
            print(f"{check}: {status}")

        # Test imports
        try:
            from arbitrage_detector import ArbitrageDetector
            print("Arbitrage Detector: OK")
        except ImportError as e:
            print(f"Arbitrage Detector: FAILED - {e}")

        try:
            from cache_layer import CacheManager
            print("Cache Manager (cache_layer): OK")
        except ImportError as e:
            print(f"Cache Manager: FAILED - {e}")

        try:
            from exchange_rate_limiter import RateLimiterManager
            print("Rate Limiter: OK")
        except ImportError as e:
            print(f"Rate Limiter: FAILED - {e}")

        try:
            from multi_channel_alerts import AlertRouter
            print("Alert Router: OK")
        except ImportError as e:
            print(f"Alert Router: FAILED - {e}")

        print("\nHealth check completed!")

    else:
        # Use legacy CLI for backward compatibility
        cli = ArbitrageCLI()

        if args.command == 'detect':
            cli.run_detection(args.symbol, args.continuous, args.interval)
        elif args.command == 'history':
            cli.show_history(args.limit)
        elif args.command == 'stats':
            cli.show_stats()
        elif args.command == 'test':
            cli.test_system()
        elif args.command == 'risk':
            cli.show_risk_status()
        elif args.command == 'backtest':
            cli.run_backtest(args.symbols, args.days)
        elif args.command == 'paper':
            cli.run_paper_trading(args.symbol, args.continuous, args.interval)
        elif args.command == 'analytics':
            cli.run_analytics(args.days, args.format)

    if args.command == 'gpu-train':
        # GPU training command
        from gpu_training_cli import GPUTrainingCLI

        gpu_cli = GPUTrainingCLI()
        training_results = gpu_cli.run_gpu_training(
            pairs=[s.strip() for s in args.symbols.split(',')],
            exchanges=['binance', 'coinbase', 'kraken'],  # Default exchanges
            num_epochs=50,  # Default epochs
            batch_size=32,  # Default batch size
            save_models=True,
            monitor_training=True
        )

        if training_results:
            print(f"\nGPU training completed for {len(training_results)} pairs")
        else:
            print("\nGPU training failed")
            sys.exit(1)

    elif args.command == 'gpu-status':
        # GPU status command
        from gpu_training_cli import GPUTrainingCLI

        gpu_cli = GPUTrainingCLI()
        gpu_cli.show_gpu_status()

if __name__ == "__main__":
    main()