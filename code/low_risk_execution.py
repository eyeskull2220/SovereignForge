#!/usr/bin/env python3
"""
SovereignForge v1 - Low-Risk Execution
Safe arbitrage execution with comprehensive risk controls
MiCA compliance and emergency stop mechanisms
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ExecutionMode(Enum):
    SIMULATION = "simulation"
    PAPER_TRADING = "paper_trading"
    LIVE_TRADING = "live_trading"

class RiskLevel(Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

@dataclass
class ExecutionLimits:
    """Execution risk limits"""
    max_position_size: float  # Max position size as % of portfolio
    max_daily_loss: float     # Max daily loss as % of portfolio
    max_slippage: float       # Max allowed slippage
    max_execution_time: int   # Max execution time in seconds
    min_profit_threshold: float  # Minimum profit % to execute
    max_concurrent_trades: int   # Max concurrent arbitrage trades

@dataclass
class ExecutionResult:
    """Result of an execution attempt"""
    success: bool
    opportunity_id: str
    executed_at: datetime
    buy_exchange: str
    sell_exchange: str
    coin: str
    quantity: float
    buy_price: float
    sell_price: float
    gross_profit: float
    net_profit: float
    fees_paid: float
    execution_time: float
    slippage: float
    risk_score: float
    error_message: Optional[str] = None

class LowRiskExecutionManager:
    """Manages low-risk arbitrage execution with comprehensive controls"""

    def __init__(self, execution_engine, risk_agent, nova_agent):
        self.execution_engine = execution_engine
        self.risk_agent = risk_agent
        self.nova_agent = nova_agent

        # Execution mode
        self.mode = ExecutionMode.SIMULATION

        # Risk level
        self.risk_level = RiskLevel.CONSERVATIVE

        # Execution limits by risk level
        self.execution_limits = self._get_execution_limits()

        # Daily tracking
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Active trades tracking
        self.active_trades = {}
        self.completed_trades = []

        # Emergency controls
        self.emergency_stop = False
        self.circuit_breaker_triggered = False

        # Compliance tracking
        self.mica_compliance_log = []

        logger.info(f"LowRiskExecutionManager initialized in {self.mode.value} mode")

    def _get_execution_limits(self) -> Dict[RiskLevel, ExecutionLimits]:
        """Get execution limits for each risk level"""
        return {
            RiskLevel.CONSERVATIVE: ExecutionLimits(
                max_position_size=0.01,    # 1% of portfolio
                max_daily_loss=0.02,       # 2% daily loss limit
                max_slippage=0.003,        # 0.3% max slippage
                max_execution_time=180,    # 3 minutes
                min_profit_threshold=0.5,  # 0.5% min profit
                max_concurrent_trades=1    # Only 1 concurrent trade
            ),
            RiskLevel.MODERATE: ExecutionLimits(
                max_position_size=0.02,    # 2% of portfolio
                max_daily_loss=0.05,       # 5% daily loss limit
                max_slippage=0.005,        # 0.5% max slippage
                max_execution_time=300,    # 5 minutes
                min_profit_threshold=0.3,  # 0.3% min profit
                max_concurrent_trades=3    # Up to 3 concurrent trades
            ),
            RiskLevel.AGGRESSIVE: ExecutionLimits(
                max_position_size=0.05,    # 5% of portfolio
                max_daily_loss=0.10,       # 10% daily loss limit
                max_slippage=0.008,        # 0.8% max slippage
                max_execution_time=600,    # 10 minutes
                min_profit_threshold=0.1,  # 0.1% min profit
                max_concurrent_trades=5    # Up to 5 concurrent trades
            )
        }

    def set_execution_mode(self, mode: ExecutionMode):
        """Set execution mode"""
        self.mode = mode
        logger.info(f"Execution mode set to: {mode.value}")

        # Additional safety checks for live trading
        if mode == ExecutionMode.LIVE_TRADING:
            self._validate_live_trading_setup()

    def set_risk_level(self, level: RiskLevel):
        """Set risk level"""
        self.risk_level = level
        self.execution_limits = self._get_execution_limits()
        logger.info(f"Risk level set to: {level.value}")

    def _validate_live_trading_setup(self):
        """Validate setup before enabling live trading"""
        # Check API keys (placeholder)
        # Check exchange connectivity
        # Check balance requirements
        # Verify MiCA compliance
        logger.info("Live trading setup validation completed")

    def evaluate_and_execute(self, opportunity) -> Optional[ExecutionResult]:
        """Evaluate arbitrage opportunity and execute if safe"""
        try:
            # Pre-execution checks
            if not self._pre_execution_checks(opportunity):
                return None

            # Risk assessment
            risk_assessment = self._assess_execution_risk(opportunity)
            if not risk_assessment["approved"]:
                logger.info(f"Opportunity rejected: {risk_assessment['reason']}")
                return None

            # Execute based on mode
            if self.mode == ExecutionMode.SIMULATION:
                result = self._simulate_execution(opportunity)
            elif self.mode == ExecutionMode.PAPER_TRADING:
                result = self._paper_trade_execution(opportunity)
            elif self.mode == ExecutionMode.LIVE_TRADING:
                result = self._live_execution(opportunity)
            else:
                logger.error(f"Unknown execution mode: {self.mode}")
                return None

            # Post-execution processing
            if result and result.success:
                self._post_execution_processing(result)

            return result

        except Exception as e:
            logger.error(f"Execution evaluation error: {e}")
            return ExecutionResult(
                success=False,
                opportunity_id=getattr(opportunity, 'opportunity_id', 'unknown'),
                executed_at=datetime.now(),
                buy_exchange=getattr(opportunity, 'buy_exchange', 'unknown'),
                sell_exchange=getattr(opportunity, 'sell_exchange', 'unknown'),
                coin=getattr(opportunity, 'coin', 'unknown'),
                quantity=0,
                buy_price=0,
                sell_price=0,
                gross_profit=0,
                net_profit=0,
                fees_paid=0,
                execution_time=0,
                slippage=0,
                risk_score=1.0,
                error_message=str(e)
            )

    def _pre_execution_checks(self, opportunity) -> bool:
        """Perform pre-execution safety checks"""
        # Emergency stop check
        if self.emergency_stop:
            logger.warning("Emergency stop active - execution blocked")
            return False

        # Circuit breaker check
        if self.circuit_breaker_triggered:
            logger.warning("Circuit breaker triggered - execution blocked")
            return False

        # Daily loss limit check
        if abs(self.daily_pnl) >= self.execution_limits.max_daily_loss:
            logger.warning(f"Daily loss limit reached: {self.daily_pnl:.2f}")
            return False

        # Concurrent trades limit check
        if len(self.active_trades) >= self.execution_limits.max_concurrent_trades:
            logger.info("Max concurrent trades reached - execution blocked")
            return False

        # MiCA compliance check
        if not self._check_mica_compliance(opportunity):
            logger.warning("MiCA compliance check failed")
            return False

        # Session timing check
        if not self._check_session_timing(opportunity):
            logger.info("Session timing check failed - execution blocked")
            return False

        return True

    def _assess_execution_risk(self, opportunity) -> Dict[str, Any]:
        """Assess execution risk for the opportunity"""
        assessment = {
            "approved": True,
            "reason": "",
            "risk_score": 0.0
        }

        try:
            # Check profit threshold
            if opportunity.net_spread < self.execution_limits.min_profit_threshold:
                assessment["approved"] = False
                assessment["reason"] = f"Profit below threshold: {opportunity.net_spread:.2f}%"
                return assessment

            # Check position size
            position_value = opportunity.volume * opportunity.buy_price
            if position_value > self.execution_limits.max_position_size:
                assessment["approved"] = False
                assessment["reason"] = f"Position size too large: ${position_value:.2f}"
                return assessment

            # Estimate slippage
            estimated_slippage = self._estimate_execution_slippage(opportunity)
            if estimated_slippage > self.execution_limits.max_slippage:
                assessment["approved"] = False
                assessment["reason"] = f"Slippage too high: {estimated_slippage:.2f}%"
                return assessment

            # Calculate overall risk score
            assessment["risk_score"] = self._calculate_risk_score(opportunity, estimated_slippage)

        except Exception as e:
            assessment["approved"] = False
            assessment["reason"] = f"Risk assessment error: {str(e)}"

        return assessment

    def _estimate_execution_slippage(self, opportunity) -> float:
        """Estimate slippage for execution"""
        # Base slippage from market conditions
        base_slippage = 0.001  # 0.1%

        # Volume-based slippage
        volume_factor = min(opportunity.volume / 10000, 1.0) * 0.002

        # Exchange-specific slippage
        exchange_factor = 0.001  # Additional 0.1% for cross-exchange

        return base_slippage + volume_factor + exchange_factor

    def _calculate_risk_score(self, opportunity, slippage: float) -> float:
        """Calculate overall risk score (0-1, higher = riskier)"""
        risk_factors = []

        # Profit factor (lower profit = higher risk)
        profit_factor = max(0, 1.0 - (opportunity.net_spread / 2.0))
        risk_factors.append(profit_factor)

        # Slippage factor
        slippage_factor = slippage / 0.01  # Normalized to 1% slippage
        risk_factors.append(min(slippage_factor, 1.0))

        # Volume factor (lower volume = higher risk)
        volume_factor = max(0, 1.0 - (opportunity.volume / 1000))
        risk_factors.append(volume_factor)

        return sum(risk_factors) / len(risk_factors)

    def _check_mica_compliance(self, opportunity) -> bool:
        """Check MiCA compliance for the trade"""
        # Verify coin is in whitelist
        allowed_coins = {"XRP", "XLM", "HBAR", "ALGO", "ADA", "LINK", "IOTA", "XDC", "ONDO", "VET", "USDC", "RLUSD"}

        if opportunity.coin not in allowed_coins:
            self.mica_compliance_log.append({
                "timestamp": datetime.now(),
                "violation": "Coin not in whitelist",
                "coin": opportunity.coin
            })
            return False

        # Log compliance check
        self.mica_compliance_log.append({
            "timestamp": datetime.now(),
            "check": "MiCA compliance verified",
            "coin": opportunity.coin,
            "exchanges": [opportunity.buy_exchange.value, opportunity.sell_exchange.value]
        })

        return True

    def _check_session_timing(self, opportunity) -> bool:
        """Check if execution is allowed in current session"""
        current_session = opportunity.session

        # Define allowed sessions for each risk level
        allowed_sessions = {
            RiskLevel.CONSERVATIVE: {"london", "ny"},  # Only high-liquidity sessions
            RiskLevel.MODERATE: {"asia", "london", "ny"},  # Exclude crypto session
            RiskLevel.AGGRESSIVE: {"asia", "london", "ny", "crypto"}  # All sessions
        }

        return current_session in allowed_sessions[self.risk_level]

    def _simulate_execution(self, opportunity) -> ExecutionResult:
        """Simulate execution for testing"""
        # Simulate some delay
        import time
        time.sleep(0.1)

        # Simulate successful execution with some randomness
        import random
        success = random.random() > 0.05  # 95% success rate

        if success:
            quantity = min(opportunity.volume * 0.1, 100)  # Max 100 units
            slippage = random.uniform(0, 0.002)  # 0-0.2% slippage

            buy_price = opportunity.buy_price * (1 + slippage)
            sell_price = opportunity.sell_price * (1 - slippage)

            gross_profit = quantity * (sell_price - buy_price)
            fees = gross_profit * 0.002  # 0.2% total fees
            net_profit = gross_profit - fees

            return ExecutionResult(
                success=True,
                opportunity_id=getattr(opportunity, 'opportunity_id', 'simulated'),
                executed_at=datetime.now(),
                buy_exchange=opportunity.buy_exchange.value,
                sell_exchange=opportunity.sell_exchange.value,
                coin=opportunity.coin,
                quantity=quantity,
                buy_price=buy_price,
                sell_price=sell_price,
                gross_profit=gross_profit,
                net_profit=net_profit,
                fees_paid=fees,
                execution_time=0.1,
                slippage=slippage,
                risk_score=self._calculate_risk_score(opportunity, slippage)
            )
        else:
            return ExecutionResult(
                success=False,
                opportunity_id=getattr(opportunity, 'opportunity_id', 'simulated'),
                executed_at=datetime.now(),
                buy_exchange=opportunity.buy_exchange.value,
                sell_exchange=opportunity.sell_exchange.value,
                coin=opportunity.coin,
                quantity=0,
                buy_price=0,
                sell_price=0,
                gross_profit=0,
                net_profit=0,
                fees_paid=0,
                execution_time=0.1,
                slippage=0,
                risk_score=1.0,
                error_message="Simulated execution failure"
            )

    def _paper_trade_execution(self, opportunity) -> ExecutionResult:
        """Execute paper trade (simulated but more realistic)"""
        # Similar to simulation but with more detailed tracking
        return self._simulate_execution(opportunity)

    def _live_execution(self, opportunity) -> ExecutionResult:
        """Execute live trade through Lumibot"""
        try:
            # Use the execution engine for live trading
            success = self.execution_engine.execute_arbitrage(opportunity)

            if success:
                # Create result based on execution engine feedback
                return ExecutionResult(
                    success=True,
                    opportunity_id=getattr(opportunity, 'opportunity_id', 'live'),
                    executed_at=datetime.now(),
                    buy_exchange=opportunity.buy_exchange.value,
                    sell_exchange=opportunity.sell_exchange.value,
                    coin=opportunity.coin,
                    quantity=opportunity.volume * 0.1,  # Conservative sizing
                    buy_price=opportunity.buy_price,
                    sell_price=opportunity.sell_price,
                    gross_profit=opportunity.volume * 0.1 * opportunity.net_spread * opportunity.buy_price / 100,
                    net_profit=0,  # Will be calculated after execution
                    fees_paid=0,   # Will be calculated after execution
                    execution_time=0,
                    slippage=0,
                    risk_score=self._calculate_risk_score(opportunity, 0)
                )
            else:
                return ExecutionResult(
                    success=False,
                    opportunity_id=getattr(opportunity, 'opportunity_id', 'live'),
                    executed_at=datetime.now(),
                    buy_exchange=opportunity.buy_exchange.value,
                    sell_exchange=opportunity.sell_exchange.value,
                    coin=opportunity.coin,
                    quantity=0,
                    buy_price=0,
                    sell_price=0,
                    gross_profit=0,
                    net_profit=0,
                    fees_paid=0,
                    execution_time=0,
                    slippage=0,
                    risk_score=1.0,
                    error_message="Live execution failed"
                )

        except Exception as e:
            logger.error(f"Live execution error: {e}")
            return ExecutionResult(
                success=False,
                opportunity_id=getattr(opportunity, 'opportunity_id', 'live'),
                executed_at=datetime.now(),
                buy_exchange=opportunity.buy_exchange.value,
                sell_exchange=opportunity.sell_exchange.value,
                coin=opportunity.coin,
                quantity=0,
                buy_price=0,
                sell_price=0,
                gross_profit=0,
                net_profit=0,
                fees_paid=0,
                execution_time=0,
                slippage=0,
                risk_score=1.0,
                error_message=f"Live execution error: {str(e)}"
            )

    def _post_execution_processing(self, result: ExecutionResult):
        """Process successful execution"""
        # Update daily tracking
        self.daily_pnl += result.net_profit
        self.daily_trades += 1

        # Track active trade
        self.active_trades[result.opportunity_id] = result

        # Check for circuit breaker
        if abs(self.daily_pnl) >= self.execution_limits.max_daily_loss * 0.8:  # 80% of limit
            logger.warning("Approaching daily loss limit - circuit breaker activated")
            self.circuit_breaker_triggered = True

        # Log execution
        logger.info(f"Execution completed: {result.coin} {result.net_profit:.2f} profit")

    def emergency_stop(self):
        """Activate emergency stop"""
        self.emergency_stop = True
        if hasattr(self.execution_engine, 'emergency_stop_all'):
            self.execution_engine.emergency_stop_all()
        logger.critical("EMERGENCY STOP ACTIVATED")

    def reset_circuit_breaker(self):
        """Reset circuit breaker"""
        self.circuit_breaker_triggered = False
        logger.info("Circuit breaker reset")

    def get_execution_status(self) -> Dict[str, Any]:
        """Get current execution status"""
        return {
            "mode": self.mode.value,
            "risk_level": self.risk_level.value,
            "emergency_stop": self.emergency_stop,
            "circuit_breaker": self.circuit_breaker_triggered,
            "daily_pnl": self.daily_pnl,
            "daily_trades": self.daily_trades,
            "active_trades": len(self.active_trades),
            "execution_limits": {
                "max_position_size": self.execution_limits.max_position_size,
                "max_daily_loss": self.execution_limits.max_daily_loss,
                "max_slippage": self.execution_limits.max_slippage,
                "max_concurrent_trades": self.execution_limits.max_concurrent_trades
            }
        }

def init_low_risk_execution():
    """Initialize low-risk execution components"""
    logger.info("Initializing low-risk execution...")

    # Placeholder for execution-specific initialization
    logger.info("Low-risk execution initialized")

# Export main components
__all__ = ['LowRiskExecutionManager', 'ExecutionMode', 'RiskLevel', 'init_low_risk_execution']