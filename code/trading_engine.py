#!/usr/bin/env python3
"""
SovereignForge v1 - Core Trading Engine
Arbitrage Detection and Execution Engine
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class Exchange(Enum):
    BINANCE = "binance"
    KRAKEN = "kraken"
    COINBASE = "coinbase"
    KUCOIN = "kucoin"
    GATEIO = "gateio"

@dataclass
class MarketData:
    """Market data structure"""
    coin: str
    exchange: Exchange
    price: float
    volume: float
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None

@dataclass
class ArbitrageOpportunity:
    """Arbitrage opportunity structure"""
    coin: str
    buy_exchange: Exchange
    sell_exchange: Exchange
    buy_price: float
    sell_price: float
    spread: float
    volume: float
    session: str
    timestamp: datetime

    @property
    def profit_percentage(self) -> float:
        """Calculate profit percentage"""
        return ((self.sell_price - self.buy_price) / self.buy_price) * 100

@dataclass
class TradingSignal:
    """Trading signal structure"""
    coin: str
    action: OrderSide
    exchange: Exchange
    price: float
    volume: float
    confidence: float
    timestamp: datetime
    reason: str

class TradingEngine:
    """Core trading engine for arbitrage detection"""

    def __init__(self, config: Dict):
        self.config = config
        self.market_data: Dict[str, List[MarketData]] = {}
        self.arbitrage_opportunities: List[ArbitrageOpportunity] = []
        self.active_positions: Dict[str, Dict] = {}
        self.session_timings = self._load_session_timings()

        # Coin whitelist - MiCA compliant
        self.allowed_coins = {
            "XRP", "XLM", "HBAR", "ALGO", "ADA", "LINK",
            "IOTA", "XDC", "ONDO", "VET", "USDC", "RLUSD"
        }

        # Exchange configurations
        self.exchanges = {
            Exchange.BINANCE: {"fee": 0.001, "min_volume": 10},
            Exchange.KRAKEN: {"fee": 0.0026, "min_volume": 25},
            Exchange.COINBASE: {"fee": 0.005, "min_volume": 10},
            Exchange.KUCOIN: {"fee": 0.001, "min_volume": 5},
            Exchange.GATEIO: {"fee": 0.002, "min_volume": 1}
        }

        logger.info("TradingEngine initialized with MiCA-compliant coin whitelist")

    def _load_session_timings(self) -> Dict[str, Tuple[int, int]]:
        """Load global session timings for arbitrage"""
        return {
            "asia": (0, 8),     # 00:00-08:00 UTC
            "london": (8, 16),  # 08:00-16:00 UTC
            "ny": (14, 21),     # 14:00-21:00 UTC
            "crypto": (0, 24)   # 24/7 crypto markets
        }

    def add_market_data(self, data: MarketData) -> None:
        """Add market data point"""
        if data.coin not in self.allowed_coins:
            logger.warning(f"Coin {data.coin} not in MiCA whitelist - ignoring")
            return

        key = f"{data.coin}_{data.exchange.value}"
        if key not in self.market_data:
            self.market_data[key] = []

        self.market_data[key].append(data)

        # Keep only recent data (last 100 points)
        if len(self.market_data[key]) > 100:
            self.market_data[key] = self.market_data[key][-100:]

        logger.debug(f"Added market data: {data.coin} @ {data.exchange.value} = ${data.price}")

    def find_arbitrage_opportunities(self) -> List[ArbitrageOpportunity]:
        """Find arbitrage opportunities across exchanges"""
        opportunities = []

        for coin in self.allowed_coins:
            if coin in ["USDC", "RLUSD"]:  # Skip stablecoins for arbitrage
                continue

            coin_opportunities = self._find_coin_arbitrage(coin)
            opportunities.extend(coin_opportunities)

        # Sort by spread descending
        opportunities.sort(key=lambda x: x.spread, reverse=True)

        self.arbitrage_opportunities = opportunities
        logger.info(f"Found {len(opportunities)} arbitrage opportunities")

        return opportunities

    def _find_coin_arbitrage(self, coin: str) -> List[ArbitrageOpportunity]:
        """Find arbitrage opportunities for a specific coin"""
        opportunities = []

        # Get latest prices for this coin across all exchanges
        latest_prices = {}
        for exchange in Exchange:
            key = f"{coin}_{exchange.value}"
            if key in self.market_data and self.market_data[key]:
                latest_prices[exchange] = self.market_data[key][-1]

        if len(latest_prices) < 2:
            return opportunities  # Need at least 2 exchanges

        # Find price differences
        exchanges_list = list(latest_prices.keys())
        for i, buy_exchange in enumerate(exchanges_list):
            for sell_exchange in exchanges_list[i+1:]:
                buy_data = latest_prices[buy_exchange]
                sell_data = latest_prices[sell_exchange]

                # Calculate spread after fees
                buy_fee = self.exchanges[buy_exchange]["fee"]
                sell_fee = self.exchanges[sell_exchange]["fee"]

                effective_buy_price = buy_data.price * (1 + buy_fee)
                effective_sell_price = sell_data.price * (1 - sell_fee)

                if effective_sell_price > effective_buy_price:
                    spread = ((effective_sell_price - effective_buy_price) / effective_buy_price) * 100

                    # Only consider opportunities with meaningful spread (>0.5%)
                    if spread > 0.5:
                        opportunity = ArbitrageOpportunity(
                            coin=coin,
                            buy_exchange=buy_exchange,
                            sell_exchange=sell_exchange,
                            buy_price=effective_buy_price,
                            sell_price=effective_sell_price,
                            spread=spread,
                            volume=min(buy_data.volume, sell_data.volume),
                            session=self._get_current_session(),
                            timestamp=datetime.now()
                        )
                        opportunities.append(opportunity)

        return opportunities

    def _get_current_session(self) -> str:
        """Get current trading session"""
        hour = datetime.now().hour

        for session, (start, end) in self.session_timings.items():
            if start <= hour < end:
                return session

        return "crypto"  # Default to crypto session

    def generate_trading_signals(self, opportunities: List[ArbitrageOpportunity]) -> List[TradingSignal]:
        """Generate trading signals from arbitrage opportunities"""
        signals = []

        for opp in opportunities[:5]:  # Limit to top 5 opportunities
            # Buy signal
            buy_signal = TradingSignal(
                coin=opp.coin,
                action=OrderSide.BUY,
                exchange=opp.buy_exchange,
                price=opp.buy_price,
                volume=opp.volume * 0.1,  # 10% of available volume
                confidence=min(opp.spread / 2, 95.0),  # Confidence based on spread
                timestamp=datetime.now(),
                reason=f"Arbitrage opportunity: buy low on {opp.buy_exchange.value}"
            )

            # Sell signal
            sell_signal = TradingSignal(
                coin=opp.coin,
                action=OrderSide.SELL,
                exchange=opp.sell_exchange,
                price=opp.sell_price,
                volume=opp.volume * 0.1,
                confidence=min(opp.spread / 2, 95.0),
                timestamp=datetime.now(),
                reason=f"Arbitrage opportunity: sell high on {opp.sell_exchange.value}"
            )

            signals.extend([buy_signal, sell_signal])

        logger.info(f"Generated {len(signals)} trading signals")
        return signals

    def execute_signal(self, signal: TradingSignal) -> bool:
        """Execute a trading signal (placeholder for actual execution)"""
        logger.info(f"Executing {signal.action.value} {signal.volume} {signal.coin} @ {signal.exchange.value}")

        # Placeholder - in real implementation this would connect to exchange APIs
        # For now, just log the execution

        position_key = f"{signal.coin}_{signal.exchange.value}"

        if signal.action == OrderSide.BUY:
            if position_key not in self.active_positions:
                self.active_positions[position_key] = {
                    "coin": signal.coin,
                    "exchange": signal.exchange,
                    "volume": 0,
                    "avg_price": 0
                }

            # Update position
            pos = self.active_positions[position_key]
            total_volume = pos["volume"] + signal.volume
            total_cost = (pos["volume"] * pos["avg_price"]) + (signal.volume * signal.price)
            pos["volume"] = total_volume
            pos["avg_price"] = total_cost / total_volume

        elif signal.action == OrderSide.SELL:
            if position_key in self.active_positions:
                pos = self.active_positions[position_key]
                if pos["volume"] >= signal.volume:
                    pos["volume"] -= signal.volume
                    if pos["volume"] == 0:
                        del self.active_positions[position_key]
                else:
                    logger.warning(f"Insufficient position for sell signal")

        return True

    def get_portfolio_status(self) -> Dict:
        """Get current portfolio status"""
        return {
            "active_positions": self.active_positions,
            "total_positions": len(self.active_positions),
            "total_value": sum(pos["volume"] * pos["avg_price"] for pos in self.active_positions.values())
        }

    def get_market_overview(self) -> Dict:
        """Get market overview across all coins and exchanges"""
        overview = {}

        for coin in self.allowed_coins:
            coin_data = {}
            for exchange in Exchange:
                key = f"{coin}_{exchange.value}"
                if key in self.market_data and self.market_data[key]:
                    latest = self.market_data[key][-1]
                    coin_data[exchange.value] = {
                        "price": latest.price,
                        "volume": latest.volume,
                        "timestamp": latest.timestamp
                    }

            if coin_data:
                overview[coin] = coin_data

        return overview