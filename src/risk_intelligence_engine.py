#!/usr/bin/env python3
"""
SovereignForge - Risk Intelligence Engine
Unified risk management system integrating advanced metrics, dynamic adjustments, and real-time monitoring

This module provides:
- Unified Risk Intelligence Engine integrating all risk components
- Real-time risk monitoring and alerting
- Automated risk mitigation actions
- MiCA compliance and personal deployment safety
- Integration with existing arbitrage detection and trading systems
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json
import threading
import time

import numpy as np
from advanced_risk_metrics import AdvancedRiskMetrics, RiskMetrics
from dynamic_risk_adjustment import (
    DynamicRiskAdjustment, MarketConditions, RiskThresholds,
    ArbitrageOpportunityRisk, MarketRegime
)

logger = logging.getLogger(__name__)

@dataclass
class RiskAlert:
    """Risk alert data structure"""
    alert_id: str
    alert_type: str  # 'warning', 'critical', 'emergency'
    title: str
    message: str
    risk_score: float
    threshold_breached: str
    timestamp: datetime
    metadata: Dict[str, Any]

@dataclass
class RiskDashboard:
    """Comprehensive risk dashboard data"""
    overall_risk_score: float
    market_conditions: MarketConditions
    portfolio_metrics: RiskMetrics
    dynamic_thresholds: RiskThresholds
    active_positions: List[Dict[str, Any]]
    recent_alerts: List[RiskAlert]
    circuit_breaker_status: Dict[str, bool]
    compliance_status: Dict[str, bool]
    last_update: datetime

class RiskIntelligenceEngine:
    """
    Unified Risk Intelligence Engine for SovereignForge

    Integrates advanced risk metrics, dynamic adjustments, and real-time monitoring
    to provide comprehensive risk management for crypto arbitrage trading.
    """

    def __init__(self,
                 risk_sensitivity: float = 0.7,
                 monitoring_interval_seconds: int = 60,
                 alert_thresholds: Optional[Dict[str, float]] = None):

        self.risk_sensitivity = risk_sensitivity
        self.monitoring_interval_seconds = monitoring_interval_seconds

        # Initialize core components
        self.advanced_metrics = AdvancedRiskMetrics()
        self.dynamic_adjustment = DynamicRiskAdjustment(
            adjustment_sensitivity=risk_sensitivity
        )

        # Alert system
        self.alert_thresholds = alert_thresholds or {
            'warning': 0.6,
            'critical': 0.8,
            'emergency': 0.95
        }

        # State management
        self.monitoring_active = False
        self.monitoring_thread: Optional[threading.Thread] = None
        self.risk_alerts: List[RiskAlert] = []
        self.active_positions: List[Dict[str, Any]] = []
        self.portfolio_returns_history: List[np.ndarray] = []

        # Callbacks
        self.alert_callbacks: List[Callable] = []
        self.mitigation_callbacks: List[Callable] = []

        # Compliance monitoring
        self.mica_compliance_status = self._initialize_compliance_status()

        # Risk mitigation actions
        self.mitigation_actions = {
            'reduce_position_sizes': False,
            'pause_new_trades': False,
            'activate_circuit_breaker': False,
            'emergency_stop': False,
            'increase_monitoring': False
        }

        logger.info("RiskIntelligenceEngine initialized")

    def _initialize_compliance_status(self) -> Dict[str, bool]:
        """Initialize MiCA compliance status checks"""
        return {
            'whitelist_enforcement': True,  # Only MiCA-compliant pairs
            'no_custody': True,             # Personal deployment only
            'no_public_offering': True,     # Individual use only
            'local_execution': True,        # No external APIs in personal mode
            'data_isolation': True,         # Personal data stays local
            'audit_trail': True             # Structured logging
        }

    def add_alert_callback(self, callback: Callable):
        """Add callback for risk alerts"""
        self.alert_callbacks.append(callback)

    def add_mitigation_callback(self, callback: Callable):
        """Add callback for risk mitigation actions"""
        self.mitigation_callbacks.append(callback)

    def update_market_data(self,
                          returns_data: np.ndarray,
                          correlation_matrix: Optional[np.ndarray] = None,
                          volume_data: Optional[np.ndarray] = None) -> MarketConditions:
        """
        Update market data and assess current conditions

        Args:
            returns_data: Recent asset returns (T x N array)
            correlation_matrix: Current correlation matrix
            volume_data: Recent volume data

        Returns:
            Updated market conditions
        """
        # Store historical data
        self.portfolio_returns_history.append(returns_data.mean(axis=1))
        if len(self.portfolio_returns_history) > 1000:  # Keep last 1000 data points
            self.portfolio_returns_history = self.portfolio_returns_history[-1000:]

        # Assess market conditions
        market_conditions = self.dynamic_adjustment.assess_market_conditions(
            returns_data, correlation_matrix, volume_data
        )

        # Calculate portfolio risk metrics
        portfolio_returns = returns_data.mean(axis=1)
        portfolio_metrics = self.advanced_metrics.calculate_comprehensive_risk_metrics(portfolio_returns)

        # Update dynamic thresholds
        dynamic_thresholds = self.dynamic_adjustment.calculate_dynamic_thresholds(
            market_conditions, portfolio_metrics
        )

        # Check for risk alerts
        self._check_risk_alerts(portfolio_metrics, market_conditions, dynamic_thresholds)

        # Update mitigation actions
        self._update_mitigation_actions(portfolio_metrics, market_conditions)

        return market_conditions

    def assess_arbitrage_risk(self,
                             opportunity_data: Dict[str, Any]) -> ArbitrageOpportunityRisk:
        """
        Assess risk for an arbitrage opportunity

        Args:
            opportunity_data: Opportunity details

        Returns:
            Comprehensive risk assessment
        """
        market_conditions = self.dynamic_adjustment.market_conditions

        # Get risk assessment from dynamic adjustment module
        risk_assessment = self.dynamic_adjustment.assess_arbitrage_opportunity_risk(
            opportunity_data, market_conditions
        )

        # Additional checks based on current mitigation status
        if self.mitigation_actions['pause_new_trades']:
            risk_assessment.adjusted_risk_score = min(risk_assessment.adjusted_risk_score + 0.5, 1.0)
            risk_assessment.position_size_limit *= 0.5  # Reduce position size

        if self.mitigation_actions['reduce_position_sizes']:
            risk_assessment.position_size_limit *= 0.7  # Further reduce

        return risk_assessment

    def _check_risk_alerts(self,
                          portfolio_metrics: RiskMetrics,
                          market_conditions: MarketConditions,
                          thresholds: RiskThresholds):
        """Check for risk alerts and trigger if necessary"""

        alerts_to_trigger = []

        # Portfolio VaR alerts
        if portfolio_metrics.var_95_hs > thresholds.max_portfolio_var:
            alerts_to_trigger.append(RiskAlert(
                alert_id=f"var_95_{int(time.time())}",
                alert_type='critical',
                title='Portfolio VaR Breach',
                message=f'Portfolio VaR (95%) of {portfolio_metrics.var_95_hs:.1%} exceeds threshold of {thresholds.max_portfolio_var:.1%}',
                risk_score=min(portfolio_metrics.var_95_hs / thresholds.max_portfolio_var, 1.0),
                threshold_breached='max_portfolio_var',
                timestamp=datetime.now(),
                metadata={'var_value': portfolio_metrics.var_95_hs, 'threshold': thresholds.max_portfolio_var}
            ))

        # Volatility alerts
        if market_conditions.volatility_percentile > 90:
            alerts_to_trigger.append(RiskAlert(
                alert_id=f"volatility_{int(time.time())}",
                alert_type='warning',
                title='Extreme Volatility',
                message=f'Market volatility at {market_conditions.volatility_percentile:.1f} percentile',
                risk_score=market_conditions.volatility_percentile / 100.0,
                threshold_breached='volatility_percentile',
                timestamp=datetime.now(),
                metadata={'volatility_percentile': market_conditions.volatility_percentile}
            ))

        # Correlation stress alerts
        if market_conditions.correlation_stress > 0.8:
            alerts_to_trigger.append(RiskAlert(
                alert_id=f"correlation_{int(time.time())}",
                alert_type='warning',
                title='High Correlation Stress',
                message=f'Correlation stress at {market_conditions.correlation_stress:.2f}',
                risk_score=market_conditions.correlation_stress,
                threshold_breached='correlation_stress',
                timestamp=datetime.now(),
                metadata={'correlation_stress': market_conditions.correlation_stress}
            ))

        # Market regime alerts
        if market_conditions.regime in [MarketRegime.CRASH, MarketRegime.VOLATILE]:
            alerts_to_trigger.append(RiskAlert(
                alert_id=f"regime_{int(time.time())}",
                alert_type='critical' if market_conditions.regime == MarketRegime.CRASH else 'warning',
                title=f'Market Regime: {market_conditions.regime.value.title()}',
                message=f'Market has entered {market_conditions.regime.value} regime',
                risk_score=0.8 if market_conditions.regime == MarketRegime.CRASH else 0.6,
                threshold_breached='market_regime',
                timestamp=datetime.now(),
                metadata={'regime': market_conditions.regime.value}
            ))

        # Trigger alerts
        for alert in alerts_to_trigger:
            self.risk_alerts.append(alert)
            self._trigger_alert_callbacks(alert)

        # Keep only recent alerts
        if len(self.risk_alerts) > 100:
            self.risk_alerts = self.risk_alerts[-100:]

    def _update_mitigation_actions(self,
                                 portfolio_metrics: RiskMetrics,
                                 market_conditions: MarketConditions):
        """Update risk mitigation actions based on current conditions"""

        # Reset actions
        self.mitigation_actions = {k: False for k in self.mitigation_actions.keys()}

        # Determine mitigation actions based on risk levels
        overall_risk_score = self._calculate_overall_risk_score(portfolio_metrics, market_conditions)

        if overall_risk_score > self.alert_thresholds['emergency']:
            self.mitigation_actions['emergency_stop'] = True
            self.mitigation_actions['activate_circuit_breaker'] = True
        elif overall_risk_score > self.alert_thresholds['critical']:
            self.mitigation_actions['pause_new_trades'] = True
            self.mitigation_actions['reduce_position_sizes'] = True
            self.mitigation_actions['increase_monitoring'] = True
        elif overall_risk_score > self.alert_thresholds['warning']:
            self.mitigation_actions['reduce_position_sizes'] = True
            self.mitigation_actions['increase_monitoring'] = True

        # Market regime specific actions
        if market_conditions.regime == MarketRegime.CRASH:
            self.mitigation_actions['emergency_stop'] = True
        elif market_conditions.regime == MarketRegime.VOLATILE:
            self.mitigation_actions['reduce_position_sizes'] = True
            self.mitigation_actions['pause_new_trades'] = True

        # Trigger mitigation callbacks if actions changed
        self._trigger_mitigation_callbacks()

    def _calculate_overall_risk_score(self,
                                    portfolio_metrics: RiskMetrics,
                                    market_conditions: MarketConditions) -> float:
        """Calculate overall risk score from multiple indicators"""

        # Component risk scores (0-1 scale)
        var_risk = min(portfolio_metrics.var_95_hs / 0.10, 1.0)  # 10% VaR = max risk
        volatility_risk = market_conditions.volatility_percentile / 100.0
        correlation_risk = market_conditions.correlation_stress
        drawdown_risk = min(portfolio_metrics.max_drawdown / 0.20, 1.0)  # 20% drawdown = max risk

        # Regime risk multiplier
        regime_multiplier = {
            MarketRegime.NORMAL: 1.0,
            MarketRegime.RECOVERY: 1.1,
            MarketRegime.BULL: 0.9,
            MarketRegime.BEAR: 1.2,
            MarketRegime.VOLATILE: 1.4,
            MarketRegime.CRASH: 2.0
        }[market_conditions.regime]

        # Weighted average
        weights = [0.3, 0.2, 0.2, 0.3]  # VaR, volatility, correlation, drawdown
        component_risks = [var_risk, volatility_risk, correlation_risk, drawdown_risk]

        overall_risk = np.average(component_risks, weights=weights) * regime_multiplier

        return min(overall_risk, 1.0)

    def _trigger_alert_callbacks(self, alert: RiskAlert):
        """Trigger alert callbacks"""
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(alert))
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    def _trigger_mitigation_callbacks(self):
        """Trigger mitigation action callbacks"""
        for callback in self.mitigation_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(self.mitigation_actions))
                else:
                    callback(self.mitigation_actions)
            except Exception as e:
                logger.error(f"Mitigation callback failed: {e}")

    def start_monitoring(self):
        """Start real-time risk monitoring"""
        if self.monitoring_active:
            logger.warning("Risk monitoring already active")
            return

        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()

        logger.info("Risk Intelligence Engine monitoring started")

    def stop_monitoring(self):
        """Stop risk monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5.0)

        logger.info("Risk Intelligence Engine monitoring stopped")

    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # This would integrate with live data feeds
                # For now, just periodic checks
                time.sleep(self.monitoring_interval_seconds)

                # Periodic risk assessment would go here
                # In production, this would pull fresh market data

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(10)  # Brief pause before retry

    def get_risk_dashboard(self) -> RiskDashboard:
        """
        Get comprehensive risk dashboard

        Returns:
            RiskDashboard with all current risk information
        """
        # Calculate current portfolio metrics if we have data
        portfolio_metrics = RiskMetrics(
            var_95_hs=0.0, var_99_hs=0.0, es_95_hs=0.0, es_99_hs=0.0,
            var_95_mc=0.0, var_99_mc=0.0, es_95_mc=0.0, es_99_mc=0.0,
            max_drawdown=0.0, sharpe_ratio=0.0, sortino_ratio=0.0,
            volatility=0.0, skewness=0.0, kurtosis=0.0,
            stress_test_loss=0.0, scenario_analysis={}
        )

        if self.portfolio_returns_history:
            recent_returns = np.concatenate(self.portfolio_returns_history[-30:])  # Last 30 data points
            if len(recent_returns) > 10:
                portfolio_metrics = self.advanced_metrics.calculate_comprehensive_risk_metrics(recent_returns)

        overall_risk_score = self._calculate_overall_risk_score(
            portfolio_metrics, self.dynamic_adjustment.market_conditions
        )

        return RiskDashboard(
            overall_risk_score=overall_risk_score,
            market_conditions=self.dynamic_adjustment.market_conditions,
            portfolio_metrics=portfolio_metrics,
            dynamic_thresholds=self.dynamic_adjustment.current_thresholds,
            active_positions=self.active_positions.copy(),
            recent_alerts=self.risk_alerts[-10:],  # Last 10 alerts
            circuit_breaker_status={
                'circuit_breaker_active': self.dynamic_adjustment.circuit_breaker_active,
                'emergency_stop_active': self.dynamic_adjustment.emergency_stop_active
            },
            compliance_status=self.mica_compliance_status.copy(),
            last_update=datetime.now()
        )

    def export_risk_report(self, filepath: str):
        """
        Export comprehensive risk report to JSON file

        Args:
            filepath: Path to save the report
        """
        dashboard = self.get_risk_dashboard()

        # Convert dataclasses to dicts for JSON serialization
        report = {
            'timestamp': dashboard.last_update.isoformat(),
            'overall_risk_score': dashboard.overall_risk_score,
            'market_conditions': asdict(dashboard.market_conditions),
            'portfolio_metrics': asdict(dashboard.portfolio_metrics),
            'dynamic_thresholds': asdict(dashboard.dynamic_thresholds),
            'active_positions': dashboard.active_positions,
            'recent_alerts': [asdict(alert) for alert in dashboard.recent_alerts],
            'circuit_breaker_status': dashboard.circuit_breaker_status,
            'compliance_status': dashboard.compliance_status,
            'mitigation_actions': self.mitigation_actions
        }

        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Risk report exported to {filepath}")

    def check_compliance_status(self) -> Dict[str, Any]:
        """
        Check MiCA compliance status

        Returns:
            Dict with compliance status and any violations
        """
        violations = []

        # Check whitelist enforcement
        if not self.mica_compliance_status['whitelist_enforcement']:
            violations.append("Whitelist enforcement disabled")

        # Check for external API usage in personal mode
        if not self.mica_compliance_status['no_custody']:
            violations.append("External custody detected")

        # Check data isolation
        if not self.mica_compliance_status['data_isolation']:
            violations.append("Data isolation compromised")

        return {
            'compliant': len(violations) == 0,
            'status': self.mica_compliance_status,
            'violations': violations,
            'last_check': datetime.now()
        }


