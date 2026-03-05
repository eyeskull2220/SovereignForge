#!/usr/bin/env python3
"""
SovereignForge v1 - Arbitrage Analysis Engine
Advanced arbitrage detection and comparative analysis
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import statistics

logger = logging.getLogger(__name__)

class ArbitrageType(Enum):
    SPATIAL = "spatial"  # Cross-exchange arbitrage
    TEMPORAL = "temporal"  # Time-based arbitrage
    STATISTICAL = "statistical"  # Statistical arbitrage
    TRIANGULAR = "triangular"  # Triangular arbitrage

@dataclass
class ArbitrageAnalysis:
    """Comprehensive arbitrage analysis"""
    opportunity_id: str
    arbitrage_type: ArbitrageType
    coin: str
    exchanges: List[str]
    entry_price: float
    exit_price: float
    gross_spread: float
    net_spread: float
    volume_opportunity: float
    execution_time: timedelta
    risk_score: float
    confidence_score: float
    session_timing: str
    market_conditions: Dict[str, float]
    timestamp: datetime

@dataclass
class ComparativeAnalysis:
    """Comparative arbitrage analysis across sessions"""
    coin: str
    session: str
    opportunities_count: int
    average_spread: float
    max_spread: float
    min_spread: float
    volume_weighted_avg: float
    execution_success_rate: float
    risk_adjusted_return: float

class ArbitrageAnalyzer:
    """Advanced arbitrage analysis engine"""

    def __init__(self, trading_engine):
        self.trading_engine = trading_engine
        self.analysis_history: List[ArbitrageAnalysis] = []
        self.session_analyses: Dict[str, List[ComparativeAnalysis]] = {}
        self.market_regime_detector = MarketRegimeDetector()

        # Analysis parameters
        self.min_spread_threshold = 0.5  # Minimum 0.5% spread
        self.max_execution_time = timedelta(minutes=5)  # Max 5 minutes execution
        self.risk_tolerance = 0.02  # 2% risk tolerance

        logger.info("ArbitrageAnalyzer initialized")

    def analyze_opportunities(self, opportunities: List) -> List[ArbitrageAnalysis]:
        """Perform comprehensive arbitrage analysis"""
        analyses = []

        for opp in opportunities:
            analysis = self._analyze_single_opportunity(opp)
            if analysis:
                analyses.append(analysis)
                self.analysis_history.append(analysis)

        # Update session analyses
        self._update_session_analysis(analyses)

        logger.info(f"Completed analysis of {len(analyses)} arbitrage opportunities")
        return analyses

    def _analyze_single_opportunity(self, opportunity) -> Optional[ArbitrageAnalysis]:
        """Analyze a single arbitrage opportunity"""
        try:
            # Calculate net spread after all costs
            net_spread = self._calculate_net_spread(opportunity)

            if net_spread < self.min_spread_threshold:
                return None

            # Assess market conditions
            market_conditions = self._assess_market_conditions(opportunity)

            # Calculate risk score
            risk_score = self._calculate_risk_score(opportunity, market_conditions)

            # Estimate execution time
            execution_time = self._estimate_execution_time(opportunity)

            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(
                net_spread, risk_score, market_conditions
            )

            analysis = ArbitrageAnalysis(
                opportunity_id=f"{opportunity.coin}_{opportunity.timestamp.strftime('%Y%m%d_%H%M%S')}",
                arbitrage_type=ArbitrageType.SPATIAL,
                coin=opportunity.coin,
                exchanges=[opportunity.buy_exchange.value, opportunity.sell_exchange.value],
                entry_price=opportunity.buy_price,
                exit_price=opportunity.sell_price,
                gross_spread=opportunity.spread,
                net_spread=net_spread,
                volume_opportunity=opportunity.volume,
                execution_time=execution_time,
                risk_score=risk_score,
                confidence_score=confidence_score,
                session_timing=opportunity.session,
                market_conditions=market_conditions,
                timestamp=datetime.now()
            )

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing opportunity: {e}")
            return None

    def _calculate_net_spread(self, opportunity) -> float:
        """Calculate net spread after all fees and costs"""
        # Get exchange fees
        buy_fee = self.trading_engine.exchanges[opportunity.buy_exchange]["fee"]
        sell_fee = self.trading_engine.exchanges[opportunity.sell_exchange]["fee"]

        # Calculate effective prices
        effective_buy = opportunity.buy_price * (1 + buy_fee)
        effective_sell = opportunity.sell_price * (1 - sell_fee)

        # Calculate net spread
        net_spread = ((effective_sell - effective_buy) / effective_buy) * 100

        # Subtract estimated slippage and other costs
        slippage_cost = self._estimate_slippage(opportunity)
        network_cost = 0.01  # 0.01% network cost estimate

        net_spread -= slippage_cost + network_cost

        return max(0, net_spread)  # Ensure non-negative

    def _estimate_slippage(self, opportunity) -> float:
        """Estimate slippage cost"""
        # Simple slippage estimation based on volume and market conditions
        volume_ratio = opportunity.volume / 1000  # Normalize to baseline
        slippage = min(0.1, volume_ratio * 0.05)  # Max 0.1% slippage
        return slippage

    def _assess_market_conditions(self, opportunity) -> Dict[str, float]:
        """Assess current market conditions"""
        conditions = {}

        # Volatility assessment
        conditions['volatility'] = self._calculate_volatility(opportunity.coin)

        # Liquidity assessment
        conditions['liquidity'] = self._assess_liquidity(opportunity)

        # Market efficiency
        conditions['efficiency'] = self._calculate_market_efficiency(opportunity.coin)

        # Session timing factor
        conditions['session_factor'] = self._get_session_factor(opportunity.session)

        return conditions

    def _calculate_volatility(self, coin: str) -> float:
        """Calculate recent volatility for coin"""
        # Get price data for the coin across exchanges
        prices = []
        for exchange in self.trading_engine.exchanges.keys():
            key = f"{coin}_{exchange.value}"
            if key in self.trading_engine.market_data:
                data_points = self.trading_engine.market_data[key][-20:]  # Last 20 points
                prices.extend([d.price for d in data_points])

        if len(prices) < 2:
            return 0.5  # Default moderate volatility

        # Calculate coefficient of variation
        try:
            mean_price = statistics.mean(prices)
            std_dev = statistics.stdev(prices)
            volatility = (std_dev / mean_price) * 100
            return min(volatility, 10.0)  # Cap at 10%
        except:
            return 0.5

    def _assess_liquidity(self, opportunity) -> float:
        """Assess liquidity for the opportunity"""
        # Average volume across both exchanges
        buy_volume = opportunity.volume  # This is already the min of both
        avg_volume = buy_volume

        # Normalize liquidity score (0-1 scale)
        liquidity_score = min(avg_volume / 1000, 1.0)
        return liquidity_score

    def _calculate_market_efficiency(self, coin: str) -> float:
        """Calculate market efficiency score"""
        # Measure how quickly price discrepancies are corrected
        # Higher score = more efficient market
        return 0.8  # Placeholder - would analyze historical arbitrage persistence

    def _get_session_factor(self, session: str) -> float:
        """Get session timing factor for arbitrage success"""
        session_factors = {
            "asia": 0.7,    # Asian session often has more opportunities
            "london": 0.8,  # London session good liquidity
            "ny": 0.9,      # NY session high efficiency
            "crypto": 0.6   # Crypto 24/7, more volatile
        }
        return session_factors.get(session, 0.7)

    def _calculate_risk_score(self, opportunity, market_conditions: Dict[str, float]) -> float:
        """Calculate risk score (0-1, higher = riskier)"""
        risk_factors = []

        # Volatility risk
        risk_factors.append(market_conditions['volatility'] / 10.0)

        # Liquidity risk
        risk_factors.append(1.0 - market_conditions['liquidity'])

        # Execution time risk
        estimated_time = self._estimate_execution_time(opportunity)
        time_risk = min(estimated_time.total_seconds() / 300, 1.0)  # Max 5 minutes
        risk_factors.append(time_risk)

        # Market efficiency risk
        efficiency_risk = 1.0 - market_conditions['efficiency']
        risk_factors.append(efficiency_risk)

        # Average risk score
        risk_score = statistics.mean(risk_factors)
        return min(risk_score, 1.0)

    def _estimate_execution_time(self, opportunity) -> timedelta:
        """Estimate execution time for arbitrage"""
        # Base time plus factors
        base_time = timedelta(seconds=30)

        # Add time for each exchange API call
        api_calls = 4  # 2 buys + 2 sells (entry + exit)
        api_time = timedelta(seconds=api_calls * 2)

        # Add slippage for market conditions
        market_delay = timedelta(seconds=10)  # Conservative estimate

        total_time = base_time + api_time + market_delay
        return total_time

    def _calculate_confidence_score(self, net_spread: float, risk_score: float,
                                  market_conditions: Dict[str, float]) -> float:
        """Calculate confidence score for arbitrage execution"""
        # Base confidence from spread
        spread_confidence = min(net_spread / 2.0, 1.0)  # Max confidence at 2% spread

        # Reduce confidence based on risk
        risk_adjusted = spread_confidence * (1.0 - risk_score)

        # Boost confidence based on market conditions
        liquidity_boost = market_conditions['liquidity'] * 0.1
        efficiency_boost = market_conditions['efficiency'] * 0.1

        final_confidence = risk_adjusted + liquidity_boost + efficiency_boost
        return min(final_confidence, 1.0)

    def _update_session_analysis(self, analyses: List[ArbitrageAnalysis]):
        """Update comparative session analysis"""
        session_groups = {}

        # Group by session
        for analysis in analyses:
            if analysis.session_timing not in session_groups:
                session_groups[analysis.session_timing] = []
            session_groups[analysis.session_timing].append(analysis)

        # Calculate comparative metrics
        for session, session_analyses in session_groups.items():
            comparative = self._calculate_comparative_metrics(session, session_analyses)
            if session not in self.session_analyses:
                self.session_analyses[session] = []
            self.session_analyses[session].append(comparative)

    def _calculate_comparative_metrics(self, session: str,
                                     analyses: List[ArbitrageAnalysis]) -> ComparativeAnalysis:
        """Calculate comparative metrics for a session"""
        if not analyses:
            return ComparativeAnalysis(
                coin="N/A", session=session, opportunities_count=0,
                average_spread=0, max_spread=0, min_spread=0,
                volume_weighted_avg=0, execution_success_rate=0, risk_adjusted_return=0
            )

        spreads = [a.net_spread for a in analyses]
        volumes = [a.volume_opportunity for a in analyses]

        # Calculate volume-weighted average spread
        total_volume = sum(volumes)
        if total_volume > 0:
            volume_weighted_avg = sum(s * v for s, v in zip(spreads, volumes)) / total_volume
        else:
            volume_weighted_avg = statistics.mean(spreads) if spreads else 0

        return ComparativeAnalysis(
            coin=analyses[0].coin,  # Assuming all same coin for session analysis
            session=session,
            opportunities_count=len(analyses),
            average_spread=statistics.mean(spreads) if spreads else 0,
            max_spread=max(spreads) if spreads else 0,
            min_spread=min(spreads) if spreads else 0,
            volume_weighted_avg=volume_weighted_avg,
            execution_success_rate=0.85,  # Placeholder
            risk_adjusted_return=volume_weighted_avg * 0.8  # Simplified calculation
        )

    def get_session_comparison(self) -> Dict[str, ComparativeAnalysis]:
        """Get latest comparative analysis by session"""
        latest_comparison = {}
        for session, analyses in self.session_analyses.items():
            if analyses:
                latest_comparison[session] = analyses[-1]  # Most recent
        return latest_comparison

    def get_market_regime(self) -> str:
        """Get current market regime assessment"""
        return self.market_regime_detector.detect_regime()

class MarketRegimeDetector:
    """Detect current market regime for arbitrage strategy"""

    def __init__(self):
        self.regime_history = []

    def detect_regime(self) -> str:
        """Detect current market regime"""
        # Placeholder implementation
        # In real implementation, would analyze volatility, correlation, volume patterns
        regimes = ["trending", "ranging", "volatile", "calm"]
        return "ranging"  # Most common for arbitrage