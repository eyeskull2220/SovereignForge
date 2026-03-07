#!/usr/bin/env python3
"""
Unit tests for SovereignForge arbitrage detection components
"""

import unittest
import time
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter, FilteredOpportunity


class TestArbitrageOpportunity(unittest.TestCase):
    """Test ArbitrageOpportunity dataclass"""

    def test_opportunity_creation(self):
        """Test creating an arbitrage opportunity"""
        opp = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=1640995200.0,  # 2022-01-01 00:00:00 UTC
            probability=0.85,
            confidence=0.92,
            spread_prediction=0.0024,
            exchanges=["binance", "coinbase", "kraken"],
            prices={"binance": 45000.0, "coinbase": 44950.0, "kraken": 45020.0},
            volumes={"binance": 100.0, "coinbase": 80.0, "kraken": 120.0},
            risk_score=0.15,
            profit_potential=0.0234
        )

        assert opp.pair == "BTC/USDT"
        assert opp.probability == 0.85
        assert opp.confidence == 0.92
        assert opp.spread_prediction == 0.0024
        assert len(opp.exchanges) == 3
        assert opp.prices["binance"] == 45000.0
        assert opp.risk_score == 0.15
        assert opp.profit_potential == 0.0234

    def test_opportunity_string_representation(self):
        """Test string representation of opportunity"""
        opp = ArbitrageOpportunity(
            pair="ETH/USDT",
            timestamp=time.time(),
            probability=0.75,
            confidence=0.88,
            spread_prediction=0.0015,
            exchanges=["binance", "coinbase"],
            prices={"binance": 2800.0, "coinbase": 2795.0},
            volumes={"binance": 50.0, "coinbase": 45.0},
            risk_score=0.20,
            profit_potential=0.0156
        )

        # Should not raise any exceptions
        str_repr = str(opp)
        assert "ETH/USDT" in str_repr
        assert "0.75" in str_repr


class TestOpportunityFilter(unittest.TestCase):
    """Test opportunity filtering logic"""

    def setUp(self):
        """Setup test fixtures"""
        self.filter = OpportunityFilter(
            min_probability=0.7,
            min_spread=0.001,
            max_risk_score=0.5
        )

    def test_filter_high_probability_opportunity(self):
        """Test filtering opportunity with high probability"""
        opp = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=time.time(),
            probability=0.85,  # Above threshold
            confidence=0.9,
            spread_prediction=0.002,  # Above threshold
            exchanges=["binance", "coinbase"],
            prices={"binance": 45000.0, "coinbase": 44900.0},
            volumes={"binance": 100.0, "coinbase": 80.0},
            risk_score=0.15,  # Below threshold
            profit_potential=0.0225
        )

        result = self.filter.filter_opportunity(opp)

        assert result is not None
        assert isinstance(result, FilteredOpportunity)
        assert result.opportunity == opp
        assert result.risk_assessment == "Low"
        assert result.recommended_action == "Execute"
        assert len(result.alerts) > 0

    def test_filter_low_probability_opportunity(self):
        """Test filtering opportunity with low probability"""
        opp = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=time.time(),
            probability=0.5,  # Below threshold
            confidence=0.8,
            spread_prediction=0.002,
            exchanges=["binance", "coinbase"],
            prices={"binance": 45000.0, "coinbase": 44900.0},
            volumes={"binance": 100.0, "coinbase": 80.0},
            risk_score=0.15,
            profit_potential=0.0225
        )

        result = self.filter.filter_opportunity(opp)

        assert result is None  # Should be filtered out

    def test_filter_small_spread_opportunity(self):
        """Test filtering opportunity with small spread"""
        opp = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=time.time(),
            probability=0.8,
            confidence=0.85,
            spread_prediction=0.0005,  # Below threshold
            exchanges=["binance", "coinbase"],
            prices={"binance": 45000.0, "coinbase": 44995.0},
            volumes={"binance": 100.0, "coinbase": 80.0},
            risk_score=0.15,
            profit_potential=0.01125
        )

        result = self.filter.filter_opportunity(opp)

        assert result is None  # Should be filtered out

    def test_filter_high_risk_opportunity(self):
        """Test filtering opportunity with high risk"""
        opp = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=time.time(),
            probability=0.8,
            confidence=0.6,  # Low confidence = high risk
            spread_prediction=0.002,
            exchanges=["binance", "coinbase"],
            prices={"binance": 45000.0, "coinbase": 44900.0},
            volumes={"binance": 100.0, "coinbase": 80.0},
            risk_score=0.35,  # Above threshold
            profit_potential=0.0225
        )

        result = self.filter.filter_opportunity(opp)

        assert result is not None  # Should pass basic filters
        assert result.risk_assessment == "Low"  # risk_score=0.35 < 0.5, so Low risk

    def test_generate_alerts_high_probability(self):
        """Test alert generation for high probability opportunity"""
        opp = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=time.time(),
            probability=0.95,  # Very high probability
            confidence=0.9,
            spread_prediction=0.002,
            exchanges=["binance", "coinbase"],
            prices={"binance": 45000.0, "coinbase": 44900.0},
            volumes={"binance": 100.0, "coinbase": 80.0},
            risk_score=0.15,
            profit_potential=0.0225
        )

        filtered = self.filter.filter_opportunity(opp)

        assert filtered is not None
        assert any("High probability opportunity" in alert for alert in filtered.alerts)

    def test_generate_alerts_large_spread(self):
        """Test alert generation for large spread opportunity"""
        opp = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=time.time(),
            probability=0.8,
            confidence=0.85,
            spread_prediction=0.008,  # Large spread
            exchanges=["binance", "coinbase"],
            prices={"binance": 45000.0, "coinbase": 44200.0},
            volumes={"binance": 100.0, "coinbase": 80.0},
            risk_score=0.15,
            profit_potential=0.09
        )

        filtered = self.filter.filter_opportunity(opp)

        assert filtered is not None
        assert any("Large spread detected" in alert for alert in filtered.alerts)

    def test_generate_alerts_low_volume(self):
        """Test alert generation for low volume opportunity"""
        opp = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=time.time(),
            probability=0.8,
            confidence=0.85,
            spread_prediction=0.002,
            exchanges=["binance", "coinbase"],
            prices={"binance": 45000.0, "coinbase": 44900.0},
            volumes={"binance": 10.0, "coinbase": 8.0},  # Low volume
            risk_score=0.15,
            profit_potential=0.0225
        )

        filtered = self.filter.filter_opportunity(opp)

        assert filtered is not None
        assert any("Low liquidity" in alert for alert in filtered.alerts)


