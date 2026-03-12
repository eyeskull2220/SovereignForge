#!/usr/bin/env python3
"""
SovereignForge - Live Arbitrage Pipeline
End-to-end arbitrage detection and execution pipeline

Supports two modes:
  - "production": Requires real services (raises on import failure)
  - "development": Allows mock fallbacks with clear warnings
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# MiCA-compliant trading pairs (USDC and RLUSD only — no USDT)
MICA_COMPLIANT_PAIRS = [
    'BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC',
    'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC',
    'XRP/RLUSD', 'XLM/RLUSD', 'HBAR/RLUSD', 'ALGO/RLUSD', 'ADA/RLUSD',
    'LINK/RLUSD', 'IOTA/RLUSD', 'VET/RLUSD',
]


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


@dataclass
class FilteredOpportunity:
    """Represents a filtered arbitrage opportunity"""
    opportunity: ArbitrageOpportunity
    grok_analysis: Optional[Any] = None
    risk_assessment: str = "Unknown"
    confidence_score: float = 0.0
    recommended_action: str = "Monitor"
    profit_estimate: float = 0.0
    alerts: Optional[List[str]] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        if self.alerts is None:
            self.alerts = []
        if self.timestamp is None:
            self.timestamp = time.time()


class OpportunityFilter:
    """Filters arbitrage opportunities based on risk and compliance"""

    def __init__(self, min_probability: float = 0.5, min_spread: float = 0.001, max_risk_score: float = 0.7):
        self.min_probability = min_probability
        self.min_spread = min_spread
        self.max_risk_score = max_risk_score
        self.compliance_enabled = True  # MiCA compliance enforced

        # Statistics
        self.filtered_count = 0
        self.passed_count = 0

    def filter_opportunity(self, opportunity: ArbitrageOpportunity) -> Optional[FilteredOpportunity]:
        """Filter an arbitrage opportunity"""
        # Check probability
        if opportunity.probability < self.min_probability:
            self.filtered_count += 1
            return None  # Filtered out

        # Check spread
        if opportunity.spread_prediction < self.min_spread:
            self.filtered_count += 1
            return None  # Filtered out

        # Check risk score
        if opportunity.risk_score > self.max_risk_score:
            self.filtered_count += 1
            return None  # Filtered out

        # Check compliance (placeholder)
        if self.compliance_enabled:
            # Would check MiCA compliance here
            compliance_passed = self._check_compliance(opportunity)
            if not compliance_passed:
                self.filtered_count += 1
                return None  # Filtered out

        # Opportunity passed all filters
        self.passed_count += 1

        # Generate alerts based on opportunity characteristics
        alerts = [f"High probability opportunity: {opportunity.probability:.3f}"]

        # Check for large spread
        if opportunity.spread_prediction > 0.005:  # Large spread threshold
            alerts.append("Large spread detected")

        # Check for low volume (simplified check)
        total_volume = sum(opportunity.volumes.values())
        if total_volume < 50:  # Low volume threshold
            alerts.append("Low liquidity")

        return FilteredOpportunity(
            opportunity=opportunity,
            grok_analysis=None,
            risk_assessment="Low",
            confidence_score=opportunity.confidence,
            recommended_action="Execute",
            profit_estimate=opportunity.profit_potential,
            alerts=alerts
        )

    def _check_compliance(self, opportunity: ArbitrageOpportunity) -> bool:
        """Check MiCA compliance using MiCAComplianceEngine."""
        try:
            from compliance import MiCAComplianceEngine
            if not hasattr(self, '_compliance_engine'):
                self._compliance_engine = MiCAComplianceEngine(personal_deployment=True)
            return self._compliance_engine.is_pair_compliant(opportunity.pair)
        except ImportError:
            logger.warning("MiCAComplianceEngine not available — using built-in pair whitelist")
            return opportunity.pair in MICA_COMPLIANT_PAIRS

    def get_filter_stats(self) -> Dict[str, int]:
        """Get filter statistics"""
        return {
            'filtered': self.filtered_count,
            'passed': self.passed_count,
            'total_processed': self.filtered_count + self.passed_count
        }


class ServiceInitError(Exception):
    """Raised when a required service fails to initialize in production mode."""


class LiveArbitragePipeline:
    """
    Live arbitrage detection and execution pipeline.

    Modes:
      - "production": All core services must be available. Raises ServiceInitError
        if HybridDataIntegrationService or RealTimeInferenceService cannot be imported.
      - "development": Falls back to mock services with clear warnings.
    """

    VALID_MODES = ("production", "development")

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_running = False
        self.mode = config.get('mode', 'development')

        if self.mode not in self.VALID_MODES:
            raise ValueError(f"Invalid pipeline mode '{self.mode}'. Must be one of {self.VALID_MODES}")

        if self.mode == 'development':
            logger.warning("WARNING: Running in DEVELOPMENT mode with mock services. "
                           "Data will be synthetic — do NOT trade real funds.")

        # ── Core services (data + inference + ensemble) ───────────────
        self.data_service = self._init_data_service()
        self.inference_service = self._init_inference_service()
        self.ensemble = self._init_ensemble()

        # Market data buffer for ensemble predictions (pair → deque of OHLCV rows)
        self._market_buffers: Dict[str, Deque[np.ndarray]] = {}
        self._ensemble_min_agreement = config.get('ensemble_min_agreement', 0.6)

        # ── Risk management ───────────────────────────────────────────
        self.opportunity_filter = self._init_risk_manager()

        # ── Alerting ──────────────────────────────────────────────────
        self.alert_system = self._init_alert_system()

        # ── Optional services (degrade gracefully in all modes) ───────
        self.cache = self._init_optional('cache_layer', 'get_cache',
                                         "CacheManager initialised (Redis + LRU fallback)")
        self.rate_limiter = self._init_optional('exchange_rate_limiter', 'get_rate_limiter',
                                                "RateLimiterManager initialised")
        self.alert_router = self._init_optional('multi_channel_alerts', 'get_alert_router',
                                                "AlertRouter initialised (multi-channel)")

        # Pipeline statistics
        self.stats = {
            'opportunities_detected': 0,
            'opportunities_filtered': 0,
            'alerts_sent': 0,
            'start_time': time.time()
        }

        logger.info(f"LiveArbitragePipeline initialized (mode={self.mode})")

    # ── Service initialization helpers ────────────────────────────────

    def _init_data_service(self):
        """Initialize data integration service."""
        try:
            from data_integration_service import HybridDataIntegrationService
            svc = HybridDataIntegrationService()
            logger.info("HybridDataIntegrationService loaded — real exchange data enabled")
            return svc
        except ImportError:
            if self.mode == 'production':
                raise ServiceInitError(
                    "HybridDataIntegrationService is required in production mode. "
                    "Ensure data_integration_service.py and its dependencies are installed."
                )
            logger.warning("HybridDataIntegrationService not available — using MockDataService")
            return MockDataService()

    def _init_inference_service(self):
        """Initialize real-time inference service."""
        try:
            from realtime_inference import get_inference_service
            svc = get_inference_service()
            logger.info("RealTimeInferenceService loaded — GPU inference enabled")
            return svc
        except ImportError:
            if self.mode == 'production':
                raise ServiceInitError(
                    "RealTimeInferenceService is required in production mode. "
                    "Ensure realtime_inference.py, PyTorch, and GPU drivers are installed."
                )
            logger.warning("RealTimeInferenceService not available — using MockInferenceService")
            return MockInferenceService()

    def _init_ensemble(self):
        """Initialize the multi-strategy ensemble (collective brain)."""
        try:
            from strategy_ensemble import StrategyEnsemble
            ensemble = StrategyEnsemble(config=self.config)
            logger.info("StrategyEnsemble loaded — collective brain enabled")
            return ensemble
        except ImportError:
            if self.mode == 'production':
                logger.warning(
                    "StrategyEnsemble not available in production — "
                    "falling back to single-strategy inference only"
                )
            else:
                logger.warning("StrategyEnsemble not available — ensemble signals disabled")
            return None

    def _init_risk_manager(self):
        """Initialize risk manager."""
        try:
            from risk_management import get_risk_manager
            svc = get_risk_manager()
            logger.info("RiskManager loaded (Kelly Criterion)")
            return svc
        except ImportError:
            if self.mode == 'production':
                raise ServiceInitError(
                    "RiskManager is required in production mode. "
                    "Ensure risk_management.py is available."
                )
            logger.warning("RiskManager not available — using MockRiskManager")
            return MockRiskManager()

    def _init_alert_system(self):
        """Initialize alert system."""
        try:
            from telegram_alerts import get_telegram_alert_system
            svc = get_telegram_alert_system()
            logger.info("TelegramAlertSystem loaded")
            return svc
        except ImportError:
            logger.warning("TelegramAlertSystem not available — using MockAlertSystem")
            return MockAlertSystem()

    def _init_optional(self, module_name: str, factory_name: str, success_msg: str):
        """Initialize an optional service that degrades gracefully in all modes."""
        try:
            mod = __import__(module_name)
            factory = getattr(mod, factory_name)
            svc = factory()
            logger.info(success_msg)
            return svc
        except ImportError:
            logger.warning(f"{module_name} not available — disabled")
            return None

    # ── Readiness check ───────────────────────────────────────────────

    def get_readiness_check(self) -> Dict[str, Any]:
        """Verify all services are properly initialized before starting.

        Returns a dict with:
          - ready (bool): True if the pipeline can start
          - services (dict): Per-service status
          - warnings (list): Non-fatal issues
          - errors (list): Fatal issues (pipeline cannot start)
        """
        services = {}
        warnings = []
        errors = []

        # Data service
        is_mock_data = isinstance(self.data_service, MockDataService)
        services['data_service'] = {
            'type': 'mock' if is_mock_data else 'real',
            'ready': True,
        }
        if is_mock_data:
            warnings.append("Data service is mock — no real market data will be received")

        # Inference service
        is_mock_inference = isinstance(self.inference_service, MockInferenceService)
        services['inference_service'] = {
            'type': 'mock' if is_mock_inference else 'real',
            'ready': True,
        }
        if is_mock_inference:
            warnings.append("Inference service is mock — no ML predictions will be generated")

        # Risk manager
        is_mock_risk = isinstance(self.opportunity_filter, MockRiskManager)
        services['risk_manager'] = {
            'type': 'mock' if is_mock_risk else 'real',
            'ready': True,
        }
        if is_mock_risk:
            warnings.append("Risk manager is mock — all opportunities will pass validation")

        # Alert system
        is_mock_alert = isinstance(self.alert_system, MockAlertSystem)
        services['alert_system'] = {
            'type': 'mock' if is_mock_alert else 'real',
            'ready': True,
        }
        if is_mock_alert:
            warnings.append("Alert system is mock — no alerts will be sent")

        # Ensemble (collective brain)
        services['ensemble'] = {
            'type': 'real' if self.ensemble else 'disabled',
            'ready': True,
        }
        if self.ensemble is None:
            warnings.append("StrategyEnsemble not available — single-strategy inference only")

        # Optional services
        services['cache'] = {'type': 'real' if self.cache else 'disabled', 'ready': True}
        services['rate_limiter'] = {'type': 'real' if self.rate_limiter else 'disabled', 'ready': True}
        services['alert_router'] = {'type': 'real' if self.alert_router else 'disabled', 'ready': True}

        # In production, mock core services are errors
        if self.mode == 'production':
            if is_mock_data:
                errors.append("Production mode requires real data service")
            if is_mock_inference:
                errors.append("Production mode requires real inference service")
            if is_mock_risk:
                errors.append("Production mode requires real risk manager")

        ready = len(errors) == 0

        return {
            'ready': ready,
            'mode': self.mode,
            'services': services,
            'warnings': warnings,
            'errors': errors,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self):
        """Start the pipeline: connect components, initialize services, begin streaming."""
        if self.is_running:
            logger.warning("Pipeline is already running")
            return

        readiness = self.get_readiness_check()
        if not readiness['ready']:
            raise ServiceInitError(
                f"Pipeline not ready: {'; '.join(readiness['errors'])}"
            )

        for w in readiness['warnings']:
            logger.warning(w)

        # Initialize data service (WebSocket connections)
        if hasattr(self.data_service, 'initialize'):
            await self.data_service.initialize()

        if hasattr(self.data_service, 'start_websocket_connections'):
            await self.data_service.start_websocket_connections()

        # Load inference models
        if hasattr(self.inference_service, 'load_models'):
            self.inference_service.load_models(MICA_COMPLIANT_PAIRS)

        # Load ensemble models for all pairs
        if self.ensemble is not None:
            ensemble_results = self.ensemble.load_all_models(
                [p for p in MICA_COMPLIANT_PAIRS if '/USDC' in p]
            )
            loaded = sum(1 for v in ensemble_results.values() if v)
            logger.info(f"Ensemble: loaded {loaded}/{len(ensemble_results)} strategy models")

        # Wire callbacks
        await self._connect_components()

        self.is_running = True
        self.stats['start_time'] = time.time()
        logger.info(f"Pipeline STARTED (mode={self.mode})")

    async def stop(self):
        """Stop the pipeline gracefully."""
        if not self.is_running:
            logger.warning("Pipeline is not running")
            return

        self.is_running = False

        # Disconnect data service
        if hasattr(self.data_service, 'stop'):
            await self.data_service.stop()
        elif hasattr(self.data_service, 'close'):
            await self.data_service.close()

        # Stop inference service
        if hasattr(self.inference_service, 'stop'):
            await self.inference_service.stop()

        logger.info("Pipeline STOPPED")

    async def _connect_components(self):
        """Connect pipeline components"""
        try:
            # Connect data service to inference service
            self.data_service.add_data_callback(self.inference_service.process_market_data)

            # Also buffer market data for ensemble predictions
            self.data_service.add_data_callback(self._buffer_market_data)

            # Connect inference service to opportunity handler
            self.inference_service.add_opportunity_callback(self._handle_opportunity)

            logger.info("Pipeline components connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect pipeline components: {e}")

    async def _buffer_market_data(self, data: Dict[str, Any]):
        """Buffer OHLCV data for ensemble predictions."""
        pair = data.get('pair')
        if not pair:
            return

        if pair not in self._market_buffers:
            self._market_buffers[pair] = deque(maxlen=100)

        # Extract OHLCV row: [timestamp, open, high, low, close, volume]
        row = np.array([
            data.get('timestamp', time.time()),
            data.get('open', data.get('price', 0.0)),
            data.get('high', data.get('price', 0.0)),
            data.get('low', data.get('price', 0.0)),
            data.get('close', data.get('price', 0.0)),
            data.get('volume', 0.0),
        ], dtype=np.float64)
        self._market_buffers[pair].append(row)

    async def _handle_opportunity(self, opportunity: ArbitrageOpportunity):
        """Handle detected arbitrage opportunity"""
        self.stats['opportunities_detected'] += 1

        try:
            # ── Ensemble confirmation (collective brain) ──────────────
            ensemble_signal = None
            if self.ensemble is not None and opportunity.pair in self._market_buffers:
                buf = self._market_buffers[opportunity.pair]
                if len(buf) >= 24:
                    market_data = np.array(list(buf), dtype=np.float64)
                    ensemble_signal = self.ensemble.predict(opportunity.pair, market_data)

                    # Gate: reject if strategies disagree
                    if ensemble_signal.agreement_score < self._ensemble_min_agreement:
                        logger.info(
                            f"Ensemble disagreement for {opportunity.pair}: "
                            f"agreement={ensemble_signal.agreement_score:.2f} "
                            f"< threshold={self._ensemble_min_agreement:.2f} — skipping"
                        )
                        self.stats['opportunities_filtered'] += 1
                        self.stats['ensemble_rejections'] = self.stats.get('ensemble_rejections', 0) + 1
                        return

                    # Boost/dampen confidence using ensemble
                    opportunity.confidence = min(
                        opportunity.confidence * ensemble_signal.confidence, 1.0
                    )
                    logger.debug(
                        f"Ensemble confirmed {opportunity.pair}: "
                        f"action={ensemble_signal.action} "
                        f"agreement={ensemble_signal.agreement_score:.2f} "
                        f"confidence={ensemble_signal.confidence:.2f}"
                    )

            # Acquire rate limit token for the primary exchange before proceeding
            if self.rate_limiter and opportunity.exchanges:
                allowed = await self.rate_limiter.acquire(
                    opportunity.exchanges[0], endpoint_type="rest_private", wait=False
                )
                if not allowed:
                    logger.debug(f"Rate limited on {opportunity.exchanges[0]} — skipping opportunity")
                    self.stats['opportunities_filtered'] += 1
                    return

            # Apply risk filtering
            if hasattr(self.opportunity_filter, 'validate_opportunity'):
                if not self.opportunity_filter.validate_opportunity(opportunity):
                    self.stats['opportunities_filtered'] += 1
                    return

            # Cache the opportunity (fire-and-forget to avoid blocking)
            if self.cache is not None:
                asyncio.create_task(self._cache_opportunity_bg(opportunity))

            # Send alert via multi-channel router (primary), fall back to Telegram-only
            if self.alert_router is not None:
                try:
                    from multi_channel_alerts import Alert as MCAlert
                    from multi_channel_alerts import AlertPriority
                    priority = (
                        AlertPriority.HIGH if opportunity.probability >= 0.8
                        else AlertPriority.MEDIUM
                    )
                    await self.alert_router.send(
                        MCAlert(
                            title=f"Arbitrage Opportunity: {opportunity.pair}",
                            message=(
                                f"Probability: {opportunity.probability:.1%}  "
                                f"Confidence: {opportunity.confidence:.1%}  "
                                f"Profit: {opportunity.profit_potential:.4f}  "
                                f"Exchanges: {', '.join(opportunity.exchanges)}"
                            ),
                            priority=priority,
                            category="arbitrage",
                        )
                    )
                    self.stats['alerts_sent'] += 1
                except Exception as e:
                    logger.warning(f"Multi-channel alert failed, falling back to Telegram: {e}")
                    if hasattr(self.alert_system, 'send_opportunity_alert'):
                        await self.alert_system.send_opportunity_alert(opportunity)
                        self.stats['alerts_sent'] += 1
            elif hasattr(self.alert_system, 'send_opportunity_alert'):
                await self.alert_system.send_opportunity_alert(opportunity)
                self.stats['alerts_sent'] += 1

            logger.info(f"Processed opportunity for {opportunity.pair}: {opportunity.probability:.3f}")

        except Exception as e:
            logger.error(f"Error handling opportunity: {e}")

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get pipeline status"""
        status = {
            'is_running': self.is_running,
            'mode': self.mode,
            'config': self.config,
            'stats': self.stats,
            'data_service': self.data_service.get_service_status() if hasattr(self.data_service, 'get_service_status') else {},
            'inference_service': self.inference_service.get_service_status() if hasattr(self.inference_service, 'get_service_status') else {},
        }
        if self.ensemble is not None:
            status['ensemble'] = self.ensemble.get_loaded_summary()
        return status


