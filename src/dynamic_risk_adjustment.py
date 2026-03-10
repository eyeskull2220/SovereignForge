#!/usr/bin/env python3
"""
SovereignForge - Dynamic Risk Adjustment Module
Implements adaptive risk management that responds to market conditions

This module provides:
- Volatility-based position sizing adjustments
- Correlation-aware risk limits
- Circuit breakers for extreme market conditions
- Adaptive risk thresholds based on market regime
- Real-time risk monitoring and alerts
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor

from advanced_risk_metrics import AdvancedRiskMetrics, RiskMetrics

logger = logging.getLogger(__name__)

class MarketRegime(Enum):
    """Market regime classifications"""
    NORMAL = "normal"
    VOLATILE = "volatile"
    CRASH = "crash"
    RECOVERY = "recovery"
    BULL = "bull"
    BEAR = "bear"

class RiskLevel(Enum):
    """Risk level classifications"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"

@dataclass
class RiskThresholds:
    """Dynamic risk thresholds that adjust based on market conditions"""
    max_position_size: float  # Maximum position size as % of portfolio
    max_portfolio_var: float  # Maximum portfolio VaR limit
    max_single_asset_var: float  # Maximum single asset VaR limit
    max_correlation_exposure: float  # Maximum correlation exposure
    max_volatility_adjustment: float  # Maximum volatility adjustment factor
    circuit_breaker_threshold: float  # Circuit breaker activation threshold
    emergency_stop_threshold: float  # Emergency stop activation threshold

@dataclass
class MarketConditions:
    """Current market condition assessment"""
    regime: MarketRegime
    volatility_percentile: float  # Current volatility percentile (0-100)
    correlation_stress: float  # Correlation stress indicator (0-1)
    liquidity_score: float  # Market liquidity score (0-1)
    momentum_score: float  # Market momentum score (-1 to 1)
    fear_greed_index: float  # Fear & greed index (0-100)
    timestamp: datetime

@dataclass
class ArbitrageOpportunityRisk:
    """Risk assessment for specific arbitrage opportunities"""
    opportunity_id: str
    base_risk_score: float
    adjusted_risk_score: float
    position_size_limit: float
    execution_probability: float
    expected_holding_time: float
    liquidation_risk: float
    counterparty_risk: float
    regulatory_risk: float

