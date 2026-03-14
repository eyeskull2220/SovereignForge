#!/usr/bin/env python3
"""
Test suite for Phase 2 Risk Management System
Tests Kelly Criterion, portfolio risk controls, position sizing
"""

import os
import sys

import numpy as np
import pytest

from live_arbitrage_pipeline import ArbitrageOpportunity


class TestRiskManagement:
    """Test Phase 2 Risk Management components"""

    def setup_method(self):
        """Setup test fixtures — fresh RiskManager each test"""
        import risk_management
        risk_management._risk_manager = None
        from risk_management import RiskManager, get_risk_manager
        self.risk_manager = get_risk_manager()

    def test_risk_manager_initialization(self):
        """Test risk manager singleton initialization"""
        assert self.risk_manager is not None
        assert hasattr(self.risk_manager, 'validate_opportunity')
        assert hasattr(self.risk_manager, 'calculate_position_size')

    def test_kelly_criterion_calculation(self):
        """Test Kelly Criterion position sizing via calculate_position_size"""
        opp_dict = {
            'pair': 'BTC/USDC',
            'prices': {'binance': 50000, 'coinbase': 50250},
            'spread_prediction': 0.005,
            'confidence': 0.8,
            'risk_score': 0.2,
        }

        position_size = self.risk_manager.calculate_position_size(opp_dict, use_kelly=True)
        assert position_size >= 0
        # Kelly should produce a conservative position
        assert position_size <= 2.0

    def test_opportunity_validation(self):
        """Test opportunity risk validation with ArbitrageOpportunity objects"""
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

        # Spread too low — should reject
        low_spread = ArbitrageOpportunity(
            pair="ETH/USDC",
            timestamp=1640995200.0,
            probability=0.8,
            confidence=0.9,
            spread_prediction=0.0005,
            exchanges=["binance", "coinbase"],
            prices={"binance": 3000, "coinbase": 3001},
            volumes={"binance": 1.0, "coinbase": 1.0},
            risk_score=0.1,
            profit_potential=1.0
        )

        assert not self.risk_manager.validate_opportunity(low_spread)

    def test_portfolio_risk_limits(self):
        """Test that portfolio exposure limits are enforced"""
        # Open a position to consume some exposure
        opp_dict = {
            'pair': 'ADA/USDC',
            'exchanges': ['binance', 'coinbase'],
            'prices': {'binance': 1.50, 'coinbase': 1.505},
            'spread_prediction': 0.003,
            'risk_score': 0.1,
            'confidence': 0.8,
        }
        pos = self.risk_manager.open_position(opp_dict)
        assert pos is not None

        # Trying to open another position for the same pair should fail
        assert not self.risk_manager.validate_opportunity(opp_dict)

    def test_position_open_close_lifecycle(self):
        """Test opening and closing a position tracks P&L"""
        opp = {
            'pair': 'XRP/USDC',
            'exchanges': ['binance', 'coinbase'],
            'prices': {'binance': 1.0, 'coinbase': 1.005},
            'spread_prediction': 0.005,
            'risk_score': 0.1,
            'confidence': 0.8,
        }
        pos = self.risk_manager.open_position(opp)
        assert pos is not None

        # Close at a profit
        closed = self.risk_manager.close_position('XRP/USDC', 1.01, 'take_profit')
        assert closed
        assert self.risk_manager.daily_pnl > 0

    def test_risk_manager_singleton(self):
        """Test risk manager singleton pattern"""
        from risk_management import get_risk_manager

        rm1 = get_risk_manager()
        rm2 = get_risk_manager()

        assert rm1 is rm2  # Same instance

        # State should persist
        rm1.test_state = "test_value"
        assert rm2.test_state == "test_value"

    def test_edge_cases(self):
        """Test edge cases and error handling"""
        # Test with spread below minimum (0.001)
        bad_opportunity = ArbitrageOpportunity(
            pair="TEST/USDC",
            timestamp=1640995200.0,
            probability=0.0,
            confidence=0.5,
            spread_prediction=0.0005,  # Below 0.001 minimum
            exchanges=["binance", "coinbase"],
            prices={"binance": 100, "coinbase": 100.05},
            volumes={"binance": 0.01, "coinbase": 0.01},
            risk_score=0.9,
            profit_potential=0.1
        )

        assert not self.risk_manager.validate_opportunity(bad_opportunity)

        # Test with negative spread
        negative_spread = ArbitrageOpportunity(
            pair="TEST2/USDC",
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

    def test_kelly_metrics(self):
        """Test Kelly criterion metrics calculation"""
        opp = {
            'pair': 'BTC/USDC',
            'prices': {'binance': 50000, 'coinbase': 50250},
            'spread_prediction': 0.005,
            'confidence': 0.8,
            'risk_score': 0.2,
        }
        metrics = self.risk_manager.calculate_kelly_metrics(opp)
        assert 'win_probability' in metrics
        assert 'kelly_fraction' in metrics
        assert metrics['win_probability'] > 0
        assert metrics['kelly_fraction'] >= 0

    def test_emergency_stop(self):
        """Test emergency stop closes all positions"""
        opp = {
            'pair': 'ADA/USDC',
            'exchanges': ['binance', 'coinbase'],
            'prices': {'binance': 1.50, 'coinbase': 1.505},
            'spread_prediction': 0.003,
            'risk_score': 0.1,
            'confidence': 0.8,
        }
        self.risk_manager.open_position(opp)
        assert len(self.risk_manager.positions) == 1

        count = self.risk_manager.emergency_stop()
        assert count == 1
        assert len(self.risk_manager.positions) == 0


if __name__ == "__main__":
    pytest.main([__file__])
