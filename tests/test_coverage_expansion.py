#!/usr/bin/env python3
"""
SovereignForge — Coverage Expansion Tests
Tests for previously untested modules: arbitrage_detector, dynamic_risk_adjustment,
performance_analyzer, personal_security, backtester.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Check torch availability (used for skip markers)
try:
    import torch
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

try:
    from scipy import stats as _scipy_stats
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

_skip_no_torch = pytest.mark.skipif(not _HAS_TORCH, reason="torch not available")
_skip_no_scipy = pytest.mark.skipif(not _HAS_SCIPY, reason="scipy not available")


# ═══════════════════════════════════════════════════════════════════════════
# ArbitrageDetector Tests (require torch)
# ═══════════════════════════════════════════════════════════════════════════

@_skip_no_torch
class TestSimpleArbitrageDetector:
    """Tests for SimpleArbitrageDetector neural network."""

    def test_init_default_input_size(self):
        from arbitrage_detector import SimpleArbitrageDetector
        model = SimpleArbitrageDetector()
        assert model is not None

    def test_init_custom_input_size(self):
        from arbitrage_detector import SimpleArbitrageDetector
        model = SimpleArbitrageDetector(input_size=10)
        assert model.network[0].in_features == 10

    def test_forward_pass(self):
        from arbitrage_detector import SimpleArbitrageDetector
        model = SimpleArbitrageDetector(input_size=6)
        model.eval()
        x = torch.randn(1, 6)
        with torch.no_grad():
            output = model(x)
        assert output.shape == (1, 1)

    def test_forward_batch(self):
        from arbitrage_detector import SimpleArbitrageDetector
        model = SimpleArbitrageDetector(input_size=6)
        model.eval()
        x = torch.randn(8, 6)
        with torch.no_grad():
            output = model(x)
        assert output.shape == (8, 1)


@_skip_no_torch
class TestLegacyArbitrageDetector:
    """Tests for LegacyArbitrageDetector LSTM model."""

    def test_init_defaults(self):
        from arbitrage_detector import LegacyArbitrageDetector
        model = LegacyArbitrageDetector()
        assert model.lstm.input_size == 22
        assert model.lstm.hidden_size == 64

    def test_forward_2d_input(self):
        from arbitrage_detector import LegacyArbitrageDetector
        model = LegacyArbitrageDetector(input_size=22)
        model.eval()
        x = torch.randn(1, 22)
        with torch.no_grad():
            output = model(x)
        assert output.dim() <= 1 or output.shape[-1] == 1

    def test_forward_3d_input_single_step(self):
        from arbitrage_detector import LegacyArbitrageDetector
        model = LegacyArbitrageDetector(input_size=22)
        model.eval()
        x = torch.randn(2, 1, 22)
        with torch.no_grad():
            output = model(x)
        assert output.shape[0] == 2

    def test_forward_3d_input_sequence(self):
        from arbitrage_detector import LegacyArbitrageDetector
        model = LegacyArbitrageDetector(input_size=22)
        model.eval()
        x = torch.randn(2, 10, 22)
        with torch.no_grad():
            output = model(x)
        assert output.shape[0] == 2


@_skip_no_torch
class TestMarketDataProcessor:
    """Tests for MarketDataProcessor feature extraction."""

    def test_extract_features_two_exchanges(self):
        from arbitrage_detector import MarketDataProcessor
        proc = MarketDataProcessor()
        data = {
            'exchanges': {
                'binance': {'bid': 45000.0, 'ask': 45010.0, 'volume': 100.0},
                'coinbase': {'bid': 44990.0, 'ask': 45000.0, 'volume': 95.0},
            },
            'price_history': [45000 + i * 0.1 for i in range(20)],
            'timestamp': datetime(2026, 3, 12, 14, 30),
        }
        features = proc.extract_features(data)
        assert features.shape == (6,)
        assert features.dtype == torch.float32

    def test_extract_features_single_exchange(self):
        from arbitrage_detector import MarketDataProcessor
        proc = MarketDataProcessor()
        data = {
            'exchanges': {'binance': {'bid': 45000.0, 'ask': 45010.0, 'volume': 100.0}},
            'timestamp': datetime(2026, 3, 12, 14, 30),
        }
        features = proc.extract_features(data)
        assert features.shape == (6,)

    def test_extract_features_no_price_history(self):
        from arbitrage_detector import MarketDataProcessor
        proc = MarketDataProcessor()
        data = {
            'exchanges': {
                'binance': {'bid': 45000.0, 'ask': 45010.0, 'volume': 100.0},
                'coinbase': {'bid': 44990.0, 'ask': 45000.0, 'volume': 95.0},
            },
            'timestamp': datetime(2026, 3, 12, 14, 30),
        }
        features = proc.extract_features(data)
        assert abs(features[3].item() - 0.02) < 1e-6

    def test_extract_features_none_values(self):
        from arbitrage_detector import MarketDataProcessor
        proc = MarketDataProcessor()
        data = {
            'exchanges': {
                'binance': {'bid': None, 'ask': None, 'volume': None},
                'coinbase': {'bid': 45000.0, 'ask': 45010.0, 'volume': 100.0},
            },
            'timestamp': datetime(2026, 3, 12, 14, 30),
        }
        features = proc.extract_features(data)
        assert features.shape == (6,)


@_skip_no_torch
class TestArbitrageDetectorMain:
    """Tests for the main ArbitrageDetector class."""

    def test_init_creates_fallback_model(self):
        from arbitrage_detector import ArbitrageDetector
        detector = ArbitrageDetector(enable_grok_reasoning=False)
        assert detector.model is not None
        assert detector.model_type == 'simple'

    def test_detect_opportunity_compliant_pair(self):
        from arbitrage_detector import ArbitrageDetector, create_sample_data
        detector = ArbitrageDetector(enable_grok_reasoning=False)
        data = create_sample_data()
        data['pair'] = 'XRP/USDC'
        result = detector.detect_opportunity(data)
        assert 'arbitrage_signal' in result
        assert 'confidence' in result
        assert 'opportunity_detected' in result
        assert result['model_type'] == 'simple'

    def test_detect_opportunity_noncompliant_pair(self):
        from arbitrage_detector import ArbitrageDetector, create_sample_data
        detector = ArbitrageDetector(enable_grok_reasoning=False)
        data = create_sample_data()
        data['pair'] = 'DOGE/USDT'
        result = detector.detect_opportunity(data)
        assert 'error' in result or result.get('model_type') == 'error'

    def test_detect_opportunity_no_pair(self):
        from arbitrage_detector import ArbitrageDetector, create_sample_data
        detector = ArbitrageDetector(enable_grok_reasoning=False)
        data = create_sample_data()
        data.pop('pair', None)
        result = detector.detect_opportunity(data)
        assert 'arbitrage_signal' in result

    def test_prepare_legacy_features(self):
        from arbitrage_detector import ArbitrageDetector, create_sample_data
        detector = ArbitrageDetector(enable_grok_reasoning=False)
        data = create_sample_data()
        features = detector._prepare_legacy_features(data)
        assert features.shape == (22,)


@_skip_no_torch
class TestLocalDatabase:
    """Tests for LocalDatabase SQLite storage."""

    def test_init_creates_tables(self):
        from arbitrage_detector import LocalDatabase
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            LocalDatabase(db_path=db_path)
            assert os.path.exists(db_path)
        finally:
            os.unlink(db_path)

    def test_save_and_retrieve_opportunity(self):
        from arbitrage_detector import LocalDatabase
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            db = LocalDatabase(db_path=db_path)
            result = {
                'timestamp': datetime.now().isoformat(),
                'arbitrage_signal': 0.85,
                'confidence': 0.92,
                'opportunity_detected': True,
            }
            market_data = {'exchanges': {'binance': {}, 'coinbase': {}}}
            db.save_opportunity(result, market_data)
            recent = db.get_recent_opportunities(limit=5)
            assert len(recent) == 1
            assert recent[0]['arbitrage_signal'] == 0.85
        finally:
            os.unlink(db_path)

    def test_get_recent_empty(self):
        from arbitrage_detector import LocalDatabase
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        try:
            db = LocalDatabase(db_path=db_path)
            recent = db.get_recent_opportunities(limit=5)
            assert recent == []
        finally:
            os.unlink(db_path)


@_skip_no_torch
class TestCreateSampleData:
    def test_sample_data_structure(self):
        from arbitrage_detector import create_sample_data
        data = create_sample_data()
        assert 'exchanges' in data
        assert 'price_history' in data
        assert 'timestamp' in data
        assert len(data['price_history']) == 100


# ═══════════════════════════════════════════════════════════════════════════
# PerformanceAnalyzer Tests (no torch needed)
# ═══════════════════════════════════════════════════════════════════════════

@_skip_no_scipy
class TestPerformanceAnalyzer:
    """Tests for PerformanceAnalyzer trade analytics."""

    @staticmethod
    def _make_trades(n=20):
        np.random.seed(42)
        trades = []
        base_time = datetime(2026, 2, 1)
        for i in range(n):
            pnl = np.random.normal(0.5, 2.0)
            trades.append({
                'timestamp': base_time + timedelta(days=i),
                'symbol': ['XRP/USDC', 'XLM/USDC', 'ADA/USDC'][i % 3],
                'buy_exchange': 'binance',
                'sell_exchange': 'coinbase',
                'quantity': 100,
                'buy_price': 0.60,
                'sell_price': 0.61,
                'pnl': pnl,
                'fees': 0.01,
            })
        return trades

    def test_analyze_empty_trades(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze_portfolio_performance([])
        assert result == {'error': 'No trades available for analysis'}

    def test_analyze_basic_metrics(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades = self._make_trades(20)
        result = analyzer.analyze_portfolio_performance(trades)
        assert 'overview' in result
        assert result['overview']['total_trades'] == 20
        assert 'risk_metrics' in result
        assert 'trading_metrics' in result

    def test_analyze_win_rate(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades = [
            {'timestamp': datetime(2026, 2, 1) + timedelta(days=i),
             'symbol': 'XRP/USDC', 'buy_exchange': 'binance',
             'sell_exchange': 'coinbase', 'quantity': 100,
             'pnl': 1.0, 'fees': 0.01}
            for i in range(5)
        ]
        result = analyzer.analyze_portfolio_performance(trades)
        assert result['overview']['win_rate'] == 1.0

    def test_sharpe_ratio_calculated(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades = self._make_trades(30)
        result = analyzer.analyze_portfolio_performance(trades)
        assert np.isfinite(result['risk_metrics']['sharpe_ratio'])

    def test_monthly_returns_breakdown(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades = self._make_trades(20)
        result = analyzer.analyze_portfolio_performance(trades)
        monthly = result['breakdown']['monthly_returns']
        assert isinstance(monthly, list)

    def test_symbol_performance_breakdown(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades = self._make_trades(20)
        result = analyzer.analyze_portfolio_performance(trades)
        symbols = result['breakdown']['symbol_performance']
        assert len(symbols) == 3

    def test_generate_text_report(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades = self._make_trades(10)
        report = analyzer.generate_performance_report(trades, output_format='text')
        assert 'SOVEREIGNFORGE PERFORMANCE REPORT' in report
        assert 'TRADING OVERVIEW' in report

    def test_generate_json_report(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades = self._make_trades(10)
        report = analyzer.generate_performance_report(trades, output_format='json')
        parsed = json.loads(report)
        assert 'overview' in parsed

    def test_generate_html_report(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades = self._make_trades(10)
        report = analyzer.generate_performance_report(trades, output_format='html')
        assert '<html>' in report
        assert 'SovereignForge Performance Report' in report

    def test_volatility_metrics(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        returns = pd.Series(np.random.normal(0.001, 0.02, 100))
        vol_metrics = analyzer._calculate_volatility_metrics(returns)
        assert 'volatility' in vol_metrics
        assert 'var_95' in vol_metrics
        assert 'skewness' in vol_metrics

    def test_win_loss_streaks(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades_df = pd.DataFrame({
            'pnl': [1, 2, 3, -1, -2, 1, 1, 1, 1, -1],
        })
        streaks = analyzer._calculate_win_loss_streaks(trades_df)
        assert streaks['best_win_streak'] == 4
        assert streaks['worst_loss_streak'] == 2

    def test_date_range_filtering(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        trades = self._make_trades(30)
        start = datetime(2026, 2, 10)
        end = datetime(2026, 2, 20)
        result = analyzer.analyze_portfolio_performance(trades, start_date=start, end_date=end)
        assert result['overview']['total_trades'] <= 30

    def test_real_time_metrics_no_risk_manager(self):
        from performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        result = analyzer.get_real_time_metrics()
        assert result == {'error': 'Risk manager not available'}

    def test_create_performance_analyzer_factory(self):
        from performance_analyzer import create_performance_analyzer
        analyzer = create_performance_analyzer()
        assert analyzer is not None


@_skip_no_scipy
class TestPerformanceDashboard:
    def test_generate_dashboard_data(self):
        from performance_analyzer import PerformanceAnalyzer, PerformanceDashboard
        analyzer = PerformanceAnalyzer()
        dashboard = PerformanceDashboard(analyzer)
        trades = TestPerformanceAnalyzer._make_trades(15)
        data = dashboard.generate_dashboard_data(trades)
        assert 'summary' in data
        assert 'charts' in data
        assert 'risk_indicators' in data

    def test_dashboard_empty_trades(self):
        from performance_analyzer import PerformanceAnalyzer, PerformanceDashboard
        analyzer = PerformanceAnalyzer()
        dashboard = PerformanceDashboard(analyzer)
        data = dashboard.generate_dashboard_data([])
        assert 'error' in data


# ═══════════════════════════════════════════════════════════════════════════
# PersonalSecurity Tests (no torch needed)
# ═══════════════════════════════════════════════════════════════════════════

class TestPersonalSecurity:
    """Tests for PersonalSecurityManager."""

    def test_init_defaults(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        assert mgr.max_memory_usage_gb == 8.0
        assert mgr.max_cpu_usage_pct == 80.0
        assert not mgr.monitoring_active
        mgr.shutdown()

    def test_allowed_data_paths(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        assert len(mgr.allowed_data_paths) > 0
        mgr.shutdown()

    def test_sensitive_files(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        assert 'api_keys.json' in mgr.sensitive_files
        assert '.env' in mgr.sensitive_files
        mgr.shutdown()

    def test_validate_data_access_unauthorized(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        result = mgr.validate_data_access('/etc/passwd')
        assert result is False
        assert len(mgr.violations) > 0
        mgr.shutdown()

    def test_validate_data_access_sensitive_file(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        for path in mgr.allowed_data_paths:
            result = mgr.validate_data_access(os.path.join(path, 'api_keys.json'))
            assert result is False
            break
        mgr.shutdown()

    def test_create_secure_environment(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        env = mgr.create_secure_environment()
        assert env['NO_EXTERNAL_NETWORK'] == '1'
        assert env['LOCAL_ONLY_EXECUTION'] == '1'
        assert env['DATA_ISOLATION_ENABLED'] == '1'
        mgr.shutdown()

    def test_security_report_structure(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        report = mgr.get_security_report()
        assert 'security_status' in report
        assert 'violations_count' in report
        assert 'resource_limits' in report
        assert 'data_isolation' in report
        mgr.shutdown()

    def test_mica_compliance_status(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        status = mgr.get_mica_compliance_status()
        assert status.get('personal_deployment') is True
        assert status.get('no_custody') is True
        mgr.shutdown()

    def test_emergency_shutdown(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        result = mgr.emergency_shutdown()
        assert result is True
        assert not mgr.monitoring_active

    def test_security_violation_dataclass(self):
        from personal_security import SecurityViolation
        v = SecurityViolation(
            violation_type='test', description='test violation',
            severity='low', timestamp=datetime.now(),
            details={'key': 'value'},
        )
        assert v.violation_type == 'test'
        assert v.severity == 'low'

    def test_local_execution_proof_dataclass(self):
        from personal_security import LocalExecutionProof
        proof = LocalExecutionProof(
            is_local_only=True, network_interfaces=['lo'],
            external_connections=[], last_check=datetime.now(),
            violations=[],
        )
        assert proof.is_local_only is True

    def test_verify_local_execution(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        proof = mgr.verify_local_execution()
        assert hasattr(proof, 'is_local_only')
        assert hasattr(proof, 'network_interfaces')
        mgr.shutdown()

    def test_graceful_shutdown(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        mgr.shutdown()
        assert not mgr.monitoring_active

    def test_perform_security_scan(self):
        from personal_security import PersonalSecurityManager
        mgr = PersonalSecurityManager(enable_network_monitoring=False)
        scan = mgr.perform_security_scan()
        assert 'security_status' in scan
        assert 'violations_found' in scan
        mgr.shutdown()


# ═══════════════════════════════════════════════════════════════════════════
# DynamicRiskAdjustment Tests (no torch needed)
# ═══════════════════════════════════════════════════════════════════════════

@_skip_no_torch
class TestDynamicRiskAdjustment:
    """Tests for DynamicRiskAdjustment adaptive risk engine (requires torch via advanced_risk_metrics)."""

    def test_init_defaults(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        assert dra.adjustment_sensitivity == 0.7
        assert dra.lookback_periods == 252
        assert not dra.circuit_breaker_active
        assert not dra.emergency_stop_active

    def test_default_market_conditions(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment, MarketRegime
        dra = DynamicRiskAdjustment()
        cond = dra.market_conditions
        assert cond.regime == MarketRegime.NORMAL
        assert cond.volatility_percentile == 50.0

    def test_classify_crash_regime(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment, MarketRegime
        dra = DynamicRiskAdjustment()
        regime = dra._classify_market_regime(85, 0.8, -0.5)
        assert regime == MarketRegime.CRASH

    def test_classify_volatile_regime(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment, MarketRegime
        dra = DynamicRiskAdjustment()
        regime = dra._classify_market_regime(75, 0.3, -0.2)
        assert regime == MarketRegime.VOLATILE

    def test_classify_bull_regime(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment, MarketRegime
        dra = DynamicRiskAdjustment()
        regime = dra._classify_market_regime(40, 0.3, 0.3)
        assert regime == MarketRegime.BULL

    def test_classify_bear_regime(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment, MarketRegime
        dra = DynamicRiskAdjustment()
        regime = dra._classify_market_regime(40, 0.3, -0.3)
        assert regime == MarketRegime.BEAR

    def test_classify_recovery_regime(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment, MarketRegime
        dra = DynamicRiskAdjustment()
        regime = dra._classify_market_regime(50, 0.3, 0.1)
        assert regime == MarketRegime.RECOVERY

    def test_classify_normal_regime(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment, MarketRegime
        dra = DynamicRiskAdjustment()
        regime = dra._classify_market_regime(65, 0.3, 0.0)
        assert regime == MarketRegime.NORMAL

    def test_assess_market_conditions(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        returns = np.random.normal(0.001, 0.03, (100, 5))
        conditions = dra.assess_market_conditions(returns)
        assert 0 <= conditions.volatility_percentile <= 100
        assert 0 <= conditions.correlation_stress <= 1
        assert 0 <= conditions.liquidity_score <= 1

    def test_assess_market_conditions_with_correlation(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        returns = np.random.normal(0.001, 0.03, (100, 5))
        corr = np.corrcoef(returns.T)
        conditions = dra.assess_market_conditions(returns, correlation_matrix=corr)
        assert conditions.correlation_stress >= 0

    def test_assess_market_conditions_with_volume(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        returns = np.random.normal(0.001, 0.03, (100, 5))
        volume = np.random.uniform(1000, 5000, 100)
        conditions = dra.assess_market_conditions(returns, volume_data=volume)
        assert 0 < conditions.liquidity_score <= 1

    def test_assess_arbitrage_opportunity_risk(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        opp_data = {
            'id': 'test_opp', 'pair': 'XRP/USDC',
            'spread': 0.002, 'volume_ratio': 1.2,
            'exchanges': ['binance', 'coinbase'],
        }
        risk = dra.assess_arbitrage_opportunity_risk(opp_data, dra.market_conditions)
        assert 0 <= risk.adjusted_risk_score <= 1
        assert risk.position_size_limit >= 0
        assert risk.regulatory_risk == 0.05

    def test_risk_higher_for_non_usdc_pair(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        opp_data = {
            'id': 'test', 'pair': 'XRP/EUR',
            'spread': 0.002, 'volume_ratio': 1.0,
            'exchanges': ['binance', 'coinbase'],
        }
        risk = dra.assess_arbitrage_opportunity_risk(opp_data, dra.market_conditions)
        assert risk.regulatory_risk == 0.2

    def test_risk_dashboard(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        dashboard = dra.get_risk_dashboard()
        assert 'current_thresholds' in dashboard
        assert 'market_conditions' in dashboard
        assert 'circuit_breaker_active' in dashboard

    def test_add_risk_alert_callback(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        cb = MagicMock()
        dra.add_risk_alert_callback(cb)
        assert cb in dra.risk_alert_callbacks

    def test_add_circuit_breaker_callback(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        cb = MagicMock()
        dra.add_circuit_breaker_callback(cb)
        assert cb in dra.circuit_breaker_callbacks

    def test_stop_monitoring(self):
        from dynamic_risk_adjustment import DynamicRiskAdjustment
        dra = DynamicRiskAdjustment()
        dra.monitoring_active = True
        dra.stop_monitoring()
        assert not dra.monitoring_active

    def test_calculate_dynamic_thresholds_crash(self):
        from advanced_risk_metrics import AdvancedRiskMetrics
        from dynamic_risk_adjustment import (
            DynamicRiskAdjustment,
            MarketConditions,
            MarketRegime,
        )
        dra = DynamicRiskAdjustment()
        crash_conditions = MarketConditions(
            regime=MarketRegime.CRASH, volatility_percentile=90,
            correlation_stress=0.9, liquidity_score=0.3,
            momentum_score=-0.5, fear_greed_index=10,
            timestamp=datetime.now(),
        )
        returns = np.random.normal(-0.01, 0.05, 100)
        metrics = AdvancedRiskMetrics().calculate_comprehensive_risk_metrics(returns)
        thresholds = dra.calculate_dynamic_thresholds(crash_conditions, metrics)
        assert thresholds.max_position_size < dra.base_thresholds.max_position_size

    def test_integrate_dynamic_risk_adjustment(self):
        from dynamic_risk_adjustment import integrate_dynamic_risk_adjustment
        mock_rm = MagicMock()
        dra = integrate_dynamic_risk_adjustment(mock_rm)
        assert len(dra.risk_alert_callbacks) == 1
        assert len(dra.circuit_breaker_callbacks) == 1


@_skip_no_torch
class TestRiskDataclasses:
    """Tests for risk-related dataclasses (requires torch via advanced_risk_metrics)."""

    def test_risk_thresholds(self):
        from dynamic_risk_adjustment import RiskThresholds
        rt = RiskThresholds(
            max_position_size=0.02, max_portfolio_var=0.05,
            max_single_asset_var=0.03, max_correlation_exposure=0.8,
            max_volatility_adjustment=0.5, circuit_breaker_threshold=0.10,
            emergency_stop_threshold=0.15,
        )
        assert rt.max_position_size == 0.02

    def test_market_conditions(self):
        from dynamic_risk_adjustment import MarketConditions, MarketRegime
        mc = MarketConditions(
            regime=MarketRegime.NORMAL, volatility_percentile=50,
            correlation_stress=0.3, liquidity_score=0.7,
            momentum_score=0.0, fear_greed_index=50,
            timestamp=datetime.now(),
        )
        assert mc.regime == MarketRegime.NORMAL

    def test_arbitrage_opportunity_risk(self):
        from dynamic_risk_adjustment import ArbitrageOpportunityRisk
        risk = ArbitrageOpportunityRisk(
            opportunity_id='test', base_risk_score=0.3,
            adjusted_risk_score=0.4, position_size_limit=0.01,
            execution_probability=0.6, expected_holding_time=300,
            liquidation_risk=0.1, counterparty_risk=0.05,
            regulatory_risk=0.02,
        )
        assert risk.opportunity_id == 'test'


# ═══════════════════════════════════════════════════════════════════════════
# Backtester Tests (no torch needed)
# ═══════════════════════════════════════════════════════════════════════════

class TestBacktestDataProvider:
    """Tests for BacktestDataProvider synthetic data generation."""

    def test_init_generates_data(self):
        from backtester import BacktestDataProvider
        provider = BacktestDataProvider()
        assert len(provider.price_data) > 0

    def test_available_symbols(self):
        from backtester import BacktestDataProvider
        provider = BacktestDataProvider()
        symbols = provider.get_available_symbols()
        assert 'BTC/USDC' in symbols
        assert 'XRP/USDC' in symbols

    def test_available_exchanges(self):
        from backtester import BacktestDataProvider
        provider = BacktestDataProvider()
        exchanges = provider.get_available_exchanges()
        assert 'binance' in exchanges
        assert 'coinbase' in exchanges

    def test_get_price_at_time(self):
        from backtester import BacktestDataProvider
        provider = BacktestDataProvider()
        price = provider.get_price_at_time(
            'BTC/USDC', 'binance', datetime.now() - timedelta(days=30)
        )
        assert price is not None
        assert 'price' in price
        assert price['price'] > 0

    def test_get_price_unknown_symbol(self):
        from backtester import BacktestDataProvider
        provider = BacktestDataProvider()
        price = provider.get_price_at_time('FAKE/USDC', 'binance', datetime.now())
        assert price is None

    def test_get_price_window(self):
        from backtester import BacktestDataProvider
        provider = BacktestDataProvider()
        start = datetime.now() - timedelta(days=30)
        end = datetime.now() - timedelta(days=25)
        window = provider.get_price_window('BTC/USDC', 'binance', start, end)
        assert isinstance(window, pd.DataFrame)
        assert len(window) > 0


class TestArbitrageBacktester:
    """Tests for ArbitrageBacktester simulation engine."""

    def test_init_defaults(self):
        from backtester import ArbitrageBacktester, BacktestDataProvider
        provider = BacktestDataProvider()
        bt = ArbitrageBacktester(provider)
        assert bt.portfolio_value == 10000.0
        assert bt.cash == 10000.0
        assert bt.trades == []

    @pytest.mark.asyncio
    async def test_run_short_backtest(self):
        from backtester import ArbitrageBacktester, BacktestDataProvider
        provider = BacktestDataProvider()
        bt = ArbitrageBacktester(provider)
        start = datetime.now() - timedelta(days=3)
        end = datetime.now() - timedelta(days=2)
        results = await bt.run_backtest(['BTC/USDC'], start, end)
        assert 'total_trades' in results or 'error' in results

    def test_find_arbitrage_opportunities(self):
        from backtester import ArbitrageBacktester, BacktestDataProvider
        provider = BacktestDataProvider()
        bt = ArbitrageBacktester(provider)
        snapshot = {
            'BTC/USDC': {
                'binance': {'bid': 45000, 'ask': 45010, 'volume': 100, 'price': 45005},
                'coinbase': {'bid': 45020, 'ask': 45030, 'volume': 90, 'price': 45025},
            }
        }
        opps = bt._find_arbitrage_opportunities(snapshot, datetime.now())
        assert isinstance(opps, list)

    def test_validate_opportunity_low_spread(self):
        from backtester import ArbitrageBacktester, BacktestDataProvider
        provider = BacktestDataProvider()
        bt = ArbitrageBacktester(provider)
        opp = {'spread_percentage': 0.0005, 'buy_volume': 100, 'sell_volume': 100}
        assert bt._validate_opportunity(opp) is False

    def test_validate_opportunity_low_volume(self):
        from backtester import ArbitrageBacktester, BacktestDataProvider
        provider = BacktestDataProvider()
        bt = ArbitrageBacktester(provider)
        opp = {'spread_percentage': 0.005, 'buy_volume': 5, 'sell_volume': 100}
        assert bt._validate_opportunity(opp) is False

    def test_validate_opportunity_good(self):
        from backtester import ArbitrageBacktester, BacktestDataProvider
        provider = BacktestDataProvider()
        bt = ArbitrageBacktester(provider)
        opp = {'spread_percentage': 0.005, 'buy_volume': 100, 'sell_volume': 100}
        assert bt._validate_opportunity(opp) is True

    def test_get_trades_df_empty(self):
        from backtester import ArbitrageBacktester, BacktestDataProvider
        provider = BacktestDataProvider()
        bt = ArbitrageBacktester(provider)
        df = bt.get_trades_df()
        assert df.empty

    @pytest.mark.asyncio
    async def test_execute_backtest_trade(self):
        from backtester import ArbitrageBacktester, BacktestDataProvider
        provider = BacktestDataProvider()
        bt = ArbitrageBacktester(provider)
        opp = {
            'symbol': 'BTC/USDC',
            'buy_exchange': 'binance', 'sell_exchange': 'coinbase',
            'buy_price': 45000, 'sell_price': 45050,
            'spread_percentage': 0.001,
            'timestamp': datetime.now(),
            'buy_volume': 100, 'sell_volume': 100,
        }
        initial = bt.portfolio_value
        await bt._execute_backtest_trade(opp)
        assert len(bt.trades) == 1
        assert bt.portfolio_value != initial

    def test_calculate_results_no_trades(self):
        from backtester import ArbitrageBacktester, BacktestDataProvider
        provider = BacktestDataProvider()
        bt = ArbitrageBacktester(provider)
        bt.start_date = datetime.now() - timedelta(days=7)
        bt.end_date = datetime.now()
        results = bt._calculate_backtest_results()
        assert results == {'error': 'No trades executed'}