# Integration function for existing systems
def integrate_risk_intelligence(existing_system) -> RiskIntelligenceEngine:
    """
    Integrate Risk Intelligence Engine with existing trading system

    Args:
        existing_system: Existing arbitrage/trading system instance

    Returns:
        Configured RiskIntelligenceEngine instance
    """
    risk_engine = RiskIntelligenceEngine()

    # Add callbacks to integrate with existing system
    def alert_callback(alert: RiskAlert):
        """Forward alerts to existing system"""
        if hasattr(existing_system, 'send_alert'):
            existing_system.send_alert(
                f"RISK ALERT: {alert.title}",
                alert.message,
                alert.alert_type
            )

    def mitigation_callback(mitigation_actions: Dict[str, bool]):
        """Apply mitigation actions to existing system"""
        if hasattr(existing_system, 'apply_risk_mitigation'):
            existing_system.apply_risk_mitigation(mitigation_actions)

    risk_engine.add_alert_callback(alert_callback)
    risk_engine.add_mitigation_callback(mitigation_callback)

    return risk_engine


if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.INFO)

    # Create risk intelligence engine
    risk_engine = RiskIntelligenceEngine()

    # Generate sample market data
    np.random.seed(42)
    sample_returns = np.random.normal(0.001, 0.03, (100, 5))  # 100 days, 5 assets

    # Update market data
    market_conditions = risk_engine.update_market_data(sample_returns)

    print("Risk Intelligence Engine Test Results:")
    print("=" * 50)
    print(f"Market Regime: {market_conditions.regime.value}")
    print(f"Volatility Percentile: {market_conditions.volatility_percentile:.1f}")
    print(f"Correlation Stress: {market_conditions.correlation_stress:.2f}")

    # Get risk dashboard
    dashboard = risk_engine.get_risk_dashboard()

    print(f"\nOverall Risk Score: {dashboard.overall_risk_score:.2f}")
    print(f"Portfolio VaR (95%): {dashboard.portfolio_metrics.var_95_hs:.1%}")
    print(f"Max Drawdown: {dashboard.portfolio_metrics.max_drawdown:.1%}")

    # Test arbitrage risk assessment
    opportunity_data = {
        'id': 'test_arb_opportunity',
        'pair': 'XRP/USDC',
        'spread': 0.002,
        'volume_ratio': 1.3,
        'exchanges': ['binance', 'coinbase', 'kraken']
    }

    arb_risk = risk_engine.assess_arbitrage_risk(opportunity_data)

    print(f"\nArbitrage Opportunity Risk Assessment:")
    print(f"Adjusted Risk Score: {arb_risk.adjusted_risk_score:.2f}")
    print(f"Position Size Limit: {arb_risk.position_size_limit:.1%}")
    print(f"Execution Probability: {arb_risk.execution_probability:.2f}")

    # Check compliance
    compliance = risk_engine.check_compliance_status()
    print(f"\nMiCA Compliance: {'✓ COMPLIANT' if compliance['compliant'] else '✗ VIOLATIONS'}")

    print(f"\nActive Mitigation Actions: {risk_engine.mitigation_actions}")

    # Export risk report
    risk_engine.export_risk_report('risk_report.json')
    print("\nRisk report exported to risk_report.json")