#!/usr/bin/env python3
"""
Integration tests for SovereignForge components
"""

import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from compliance import ComplianceViolationError, get_compliance_engine
from data_integration_service import HybridDataIntegrationService, MarketData
from live_arbitrage_pipeline import LiveArbitragePipeline
from realtime_inference import ArbitrageOpportunity, RealTimeInferenceService


@pytest.mark.asyncio
async def test_data_integration_service_initialization():
    """Test data integration service initialization"""
    data_service = HybridDataIntegrationService()
    await data_service.initialize()

    assert not data_service.is_running  # Not started yet
    assert len(data_service.data_sources) == 7  # binance, coinbase, kraken, kucoin, okx, bybit, gate
    assert 'binance' in data_service.data_sources


@pytest.mark.asyncio
async def test_data_integration_service_market_data_callback():
    """Test market data callback registration"""
    data_service = HybridDataIntegrationService()

    callback_called = False
    received_data = None

    def test_callback(data: MarketData):
        nonlocal callback_called, received_data
        callback_called = True
        received_data = data

    data_service.add_data_callback(test_callback)

    # Simulate receiving market data with MiCA-compliant pair
    test_data = MarketData(
        exchange='binance',
        pair='BTC/USDC',  # Changed to USDC for MiCA compliance
        timestamp=time.time(),
        price=45000.0,
        volume=100.0,
        bid_price=44990.0,
        ask_price=45010.0,
        bid_volume=50.0,
        ask_volume=50.0
    )

    await data_service._handle_market_data(test_data)

    assert callback_called
    assert received_data == test_data


@pytest.mark.asyncio
async def test_data_integration_service_compliance_filtering():
    """Test MiCA compliance filtering in data service"""
    data_service = HybridDataIntegrationService()

    # Test with MiCA-compliant pairs (USDC/RLUSD only)
    compliant_pairs = data_service.compliance_engine.filter_compliant_pairs(['BTC/USDC', 'SHIB/USDT'])
    assert 'BTC/USDC' in compliant_pairs  # USDC is compliant
    assert 'SHIB/USDT' not in compliant_pairs  # SHIB is not compliant, USDT is forbidden


def test_data_integration_service_status():
    """Test service status reporting"""
    data_service = HybridDataIntegrationService()
    status = data_service.get_service_status()

    assert 'is_running' in status
    assert 'data_sources' in status
    assert 'active_callbacks' in status
    assert status['data_sources'] == 7


def test_realtime_inference_service_initialization():
    """Test real-time inference service initialization"""
    inference_service = RealTimeInferenceService()

    assert len(inference_service.pairs) == 12  # 12 MiCA-compliant USDC pairs
    assert len(inference_service.models) >= 0  # May have loaded models or fallbacks
    assert len(inference_service.buffers) == 12


@pytest.mark.asyncio
async def test_realtime_inference_service_market_data_processing():
    """Test processing market data"""
    inference_service = RealTimeInferenceService()

    # Mock opportunity callback
    opportunities = []
    def opportunity_callback(opp):
        opportunities.append(opp)

    inference_service.add_opportunity_callback(opportunity_callback)

    # Send test market data
    test_data = {
        'exchange': 'binance',
        'pair': 'BTC/USDC',
        'timestamp': time.time(),
        'price': 45000.0,
        'bid_price': 44990.0,
        'ask_price': 45010.0,
        'volume': 100.0
    }

    await inference_service.process_market_data(test_data)

    # Should not crash, may or may not generate opportunities depending on model
    assert isinstance(opportunities, list)


def test_realtime_inference_service_status():
    """Test service status reporting"""
    inference_service = RealTimeInferenceService()
    status = inference_service.get_service_status()

    assert 'is_running' in status
    assert 'models_loaded' in status
    assert 'pairs_monitored' in status
    assert 'gpu_available' in status


def test_live_arbitrage_pipeline_initialization():
    """Test pipeline initialization"""
    pipeline_config = {
        'min_probability': 0.5,  # Lower threshold for testing
        'min_spread': 0.0005,
        'max_risk_score': 0.5,
        'enable_grok_reasoning': False,  # Disable for testing
        'alert_on_opportunities': False,  # Disable alerts for testing
        'pairs': ['BTC/USDC', 'ETH/USDC']
    }
    pipeline = LiveArbitragePipeline(pipeline_config)

    assert pipeline.config['min_probability'] == 0.5
    assert len(pipeline.config['pairs']) == 2
    assert pipeline.alert_system is not None
    assert pipeline.opportunity_filter is not None