# ── Mock classes (development mode only) ─────────────────────────────────

    async def _cache_opportunity_bg(self, opportunity: ArbitrageOpportunity):
        """Background cache write — non-blocking."""
        try:
            await self.cache.cache_opportunity(
                f"{opportunity.pair}:{opportunity.timestamp}",
                {
                    'pair': opportunity.pair,
                    'probability': opportunity.probability,
                    'confidence': opportunity.confidence,
                    'exchanges': opportunity.exchanges,
                    'profit_potential': opportunity.profit_potential,
                }
            )
        except Exception:
            pass  # Cache failure is non-fatal


class MockDataService:
    """Mock data service — used only in development mode."""

    def __init__(self):
        self.data_sources = ['binance', 'coinbase', 'kraken', 'kucoin', 'okx']
        self._callbacks = []

    def add_data_callback(self, callback):
        self._callbacks.append(callback)

    async def initialize(self):
        logger.info("MockDataService.initialize() — no-op")

    async def start_websocket_connections(self):
        logger.info("MockDataService.start_websocket_connections() — no-op")

    async def stop(self):
        logger.info("MockDataService.stop() — no-op")

    def get_service_status(self):
        return {'is_running': True, 'type': 'mock', 'data_sources': len(self.data_sources)}


class MockInferenceService:
    """Mock inference service — used only in development mode."""

    def __init__(self):
        self.pairs = MICA_COMPLIANT_PAIRS[:10]
        self.models = {}
        self._callbacks = []

    def add_opportunity_callback(self, callback):
        self._callbacks.append(callback)

    def load_models(self, pairs):
        logger.info(f"MockInferenceService.load_models({len(pairs)} pairs) — no-op")

    async def process_market_data(self, data):
        pass

    async def stop(self):
        logger.info("MockInferenceService.stop() — no-op")

    def get_service_status(self):
        return {
            'is_running': True,
            'type': 'mock',
            'models_loaded': 0,
            'pairs_monitored': len(self.pairs),
            'gpu_available': False
        }


class MockRiskManager:
    """Mock risk manager — approves all opportunities."""

    def validate_opportunity(self, opportunity):
        return True


class MockAlertSystem:
    """Mock alert system — silently discards alerts."""

    async def send_opportunity_alert(self, opportunity):
        pass

    def add_alert_callback(self, callback):
        pass
