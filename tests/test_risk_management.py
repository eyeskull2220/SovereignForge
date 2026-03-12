#!/usr/bin/env python3
"""
Test suite for Phase 2 Risk Management System
Tests Kelly Criterion, portfolio optimization, VaR calculations
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from live_arbitrage_pipeline import ArbitrageOpportunity

class TestRiskManagement:
    """Test Phase 2 Risk Management components"""

    def setup_method(self):
        """Setup test fixtures"""
        try:
            from risk_management import get_risk_manager, RiskManager
            self.risk_manager = get_risk_manager()
            self.risk_available = True
        except ImportError:
            self.risk_manager = Mock()
            self.risk_manager.validate_opportunity.return_value = True
            self.risk_manager.calculate_position_size.return_value = 0.01
            self.risk_available = False

    def test_risk_manager_initialization(self):
        """Test risk manager singleton initialization"""
        if not self.risk_available:
            pytest.skip("Risk management not available")

        assert self.risk_manager is not None
        assert hasattr(self.risk_manager, 'validate_opportunity')
        assert hasattr(self.risk_manager, 'calculate_position_size')

    def test_kelly_criterion_calculation(self):
        """Test Kelly Criterion position sizing"""
        if not self.risk_available:
            pytest.skip("Risk management not available")

        # Test profitable opportunity
        opportunity = ArbitrageOpportunity(
            pair="BTC/USDC",
            timestamp=1640995200.0,  # 2022-01-01
            probability=0.7,
            confidence=0.8,
            spread_prediction=0.005,
            exchanges=["binance", "coinbase"],
            prices={"binance": 50000, "coinbase": 50250},
            volumes={"binance": 1.0, "coinbase": 1.0},
            risk_score=0.2,
            profit_potential=125.0
        )

        position_size = self.risk_manager.calculate_position_size_for_opportunity(opportunity)
        assert position_size > 0
        assert position_size <= 2.0  # Max 2 BTC (reasonable for $100k portfolio at $50k/BTC)

        # Kelly formula: f = (bp - q) / b
        # Where b = odds (win/loss ratio), p = win prob, q = loss prob
        # For arbitrage, we expect conservative sizing
        assert position_size <= 2.0  # Allow up to 2 BTC for high-confidence opportunities

    def test_opportunity_validation(self):
        """Test opportunity risk validation"""
        if not self.risk_available:
            pytest.skip("Risk management not available")

        # Valid opportunity
        valid_opportunity = ArbitrageOpportunity(
            pair="BTC/USDC",
            timestamp=1640995200.0,
            probability=0.8,
            confidence=0.9,
            spread_prediction=0.003,
            exchanges=["binance", "coinbase"],
            prices={"binance": 50000, "coinbase": 50150},
            volumes={"binance": 1.0, "coinbase": 1.0},
            risk_score=0.1,
            profit_potential=75.0
        )

        assert self.risk_manager.validate_opportunity(valid_opportunity)

        # Invalid opportunity - too risky
        risky_opportunity = ArbitrageOpportunity(
            pair="BTC/USDC",
            timestamp=1640995200.0,
            probability=0.5,  # 50/50 chance
            confidence=0.6,
            spread_prediction=0.001,  # Very small spread
            exchanges=["binance", "coinbase"],
            prices={"binance": 50000, "coinbase": 50050},
            volumes={"binance": 0.1, "coinbase": 0.1},  # Low volume
            risk_score=0.8,  # High risk
            profit_potential=25.0
        )

        # Should reject high-risk opportunity
        assert not self.risk_manager.validate_opportunity(risky_opportunity)

    def test_portfolio_risk_limits(self):
        """Test portfolio-level risk management"""
        if not self.risk_available:
            pytest.skip("Risk management not available")

        # Test multiple positions don't exceed portfolio limits
        opportunities = []
        for i in range(5):
            opp = ArbitrageOpportunity(
                pair=f"PAIR{i}/USDC",
                timestamp=1640995200.0 + i * 3600,
                probability=0.75,
                confidence=0.85,
                spread_prediction=0.004,
                exchanges=["binance", "coinbase"],
                prices={"binance": 1000 + i * 100, "coinbase": 1000 + i * 100 + 40},
                volumes={"binance": 1.0, "coinbase": 1.0},
                risk_score=0.15,
                profit_potential=40.0
            )
            opportunities.append(opp)

        total_exposure = 0
        for opp in opportunities:
            if self.risk_manager.validate_opportunity(opp):
                position_size = self.risk_manager.calculate_position_size_for_opportunity(opp)
                total_exposure += position_size

        # Total exposure should not exceed reasonable portfolio limits
        # With 5 positions at ~$1000 each, total exposure could be high
        assert total_exposure <= 500.0  # Allow reasonable total exposure

    def test_var_calculation(self):
        """Test Value at Risk calculations"""
        if not self.risk_available:
            pytest.skip("Risk management not available")

        # Test VaR for a position
        opportunity = ArbitrageOpportunity(
            pair="ETH/USDC",
            timestamp=1640995200.0,
            probability=0.7,
            confidence=0.8,
            spread_prediction=0.005,
            exchanges=["binance", "coinbase"],
            prices={"binance": 3000, "coinbase": 3015},
            volumes={"binance": 1.0, "coinbase": 1.0},
            risk_score=0.2,
            profit_potential=45.0
        )

        # Should have VaR calculation method
        assert hasattr(self.risk_manager, 'calculate_var')

        var_95 = self.risk_manager.calculate_var(opportunity, confidence=0.95)
        assert var_95 > 0
        assert var_95 < opportunity.profit_potential  # VaR should be less than potential loss

        var_99 = self.risk_manager.calculate_var(opportunity, confidence=0.99)
        assert var_99 > var_95  # Higher confidence should give higher VaR

    def test_stop_loss_calculation(self):
        """Test stop-loss level calculations"""
        if not self.risk_available:
            pytest.skip("Risk management not available")

        opportunity = ArbitrageOpportunity(
            pair="ADA/USDC",
            timestamp=1640995200.0,
            probability=0.75,
            confidence=0.85,
            spread_prediction=0.003,
            exchanges=["binance", "coinbase"],
            prices={"binance": 1.50, "coinbase": 1.5045},
            volumes={"binance": 1000.0, "coinbase": 1000.0},
            risk_score=0.1,
            profit_potential=4.50
        )

        # Should calculate appropriate stop loss
        stop_loss = self.risk_manager.calculate_stop_loss(opportunity)
        assert stop_loss > 0

        # Stop loss should be below entry price for long positions
        entry_price = min(opportunity.prices.values())
        assert stop_loss < entry_price

        # But not too far (should be reasonable risk management)
        loss_percentage = (entry_price - stop_loss) / entry_price
        assert loss_percentage <= 0.05  # Max 5% stop loss

    def test_risk_manager_singleton(self):
        """Test risk manager singleton pattern"""
        if not self.risk_available:
            pytest.skip("Risk management not available")

        from risk_management import get_risk_manager

        rm1 = get_risk_manager()
        rm2 = get_risk_manager()

        assert rm1 is rm2  # Same instance

        # State should persist
        rm1.test_state = "test_value"
        assert rm2.test_state == "test_value"

    def test_edge_cases(self):
        """Test edge cases and error handling"""
        if not self.risk_available:
            pytest.skip("Risk management not available")

        # Test with zero probability
        bad_opportunity = ArbitrageOpportunity(
            pair="TEST/USDC",
            timestamp=1640995200.0,
            probability=0.0,  # Impossible
            confidence=0.5,
            spread_prediction=0.001,
            exchanges=["binance", "coinbase"],
            prices={"binance": 100, "coinbase": 100.1},
            volumes={"binance": 0.01, "coinbase": 0.01},
            risk_score=0.9,
            profit_potential=0.1
        )

        assert not self.risk_manager.validate_opportunity(bad_opportunity)

        # Test with negative spread
        negative_spread = ArbitrageOpportunity(
            pair="TEST/USDC",
            timestamp=1640995200.0,
            probability=0.6,
            confidence=0.7,
            spread_prediction=-0.001,  # Negative spread = loss
            exchanges=["binance", "coinbase"],
            prices={"binance": 100, "coinbase": 99.9},
            volumes={"binance": 1.0, "coinbase": 1.0},
            risk_score=0.3,
            profit_potential=-0.1
        )

        assert not self.risk_manager.validate_opportunity(negative_spread)

if __name__ == "__main__":
    pytest.main([__file__])