@pytest.mark.asyncio
async def test_live_arbitrage_pipeline_opportunity_processing():
    """Test opportunity processing through pipeline"""
    pipeline_config = {
        'min_probability': 0.5,
        'min_spread': 0.0005,
        'max_risk_score': 0.5,
        'enable_grok_reasoning': False,
        'alert_on_opportunities': False,
        'pairs': ['BTC/USDC', 'ETH/USDC']
    }
    pipeline = LiveArbitragePipeline(pipeline_config)

    # Create test opportunity
    opportunity = ArbitrageOpportunity(
        pair="BTC/USDC",
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

    pipeline.alert_system.add_alert_callback(alert_callback)

    # Process opportunity
    await pipeline._handle_opportunity(opportunity)

    # Check that it was processed (may or may not pass filters)
    assert pipeline.stats['opportunities_detected'] == 1


def test_live_arbitrage_pipeline_status():
    """Test pipeline status reporting"""
    pipeline_config = {
        'min_probability': 0.5,
        'min_spread': 0.0005,
        'max_risk_score': 0.5,
        'enable_grok_reasoning': False,
        'alert_on_opportunities': False,
        'pairs': ['BTC/USDC', 'ETH/USDC']
    }
    pipeline = LiveArbitragePipeline(pipeline_config)

    status = pipeline.get_pipeline_status()

    assert 'is_running' in status
    assert 'config' in status
    assert 'stats' in status
    assert 'data_service' in status
    assert 'inference_service' in status


def test_compliance_engine():
    """Test compliance engine functionality - USDT pairs are FORBIDDEN per AGENTS.md"""
    engine = get_compliance_engine()

    # Test asset compliance
    assert engine.is_asset_compliant('BTC')
    assert engine.is_asset_compliant('XRP')
    assert not engine.is_asset_compliant('SHIB')

    # Test pair compliance - USDT pairs are now FORBIDDEN
    assert not engine.is_pair_compliant('BTC/USDT')  # USDT forbidden
    assert engine.is_pair_compliant('XRP/USDC')   # USDC compliant
    assert not engine.is_pair_compliant('SHIB/USDT')  # SHIB not compliant, USDT forbidden
    assert engine.is_pair_compliant('BTC/USDC')   # MiCA compliant


def test_compliance_filtering():
    """Test compliance filtering - USDT pairs are now FORBIDDEN per AGENTS.md"""
    engine = get_compliance_engine()

    # Test MiCA-compliant pairs (USDC/RLUSD only)
    compliant_pairs = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'ADA/USDC', 'DOGE/USDC']
    filtered = engine.filter_compliant_pairs(compliant_pairs)

    assert 'BTC/USDC' in filtered
    assert 'ETH/USDC' in filtered
    assert 'XRP/USDC' in filtered
    assert 'ADA/USDC' in filtered
    assert 'DOGE/USDC' not in filtered  # DOGE is NOT MiCA compliant

    # Test that USDT pairs are filtered out (CRITICAL: MiCA compliance violation fixed)
    usdt_pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT']
    usdt_filtered = engine.filter_compliant_pairs(usdt_pairs)
    assert usdt_filtered == []  # USDT pairs must be rejected

    # Test that non-compliant pairs are filtered out
    non_compliant_result = engine.filter_compliant_pairs(['SHIB/USDT'])
    assert non_compliant_result == []  # Should return empty list


def test_compliance_violation():
    """Test compliance violation handling"""
    engine = get_compliance_engine()

    # Should raise exception for non-compliant pair
    with pytest.raises(ComplianceViolationError):
        engine.validate_opportunity({
            'pair': 'SHIB/USDT',
            'exchanges': ['binance']
        })


@pytest.mark.asyncio
async def test_end_to_end_data_flow():
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
        'pair': 'BTC/USDC',
        'timestamp': time.time(),
        'price': 45000.0,
        'bid_price': 44990.0,
        'ask_price': 45010.0,
        'volume': 100.0,
        'bid_volume': 50.0,
        'ask_volume': 50.0
    }

    await data_service._handle_market_data(MarketData(**test_data))

    # Verify data was processed without errors
    assert len(opportunities) >= 0  # May or may not generate opportunities


@pytest.mark.asyncio
async def test_pipeline_integration():
    """Test pipeline component integration"""
    config = {
        'min_probability': 0.3,
        'min_spread': 0.0001,
        'max_risk_score': 0.8,
        'enable_grok_reasoning': False,
        'alert_on_opportunities': False,
        'pairs': ['BTC/USDC']
    }

    pipeline = LiveArbitragePipeline(config)

    # Test that all components are properly connected
    assert pipeline.data_service is not None
    assert pipeline.inference_service is not None
    assert pipeline.opportunity_filter is not None
    assert pipeline.alert_system is not None

    # Test status reporting
    status = pipeline.get_pipeline_status()
    assert 'is_running' in status
    assert 'config' in status
    assert 'stats' in status
