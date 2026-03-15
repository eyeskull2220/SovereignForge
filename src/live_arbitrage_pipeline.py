#!/usr/bin/env python3
"""
SovereignForge - Live Arbitrage Pipeline
End-to-end arbitrage detection and execution pipeline

Supports two modes:
  - "production": Requires real services (raises on import failure)
  - "development": Allows mock fallbacks with clear warnings
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

import numpy as np

try:
    from dynamic_risk_adjustment import DynamicRiskAdjustment
    DYNAMIC_RISK_AVAILABLE = True
except ImportError:
    DYNAMIC_RISK_AVAILABLE = False

try:
    from regime_detector import RegimeDetector
    REGIME_DETECTOR_AVAILABLE = True
except ImportError:
    REGIME_DETECTOR_AVAILABLE = False

try:
    from cointegration_detector import CointegrationDetector
    COINTEGRATION_AVAILABLE = True
except ImportError:
    COINTEGRATION_AVAILABLE = False

logger = logging.getLogger(__name__)

# MiCA-compliant trading pairs — derived from compliance engine (no USDT)
try:
    from compliance import MiCAComplianceEngine
    _compliance_engine = MiCAComplianceEngine()
    MICA_COMPLIANT_PAIRS = _compliance_engine.get_compliant_pairs()
except ImportError:
    # Minimal fallback — should never happen in production
    MICA_COMPLIANT_PAIRS = [f"{asset}/USDC" for asset in ['XRP', 'XLM', 'HBAR', 'ALGO', 'ADA', 'LINK', 'IOTA', 'VET', 'XDC', 'ONDO', 'BTC', 'ETH']]


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
        self.cross_exchange_scorer = None  # Set by _init_ensemble if configured
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

        # ── Order execution ────────────────────────────────────────────
        self.order_executor = self._init_order_executor()

        # ── Optional services (degrade gracefully in all modes) ───────
        self.cache = self._init_optional('cache_layer', 'get_cache',
                                         "CacheManager initialised (Redis + LRU fallback)")
        self.rate_limiter = self._init_optional('exchange_rate_limiter', 'get_rate_limiter',
                                                "RateLimiterManager initialised")
        self.alert_router = self._init_optional('multi_channel_alerts', 'get_alert_router',
                                                "AlertRouter initialised (multi-channel)")

        # ── Safety: opportunity dedup cache (pair+exchanges → timestamp) ──
        self._dedup_cache: Dict[str, float] = {}
        self._dedup_window = config.get('dedup_window_seconds', 60)

        # ── Fee config ────────────────────────────────────────────────
        self._default_taker_fee = config.get('default_taker_fee', 0.001)  # 0.1%
        self._exchange_fees = {
            'binance': 0.001,    # 0.1% taker
            'coinbase': 0.004,   # 0.4% taker (Advanced Trade)
            'kraken': 0.0026,    # 0.26% taker
            'kucoin': 0.001,     # 0.1% taker
            'okx': 0.001,        # 0.1% taker
            'bybit': 0.001,      # 0.1% taker
            'gate': 0.002,       # 0.2% taker
        }
        self._min_net_profit = config.get('min_net_profit', 0.25)  # $0.25 minimum

        # ── State persistence paths ───────────────────────────────────
        self._project_root = Path(__file__).resolve().parent.parent
        self._pipeline_state_path = self._project_root / "reports" / "pipeline_state.json"
        self._paper_trading_state_path = self._project_root / "reports" / "paper_trading_state.json"

        # ── Cached initial capital (avoid re-reading config on every trade) ──
        try:
            _cfg_path = self._project_root / "config" / "trading_config.json"
            with open(_cfg_path) as _f:
                _cfg = json.load(_f)
            self._initial_capital = _cfg.get('capital_allocation', {}).get('initial_capital', 300.0)
        except Exception:
            self._initial_capital = 300.0  # Safe fallback

        # Pipeline statistics
        self.stats = {
            'opportunities_detected': 0,
            'opportunities_filtered': 0,
            'opportunities_executed': 0,
            'alerts_sent': 0,
            'trades_successful': 0,
            'trades_failed': 0,
            'total_pnl': 0.0,
            'start_time': time.time()
        }

        # Dynamic risk adjustment (VaR-based circuit breakers)
        self._dynamic_risk = None
        if DYNAMIC_RISK_AVAILABLE:
            try:
                self._dynamic_risk = DynamicRiskAdjustment()
                logger.info("Dynamic risk adjustment initialized")
            except Exception as e:
                logger.warning(f"Dynamic risk adjustment unavailable: {e}")

        # Market regime detector
        self._regime_detector = None
        if REGIME_DETECTOR_AVAILABLE:
            try:
                self._regime_detector = RegimeDetector()
                logger.info("Market regime detector initialized")
            except Exception as e:
                logger.warning(f"Regime detector unavailable: {e}")

        # Cointegration detector for pairs arbitrage
        self._cointegration_detector = None
        if COINTEGRATION_AVAILABLE:
            try:
                self._cointegration_detector = CointegrationDetector()
                logger.info("Cointegration detector initialized")
            except Exception as e:
                logger.warning(f"Cointegration detector unavailable: {e}")

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
        """Initialize the multi-strategy ensemble (collective brain) and cross-exchange scorer."""
        try:
            from strategy_ensemble import StrategyEnsemble, CrossExchangeScorer
            ensemble = StrategyEnsemble(config=self.config)
            logger.info("StrategyEnsemble loaded — collective brain enabled")

            # Initialize CrossExchangeScorer if configured
            cx_config = self.config.get('cross_exchange', {})
            if cx_config.get('enabled', False):
                risk_mgr = None
                try:
                    from risk_management import get_risk_manager
                    risk_mgr = get_risk_manager()
                except ImportError:
                    pass
                self.cross_exchange_scorer = CrossExchangeScorer(
                    ensemble=ensemble,
                    risk_manager=risk_mgr,
                    min_signal_spread=cx_config.get('min_signal_spread', 0.2),
                    min_confidence=cx_config.get('min_confidence', 0.3),
                )
                logger.info("CrossExchangeScorer loaded — cross-exchange arbitrage detection enabled")
            else:
                self.cross_exchange_scorer = None

            return ensemble
        except ImportError:
            self.cross_exchange_scorer = None
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

    def _init_order_executor(self):
        """Initialize order executor (paper trading by default)."""
        trading_config = self.config.get('trading', {})
        dry_run = trading_config.get('dry_run_mode', True)
        trading_enabled = trading_config.get('trading_enabled', False)

        # Exchange configs for paper trading (dummy keys, no real API calls)
        cross_exchange_config = self.config.get('cross_exchange', {})
        configured_exchanges = cross_exchange_config.get('exchanges', ['binance', 'coinbase', 'kraken', 'okx'])

        try:
            from order_executor import PaperTradingExecutor, OrderExecutor, create_demo_executor

            if dry_run or not trading_enabled:
                executor = create_demo_executor()
                logger.info("PaperTradingExecutor loaded — trades will be simulated")
                return executor

            # Live trading: requires exchange configs with API keys
            exchange_configs = {}
            try:
                api_keys_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
                if api_keys_path.exists():
                    with open(api_keys_path) as f:
                        exchange_configs = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load API keys: {e}")

            if exchange_configs:
                executor = OrderExecutor(exchange_configs)
                logger.warning("LIVE OrderExecutor loaded — REAL TRADES WILL BE PLACED")
                return executor

            logger.warning("No API keys found — falling back to PaperTradingExecutor")
            return create_demo_executor()

        except ImportError:
            logger.warning("OrderExecutor not available — trade execution disabled")
            return None

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
            # ── Periodic market condition assessment (every 50 opportunities) ──
            if self._dynamic_risk and self.stats.get('opportunities_detected', 0) % 50 == 0:
                try:
                    # Build recent returns from market buffer for this pair
                    buf = self._market_buffers.get(opportunity.pair)
                    if buf and len(buf) >= 10:
                        closes = np.array([row[4] for row in buf], dtype=np.float64)
                        recent_returns = np.diff(closes) / closes[:-1]
                        conditions = self._dynamic_risk.assess_market_conditions(recent_returns.reshape(-1, 1))
                        if conditions:
                            self._last_market_conditions = conditions
                            logger.info(f"Market conditions updated: regime={conditions.regime.value}")
                except (ValueError, IndexError) as e:
                    logger.debug(f"Market assessment skipped: {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error in market assessment: {e}")

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

            # ── Trade execution ───────────────────────────────────────
            if self.order_executor is not None:
                await self._execute_trade(opportunity)

            logger.info(f"Processed opportunity for {opportunity.pair}: {opportunity.probability:.3f}")

        except Exception as e:
            logger.error(f"Error handling opportunity: {e}")

    async def _execute_trade(self, opportunity: ArbitrageOpportunity):
        """Execute a trade for a confirmed opportunity with safety checks."""
        # SAFETY: Block trade execution with mock risk manager
        if hasattr(self.opportunity_filter, '_is_mock') or type(self.opportunity_filter).__name__ == 'MockRiskManager':
            logger.critical("BLOCKED: Cannot execute trades with MockRiskManager. Set mode to 'production'.")
            return

        # Dynamic risk check — circuit breaker and emergency stop gate
        if self._dynamic_risk is not None:
            try:
                if self._dynamic_risk.emergency_stop_active:
                    logger.critical(f"EMERGENCY STOP active — blocking trade for {opportunity.pair}")
                    self.stats['circuit_breaker_blocks'] = self.stats.get('circuit_breaker_blocks', 0) + 1
                    return
                if self._dynamic_risk.circuit_breaker_active:
                    logger.warning(f"Circuit breaker active — blocking trade for {opportunity.pair}")
                    self.stats['circuit_breaker_blocks'] = self.stats.get('circuit_breaker_blocks', 0) + 1
                    return
            except Exception as e:
                logger.error(f"Dynamic risk check FAILED — blocking trade for {opportunity.pair}: {e}")
                self.stats['circuit_breaker_blocks'] = self.stats.get('circuit_breaker_blocks', 0) + 1
                return

        try:
            # Dedup check: skip if same opportunity was recently executed
            dedup_key = f"{opportunity.pair}:{'-'.join(sorted(opportunity.exchanges))}"
            now = time.time()
            if dedup_key in self._dedup_cache:
                if now - self._dedup_cache[dedup_key] < self._dedup_window:
                    logger.debug(f"Dedup: skipping {opportunity.pair} (executed {now - self._dedup_cache[dedup_key]:.0f}s ago)")
                    return

            # Evict stale dedup entries
            stale_keys = [k for k, t in self._dedup_cache.items() if now - t > self._dedup_window * 2]
            for k in stale_keys:
                del self._dedup_cache[k]

            # Determine buy/sell exchanges from prices
            if len(opportunity.prices) < 2:
                logger.warning(f"Need ≥2 exchange prices for arbitrage, got {len(opportunity.prices)}")
                return

            buy_exchange = min(opportunity.prices, key=opportunity.prices.get)
            sell_exchange = max(opportunity.prices, key=opportunity.prices.get)

            buy_price = opportunity.prices[buy_exchange]
            sell_price = opportunity.prices[sell_exchange]

            if buy_price <= 0 or sell_price <= 0:
                return

            # Fee-inclusive profit calculation
            spread = sell_price - buy_price
            spread_pct = spread / buy_price

            # Position sizing: prefer RiskManager if available, fall back to config-based sizing
            quantity = None
            if hasattr(self.opportunity_filter, 'calculate_position_size'):
                try:
                    opp_data = {
                        'pair': opportunity.pair,
                        'buy_exchange': buy_exchange,
                        'sell_exchange': sell_exchange,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'spread_pct': spread_pct,
                    }
                    rm_result = self.opportunity_filter.calculate_position_size(opp_data)
                    if isinstance(rm_result, dict) and 'quantity' in rm_result:
                        quantity = rm_result['quantity']
                    elif isinstance(rm_result, (int, float)) and rm_result > 0:
                        quantity = float(rm_result)
                    if quantity is not None:
                        logger.debug(f"Position size from RiskManager: {quantity} for {opportunity.pair}")
                except Exception as e:
                    logger.warning(f"RiskManager position sizing failed, using fallback: {e}")
                    quantity = None

            if quantity is None:
                # Fallback: ad-hoc percentage sizing
                trading_config = self.config.get('trading', {})
                max_position_pct = trading_config.get('max_position_size_percent', 2.0) / 100.0
                if hasattr(self.opportunity_filter, 'portfolio_value') and self.opportunity_filter.portfolio_value > 0:
                    base_capital = self.opportunity_filter.portfolio_value
                else:
                    base_capital = self._initial_capital
                quantity = (base_capital * max_position_pct) / buy_price

            buy_fee_rate = self._exchange_fees.get(buy_exchange, 0.001)
            sell_fee_rate = self._exchange_fees.get(sell_exchange, 0.001)
            buy_fee = buy_price * quantity * buy_fee_rate
            sell_fee = sell_price * quantity * sell_fee_rate
            net_profit = (spread * quantity) - buy_fee - sell_fee

            if net_profit < self._min_net_profit:
                logger.debug(
                    f"Net profit ${net_profit:.2f} below minimum ${self._min_net_profit:.2f} "
                    f"for {opportunity.pair} (spread={spread_pct:.4%})"
                )
                self.stats['opportunities_filtered'] += 1
                return

            # Build executor-compatible dict
            trade_request = {
                'symbol': opportunity.pair,
                'buy_exchange': buy_exchange,
                'sell_exchange': sell_exchange,
                'spread_percentage': spread_pct,
                'quantity': quantity,
                'buy_price': buy_price,
                'sell_price': sell_price,
            }

            # Execute
            logger.info(
                f"Executing trade: {opportunity.pair} "
                f"BUY@{buy_exchange}=${buy_price:.4f} → SELL@{sell_exchange}=${sell_price:.4f} "
                f"qty={quantity:.6f} est_profit=${net_profit:.2f}"
            )

            result = await self.order_executor.execute_arbitrage_trade(trade_request)

            # Update stats and dedup cache
            self._dedup_cache[dedup_key] = now
            self.stats['opportunities_executed'] += 1

            if result.get('success'):
                self.stats['trades_successful'] += 1
                self.stats['total_pnl'] += result.get('pnl', 0)
                logger.info(f"Trade SUCCESS: {opportunity.pair} P&L=${result.get('pnl', 0):.2f}")
            else:
                self.stats['trades_failed'] += 1
                logger.warning(f"Trade FAILED: {opportunity.pair} — {result.get('errors', [])}")

            # Persist pipeline state for dashboard
            await self._persist_pipeline_state(opportunity, result)

        except Exception as e:
            logger.error(f"Trade execution error for {opportunity.pair}: {e}")
            self.stats['trades_failed'] += 1

    @staticmethod
    def _atomic_write_json(data: dict, path: Path):
        """Write JSON atomically: write to temp file, then rename."""
        tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            # Keep one backup
            backup = path.with_suffix('.json.bak')
            if path.exists():
                try:
                    shutil.copy2(path, backup)
                except Exception:
                    pass
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise

    async def _persist_pipeline_state(self, opportunity: ArbitrageOpportunity, trade_result: Dict):
        """Persist pipeline state to JSON for dashboard consumption."""
        try:
            self._pipeline_state_path.parent.mkdir(parents=True, exist_ok=True)

            # Load existing state or create new
            state = {}
            if self._pipeline_state_path.exists():
                with open(self._pipeline_state_path) as f:
                    state = json.load(f)

            state['is_running'] = self.is_running
            state['last_updated'] = datetime.now().isoformat()
            state['opportunities_detected'] = self.stats['opportunities_detected']
            state['trades_successful'] = self.stats['trades_successful']
            state['trades_failed'] = self.stats['trades_failed']
            state['total_pnl'] = self.stats['total_pnl']

            # Track connected exchanges
            if hasattr(self.data_service, 'get_connection_health'):
                health = self.data_service.get_connection_health()
                state['connected_exchanges'] = [
                    ex for ex, h in health.items() if h.get('healthy', False)
                ]

            # Keep last 50 opportunities
            recent = state.get('recent_opportunities', [])
            recent.insert(0, {
                'pair': opportunity.pair,
                'probability': opportunity.probability,
                'confidence': opportunity.confidence,
                'exchanges': opportunity.exchanges,
                'profit_potential': opportunity.profit_potential,
                'trade_success': trade_result.get('success', False),
                'trade_pnl': trade_result.get('pnl', 0),
                'timestamp': datetime.now().isoformat(),
            })
            state['recent_opportunities'] = recent[:50]

            await asyncio.to_thread(self._atomic_write_json, state, self._pipeline_state_path)

        except Exception as e:
            logger.debug(f"Failed to persist pipeline state: {e}")

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
        if self._dynamic_risk is not None:
            last_cond = getattr(self, '_last_market_conditions', None)
            status['dynamic_risk'] = {
                'enabled': True,
                'circuit_breaker_active': self._dynamic_risk.circuit_breaker_active,
                'emergency_stop_active': self._dynamic_risk.emergency_stop_active,
                'circuit_breaker_blocks': self.stats.get('circuit_breaker_blocks', 0),
                'last_regime': last_cond.regime.value if last_cond else None,
            }
        if self._regime_detector is not None and self._regime_detector.last_regime is not None:
            status['market_regime'] = self._regime_detector.last_regime.value
        if self._cointegration_detector is not None:
            status['cointegration'] = self._cointegration_detector.get_status()
        return status

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
        except Exception as e:
            logger.debug(f"Cache write failed: {e}")


# ── Mock classes (development mode only) ─────────────────────────────────


class MockDataService:
    """Mock data service — used only in development mode."""

    def __init__(self):
        self.data_sources = ['binance', 'coinbase', 'kraken', 'kucoin', 'okx', 'bybit']
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
        self.pairs = [p for p in MICA_COMPLIANT_PAIRS if p.endswith('/USDC')]
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
    _is_mock = True

    def validate_opportunity(self, opportunity):
        return True


class MockAlertSystem:
    """Mock alert system — silently discards alerts."""

    async def send_opportunity_alert(self, opportunity):
        pass

    def add_alert_callback(self, callback):
        pass