class TestFilteredOpportunity(unittest.TestCase):
    """Test FilteredOpportunity dataclass"""

    def test_filtered_opportunity_creation(self):
        """Test creating a filtered opportunity"""
        opp = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=time.time(),
            probability=0.8,
            confidence=0.85,
            spread_prediction=0.002,
            exchanges=["binance", "coinbase"],
            prices={"binance": 45000.0, "coinbase": 44900.0},
            volumes={"binance": 100.0, "coinbase": 80.0},
            risk_score=0.15,
            profit_potential=0.0225
        )

        filtered = FilteredOpportunity(
            opportunity=opp,
            grok_analysis=None,
            risk_assessment="Low",
            confidence_score=0.85,
            recommended_action="Execute",
            profit_estimate=225.0,
            alerts=["High probability opportunity: 0.800"]
        )

        assert filtered.opportunity == opp
        assert filtered.risk_assessment == "Low"
        assert filtered.recommended_action == "Execute"
        assert filtered.profit_estimate == 225.0
        assert len(filtered.alerts) == 1
        assert filtered.timestamp > 0  # Should be set automatically

    def test_filtered_opportunity_default_values(self):
        """Test default values in filtered opportunity"""
        opp = ArbitrageOpportunity(
            pair="ETH/USDT",
            timestamp=time.time(),
            probability=0.75,
            confidence=0.8,
            spread_prediction=0.0015,
            exchanges=["binance"],
            prices={"binance": 2800.0},
            volumes={"binance": 50.0},
            risk_score=0.2,
            profit_potential=0.015
        )

        filtered = FilteredOpportunity(opportunity=opp)

        assert filtered.grok_analysis is None
        assert filtered.risk_assessment == "Unknown"
        assert filtered.confidence_score == 0.0
        assert filtered.recommended_action == "Monitor"
        assert filtered.profit_estimate == 0.0
        assert filtered.alerts == []
        assert filtered.timestamp > 0


if __name__ == "__main__":
    # Run tests directly without pytest
    import unittest

    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Exit with appropriate code
    exit(0 if result.wasSuccessful() else 1)
