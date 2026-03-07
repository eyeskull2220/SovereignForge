#!/usr/bin/env python3
"""
SovereignForge - Live Arbitrage Pipeline
End-to-end arbitrage detection and execution pipeline
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import time

logger = logging.getLogger(__name__)

@dataclass
class ArbitrageOpportunity:
    """Represents a detected arbitrage opportunity"""
    pair: str
    timestamp: float
    probability: float
    confidence: float
    spread_prediction: float
    exchanges: List[str]
    prices: Dict[str, float]
    volumes: Dict[str, float]
    risk_score: float
    profit_potential: float

class LiveArbitragePipeline:
    """
    Live arbitrage detection and execution pipeline
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_running = False

        # Initialize components
        try:
            from data_integration_service import HybridDataIntegrationService
            self.data_service = HybridDataIntegrationService()
        except ImportError:
            logger.warning("DataIntegrationService not available, using mock")
            self.data_service = MockDataService()

        try:
            from realtime_inference import RealTimeInferenceService
            self.inference_service = RealTimeInferenceService()
        except ImportError:
            logger.warning("RealTimeInferenceService not available, using mock")
            self.inference_service = MockInferenceService()

        try:
            from risk_management import RiskManager
            self.opportunity_filter = RiskManager()
        except ImportError:
            logger.warning("RiskManager not available, using mock")
            self.opportunity_filter = MockRiskManager()

        try:
            from telegram_alerts import TelegramAlertSystem, TelegramConfig
            # Create disabled config for testing
            config = TelegramConfig(token='', chat_ids=[], enabled=False)
            self.alert_system = TelegramAlertSystem(config)
        except ImportError:
            logger.warning("TelegramAlertSystem not available, using mock")
            self.alert_system = MockAlertSystem()

        # Pipeline statistics
        self.stats = {
            'opportunities_detected': 0,
            'opportunities_filtered': 0,
            'alerts_sent': 0,
            'start_time': time.time()
        }

        logger.info("LiveArbitragePipeline initialized")

    async def _connect_components(self):
        """Connect pipeline components"""
        try:
            # Connect data service to inference service
            self.data_service.add_data_callback(self.inference_service.process_market_data)

            # Connect inference service to opportunity handler
            self.inference_service.add_opportunity_callback(self._handle_opportunity)

            logger.info("Pipeline components connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect pipeline components: {e}")

    async def _handle_opportunity(self, opportunity: ArbitrageOpportunity):
        """Handle detected arbitrage opportunity"""
        self.stats['opportunities_detected'] += 1

        try:
            # Apply risk filtering
            if hasattr(self.opportunity_filter, 'validate_opportunity'):
                if not self.opportunity_filter.validate_opportunity(opportunity):
                    self.stats['opportunities_filtered'] += 1
                    return

            # Send alert
            if hasattr(self.alert_system, 'send_opportunity_alert'):
                await self.alert_system.send_opportunity_alert(opportunity)
                self.stats['alerts_sent'] += 1

            logger.info(f"Processed opportunity for {opportunity.pair}: {opportunity.probability:.3f}")

        except Exception as e:
            logger.error(f"Error handling opportunity: {e}")

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get pipeline status"""
        return {
            'is_running': self.is_running,
            'config': self.config,
            'stats': self.stats,
            'data_service': self.data_service.get_service_status() if hasattr(self.data_service, 'get_service_status') else {},
            'inference_service': self.inference_service.get_service_status() if hasattr(self.inference_service, 'get_service_status') else {}
        }

# Mock classes for when real implementations are not available

class MockDataService:
    """Mock data service"""
    def __init__(self):
        self.data_sources = ['binance', 'coinbase', 'kraken', 'kucoin', 'okx']

    def add_data_callback(self, callback):
        pass

    def get_service_status(self):
        return {'is_running': True, 'data_sources': 5, 'active_callbacks': 1}

class MockInferenceService:
    """Mock inference service"""
    def __init__(self):
        self.pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT']
        self.models = {}

    def add_opportunity_callback(self, callback):
        pass

    async def process_market_data(self, data):
        pass

    def get_service_status(self):
        return {
            'is_running': True,
            'models_loaded': 0,
            'pairs_monitored': 7,
            'gpu_available': False
        }

class MockRiskManager:
    """Mock risk manager"""
    def validate_opportunity(self, opportunity):
        return True

class MockAlertSystem:
    """Mock alert system"""
    async def send_opportunity_alert(self, opportunity):
        pass

    def add_alert_callback(self, callback):
        pass