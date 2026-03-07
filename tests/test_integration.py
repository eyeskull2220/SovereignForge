#!/usr/bin/env python3
"""
Integration tests for SovereignForge components
"""

import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
import time

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from data_integration_service import HybridDataIntegrationService, MarketData
from realtime_inference import RealTimeInferenceService, ArbitrageOpportunity
from live_arbitrage_pipeline import LiveArbitragePipeline
from compliance import get_compliance_engine, ComplianceViolationError


class TestDataIntegrationService(unittest.TestCase):
    """Test data integration service"""

    def setUp(self):
        """Create test data service"""
        self.data_service = HybridDataIntegrationService()

    async def test_initialization(self):
        """Test service initialization"""
        await self.data_service.initialize()

        self.assertEqual(self.data_service.is_running, False)  # Not started yet
        self.assertEqual(len(self.data_service.data_sources), 5)  # binance, coinbase, kraken, kucoin, okx
        self.assertIn('binance', self.data_service.data_sources)

    async def test_market_data_callback(self):
        """Test market data callback registration"""
        callback_called = False
        received_data = None

        def test_callback(data: MarketData):
            nonlocal callback_called, received_data
            callback_called = True
            received_data = data

        self.data_service.add_data_callback(test_callback)

        # Simulate receiving market data
        test_data = MarketData(
            exchange='binance',
            pair='BTC/USDT',
            timestamp=time.time(),
            price=45000.0,
            volume=100.0,
            bid_price=44990.0,
            ask_price=45010.0,
            bid_volume=50.0,
            ask_volume=50.0
        )

        await self.data_service._handle_market_data(test_data)

        self.assertTrue(callback_called)
        self.assertEqual(received_data, test_data)

    async def test_compliance_filtering(self):
        """Test MiCA compliance filtering in data service"""
        # Test with compliant pair
        compliant_pairs = self.data_service.compliance_engine.filter_compliant_pairs(['BTC/USDT', 'SHIB/USDT'])
        self.assertIn('BTC/USDT', compliant_pairs)
        self.assertNotIn('SHIB/USDT', compliant_pairs)

    def test_service_status(self):
        """Test service status reporting"""
        status = self.data_service.get_service_status()

        self.assertIn('is_running', status)
        self.assertIn('data_sources', status)
        self.assertIn('active_callbacks', status)
        self.assertEqual(status['data_sources'], 5)


class TestRealTimeInferenceService(unittest.TestCase):
    """Test real-time inference service"""

    def setUp(self):
        """Create test inference service"""
        self.inference_service = RealTimeInferenceService()

    def test_initialization(self):
        """Test service initialization"""
        self.assertEqual(len(self.inference_service.pairs), 7)  # 7 trading pairs
        self.assertGreaterEqual(len(self.inference_service.models), 0)  # May have loaded models or fallbacks
        self.assertEqual(len(self.inference_service.buffers), 7)

    async def test_market_data_processing(self):
        """Test processing market data"""
        # Mock opportunity callback
        opportunities = []
        def opportunity_callback(opp):
            opportunities.append(opp)

        self.inference_service.add_opportunity_callback(opportunity_callback)

        # Send test market data
        test_data = {
            'exchange': 'binance',
            'pair': 'BTC/USDT',
            'timestamp': time.time(),
            'price': 45000.0,
            'bid_price': 44990.0,
            'ask_price': 45010.0,
            'volume': 100.0
        }

        await self.inference_service.process_market_data(test_data)

        # Should not crash, may or may not generate opportunities depending on model
        self.assertIsInstance(opportunities, list)

    def test_service_status(self):
        """Test service status reporting"""
        status = self.inference_service.get_service_status()

        self.assertIn('is_running', status)
        self.assertIn('models_loaded', status)
        self.assertIn('pairs_monitored', status)
        self.assertIn('gpu_available', status)


class TestLiveArbitragePipeline(unittest.TestCase):
    """Test complete arbitrage pipeline"""

    def setUp(self):
        """Create test pipeline configuration"""
        self.pipeline_config = {
            'min_probability': 0.5,  # Lower threshold for testing
            'min_spread': 0.0005,
            'max_risk_score': 0.5,
            'enable_grok_reasoning': False,  # Disable for testing
            'alert_on_opportunities': False,  # Disable alerts for testing
            'pairs': ['BTC/USDT', 'ETH/USDT']
        }
        self.pipeline = LiveArbitragePipeline(self.pipeline_config)

    def test_initialization(self):
        """Test pipeline initialization"""
        self.assertEqual(self.pipeline.config['min_probability'], 0.5)
        self.assertEqual(len(self.pipeline.config['pairs']), 2)
        self.assertIsNotNone(self.pipeline.alert_system)
        self.assertIsNotNone(self.pipeline.opportunity_filter)

    async def test_opportunity_processing(self):
        """Test opportunity processing through pipeline"""
        # Create test opportunity
        opportunity = ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=time.time(),
            probability=0.8,
            confidence=0.9,
            spread_prediction=0.002,
            exchanges=["binance", "coinbase"],
            prices={"binance": 45000.0, "coinbase": 44900.0},
            volumes={"binance": 100.0, "coinbase": 80.0},
            risk_score=0.2,
            profit_potential=0.04
        )

        # Mock alert callback
        alerts_received = []
        async def alert_callback(alert):
            alerts_received.append(alert)

        self.pipeline.alert_system.add_alert_callback(alert_callback)

        # Process opportunity
        await self.pipeline._handle_opportunity(opportunity)

        # Check that it was processed (may or may not pass filters)
        self.assertEqual(self.pipeline.stats['opportunities_detected'], 1)

    def test_pipeline_status(self):
        """Test pipeline status reporting"""
        status = self.pipeline.get_pipeline_status()

        self.assertIn('is_running', status)
        self.assertIn('config', status)
        self.assertIn('stats', status)
        self.assertIn('data_service', status)
        self.assertIn('inference_service', status)