class DynamicRiskAdjustment:
    """
    Dynamic risk adjustment engine that adapts to market conditions
    """

    def __init__(self,
                 base_risk_thresholds: Optional[RiskThresholds] = None,
                 adjustment_sensitivity: float = 0.7,
                 lookback_periods: int = 252,  # Trading days
                 update_frequency_seconds: int = 300):  # 5 minutes

        self.adjustment_sensitivity = adjustment_sensitivity
        self.lookback_periods = lookback_periods
        self.update_frequency_seconds = update_frequency_seconds

        # Base risk thresholds (conservative defaults)
        self.base_thresholds = base_risk_thresholds or RiskThresholds(
            max_position_size=0.02,  # 2% max position
            max_portfolio_var=0.05,  # 5% max portfolio VaR
            max_single_asset_var=0.03,  # 3% max single asset VaR
            max_correlation_exposure=0.8,  # 80% max correlation
            max_volatility_adjustment=0.5,  # 50% max volatility adjustment
            circuit_breaker_threshold=0.10,  # 10% circuit breaker
            emergency_stop_threshold=0.15  # 15% emergency stop
        )

        # Current state
        self.current_thresholds = self.base_thresholds
        self.market_conditions = self._get_default_market_conditions()
        self.risk_metrics_calculator = AdvancedRiskMetrics()

        # Historical data for regime detection
        self.volatility_history: List[float] = []
        self.correlation_history: List[float] = []
        self.returns_history: List[np.ndarray] = []

        # Risk monitoring
        self.monitoring_active = False
        self.risk_alerts: List[Dict[str, Any]] = []
        self.circuit_breaker_active = False
        self.emergency_stop_active = False

        # Callbacks for risk events
        self.risk_alert_callbacks: List[Callable] = []
        self.circuit_breaker_callbacks: List[Callable] = []

        logger.info("DynamicRiskAdjustment initialized")

    def _get_default_market_conditions(self) -> MarketConditions:
        """Get default market conditions for initialization"""
        return MarketConditions(
            regime=MarketRegime.NORMAL,
            volatility_percentile=50.0,
            correlation_stress=0.3,
            liquidity_score=0.7,
            momentum_score=0.0,
            fear_greed_index=50.0,
            timestamp=datetime.now()
        )

    def assess_market_conditions(self,
                               recent_returns: np.ndarray,
                               correlation_matrix: Optional[np.ndarray] = None,
                               volume_data: Optional[np.ndarray] = None) -> MarketConditions:
        """
        Assess current market conditions based on recent data

        Args:
            recent_returns: Recent asset returns (T x N array)
            correlation_matrix: Current correlation matrix
            volume_data: Recent volume data for liquidity assessment

        Returns:
            MarketConditions object with current assessment
        """
        # Calculate volatility percentile
        current_volatility = np.std(recent_returns, axis=0).mean()
        self.volatility_history.append(current_volatility)

        # Keep only recent history
        if len(self.volatility_history) > self.lookback_periods:
            self.volatility_history = self.volatility_history[-self.lookback_periods:]

        volatility_percentile = np.percentile(self.volatility_history, current_volatility * 100)

        # Assess correlation stress
        correlation_stress = 0.3  # Default moderate stress
        if correlation_matrix is not None:
            # Calculate average correlation (excluding diagonal)
            n = correlation_matrix.shape[0]
            avg_correlation = (np.sum(correlation_matrix) - n) / (n * (n - 1))
            correlation_stress = min(abs(avg_correlation), 1.0)
            self.correlation_history.append(avg_correlation)

        # Assess liquidity (simplified - based on volume stability)
        liquidity_score = 0.7  # Default good liquidity
        if volume_data is not None:
            volume_volatility = np.std(volume_data) / np.mean(volume_data)
            liquidity_score = max(0.1, 1.0 - volume_volatility)

        # Assess momentum (simplified - based on recent returns trend)
        momentum_score = 0.0
        if len(recent_returns) > 10:
            short_trend = np.mean(recent_returns[-5:])
            long_trend = np.mean(recent_returns[-20:])
            momentum_score = (short_trend - long_trend) * 10  # Scale for readability

        # Determine market regime
        regime = self._classify_market_regime(
            volatility_percentile, correlation_stress, momentum_score
        )

        # Fear & greed index (simplified proxy)
        fear_greed_index = 50.0 + (momentum_score * 20) - (volatility_percentile - 50) * 0.5
        fear_greed_index = np.clip(fear_greed_index, 0, 100)

        conditions = MarketConditions(
            regime=regime,
            volatility_percentile=volatility_percentile,
            correlation_stress=correlation_stress,
            liquidity_score=liquidity_score,
            momentum_score=momentum_score,
            fear_greed_index=fear_greed_index,
            timestamp=datetime.now()
        )

        self.market_conditions = conditions
        return conditions

    def _classify_market_regime(self,
                              volatility_percentile: float,
                              correlation_stress: float,
                              momentum_score: float) -> MarketRegime:
        """
        Classify current market regime based on indicators
        """
        # High volatility + high correlation stress = Crash regime
        if volatility_percentile > 80 and correlation_stress > 0.7:
            return MarketRegime.CRASH

        # High volatility + negative momentum = Volatile regime
        elif volatility_percentile > 70 and momentum_score < -0.1:
            return MarketRegime.VOLATILE

        # Strong positive momentum = Bull regime
        elif momentum_score > 0.2:
            return MarketRegime.BULL

        # Strong negative momentum = Bear regime
        elif momentum_score < -0.2:
            return MarketRegime.BEAR

        # Moderate conditions recovering = Recovery regime
        elif volatility_percentile < 60 and momentum_score > 0.05:
            return MarketRegime.RECOVERY

        # Default to normal
        else:
            return MarketRegime.NORMAL

    def calculate_dynamic_thresholds(self,
                                   market_conditions: MarketConditions,
                                   portfolio_risk_metrics: RiskMetrics) -> RiskThresholds:
        """
        Calculate dynamic risk thresholds based on current market conditions

        Args:
            market_conditions: Current market condition assessment
            portfolio_risk_metrics: Current portfolio risk metrics

        Returns:
            Adjusted RiskThresholds object
        """
        # Base adjustments based on market regime
        regime_multipliers = {
            MarketRegime.NORMAL: 1.0,
            MarketRegime.RECOVERY: 0.9,  # Slightly more aggressive in recovery
            MarketRegime.BULL: 0.8,      # More aggressive in bull markets
            MarketRegime.VOLATILE: 1.5,  # More conservative in volatility
            MarketRegime.BEAR: 1.3,      # Conservative in bear markets
            MarketRegime.CRASH: 2.0      # Very conservative in crashes
        }

        regime_multiplier = regime_multipliers[market_conditions.regime]

        # Volatility-based adjustments
        volatility_adjustment = 1.0 + (market_conditions.volatility_percentile - 50) / 100 * self.adjustment_sensitivity

        # Correlation stress adjustments
        correlation_adjustment = 1.0 + market_conditions.correlation_stress * 0.5

        # Liquidity adjustments
        liquidity_adjustment = 2.0 - market_conditions.liquidity_score  # Inverse relationship

        # Combined adjustment factor
        total_adjustment = (regime_multiplier * volatility_adjustment *
                          correlation_adjustment * liquidity_adjustment)

        # Apply sensitivity dampening
        total_adjustment = 1.0 + (total_adjustment - 1.0) * self.adjustment_sensitivity

        # Calculate adjusted thresholds
        adjusted_thresholds = RiskThresholds(
            max_position_size=min(self.base_thresholds.max_position_size / total_adjustment, 0.05),
            max_portfolio_var=min(self.base_thresholds.max_portfolio_var * total_adjustment, 0.10),
            max_single_asset_var=min(self.base_thresholds.max_single_asset_var * total_adjustment, 0.08),
            max_correlation_exposure=min(self.base_thresholds.max_correlation_exposure / correlation_adjustment, 0.95),
            max_volatility_adjustment=self.base_thresholds.max_volatility_adjustment,
            circuit_breaker_threshold=self.base_thresholds.circuit_breaker_threshold * total_adjustment,
            emergency_stop_threshold=self.base_thresholds.emergency_stop_threshold * total_adjustment
        )

        self.current_thresholds = adjusted_thresholds
        return adjusted_thresholds

    def assess_arbitrage_opportunity_risk(self,
                                        opportunity_data: Dict[str, Any],
                                        market_conditions: MarketConditions) -> ArbitrageOpportunityRisk:
        """
        Assess risk for a specific arbitrage opportunity

        Args:
            opportunity_data: Opportunity details (prices, spreads, volumes, etc.)
            market_conditions: Current market conditions

        Returns:
            ArbitrageOpportunityRisk assessment
        """
        # Extract opportunity characteristics
        spread = opportunity_data.get('spread', 0.001)
        volume_ratio = opportunity_data.get('volume_ratio', 1.0)
        exchanges_involved = opportunity_data.get('exchanges', [])
        pair = opportunity_data.get('pair', 'UNKNOWN')

        # Base risk score (0-1 scale, higher = riskier)
        base_risk_score = 0.3  # Moderate base risk

        # Adjust for spread size (larger spreads = higher risk)
        spread_risk = min(spread * 100, 0.3)  # Cap at 30% additional risk
        base_risk_score += spread_risk

        # Adjust for volume imbalance
        volume_risk = abs(volume_ratio - 1.0) * 0.2  # Up to 20% additional risk
        base_risk_score += volume_risk

        # Adjust for exchange concentration risk
        exchange_risk = 0.0
        if len(exchanges_involved) < 2:
            exchange_risk = 0.2  # Single exchange risk
        elif len(exchanges_involved) > 3:
            exchange_risk = -0.1  # Diversification benefit
        base_risk_score += exchange_risk

        # Market condition adjustments
        market_adjustment = 0.0
        if market_conditions.regime == MarketRegime.CRASH:
            market_adjustment += 0.3
        elif market_conditions.regime == MarketRegime.VOLATILE:
            market_adjustment += 0.2
        elif market_conditions.regime == MarketRegime.BULL:
            market_adjustment -= 0.1  # Lower risk in bull markets

        adjusted_risk_score = min(base_risk_score + market_adjustment, 1.0)

        # Calculate position size limit based on risk score
        position_size_limit = self.current_thresholds.max_position_size * (1 - adjusted_risk_score)

        # Estimate execution probability (inverse of risk score)
        execution_probability = 1 - adjusted_risk_score

        # Estimate holding time (higher risk = longer holding)
        expected_holding_time = 300 + (adjusted_risk_score * 2700)  # 5min to 1 hour

        # Assess liquidation risk (higher in volatile markets)
        liquidation_risk = market_conditions.volatility_percentile / 100 * 0.5

        # Assess counterparty risk (exchange-specific)
        counterparty_risk = 0.1  # Base counterparty risk

        # Regulatory risk (MiCA compliance - very low for compliant pairs)
        regulatory_risk = 0.05 if pair.endswith('USDC') else 0.2

        return ArbitrageOpportunityRisk(
            opportunity_id=opportunity_data.get('id', 'unknown'),
            base_risk_score=base_risk_score,
            adjusted_risk_score=adjusted_risk_score,
            position_size_limit=position_size_limit,
            execution_probability=execution_probability,
            expected_holding_time=expected_holding_time,
            liquidation_risk=liquidation_risk,
            counterparty_risk=counterparty_risk,
            regulatory_risk=regulatory_risk
        )

    def check_circuit_breakers(self,
                             portfolio_metrics: RiskMetrics,
                             market_conditions: MarketConditions) -> Tuple[bool, bool, str]:
        """
        Check if circuit breakers should be activated

        Returns:
            Tuple of (circuit_breaker_triggered, emergency_stop_triggered, reason)
        """
        # Check circuit breaker conditions
        circuit_breaker_triggered = False
        emergency_stop_triggered = False
        reason = ""

        # Circuit breaker: Extreme portfolio loss
        if portfolio_metrics.var_95_hs > self.current_thresholds.circuit_breaker_threshold:
            circuit_breaker_triggered = True
            reason = f"Portfolio VaR ({portfolio_metrics.var_95_hs:.1%}) exceeds circuit breaker threshold"

        # Circuit breaker: Extreme volatility
        elif market_conditions.volatility_percentile > 95:
            circuit_breaker_triggered = True
            reason = f"Extreme volatility ({market_conditions.volatility_percentile:.1f} percentile)"

        # Circuit breaker: Correlation breakdown
        elif market_conditions.correlation_stress > 0.9:
            circuit_breaker_triggered = True
            reason = f"Correlation breakdown (stress: {market_conditions.correlation_stress:.1f})"

        # Emergency stop: Catastrophic conditions
        if portfolio_metrics.var_99_hs > self.current_thresholds.emergency_stop_threshold:
            emergency_stop_triggered = True
            reason = f"Emergency stop: Portfolio VaR ({portfolio_metrics.var_99_hs:.1%}) exceeds emergency threshold"

        # Update state
        self.circuit_breaker_active = circuit_breaker_triggered
        self.emergency_stop_active = emergency_stop_triggered

        # Trigger callbacks if activated
        if circuit_breaker_triggered:
            self._trigger_circuit_breaker_callbacks(reason)

        return circuit_breaker_triggered, emergency_stop_triggered, reason

    def add_risk_alert_callback(self, callback: Callable):
        """Add callback for risk alerts"""
        self.risk_alert_callbacks.append(callback)

    def add_circuit_breaker_callback(self, callback: Callable):
        """Add callback for circuit breaker events"""
        self.circuit_breaker_callbacks.append(callback)

    def _trigger_circuit_breaker_callbacks(self, reason: str):
        """Trigger circuit breaker callbacks"""
        for callback in self.circuit_breaker_callbacks:
            try:
                asyncio.create_task(callback(reason))
            except Exception as e:
                logger.error(f"Circuit breaker callback failed: {e}")

    async def start_monitoring(self):
        """Start real-time risk monitoring"""
        self.monitoring_active = True
        logger.info("Dynamic risk monitoring started")

        while self.monitoring_active:
            try:
                # This would integrate with live data feeds
                # For now, just sleep and check periodically
                await asyncio.sleep(self.update_frequency_seconds)

            except Exception as e:
                logger.error(f"Risk monitoring error: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    def stop_monitoring(self):
        """Stop risk monitoring"""
        self.monitoring_active = False
        logger.info("Dynamic risk monitoring stopped")

    def get_risk_dashboard(self) -> Dict[str, Any]:
        """
        Get comprehensive risk dashboard data

        Returns:
            Dict containing current risk state, thresholds, alerts, etc.
        """
        return {
            'current_thresholds': self.current_thresholds,
            'market_conditions': self.market_conditions,
            'circuit_breaker_active': self.circuit_breaker_active,
            'emergency_stop_active': self.emergency_stop_active,
            'recent_alerts': self.risk_alerts[-10:],  # Last 10 alerts
            'monitoring_active': self.monitoring_active,
            'last_update': datetime.now()
        }


# Integration functions for existing risk management
def integrate_dynamic_risk_adjustment(existing_risk_manager) -> DynamicRiskAdjustment:
    """
    Integrate dynamic risk adjustment with existing risk management system

    Args:
        existing_risk_manager: Existing RiskManager instance

    Returns:
        Configured DynamicRiskAdjustment instance
    """
    # Create dynamic risk adjustment with conservative base thresholds
    base_thresholds = RiskThresholds(
        max_position_size=0.02,  # 2%
        max_portfolio_var=0.05,  # 5%
        max_single_asset_var=0.03,  # 3%
        max_correlation_exposure=0.8,  # 80%
        max_volatility_adjustment=0.5,  # 50%
        circuit_breaker_threshold=0.10,  # 10%
        emergency_stop_threshold=0.15  # 15%
    )

    dynamic_risk = DynamicRiskAdjustment(
        base_risk_thresholds=base_thresholds,
        adjustment_sensitivity=0.7,
        lookback_periods=252
    )

    # Add callbacks to integrate with existing system
    def risk_alert_callback(alert_data):
        # Forward to existing risk manager's alert system
        if hasattr(existing_risk_manager, 'send_alert'):
            existing_risk_manager.send_alert("Dynamic Risk Alert", str(alert_data))

    def circuit_breaker_callback(reason):
        # Trigger existing emergency stop if available
        if hasattr(existing_risk_manager, 'emergency_stop'):
            existing_risk_manager.emergency_stop(reason)

    dynamic_risk.add_risk_alert_callback(risk_alert_callback)
    dynamic_risk.add_circuit_breaker_callback(circuit_breaker_callback)

    return dynamic_risk


if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.INFO)

    # Create dynamic risk adjustment instance
    risk_adjuster = DynamicRiskAdjustment()

    # Generate sample market data
    np.random.seed(42)
    sample_returns = np.random.normal(0.001, 0.03, (100, 5))  # 100 days, 5 assets

    # Assess market conditions
    market_conditions = risk_adjuster.assess_market_conditions(sample_returns)

    print("Market Conditions Assessment:")
    print(f"Regime: {market_conditions.regime.value}")
    print(f"Volatility Percentile: {market_conditions.volatility_percentile:.1f}")
    print(f"Correlation Stress: {market_conditions.correlation_stress:.2f}")
    print(f"Liquidity Score: {market_conditions.liquidity_score:.2f}")
    print(f"Momentum Score: {market_conditions.momentum_score:.2f}")

    # Calculate portfolio risk metrics
    portfolio_returns = np.mean(sample_returns, axis=1)
    risk_metrics = risk_adjuster.risk_metrics_calculator.calculate_comprehensive_risk_metrics(portfolio_returns)

    # Calculate dynamic thresholds
    dynamic_thresholds = risk_adjuster.calculate_dynamic_thresholds(market_conditions, risk_metrics)

    print(f"\nDynamic Risk Thresholds:")
    print(f"Max Position Size: {dynamic_thresholds.max_position_size:.1%}")
    print(f"Max Portfolio VaR: {dynamic_thresholds.max_portfolio_var:.1%}")
    print(f"Circuit Breaker Threshold: {dynamic_thresholds.circuit_breaker_threshold:.1%}")

    # Test arbitrage opportunity risk assessment
    opportunity_data = {
        'id': 'test_opportunity',
        'pair': 'XRP/USDC',
        'spread': 0.002,
        'volume_ratio': 1.2,
        'exchanges': ['binance', 'coinbase']
    }

    opportunity_risk = risk_adjuster.assess_arbitrage_opportunity_risk(opportunity_data, market_conditions)

    print(f"\nArbitrage Opportunity Risk Assessment:")
    print(f"Base Risk Score: {opportunity_risk.base_risk_score:.2f}")
    print(f"Adjusted Risk Score: {opportunity_risk.adjusted_risk_score:.2f}")
    print(f"Position Size Limit: {opportunity_risk.position_size_limit:.1%}")
    print(f"Execution Probability: {opportunity_risk.execution_probability:.2f}")

    # Check circuit breakers
    circuit_triggered, emergency_stop, reason = risk_adjuster.check_circuit_breakers(risk_metrics, market_conditions)

    print(f"\nCircuit Breaker Check:")
    print(f"Circuit Breaker Active: {circuit_triggered}")
    print(f"Emergency Stop Active: {emergency_stop}")
    if reason:
        print(f"Reason: {reason}")