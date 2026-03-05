"""
SovereignForge v1 - Database Layer
SQLAlchemy-based data persistence with TimescaleDB support
"""

import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool

logging.basicConfig(level=logging.INFO)

Base = declarative_base()

class PriceData(Base):
    """Price data table for time-series storage"""
    __tablename__ = 'price_data'

    id = Column(Integer, primary_key=True)
    coin = Column(String(10), nullable=False, index=True)
    exchange = Column(String(50), nullable=False, index=True)
    price = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    # Composite index for efficient queries
    __table_args__ = (
        Index('idx_coin_exchange_time', 'coin', 'exchange', 'timestamp'),
    )

class ArbitrageOpportunity(Base):
    """Arbitrage opportunities table"""
    __tablename__ = 'arbitrage_opportunities'

    id = Column(Integer, primary_key=True)
    coin = Column(String(10), nullable=False)
    buy_exchange = Column(String(50), nullable=False)
    sell_exchange = Column(String(50), nullable=False)
    buy_price = Column(Float, nullable=False)
    sell_price = Column(Float, nullable=False)
    spread = Column(Float, nullable=False)
    session = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    executed = Column(Integer, default=0)  # 0=not executed, 1=executed

class TradingHistory(Base):
    """Trading execution history"""
    __tablename__ = 'trading_history'

    id = Column(Integer, primary_key=True)
    coin = Column(String(10), nullable=False)
    exchange = Column(String(50), nullable=False)
    side = Column(String(10), nullable=False)  # 'buy' or 'sell'
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    arbitrage_id = Column(Integer, ForeignKey('arbitrage_opportunities.id'), nullable=True)

class DatabaseManager:
    """Database manager for SovereignForge"""

    def __init__(self, db_url: str = None):
        if db_url is None:
            # Use SQLite for local development (can be migrated to TimescaleDB later)
            db_url = 'sqlite:///E:/SovereignForge/data/trading.db'

        # Configure engine
        if 'sqlite' in db_url:
            self.engine = create_engine(
                db_url,
                connect_args={'check_same_thread': False},
                poolclass=StaticPool,
                echo=False
            )
        else:
            # For PostgreSQL/TimescaleDB
            self.engine = create_engine(db_url, echo=False)

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Create tables
        Base.metadata.create_all(bind=self.engine)

        logging.info(f"Database initialized: {db_url}")

    def get_session(self):
        """Get database session"""
        return self.SessionLocal()

    def store_price_data(self, coin: str, exchange: str, price: float,
                        volume: Optional[float] = None, timestamp: Optional[datetime] = None):
        """Store price data point"""
        if timestamp is None:
            timestamp = datetime.utcnow()

        session = self.get_session()
        try:
            price_data = PriceData(
                coin=coin,
                exchange=exchange,
                price=price,
                volume=volume,
                timestamp=timestamp
            )
            session.add(price_data)
            session.commit()
            logging.debug(f"Stored price data: {coin}@{exchange} = {price}")
        except Exception as e:
            session.rollback()
            logging.error(f"Error storing price data: {e}")
        finally:
            session.close()

    def get_recent_prices(self, coin: str, exchange: str, limit: int = 100) -> List[PriceData]:
        """Get recent price data for coin/exchange"""
        session = self.get_session()
        try:
            prices = session.query(PriceData)\
                .filter_by(coin=coin, exchange=exchange)\
                .order_by(PriceData.timestamp.desc())\
                .limit(limit)\
                .all()
            return prices
        finally:
            session.close()

    def store_arbitrage_opportunity(self, coin: str, buy_exchange: str, sell_exchange: str,
                                   buy_price: float, sell_price: float, spread: float,
                                   session_name: str) -> int:
        """Store arbitrage opportunity"""
        session = self.get_session()
        try:
            opp = ArbitrageOpportunity(
                coin=coin,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                buy_price=buy_price,
                sell_price=sell_price,
                spread=spread,
                session=session_name
            )
            session.add(opp)
            session.commit()
            logging.info(f"Stored arbitrage opportunity: {coin} {spread:.2f}%")
            return opp.id
        except Exception as e:
            session.rollback()
            logging.error(f"Error storing arbitrage opportunity: {e}")
            return -1
        finally:
            session.close()

    def get_recent_opportunities(self, limit: int = 50) -> List[ArbitrageOpportunity]:
        """Get recent arbitrage opportunities"""
        session = self.get_session()
        try:
            opps = session.query(ArbitrageOpportunity)\
                .filter_by(executed=0)\
                .order_by(ArbitrageOpportunity.timestamp.desc())\
                .limit(limit)\
                .all()
            return opps
        finally:
            session.close()

    def mark_opportunity_executed(self, opp_id: int):
        """Mark arbitrage opportunity as executed"""
        session = self.get_session()
        try:
            opp = session.query(ArbitrageOpportunity).filter_by(id=opp_id).first()
            if opp:
                opp.executed = 1
                session.commit()
                logging.info(f"Marked opportunity {opp_id} as executed")
        except Exception as e:
            session.rollback()
            logging.error(f"Error marking opportunity executed: {e}")
        finally:
            session.close()

    def store_trade(self, coin: str, exchange: str, side: str,
                   quantity: float, price: float, arbitrage_id: Optional[int] = None):
        """Store trading execution"""
        session = self.get_session()
        try:
            trade = TradingHistory(
                coin=coin,
                exchange=exchange,
                side=side,
                quantity=quantity,
                price=price,
                arbitrage_id=arbitrage_id
            )
            session.add(trade)
            session.commit()
            logging.info(f"Stored trade: {side} {quantity} {coin} @ {exchange}")
        except Exception as e:
            session.rollback()
            logging.error(f"Error storing trade: {e}")
        finally:
            session.close()

    def get_price_history(self, coin: str, exchange: str,
                         start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None) -> List[PriceData]:
        """Get price history for analysis"""
        session = self.get_session()
        try:
            query = session.query(PriceData)\
                .filter_by(coin=coin, exchange=exchange)\
                .order_by(PriceData.timestamp)

            if start_time:
                query = query.filter(PriceData.timestamp >= start_time)
            if end_time:
                query = query.filter(PriceData.timestamp <= end_time)

            return query.all()
        finally:
            session.close()

    def cleanup_old_data(self, days: int = 30):
        """Clean up old price data (keep last 30 days by default)"""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        session = self.get_session()
        try:
            deleted = session.query(PriceData)\
                .filter(PriceData.timestamp < cutoff)\
                .delete()
            session.commit()
            logging.info(f"Cleaned up {deleted} old price records")
        except Exception as e:
            session.rollback()
            logging.error(f"Error cleaning up data: {e}")
        finally:
            session.close()

# Global database instance
db_manager = None

def init_database(db_url: str = None) -> DatabaseManager:
    """Initialize global database manager"""
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager(db_url)
    return db_manager

def get_database() -> DatabaseManager:
    """Get global database manager"""
    global db_manager
    if db_manager is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return db_manager