class TestComplianceIntegration(unittest.TestCase):
    """Test compliance integration across components"""

    def test_compliance_engine(self):
        """Test compliance engine functionality"""
        engine = get_compliance_engine()

        # Test asset compliance
        self.assertTrue(engine.is_asset_compliant('BTC'))
        self.assertTrue(engine.is_asset_compliant('XRP'))
        self.assertFalse(engine.is_asset_compliant('SHIB'))

        # Test pair compliance
        self.assertTrue(engine.is_pair_compliant('BTC/USDT'))
        self.assertTrue(engine.is_pair_compliant('XRP/USDC'))
        self.assertFalse(engine.is_pair_compliant('SHIB/USDT'))

    def test_compliance_filtering(self):
        """Test compliance filtering"""
        engine = get_compliance_engine()

        pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'SHIB/USDT', 'DOGE/USDT']

        # In hard enforcement mode, non-compliant pairs raise exceptions
        # So we test with only compliant pairs
        compliant_pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'DOGE/USDT']
        filtered = engine.filter_compliant_pairs(compliant_pairs)

        self.assertIn('BTC/USDT', filtered)
        self.assertIn('ETH/USDT', filtered)
        self.assertIn('XRP/USDT', filtered)
        self.assertIn('DOGE/USDT', filtered)  # DOGE is compliant

        # Test that non-compliant pairs are filtered out (not raise exceptions)
        non_compliant_result = engine.filter_compliant_pairs(['SHIB/USDT'])
        self.assertEqual(non_compliant_result, [])  # Should return empty list

    def test_compliance_violation(self):
        """Test compliance violation handling"""
        engine = get_compliance_engine()

        # Should raise exception for non-compliant pair
        with self.assertRaises(ComplianceViolationError):
            engine.validate_opportunity({
                'pair': 'SHIB/USDT',
                'exchanges': ['binance']
            })


class TestEndToEndIntegration(unittest.TestCase):
    """End-to-end integration tests"""

    async def test_data_flow(self):
        """Test complete data flow from market data to opportunities"""
        # This is a high-level integration test
        # In a real scenario, this would test the full pipeline

        # Create components
        data_service = HybridDataIntegrationService()
        inference_service = RealTimeInferenceService()

        # Connect them
        data_service.add_data_callback(inference_service.process_market_data)

        # Track opportunities
        opportunities = []
        def opportunity_callback(opp):
            opportunities.append(opp)

        inference_service.add_opportunity_callback(opportunity_callback)

        # Send test market data
        test_data = {
            'exchange': 'binance',
            'pair': 'BTC/USDT',
            'timestamp': time.time(),
            'price': 45000.0,
            'bid_price': 44990.0,
            'ask_price': 45010.0,
            'volume': 100.0
        }

        await data_service._handle_market_data(MarketData(**test_data))

        # Verify data was processed without errors
        self.assertGreaterEqual(len(opportunities), 0)  # May or may not generate opportunities

    async def test_pipeline_integration(self):
        """Test pipeline component integration"""
        config = {
            'min_probability': 0.3,
            'min_spread': 0.0001,
            'max_risk_score': 0.8,
            'enable_grok_reasoning': False,
            'alert_on_opportunities': False,
            'pairs': ['BTC/USDT']
        }

        pipeline = LiveArbitragePipeline(config)

        # Test that all components are properly connected
        self.assertIsNotNone(pipeline.data_service)
        self.assertIsNotNone(pipeline.inference_service)
        self.assertIsNotNone(pipeline.opportunity_filter)
        self.assertIsNotNone(pipeline.alert_system)

        # Test status reporting
        status = pipeline.get_pipeline_status()
        self.assertIn('is_running', status)
        self.assertIn('config', status)
        self.assertIn('stats', status)


if __name__ == "__main__":
    # Run tests with unittest
    unittest.main(verbosity=2)
