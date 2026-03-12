#!/usr/bin/env python3
"""
Expanded test coverage for SovereignForge modules.
Covers: monitoring, compliance, order_executor, live_arbitrage_pipeline,
        risk_management (consolidated module).
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import pytest

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))


# ── Compliance Engine ──────────────────────────────────────────────────────

class TestMiCAComplianceEngine:
    """Tests for src/compliance.py"""

    def setup_method(self):
        # Reset singleton so each test gets a fresh instance
        import compliance
        compliance._compliance_engine = None
        from compliance import MiCAComplianceEngine
        self.engine = MiCAComplianceEngine(personal_deployment=True)

    def test_usdc_pairs_compliant(self):
        """USDC pairs with compliant assets should pass"""
        from compliance import MiCAComplianceEngine
        engine = MiCAComplianceEngine(personal_deployment=True)
        for pair in ['XRP/USDC', 'ADA/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC']:
            assert engine.is_pair_compliant(pair), f"{pair} should be compliant"

    def test_usdt_pairs_forbidden(self):
        """No USDT pairs should ever be compliant"""
        assert not self.engine.is_pair_compliant('BTC/USDT')
        assert not self.engine.is_pair_compliant('XRP/USDT')
        assert not self.engine.is_pair_compliant('ETH/USDT')

    def test_rlusd_pairs_compliant(self):
        """RLUSD pairs should be compliant"""
        assert self.engine.is_pair_compliant('XRP/RLUSD')
        assert self.engine.is_pair_compliant('ADA/RLUSD')

    def test_is_asset_compliant(self):
        """Check individual asset compliance"""
        assert self.engine.is_asset_compliant('BTC')
        assert self.engine.is_asset_compliant('XRP')
        assert self.engine.is_asset_compliant('USDC')
        assert not self.engine.is_asset_compliant('SHIB')

    def test_filter_compliant_pairs(self):
        """Filter should remove non-compliant pairs"""
        pairs = ['XRP/USDC', 'BTC/USDT', 'ADA/USDC', 'SHIB/USDT']
        result = self.engine.filter_compliant_pairs(pairs)
        assert 'XRP/USDC' in result
        assert 'ADA/USDC' in result
        assert 'BTC/USDT' not in result
        assert 'SHIB/USDT' not in result

    def test_validate_opportunity_compliant(self):
        """Valid opportunity should pass"""
        assert self.engine.validate_opportunity({'pair': 'XRP/USDC'})

    def test_validate_opportunity_non_compliant(self):
        """Non-compliant opportunity should raise"""
        from compliance import ComplianceViolationError
        with pytest.raises(ComplianceViolationError):
            self.engine.validate_opportunity({'pair': 'BTC/USDT'})

    def test_compliance_report(self):
        """Report should contain expected keys"""
        report = self.engine.get_compliance_report()
        assert 'compliant_assets' in report
        assert 'compliant_stablecoins' in report
        assert 'compliant_pairs' in report
        assert report['status'] == 'ACTIVE'

    def test_strict_mode_excludes_btc_eth(self):
        """Non-personal deployment should exclude BTC/ETH"""
        from compliance import MiCAComplianceEngine
        strict = MiCAComplianceEngine(personal_deployment=False)
        assert not strict.is_asset_compliant('BTC')
        assert not strict.is_asset_compliant('ETH')
        assert strict.is_asset_compliant('XRP')

    def test_singleton(self):
        """get_compliance_engine should return singleton"""
        import compliance
        compliance._compliance_engine = None
        from compliance import get_compliance_engine
        e1 = get_compliance_engine()
        e2 = get_compliance_engine()
        assert e1 is e2

    def test_stablecoin_to_stablecoin(self):
        """USDC/RLUSD pair should be compliant"""
        assert self.engine.is_pair_compliant('USDC/RLUSD')
        assert self.engine.is_pair_compliant('RLUSD/USDC')


# ── Monitoring ─────────────────────────────────────────────────────────────

class TestAlertManager:
    """Tests for src/monitoring.py AlertManager"""

    def setup_method(self):
        from monitoring import AlertManager
        self.am = AlertManager()

    def test_initialization(self):
        assert self.am.alerts_enabled
        assert self.am.cooldown_period == 300

    def test_format_alert_message(self):
        msg = self.am._format_alert_message('warning', 'Test Title', 'Test message', {'key': 'value'})
        assert 'Test Title' in msg
        assert 'Test message' in msg
        assert 'key: value' in msg
        assert 'WARNING' in msg

    def test_format_alert_message_no_details(self):
        msg = self.am._format_alert_message('critical', 'Title', 'Body')
        assert 'CRITICAL' in msg
        assert 'Title' in msg

    def test_cooldown(self):
        """Alert cooldown should prevent duplicate alerts"""
        async def run():
            # First alert should go through
            self.am.alert_cooldowns = {}
            await self.am.send_alert('warning', 'Test', 'msg1')
            assert 'warning:Test' in self.am.alert_cooldowns

            # Second alert with same key should be in cooldown
            first_time = self.am.alert_cooldowns['warning:Test']
            await self.am.send_alert('warning', 'Test', 'msg2')
            # Time should not have changed (cooldown blocked it)
            assert self.am.alert_cooldowns['warning:Test'] == first_time

        asyncio.run(run())

    def test_alerts_disabled(self):
        """Disabled alerts should not send"""
        async def run():
            self.am.alerts_enabled = False
            await self.am.send_alert('critical', 'Test', 'msg')
            # No cooldown entry should be created
            assert len(self.am.alert_cooldowns) == 0

        asyncio.run(run())

    def test_send_heartbeat(self):
        """Heartbeat should not raise"""
        async def run():
            await self.am.send_heartbeat()

        asyncio.run(run())

    def test_alert_critical_error(self):
        """Critical error alert should not raise"""
        async def run():
            await self.am.alert_critical_error(RuntimeError("test"), context="unit test")

        asyncio.run(run())

    def test_alert_risk_limit_breached(self):
        """Risk limit breach alerts"""
        async def run():
            await self.am.alert_risk_limit_breached('daily_loss_limit', 0.06, 0.05)

        asyncio.run(run())

    def test_alert_trading_anomaly(self):
        """Trading anomaly alert should not raise"""
        async def run():
            await self.am.alert_trading_anomaly('flash_crash', {'pair': 'BTC/USDC'})

        asyncio.run(run())


# ── Risk Management (consolidated module) ──────────────────────────────────

class TestRiskManager:
    """Tests for src/risk_management.py — RiskManager class"""

    def setup_method(self):
        import risk_management
        risk_management._risk_manager = None
        from risk_management import RiskLimits, RiskManager
        self.rm = RiskManager(initial_capital=10000.0)

    def test_initialization(self):
        assert self.rm.initial_capital == 10000.0
        assert self.rm.current_capital == 10000.0
        assert len(self.rm.positions) == 0

    def test_validate_opportunity_valid(self):
        opp = {
            'pair': 'XRP/USDC',
            'exchanges': ['binance', 'coinbase'],
            'prices': {'binance': 1.0, 'coinbase': 1.003},
            'spread_prediction': 0.003,
        }
        assert self.rm.validate_opportunity(opp)

    def test_validate_opportunity_low_spread(self):
        opp = {
            'pair': 'XRP/USDC',
            'exchanges': ['binance', 'coinbase'],
            'prices': {'binance': 1.0, 'coinbase': 1.0005},
            'spread_prediction': 0.0005,
        }
        assert not self.rm.validate_opportunity(opp)

    def test_validate_opportunity_max_positions(self):
        """Should reject when max positions reached"""
        from risk_management import Position
        for i in range(5):
            self.rm.positions[f'PAIR{i}/USDC'] = Position(
                pair=f'PAIR{i}/USDC', exchange='binance', side='buy',
                size=1.0, entry_price=100.0, current_price=100.0,
                stop_loss=99.0, take_profit=101.0, timestamp=datetime.now()
            )
        opp = {
            'pair': 'NEW/USDC',
            'exchanges': ['binance', 'coinbase'],
            'prices': {'binance': 1.0, 'coinbase': 1.003},
            'spread_prediction': 0.003,
        }
        assert not self.rm.validate_opportunity(opp)

    def test_validate_opportunity_duplicate_pair(self):
        """Should reject if position already exists for pair"""
        from risk_management import Position
        self.rm.positions['XRP/USDC'] = Position(
            pair='XRP/USDC', exchange='binance', side='buy',
            size=1.0, entry_price=1.0, current_price=1.0,
            stop_loss=0.99, take_profit=1.01, timestamp=datetime.now()
        )
        opp = {
            'pair': 'XRP/USDC',
            'exchanges': ['binance', 'coinbase'],
            'prices': {'binance': 1.0, 'coinbase': 1.003},
            'spread_prediction': 0.003,
        }
        assert not self.rm.validate_opportunity(opp)

    def test_calculate_position_size(self):
        opp = {
            'pair': 'BTC/USDC',
            'prices': {'binance': 50000, 'coinbase': 50250},
            'spread_prediction': 0.005,
            'risk_score': 0.2,
            'confidence': 0.8,
        }
        size = self.rm.calculate_position_size(opp)
        assert size >= 0

    def test_calculate_position_size_no_kelly(self):
        opp = {
            'pair': 'BTC/USDC',
            'prices': {'binance': 50000, 'coinbase': 50250},
            'spread_prediction': 0.005,
            'risk_score': 0.2,
            'confidence': 0.8,
        }
        size = self.rm.calculate_position_size(opp, use_kelly=False)
        assert size >= 0

    def test_open_and_close_position(self):
        opp = {
            'pair': 'ADA/USDC',
            'exchanges': ['binance', 'coinbase'],
            'prices': {'binance': 1.50, 'coinbase': 1.505},
            'spread_prediction': 0.003,
            'risk_score': 0.1,
            'confidence': 0.8,
        }
        pos = self.rm.open_position(opp)
        assert pos is not None
        assert 'ADA/USDC' in self.rm.positions

        closed = self.rm.close_position('ADA/USDC', 1.51, reason='take_profit')
        assert closed
        assert 'ADA/USDC' not in self.rm.positions
        assert len(self.rm.trade_history) == 1

    def test_close_nonexistent_position(self):
        assert not self.rm.close_position('FAKE/USDC', 100.0)

    def test_check_stop_losses(self):
        from risk_management import Position
        self.rm.positions['XRP/USDC'] = Position(
            pair='XRP/USDC', exchange='binance', side='buy',
            size=100.0, entry_price=1.0, current_price=1.0,
            stop_loss=0.95, take_profit=1.05, timestamp=datetime.now()
        )
        # Price drops below stop loss
        closed = self.rm.check_stop_losses({'XRP/USDC': 0.94})
        assert 'XRP/USDC' in closed

    def test_check_take_profit(self):
        from risk_management import Position
        self.rm.positions['ADA/USDC'] = Position(
            pair='ADA/USDC', exchange='binance', side='buy',
            size=100.0, entry_price=1.0, current_price=1.0,
            stop_loss=0.95, take_profit=1.05, timestamp=datetime.now()
        )
        closed = self.rm.check_stop_losses({'ADA/USDC': 1.06})
        assert 'ADA/USDC' in closed

    def test_portfolio_status(self):
        status = self.rm.get_portfolio_status()
        assert 'portfolio_value' in status
        assert 'open_positions' in status
        assert status['open_positions'] == 0

    def test_emergency_stop(self):
        from risk_management import Position
        self.rm.positions['XRP/USDC'] = Position(
            pair='XRP/USDC', exchange='binance', side='buy',
            size=100.0, entry_price=1.0, current_price=1.0,
            stop_loss=0.95, take_profit=1.05, timestamp=datetime.now()
        )
        count = self.rm.emergency_stop()
        assert count == 1
        assert len(self.rm.positions) == 0

    def test_kelly_metrics(self):
        opp = {
            'pair': 'BTC/USDC',
            'prices': {'binance': 50000, 'coinbase': 50250},
            'spread_prediction': 0.005,
            'risk_score': 0.2,
            'confidence': 0.8,
        }
        metrics = self.rm.calculate_kelly_metrics(opp)
        assert 'win_probability' in metrics
        assert 'kelly_fraction' in metrics
        assert 'expected_value_per_trade' in metrics

    def test_singleton(self):
        import risk_management
        risk_management._risk_manager = None
        from risk_management import get_risk_manager
        rm1 = get_risk_manager()
        rm2 = get_risk_manager()
        assert rm1 is rm2

    def test_aliases(self):
        from risk_management import (
            RiskManagementEngine,
            RiskManager,
            get_risk_management_engine,
            get_risk_manager,
        )
        assert RiskManagementEngine is RiskManager
        assert get_risk_management_engine is get_risk_manager


class TestTradingRiskManager:
    """Tests for src/risk_management.py — TradingRiskManager class"""

    def setup_method(self):
        from risk_management import TradingRiskManager
        self.trm = TradingRiskManager()

    def test_default_config(self):
        assert self.trm.portfolio_value == 10000.0
        assert self.trm.max_daily_loss == 0.05
        assert self.trm.max_open_positions == 3

    def test_custom_config(self):
        from risk_management import TradingRiskManager
        trm = TradingRiskManager({'initial_capital': 50000.0, 'max_daily_loss': 0.03,
                                   'max_single_trade': 0.01, 'max_open_positions': 5,
                                   'max_drawdown': 0.08, 'kelly_fraction': 0.25,
                                   'stop_loss_pct': 0.003, 'take_profit_pct': 0.008,
                                   'min_arbitrage_spread': 0.002, 'max_slippage': 0.001,
                                   'volatility_lookback': 30, 'risk_free_rate': 0.03})
        assert trm.portfolio_value == 50000.0
        assert trm.max_daily_loss == 0.03

    def test_calculate_position_size_approved(self):
        opp = {'spread_percentage': 0.005, 'confidence': 0.8, 'symbol': 'BTC/USDC', 'entry_price': 50000}
        result = self.trm.calculate_position_size(opp)
        assert result['approved']
        assert result['position_value'] > 0
        assert result['quantity'] > 0

    def test_calculate_position_size_spread_too_low(self):
        opp = {'spread_percentage': 0.0005, 'confidence': 0.8, 'symbol': 'BTC/USDC', 'entry_price': 50000}
        result = self.trm.calculate_position_size(opp)
        assert not result['approved']

    def test_can_open_position_respects_daily_loss(self):
        self.trm.daily_pnl = -600  # Exceeds 5% of 10000
        opp = {'spread_percentage': 0.005, 'confidence': 0.8, 'symbol': 'BTC/USDC', 'entry_price': 50000}
        result = self.trm.calculate_position_size(opp)
        assert not result['approved']

    def test_can_open_position_respects_max_positions(self):
        for i in range(3):
            self.trm.open_positions[f'pos_{i}'] = {'symbol': f'PAIR{i}/USDC'}
        opp = {'spread_percentage': 0.005, 'confidence': 0.8, 'symbol': 'BTC/USDC', 'entry_price': 50000}
        result = self.trm.calculate_position_size(opp)
        assert not result['approved']

    def test_open_close_position_lifecycle(self):
        pos = self.trm.open_position({
            'symbol': 'XRP/USDC', 'side': 'buy', 'quantity': 100,
            'entry_price': 1.0, 'position_value': 100.0,
            'stop_loss': 0.995, 'take_profit': 1.01,
        })
        assert pos['status'] == 'open'
        pos_id = pos['id']

        closed = self.trm.close_position(pos_id, 1.005, 'take_profit')
        assert closed is not None
        assert closed['pnl'] == pytest.approx(0.5, abs=0.01)
        assert pos_id not in self.trm.open_positions

    def test_close_nonexistent_position(self):
        assert self.trm.close_position('fake_id', 100.0) is None

    def test_check_stop_loss_trigger(self):
        self.trm.open_position({
            'symbol': 'XRP/USDC', 'side': 'buy', 'quantity': 100,
            'entry_price': 1.0, 'position_value': 100.0,
            'stop_loss': 0.995, 'take_profit': 1.01,
        })
        triggered = self.trm.check_stop_loss_take_profit({'XRP/USDC': 0.99})
        assert len(triggered) == 1
        assert triggered[0]['exit_reason'] == 'stop_loss'

    def test_check_take_profit_trigger(self):
        self.trm.open_position({
            'symbol': 'ADA/USDC', 'side': 'buy', 'quantity': 100,
            'entry_price': 1.0, 'position_value': 100.0,
            'stop_loss': 0.995, 'take_profit': 1.01,
        })
        triggered = self.trm.check_stop_loss_take_profit({'ADA/USDC': 1.02})
        assert len(triggered) == 1
        assert triggered[0]['exit_reason'] == 'take_profit'

    def test_risk_metrics(self):
        metrics = self.trm.get_risk_metrics()
        assert 'portfolio_value' in metrics
        assert 'sharpe_ratio' in metrics
        assert 'risk_limits' in metrics

    def test_reset_daily_stats(self):
        self.trm.daily_pnl = 500.0
        self.trm.daily_trades = 10
        self.trm.reset_daily_stats()
        assert self.trm.daily_pnl == 0.0
        assert self.trm.daily_trades == 0

    def test_emergency_stop(self):
        self.trm.open_position({
            'symbol': 'XRP/USDC', 'side': 'buy', 'quantity': 100,
            'entry_price': 1.0, 'position_value': 100.0,
            'stop_loss': 0.995, 'take_profit': 1.01,
        })
        self.trm.open_position({
            'symbol': 'ADA/USDC', 'side': 'buy', 'quantity': 200,
            'entry_price': 0.5, 'position_value': 100.0,
            'stop_loss': 0.495, 'take_profit': 0.51,
        })
        closed = self.trm.emergency_stop()
        assert len(closed) == 2
        assert len(self.trm.open_positions) == 0

    def test_drawdown_tracking(self):
        pos = self.trm.open_position({
            'symbol': 'XRP/USDC', 'side': 'buy', 'quantity': 1000,
            'entry_price': 1.0, 'position_value': 1000.0,
            'stop_loss': 0.9, 'take_profit': 1.1,
        })
        # Close at a loss
        self.trm.close_position(pos['id'], 0.95, 'stop_loss')
        assert self.trm.current_drawdown > 0

    def test_asset_config_known(self):
        cfg = self.trm._get_asset_config('BTC/USDC')
        assert cfg['volatility'] == 0.03

    def test_asset_config_unknown(self):
        cfg = self.trm._get_asset_config('UNKNOWN/USDC')
        assert cfg['volatility'] == 0.05  # default


class TestArbitrageRiskAssessor:
    """Tests for src/risk_management.py — ArbitrageRiskAssessor"""

    def setup_method(self):
        from risk_management import ArbitrageRiskAssessor, TradingRiskManager
        self.trm = TradingRiskManager()
        self.assessor = ArbitrageRiskAssessor(self.trm)

    def test_assess_low_risk(self):
        signal = {'spread_percentage': 0.02, 'confidence': 0.9, 'position_size_pct': 0.01}
        market = {'volatility': 0.01, 'exchanges': {'binance': {'volume': 1000}, 'coinbase': {'volume': 1000}}}
        result = self.assessor.assess_arbitrage_risk(signal, market)
        assert result['approved']
        assert result['overall_risk_score'] < 0.6

    def test_assess_high_risk(self):
        signal = {'spread_percentage': 0.001, 'confidence': 0.3, 'position_size_pct': 0.1}
        market = {'volatility': 0.08, 'exchanges': {'binance': {'volume': 50}}}
        result = self.assessor.assess_arbitrage_risk(signal, market)
        assert not result['approved']
        assert result['overall_risk_score'] > 0.6

    def test_recommendations_generated(self):
        signal = {'spread_percentage': 0.001, 'confidence': 0.3, 'position_size_pct': 0.1}
        market = {'volatility': 0.08, 'exchanges': {'binance': {'volume': 50}}}
        result = self.assessor.assess_arbitrage_risk(signal, market)
        assert len(result['recommendations']) > 0

    def test_create_default_risk_manager(self):
        from risk_management import create_default_risk_manager
        trm = create_default_risk_manager()
        assert trm.portfolio_value == 10000.0


# ── Live Arbitrage Pipeline ────────────────────────────────────────────────

class TestLiveArbitragePipeline:
    """Tests for src/live_arbitrage_pipeline.py"""

    def test_arbitrage_opportunity_dataclass(self):
        from live_arbitrage_pipeline import ArbitrageOpportunity
        opp = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.8,
            confidence=0.9, spread_prediction=0.005,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.005},
            volumes={'binance': 1000, 'coinbase': 1000},
            risk_score=0.2, profit_potential=5.0,
        )
        assert opp.pair == 'XRP/USDC'
        assert opp.probability == 0.8

    def test_filtered_opportunity_defaults(self):
        from live_arbitrage_pipeline import ArbitrageOpportunity, FilteredOpportunity
        opp = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.8,
            confidence=0.9, spread_prediction=0.005,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.005},
            volumes={'binance': 1000, 'coinbase': 1000},
            risk_score=0.2, profit_potential=5.0,
        )
        fo = FilteredOpportunity(opportunity=opp)
        assert fo.alerts == []
        assert fo.timestamp is not None
        assert fo.recommended_action == 'Monitor'

    def test_opportunity_filter_passes_good_opportunity(self):
        from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
        f = OpportunityFilter(min_probability=0.5, min_spread=0.001, max_risk_score=0.7)
        opp = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.8,
            confidence=0.9, spread_prediction=0.005,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.005},
            volumes={'binance': 1000, 'coinbase': 1000},
            risk_score=0.2, profit_potential=5.0,
        )
        result = f.filter_opportunity(opp)
        assert result is not None
        assert result.recommended_action == 'Execute'

    def test_opportunity_filter_rejects_low_probability(self):
        from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
        f = OpportunityFilter(min_probability=0.5)
        opp = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.3,
            confidence=0.9, spread_prediction=0.005,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.005},
            volumes={'binance': 1000, 'coinbase': 1000},
            risk_score=0.2, profit_potential=5.0,
        )
        assert f.filter_opportunity(opp) is None

    def test_opportunity_filter_rejects_high_risk(self):
        from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
        f = OpportunityFilter(max_risk_score=0.7)
        opp = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.8,
            confidence=0.9, spread_prediction=0.005,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.005},
            volumes={'binance': 1000, 'coinbase': 1000},
            risk_score=0.9, profit_potential=5.0,
        )
        assert f.filter_opportunity(opp) is None

    def test_opportunity_filter_rejects_low_spread(self):
        from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
        f = OpportunityFilter(min_spread=0.001)
        opp = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.8,
            confidence=0.9, spread_prediction=0.0005,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.005},
            volumes={'binance': 1000, 'coinbase': 1000},
            risk_score=0.2, profit_potential=5.0,
        )
        assert f.filter_opportunity(opp) is None

    def test_filter_stats(self):
        from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
        f = OpportunityFilter()
        good = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.8,
            confidence=0.9, spread_prediction=0.005,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.005},
            volumes={'binance': 1000, 'coinbase': 1000},
            risk_score=0.2, profit_potential=5.0,
        )
        bad = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.1,
            confidence=0.2, spread_prediction=0.0001,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.0001},
            volumes={'binance': 10, 'coinbase': 10},
            risk_score=0.9, profit_potential=0.01,
        )
        f.filter_opportunity(good)
        f.filter_opportunity(bad)
        stats = f.get_filter_stats()
        assert stats['passed'] == 1
        assert stats['filtered'] == 1
        assert stats['total_processed'] == 2

    def test_large_spread_alert(self):
        """Large spreads should generate alert"""
        from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
        f = OpportunityFilter()
        opp = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.8,
            confidence=0.9, spread_prediction=0.01,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.01},
            volumes={'binance': 1000, 'coinbase': 1000},
            risk_score=0.2, profit_potential=10.0,
        )
        result = f.filter_opportunity(opp)
        assert 'Large spread detected' in result.alerts

    def test_low_liquidity_alert(self):
        """Low volume should generate liquidity alert"""
        from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
        f = OpportunityFilter()
        opp = ArbitrageOpportunity(
            pair='XRP/USDC', timestamp=time.time(), probability=0.8,
            confidence=0.9, spread_prediction=0.005,
            exchanges=['binance', 'coinbase'],
            prices={'binance': 1.0, 'coinbase': 1.005},
            volumes={'binance': 10, 'coinbase': 10},
            risk_score=0.2, profit_potential=5.0,
        )
        result = f.filter_opportunity(opp)
        assert 'Low liquidity' in result.alerts

    def test_mock_classes_exist(self):
        from live_arbitrage_pipeline import (
            MockAlertSystem,
            MockDataService,
            MockInferenceService,
            MockRiskManager,
        )
        ds = MockDataService()
        assert 'binance' in ds.data_sources
        ds.add_data_callback(lambda x: None)
        assert ds.get_service_status()['is_running']

        inf = MockInferenceService()
        inf.add_opportunity_callback(lambda x: None)
        assert inf.get_service_status()['is_running']

        rm = MockRiskManager()
        assert rm.validate_opportunity(None)

    def test_pipeline_initialization_development(self):
        from live_arbitrage_pipeline import LiveArbitragePipeline
        pipeline = LiveArbitragePipeline({'mode': 'development'})
        assert not pipeline.is_running
        assert pipeline.mode == 'development'
        assert pipeline.stats['opportunities_detected'] == 0

    def test_pipeline_status(self):
        from live_arbitrage_pipeline import LiveArbitragePipeline
        pipeline = LiveArbitragePipeline({'mode': 'development'})
        status = pipeline.get_pipeline_status()
        assert 'is_running' in status
        assert 'stats' in status
        assert status['mode'] == 'development'

    def test_pipeline_invalid_mode_raises(self):
        from live_arbitrage_pipeline import LiveArbitragePipeline
        with pytest.raises(ValueError, match="Invalid pipeline mode"):
            LiveArbitragePipeline({'mode': 'invalid'})

    def test_pipeline_default_mode_is_development(self):
        from live_arbitrage_pipeline import LiveArbitragePipeline
        pipeline = LiveArbitragePipeline({})
        assert pipeline.mode == 'development'


class TestPipelineReadiness:
    """Tests for pipeline readiness checks and production/development mode enforcement."""

    def test_development_mode_readiness_with_mocks(self):
        """Development mode should be ready even with mock services."""
        from live_arbitrage_pipeline import LiveArbitragePipeline
        pipeline = LiveArbitragePipeline({'mode': 'development'})
        check = pipeline.get_readiness_check()
        assert check['ready']
        assert check['mode'] == 'development'
        assert len(check['errors']) == 0
        # Should have warnings about mock services
        assert len(check['warnings']) > 0

    def test_development_mode_identifies_service_types(self):
        """Readiness check should report service types correctly."""
        from live_arbitrage_pipeline import LiveArbitragePipeline
        pipeline = LiveArbitragePipeline({'mode': 'development'})
        check = pipeline.get_readiness_check()
        # Every service should have a type field
        for name, info in check['services'].items():
            assert 'type' in info, f"Service {name} missing 'type'"
            assert info['type'] in ('real', 'mock', 'disabled'), f"Unexpected type for {name}: {info['type']}"

    def test_production_mode_rejects_missing_data_service(self):
        """Production mode should raise if HybridDataIntegrationService is unavailable."""
        from live_arbitrage_pipeline import LiveArbitragePipeline, ServiceInitError
        with patch.dict('sys.modules', {'data_integration_service': None}):
            with pytest.raises(ServiceInitError, match="HybridDataIntegrationService"):
                LiveArbitragePipeline({'mode': 'production'})

    def test_production_mode_rejects_missing_inference(self):
        """Production mode should raise if RealTimeInferenceService is unavailable."""
        from live_arbitrage_pipeline import LiveArbitragePipeline, ServiceInitError
        # Mock the data service to pass, but block inference
        with patch('live_arbitrage_pipeline.LiveArbitragePipeline._init_data_service') as mock_ds:
            mock_ds.return_value = MagicMock()
            with patch.dict('sys.modules', {'realtime_inference': None}):
                with pytest.raises(ServiceInitError, match="RealTimeInferenceService"):
                    LiveArbitragePipeline({'mode': 'production'})

    def test_service_init_error_is_exception(self):
        """ServiceInitError should be a proper exception."""
        from live_arbitrage_pipeline import ServiceInitError
        assert issubclass(ServiceInitError, Exception)
        err = ServiceInitError("test error")
        assert str(err) == "test error"


class TestPipelineLifecycle:
    """Tests for pipeline start/stop lifecycle."""

    def test_start_stop_development_mode(self):
        """Pipeline should start and stop cleanly in development mode."""
        from live_arbitrage_pipeline import LiveArbitragePipeline

        async def run():
            pipeline = LiveArbitragePipeline({'mode': 'development'})
            assert not pipeline.is_running
            await pipeline.start()
            assert pipeline.is_running
            await pipeline.stop()
            assert not pipeline.is_running

        asyncio.run(run())

    def test_double_start_warns(self):
        """Starting an already-running pipeline should warn, not crash."""
        from live_arbitrage_pipeline import LiveArbitragePipeline

        async def run():
            pipeline = LiveArbitragePipeline({'mode': 'development'})
            await pipeline.start()
            # Second start should just warn
            await pipeline.start()
            assert pipeline.is_running
            await pipeline.stop()

        asyncio.run(run())

    def test_double_stop_warns(self):
        """Stopping a non-running pipeline should warn, not crash."""
        from live_arbitrage_pipeline import LiveArbitragePipeline

        async def run():
            pipeline = LiveArbitragePipeline({'mode': 'development'})
            # Stop without starting should just warn
            await pipeline.stop()
            assert not pipeline.is_running

        asyncio.run(run())

    def test_start_wires_callbacks(self):
        """After start, mock services should have callbacks registered."""
        from live_arbitrage_pipeline import (
            LiveArbitragePipeline,
            MockDataService,
            MockInferenceService,
        )

        async def run():
            pipeline = LiveArbitragePipeline({'mode': 'development'})
            await pipeline.start()
            # Check that callbacks were added
            if isinstance(pipeline.data_service, MockDataService):
                assert len(pipeline.data_service._callbacks) > 0
            if isinstance(pipeline.inference_service, MockInferenceService):
                assert len(pipeline.inference_service._callbacks) > 0
            await pipeline.stop()

        asyncio.run(run())

    def test_handle_opportunity_increments_stats(self):
        """_handle_opportunity should increment stats."""
        from live_arbitrage_pipeline import ArbitrageOpportunity, LiveArbitragePipeline

        async def run():
            pipeline = LiveArbitragePipeline({'mode': 'development'})
            opp = ArbitrageOpportunity(
                pair='XRP/USDC', timestamp=time.time(), probability=0.8,
                confidence=0.9, spread_prediction=0.005,
                exchanges=['binance', 'coinbase'],
                prices={'binance': 1.0, 'coinbase': 1.005},
                volumes={'binance': 1000, 'coinbase': 1000},
                risk_score=0.2, profit_potential=5.0,
            )
            await pipeline._handle_opportunity(opp)
            assert pipeline.stats['opportunities_detected'] == 1

        asyncio.run(run())


# ── Order Executor ─────────────────────────────────────────────────────────

class TestOrderExecutorValidation:
    """Tests for src/order_executor.py — validation and stats logic (no exchange connections)"""

    def test_validate_missing_fields(self):
        """Missing required fields should fail validation"""
        from order_executor import OrderExecutor
        # Create executor with no exchanges (will fail init gracefully)
        executor = OrderExecutor.__new__(OrderExecutor)
        executor.exchanges = {}
        executor.active_orders = {}
        executor.order_history = []
        executor.execution_stats = executor._init_execution_stats()
        executor.risk_manager = None

        opp = {'symbol': 'BTC/USDC'}  # Missing buy_exchange, sell_exchange, etc.
        assert not executor._validate_arbitrage_opportunity(opp)

    def test_validate_low_spread(self):
        """Spread below fees should fail"""
        from order_executor import OrderExecutor
        executor = OrderExecutor.__new__(OrderExecutor)
        executor.exchanges = {'binance': Mock(), 'coinbase': Mock()}

        opp = {
            'symbol': 'BTC/USDC', 'buy_exchange': 'binance',
            'sell_exchange': 'coinbase', 'spread_percentage': 0.0005,
            'quantity': 0.01,
        }
        assert not executor._validate_arbitrage_opportunity(opp)

    def test_validate_exchange_not_available(self):
        """Missing exchange should fail"""
        from order_executor import OrderExecutor
        executor = OrderExecutor.__new__(OrderExecutor)
        executor.exchanges = {'binance': Mock()}

        opp = {
            'symbol': 'BTC/USDC', 'buy_exchange': 'binance',
            'sell_exchange': 'coinbase', 'spread_percentage': 0.005,
            'quantity': 0.01,
        }
        assert not executor._validate_arbitrage_opportunity(opp)

    def test_validate_valid_opportunity(self):
        """Valid opportunity should pass"""
        from order_executor import OrderExecutor
        executor = OrderExecutor.__new__(OrderExecutor)
        executor.exchanges = {'binance': Mock(), 'coinbase': Mock()}

        opp = {
            'symbol': 'BTC/USDC', 'buy_exchange': 'binance',
            'sell_exchange': 'coinbase', 'spread_percentage': 0.005,
            'quantity': 0.01,
        }
        assert executor._validate_arbitrage_opportunity(opp)

    def test_execution_stats_init(self):
        from order_executor import OrderExecutor
        executor = OrderExecutor.__new__(OrderExecutor)
        stats = executor._init_execution_stats()
        assert stats['total_orders'] == 0
        assert stats['success_rate'] == 0.0

    def test_execution_stats_update(self):
        from order_executor import OrderExecutor
        executor = OrderExecutor.__new__(OrderExecutor)
        executor.execution_stats = executor._init_execution_stats()

        result = {'success': True, 'execution_time': 0.5}
        executor._update_execution_stats(result)
        assert executor.execution_stats['total_orders'] == 2
        assert executor.execution_stats['successful_orders'] == 2

    def test_paper_trading_balance(self):
        """Paper trading should track balances"""
        from order_executor import PaperTradingExecutor
        # Bypass real exchange init
        with patch('order_executor.OrderExecutor._init_exchanges'):
            executor = PaperTradingExecutor({'binance': {}, 'coinbase': {}}, initial_balance=10000.0)
            balance = executor.get_paper_balance('binance')
            assert balance['USDC'] == 10000.0

    def test_paper_trading_update_balance_buy(self):
        """Paper trading buy should deduct quote and add base"""
        from order_executor import PaperTradingExecutor
        with patch('order_executor.OrderExecutor._init_exchanges'):
            executor = PaperTradingExecutor({'binance': {}}, initial_balance=10000.0)
            executor._update_paper_balance('binance', 'XRP/USDC', 'buy', 100, 1.0, 0.1)
            balance = executor.get_paper_balance('binance')
            assert balance['XRP'] == 100
            assert balance['USDC'] < 10000.0

    def test_paper_trading_update_balance_sell(self):
        """Paper trading sell should deduct base and add quote"""
        from order_executor import PaperTradingExecutor
        with patch('order_executor.OrderExecutor._init_exchanges'):
            executor = PaperTradingExecutor({'binance': {}}, initial_balance=10000.0)
            # First buy some XRP
            executor._update_paper_balance('binance', 'XRP/USDC', 'buy', 100, 1.0, 0.1)
            # Then sell it
            executor._update_paper_balance('binance', 'XRP/USDC', 'sell', 50, 1.05, 0.05)
            balance = executor.get_paper_balance('binance')
            assert balance['XRP'] == 50

    def test_paper_orders_tracked(self):
        """Paper orders should be tracked"""
        from order_executor import PaperTradingExecutor
        with patch('order_executor.OrderExecutor._init_exchanges'):
            executor = PaperTradingExecutor({'binance': {}}, initial_balance=10000.0)

            async def run():
                result = await executor._execute_single_order('binance', 'XRP/USDC', 'buy', 100, 1.0)
                assert result['success']
                orders = executor.get_paper_orders()
                assert len(orders) == 1

            asyncio.run(run())

    def test_health_check_no_exchanges(self):
        """Health check with no exchanges should return False"""
        from order_executor import OrderExecutor
        executor = OrderExecutor.__new__(OrderExecutor)
        executor.exchanges = {}

        async def run():
            return await executor.is_healthy()

        assert not asyncio.run(run())


# ── MICA Compliant Pairs ──────────────────────────────────────────────────

class TestMiCACompliantPairs:
    """Verify the MICA_COMPLIANT_PAIRS constant"""

    def test_no_usdt_in_compliant_pairs(self):
        from live_arbitrage_pipeline import MICA_COMPLIANT_PAIRS
        for pair in MICA_COMPLIANT_PAIRS:
            assert 'USDT' not in pair, f"USDT found in compliant pair: {pair}"

    def test_all_pairs_have_usdc_or_rlusd(self):
        from live_arbitrage_pipeline import MICA_COMPLIANT_PAIRS
        for pair in MICA_COMPLIANT_PAIRS:
            quote = pair.split('/')[1]
            assert quote in ('USDC', 'RLUSD'), f"Unexpected quote currency in {pair}"


# ── Pre-Trade Balance Checks ─────────────────────────────────────────────

class TestPreTradeBalanceCheck:
    """Tests for order_executor.py pre-trade balance validation."""

    def test_balance_check_passes_sufficient_funds(self):
        """Should pass when both exchanges have enough funds."""
        from order_executor import OrderExecutor

        executor = OrderExecutor.__new__(OrderExecutor)
        executor.exchanges = {'binance': Mock(), 'coinbase': Mock()}

        # Mock get_account_balance
        executor.get_account_balance = Mock(side_effect=lambda name: {
            'total': {}, 'used': {},
            'free': {'USDC': 50000.0, 'BTC': 1.0},
            'timestamp': None,
        })

        trade_params = {
            'symbol': 'BTC/USDC', 'buy_exchange': 'binance',
            'sell_exchange': 'coinbase', 'quantity': 0.1,
            'buy_price': 50000.0, 'sell_price': 50250.0,
        }

        async def run():
            ok, err = await executor._check_sufficient_balance(trade_params)
            assert ok
            assert err == ''

        asyncio.run(run())

    def test_balance_check_fails_insufficient_quote(self):
        """Should fail when buy exchange lacks quote currency."""
        from order_executor import OrderExecutor

        executor = OrderExecutor.__new__(OrderExecutor)
        executor.exchanges = {'binance': Mock(), 'coinbase': Mock()}

        executor.get_account_balance = Mock(side_effect=lambda name: {
            'total': {}, 'used': {},
            'free': {'USDC': 100.0, 'BTC': 1.0},  # Only $100 USDC
            'timestamp': None,
        })

        trade_params = {
            'symbol': 'BTC/USDC', 'buy_exchange': 'binance',
            'sell_exchange': 'coinbase', 'quantity': 0.1,
            'buy_price': 50000.0, 'sell_price': 50250.0,
        }

        async def run():
            ok, err = await executor._check_sufficient_balance(trade_params)
            assert not ok
            assert 'Insufficient USDC' in err

        asyncio.run(run())

    def test_balance_check_fails_insufficient_base(self):
        """Should fail when sell exchange lacks base currency."""
        from order_executor import OrderExecutor

        executor = OrderExecutor.__new__(OrderExecutor)
        executor.exchanges = {'binance': Mock(), 'coinbase': Mock()}

        def mock_balance(name):
            if name == 'binance':
                return {'total': {}, 'used': {}, 'free': {'USDC': 50000.0}, 'timestamp': None}
            return {'total': {}, 'used': {}, 'free': {'BTC': 0.001}, 'timestamp': None}

        executor.get_account_balance = Mock(side_effect=mock_balance)

        trade_params = {
            'symbol': 'BTC/USDC', 'buy_exchange': 'binance',
            'sell_exchange': 'coinbase', 'quantity': 0.1,
            'buy_price': 50000.0, 'sell_price': 50250.0,
        }

        async def run():
            ok, err = await executor._check_sufficient_balance(trade_params)
            assert not ok
            assert 'Insufficient BTC' in err

        asyncio.run(run())

    def test_paper_trading_balance_check_insufficient_base(self):
        """PaperTradingExecutor should fail when sell exchange has no base asset."""
        from order_executor import PaperTradingExecutor

        with patch('order_executor.OrderExecutor._init_exchanges'):
            executor = PaperTradingExecutor(
                {'binance': {}, 'coinbase': {}}, initial_balance=10000.0
            )

        trade_params = {
            'symbol': 'XRP/USDC', 'buy_exchange': 'binance',
            'sell_exchange': 'coinbase', 'quantity': 100,
            'buy_price': 1.0, 'sell_price': 1.005,
        }

        async def run():
            # coinbase has 0 XRP, so sell-side check fails
            ok, err = await executor._check_sufficient_balance(trade_params)
            assert not ok
            assert 'Insufficient paper XRP' in err

        asyncio.run(run())

    def test_paper_trading_balance_check_sufficient(self):
        """PaperTradingExecutor should pass when both sides have funds."""
        from order_executor import PaperTradingExecutor

        with patch('order_executor.OrderExecutor._init_exchanges'):
            executor = PaperTradingExecutor(
                {'binance': {}, 'coinbase': {}}, initial_balance=10000.0
            )
            # Give coinbase some XRP
            executor.paper_balances['coinbase']['XRP'] = 500.0

        trade_params = {
            'symbol': 'XRP/USDC', 'buy_exchange': 'binance',
            'sell_exchange': 'coinbase', 'quantity': 100,
            'buy_price': 1.0, 'sell_price': 1.005,
        }

        async def run():
            ok, err = await executor._check_sufficient_balance(trade_params)
            assert ok
            assert err == ''

        asyncio.run(run())
