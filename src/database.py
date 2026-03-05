# SovereignForge Database Manager - Wave 6
# Production-ready database operations with PostgreSQL and connection pooling

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import os

import asyncpg
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
import pandas as pd

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Production database manager with PostgreSQL and async operations"""

    def __init__(self):
        self.pool = None
        self.engine = None
        self.database_url = os.getenv('DATABASE_URL', 'postgresql://sovereignforge:sovereignforge_pass@postgres:5432/sovereignforge')

        # Connection pool settings
        self.pool_config = {
            'min_size': int(os.getenv('DB_POOL_MIN_SIZE', '5')),
            'max_size': int(os.getenv('DB_POOL_MAX_SIZE', '20')),
            'max_queries': int(os.getenv('DB_MAX_QUERIES', '50000')),
            'max_inactive_connection_lifetime': float(os.getenv('DB_MAX_INACTIVE_LIFETIME', '300.0')),
        }

    async def initialize(self):
        """Initialize database connections and create tables if needed"""
        try:
            # Create asyncpg connection pool
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=self.pool_config['min_size'],
                max_size=self.pool_config['max_size'],
                max_queries=self.pool_config['max_queries'],
                max_inactive_connection_lifetime=self.pool_config['max_inactive_connection_lifetime'],
                command_timeout=60,
            )

            # Create SQLAlchemy engine for pandas operations
            self.engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=self.pool_config['min_size'],
                max_overflow=self.pool_config['max_size'] - self.pool_config['min_size'],
                pool_timeout=30,
                pool_recycle=3600,
            )

            # Test connection
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")

            logger.info("Database manager initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            return False

    async def close(self):
        """Close database connections"""
        if self.pool:
            await self.pool.close()
        if self.engine:
            self.engine.dispose()
        logger.info("Database connections closed")

    async def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    async def store_arbitrage_opportunity(self, result: dict, market_data: dict):
        """Store arbitrage detection result in database"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO trading.arbitrage_opportunities
                    (timestamp, symbol, arbitrage_signal, confidence, opportunity_detected, exchanges, market_data)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                result['timestamp'],
                result.get('symbol', 'BTC/USDT'),
                result['arbitrage_signal'],
                result['confidence'],
                result['opportunity_detected'],
                json.dumps(result.get('exchanges', [])),
                json.dumps(market_data)
                )

        except Exception as e:
            logger.error(f"Failed to store arbitrage opportunity: {e}")
            raise

    async def store_trade_execution(self, trade_result: dict):
        """Store trade execution result in database"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO trading.trade_executions
                    (timestamp, symbol, buy_exchange, sell_exchange, quantity,
                     buy_price, sell_price, pnl, fees, order_ids, status, execution_time_ms)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                trade_result.get('timestamp', datetime.now().isoformat()),
                trade_result.get('symbol', 'BTC/USDT'),
                trade_result.get('buy_exchange', 'binance'),
                trade_result.get('sell_exchange', 'coinbase'),
                trade_result.get('quantity', 0),
                trade_result.get('buy_price', 0),
                trade_result.get('sell_price', 0),
                trade_result.get('pnl', 0),
                trade_result.get('fees', 0),
                json.dumps(trade_result.get('order_ids', {})),
                trade_result.get('status', 'completed'),
                trade_result.get('execution_time_ms', 0)
                )

        except Exception as e:
            logger.error(f"Failed to store trade execution: {e}")
            raise

    async def store_market_snapshot(self, symbol: str, exchange: str, snapshot: dict):
        """Store market data snapshot"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO trading.market_snapshots
                    (timestamp, symbol, exchange, bid_price, ask_price, bid_volume, ask_volume,
                     last_price, volume_24h, price_change_24h, raw_data)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                datetime.now(),
                symbol,
                exchange,
                snapshot.get('bid'),
                snapshot.get('ask'),
                snapshot.get('bidVolume'),
                snapshot.get('askVolume'),
                snapshot.get('last'),
                snapshot.get('volume'),
                snapshot.get('percentage'),
                json.dumps(snapshot)
                )

        except Exception as e:
            logger.error(f"Failed to store market snapshot: {e}")

    async def get_recent_opportunities(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent arbitrage opportunities"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT timestamp, symbol, arbitrage_signal, confidence, opportunity_detected, exchanges
                    FROM trading.arbitrage_opportunities
                    ORDER BY timestamp DESC
                    LIMIT $1
                """, limit)

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get recent opportunities: {e}")
            return []

    async def get_trading_performance(self, days: int = 30) -> Dict[str, Any]:
        """Get trading performance metrics"""
        try:
            async with self.pool.acquire() as conn:
                # Get trade statistics
                trade_stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_trades,
                        COUNT(CASE WHEN pnl > 0 THEN 1 END) as winning_trades,
                        COUNT(CASE WHEN pnl < 0 THEN 1 END) as losing_trades,
                        AVG(pnl) as avg_pnl,
                        SUM(pnl) as total_pnl,
                        STDDEV(pnl) as pnl_stddev
                    FROM trading.trade_executions
                    WHERE timestamp >= NOW() - INTERVAL '%s days'
                """ % days)

                # Get opportunity statistics
                opp_stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_opportunities,
                        COUNT(CASE WHEN opportunity_detected THEN 1 END) as detected_opportunities,
                        AVG(arbitrage_signal) as avg_signal,
                        AVG(confidence) as avg_confidence
                    FROM trading.arbitrage_opportunities
                    WHERE timestamp >= NOW() - INTERVAL '%s days'
                """ % days)

                return {
                    'trade_stats': dict(trade_stats) if trade_stats else {},
                    'opportunity_stats': dict(opp_stats) if opp_stats else {},
                    'period_days': days
                }

        except Exception as e:
            logger.error(f"Failed to get trading performance: {e}")
            return {}

    async def get_portfolio_metrics(self) -> Dict[str, Any]:
        """Get current portfolio metrics"""
        try:
            async with self.pool.acquire() as conn:
                # Calculate portfolio value and P&L
                portfolio = await conn.fetchrow("""
                    SELECT
                        SUM(pnl) as total_pnl,
                        AVG(pnl) as avg_trade_pnl,
                        COUNT(*) as total_trades,
                        MAX(timestamp) as last_trade_time
                    FROM trading.trade_executions
                    WHERE timestamp >= CURRENT_DATE
                """)

                # Calculate Sharpe ratio (simplified)
                daily_returns = await conn.fetch("""
                    SELECT
                        DATE(timestamp) as trade_date,
                        SUM(pnl) as daily_pnl
                    FROM trading.trade_executions
                    WHERE timestamp >= NOW() - INTERVAL '30 days'
                    GROUP BY DATE(timestamp)
                    ORDER BY trade_date
                """)

                return {
                    'portfolio': dict(portfolio) if portfolio else {},
                    'daily_returns': [dict(row) for row in daily_returns]
                }

        except Exception as e:
            logger.error(f"Failed to get portfolio metrics: {e}")
            return {}

    def get_pandas_dataframe(self, query: str, params: tuple = None) -> pd.DataFrame:
        """Execute query and return pandas DataFrame"""
        try:
            with self.engine.connect() as conn:
                if params:
                    result = conn.execute(text(query), params)
                else:
                    result = conn.execute(text(query))
                return pd.DataFrame(result.fetchall(), columns=result.keys())
        except Exception as e:
            logger.error(f"Failed to execute pandas query: {e}")
            return pd.DataFrame()

    async def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute raw SQL query"""
        try:
            async with self.pool.acquire() as conn:
                if params:
                    rows = await conn.fetch(query, *params)
                else:
                    rows = await conn.fetch(query)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            return []

    async def execute_update(self, query: str, params: tuple = None) -> int:
        """Execute update/insert/delete query"""
        try:
            async with self.pool.acquire() as conn:
                if params:
                    result = await conn.execute(query, *params)
                else:
                    result = await conn.execute(query)
                return int(result.split()[-1])  # Return affected rows
        except Exception as e:
            logger.error(f"Failed to execute update: {e}")
            return 0