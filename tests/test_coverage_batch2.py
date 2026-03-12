"""
Test coverage expansion — batch 2.

Covers 8 previously untested modules that import cleanly without torch/GPU:
  cache_layer, monitoring, xactions, training_monitor,
  grok_reasoning, database, exchange_rate_limiter, websocket_validator

Run:
    PYTHONPATH=src python -m pytest tests/test_coverage_batch2.py -v --tb=short
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Modules under test ──────────────────────────────────────────────────
from cache_layer import (
    DEFAULT_TTL,
    CacheManager,
    LRUCache,
    RedisCache,
    get_cache,
)
from database import DatabaseManager
from exchange_rate_limiter import (
    ExchangeLimits,
    ExchangeRateLimiter,
    RateLimiterManager,
    TokenBucket,
)
from grok_reasoning import GrokReasoningEngine
from monitoring import AlertManager, MetricsCollector
from training_monitor import (
    GPUTrainingMonitor,
    TrainingAlert,
    TrainingMetrics,
    TrainingMonitor,
)
from websocket_validator import (
    DataQualityMetrics,
    ExchangeConnection,
    WebSocketMetrics,
    WebSocketValidator,
)
from xactions import (
    ArbitrageTransaction,
    TransactionLeg,
    TransactionManager,
    TransactionStatus,
    TransactionType,
)

# ── Helpers ──────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_legs(qty="0.001", buy_price="50000", sell_price="50100"):
    return [
        TransactionLeg(
            exchange="binance",
            symbol="XRP/USDC",
            side="buy",
            quantity=Decimal(qty),
            price=Decimal(buy_price),
        ),
        TransactionLeg(
            exchange="coinbase",
            symbol="XRP/USDC",
            side="sell",
            quantity=Decimal(qty),
            price=Decimal(sell_price),
        ),
    ]


# =========================================================================
# cache_layer — LRUCache
# =========================================================================

class TestLRUCache:

    def test_set_and_get(self):
        cache = LRUCache(max_size=16)
        _run(cache.set("k1", {"price": 42}, ttl=60))
        result = _run(cache.get("k1"))
        assert result == {"price": 42}
        assert cache.hits == 1

    def test_miss_returns_none(self):
        cache = LRUCache()
        result = _run(cache.get("nonexistent"))
        assert result is None
        assert cache.misses == 1

    def test_ttl_expiry(self):
        cache = LRUCache()
        _run(cache.set("k1", "v1", ttl=0))
        time.sleep(0.01)
        result = _run(cache.get("k1"))
        assert result is None

    def test_eviction_on_capacity(self):
        cache = LRUCache(max_size=2)
        _run(cache.set("a", 1, ttl=60))
        _run(cache.set("b", 2, ttl=60))
        _run(cache.set("c", 3, ttl=60))
        assert _run(cache.get("a")) is None  # evicted
        assert _run(cache.get("c")) == 3
        assert cache.evictions >= 1

    def test_delete(self):
        cache = LRUCache()
        _run(cache.set("k", "v", ttl=60))
        assert _run(cache.delete("k")) is True
        assert _run(cache.delete("k")) is False

    def test_clear(self):
        cache = LRUCache()
        _run(cache.set("a", 1, ttl=60))
        _run(cache.set("b", 2, ttl=60))
        _run(cache.clear())
        assert _run(cache.get("a")) is None

    def test_stats(self):
        cache = LRUCache(max_size=100)
        _run(cache.set("k", "v", ttl=60))
        _run(cache.get("k"))
        _run(cache.get("miss"))
        s = cache.stats()
        assert s["backend"] == "lru_memory"
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["size"] == 1
        assert 0.0 <= s["hit_rate"] <= 1.0

    def test_lru_order(self):
        cache = LRUCache(max_size=2)
        _run(cache.set("a", 1, ttl=60))
        _run(cache.set("b", 2, ttl=60))
        _run(cache.get("a"))  # access 'a' → 'b' is now LRU
        _run(cache.set("c", 3, ttl=60))
        assert _run(cache.get("b")) is None  # 'b' evicted
        assert _run(cache.get("a")) == 1


# =========================================================================
# cache_layer — RedisCache (offline mode)
# =========================================================================

class TestRedisCacheFallback:

    def test_get_when_unavailable(self):
        rc = RedisCache()
        result = _run(rc.get("anything"))
        assert result is None

    def test_set_when_unavailable(self):
        rc = RedisCache()
        _run(rc.set("k", "v"))  # should not raise

    def test_delete_when_unavailable(self):
        rc = RedisCache()
        assert _run(rc.delete("k")) is False

    def test_stats(self):
        rc = RedisCache()
        s = rc.stats()
        assert s["backend"] == "redis"
        assert s["available"] is False


# =========================================================================
# cache_layer — CacheManager (LRU-only mode)
# =========================================================================

class TestCacheManager:

    def test_set_and_get_via_lru(self):
        cm = CacheManager()
        _run(cm.connect())  # redis won't be available → LRU fallback
        _run(cm.set("market_data", "XRP/USDC:binance", {"bid": 0.5}))
        result = _run(cm.get("market_data", "XRP/USDC:binance"))
        assert result == {"bid": 0.5}

    def test_domain_ttl_defaults(self):
        cm = CacheManager()
        assert cm._ttl("market_data") == DEFAULT_TTL["market_data"]
        assert cm._ttl("unknown") == DEFAULT_TTL["default"]

    def test_cache_ticker_helper(self):
        cm = CacheManager()
        _run(cm.connect())
        _run(cm.cache_ticker("binance", "XRP/USDC", {"last": 0.6}))
        result = _run(cm.get_ticker("binance", "XRP/USDC"))
        assert result["last"] == 0.6

    def test_cache_prediction_helper(self):
        cm = CacheManager()
        _run(cm.connect())
        _run(cm.cache_prediction("XRP/USDC", {"signal": 0.9}))
        result = _run(cm.get_prediction("XRP/USDC"))
        assert result["signal"] == 0.9

    def test_delete(self):
        cm = CacheManager()
        _run(cm.connect())
        _run(cm.set("market_data", "k", "v"))
        _run(cm.delete("market_data", "k"))
        assert _run(cm.get("market_data", "k")) is None

    def test_stats(self):
        cm = CacheManager()
        s = cm.stats()
        assert "redis" in s
        assert "lru" in s

    def test_get_cache_singleton(self):
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2


# =========================================================================
# monitoring — AlertManager
# =========================================================================

class TestAlertManager:

    def test_init(self):
        am = AlertManager()
        assert am.alerts_enabled is True
        assert am.cooldown_period == 300

    def test_send_alert_no_webhook(self):
        am = AlertManager()
        am.slack_webhook = None
        _run(am.send_alert("warning", "Test", "msg"))

    def test_cooldown(self):
        am = AlertManager()
        am.slack_webhook = None
        am.cooldown_period = 9999
        _run(am.send_alert("info", "Title", "first call"))
        _run(am.send_alert("info", "Title", "second call — should be in cooldown"))
        # cooldown key exists
        assert "info:Title" in am.alert_cooldowns

    def test_format_alert_message(self):
        am = AlertManager()
        msg = am._format_alert_message("critical", "Down", "System down", {"node": "A"})
        assert "CRITICAL" in msg
        assert "Down" in msg
        assert "node: A" in msg

    def test_alerts_disabled(self):
        am = AlertManager()
        am.alerts_enabled = False
        _run(am.send_alert("critical", "X", "Y"))  # should not raise

    def test_send_heartbeat(self):
        am = AlertManager()
        am.slack_webhook = None
        _run(am.send_heartbeat())

    def test_alert_risk_limit(self):
        am = AlertManager()
        am.slack_webhook = None
        _run(am.alert_risk_limit_breached("daily_loss_limit", 500.0, 300.0))

    def test_alert_trading_anomaly(self):
        am = AlertManager()
        am.slack_webhook = None
        _run(am.alert_trading_anomaly("flash_crash", {"drop_pct": 15}))


# =========================================================================
# monitoring — MetricsCollector (prometheus not installed → graceful skip)
# =========================================================================

try:
    from prometheus_client import CollectorRegistry as _CR
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False

_skip_no_prometheus = pytest.mark.skipif(
    not _HAS_PROMETHEUS,
    reason="prometheus_client not available",
)


@_skip_no_prometheus
class TestMetricsCollector:

    def test_init_disabled(self):
        with patch.dict(os.environ, {"METRICS_ENABLED": "false"}):
            mc = MetricsCollector()
            assert mc.metrics_enabled is False

    def test_get_metrics_text_disabled(self):
        with patch.dict(os.environ, {"METRICS_ENABLED": "false"}):
            mc = MetricsCollector()
            assert mc.get_metrics_text() == ""


# =========================================================================
# xactions — TransactionLeg / ArbitrageTransaction dataclasses
# =========================================================================

class TestTransactionDataclasses:

    def test_transaction_leg_defaults(self):
        leg = TransactionLeg(
            exchange="binance", symbol="XRP/USDC", side="buy",
            quantity=Decimal("1"), price=Decimal("0.5"),
        )
        assert leg.status == TransactionStatus.PENDING
        assert leg.executed_quantity == Decimal("0")
        assert leg.fees == Decimal("0")

    def test_arbitrage_transaction_auto_timestamp(self):
        tx = ArbitrageTransaction(
            transaction_id="t1",
            transaction_type=TransactionType.SIMPLE_ARBITRAGE,
            legs=[],
            expected_profit=Decimal("10"),
            expected_profit_pct=0.5,
            risk_score=0.2,
        )
        assert tx.created_timestamp is not None
        assert tx.status == TransactionStatus.PENDING

    def test_transaction_status_values(self):
        assert TransactionStatus.PENDING.value == "pending"
        assert TransactionStatus.COMPLETED.value == "completed"
        assert TransactionStatus.FAILED.value == "failed"
        assert TransactionStatus.CANCELLED.value == "cancelled"
        assert TransactionStatus.TIMEOUT.value == "timeout"

    def test_transaction_type_values(self):
        assert TransactionType.SIMPLE_ARBITRAGE.value == "simple_arbitrage"
        assert TransactionType.TRIANGULAR_ARBITRAGE.value == "triangular_arbitrage"
        assert TransactionType.CROSS_EXCHANGE_ARBITRAGE.value == "cross_exchange_arbitrage"


# =========================================================================
# xactions — TransactionManager
# =========================================================================

class TestTransactionManager:

    def _make_manager(self, tmp_path):
        log_path = os.path.join(str(tmp_path), "tx.log")
        return TransactionManager(audit_log_path=log_path)

    def test_validate_structure_balanced(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        legs = _make_legs()
        assert mgr._validate_transaction_structure(legs) is True

    def test_validate_structure_unbalanced(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        legs = [
            TransactionLeg("ex", "XRP/USDC", "buy", Decimal("1"), Decimal("1")),
            TransactionLeg("ex", "XRP/USDC", "sell", Decimal("2"), Decimal("1")),
        ]
        assert mgr._validate_transaction_structure(legs) is False

    def test_validate_structure_too_few_legs(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        legs = [TransactionLeg("ex", "XRP/USDC", "buy", Decimal("1"), Decimal("1"))]
        assert mgr._validate_transaction_structure(legs) is False

    def test_check_risk_limits_pass(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr._check_risk_limits(Decimal("100"), 0.3) is True

    def test_check_risk_limits_high_risk(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr._check_risk_limits(Decimal("100"), 0.95) is False

    def test_check_risk_limits_low_profit(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr._check_risk_limits(Decimal("1"), 0.3) is False

    def test_concurrent_limit(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr.max_concurrent_transactions = 2
        mgr.active_transactions = {"a": None, "b": None}
        assert mgr._check_concurrent_limits() is False

    def test_calculate_transaction_value(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        legs = _make_legs()
        val = mgr._calculate_transaction_value(legs)
        assert val > Decimal("0")

    def test_create_transaction_mica_fallback(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        legs = _make_legs()
        tx = mgr.create_arbitrage_transaction(
            TransactionType.SIMPLE_ARBITRAGE, legs, Decimal("100"), 0.3,
        )
        assert tx is not None
        assert tx.compliance_check_passed is True
        assert tx.transaction_id in mgr.active_transactions

    def test_cancel_transaction(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        legs = _make_legs()
        tx = mgr.create_arbitrage_transaction(
            TransactionType.SIMPLE_ARBITRAGE, legs, Decimal("100"), 0.3,
        )
        assert tx is not None
        cancelled = mgr.cancel_transaction(tx.transaction_id, "test cancel")
        assert cancelled is True
        assert len(mgr.active_transactions) == 0
        assert len(mgr.completed_transactions) == 1

    def test_cancel_nonexistent(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.cancel_transaction("bogus") is False

    def test_get_transaction_stats(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        stats = mgr.get_transaction_stats()
        assert stats["total_transactions"] == 0
        assert stats["success_rate"] == 0.0

    def test_get_active_transactions(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.get_active_transactions() == []

    def test_get_transaction_history(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.get_transaction_history() == []

    def test_calculate_results(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        legs = _make_legs()
        for leg in legs:
            leg.executed_price = leg.price
            leg.executed_quantity = leg.quantity
            leg.fees = Decimal("0.01")
        tx = ArbitrageTransaction(
            transaction_id="t1",
            transaction_type=TransactionType.SIMPLE_ARBITRAGE,
            legs=legs,
            expected_profit=Decimal("0.1"),
            expected_profit_pct=0.2,
            risk_score=0.1,
        )
        mgr._calculate_transaction_results(tx)
        assert tx.actual_profit is not None


# =========================================================================
# training_monitor — TrainingMonitor
# =========================================================================

class TestTrainingMonitor:

    def test_init_creates_log_dir(self, tmp_path):
        log_dir = os.path.join(str(tmp_path), "train_logs")
        tm = TrainingMonitor(log_dir=log_dir, gpu_monitoring=False)
        assert os.path.isdir(log_dir)
        assert tm.monitoring_active is False

    def test_log_metrics(self, tmp_path):
        log_dir = os.path.join(str(tmp_path), "logs")
        tm = TrainingMonitor(log_dir=log_dir, gpu_monitoring=False)
        tm.log_metrics(epoch=1, step=10, loss=0.5, learning_rate=1e-3)
        assert len(tm.metrics_history) == 1
        assert tm.current_epoch == 1
        assert tm.current_step == 10

    def test_get_training_stats_no_metrics(self, tmp_path):
        tm = TrainingMonitor(log_dir=str(tmp_path), gpu_monitoring=False)
        stats = tm.get_training_stats()
        assert stats == {"status": "no_metrics"}

    def test_get_training_stats_with_metrics(self, tmp_path):
        tm = TrainingMonitor(log_dir=str(tmp_path), gpu_monitoring=False)
        tm.log_metrics(0, 0, 1.0, 1e-3)
        stats = tm.get_training_stats()
        assert stats["latest_loss"] == 1.0
        assert stats["current_epoch"] == 0

    def test_alert_on_high_loss(self, tmp_path):
        tm = TrainingMonitor(log_dir=str(tmp_path), gpu_monitoring=False)
        tm.alert_thresholds["max_loss"] = 1.0
        tm.log_metrics(0, 0, 15.0, 1e-3)
        assert any(a.alert_type == "high_loss" for a in tm.alerts_history)

    def test_alert_on_low_lr(self, tmp_path):
        tm = TrainingMonitor(log_dir=str(tmp_path), gpu_monitoring=False)
        tm.log_metrics(0, 0, 0.5, 1e-10)
        assert any(a.alert_type == "low_learning_rate" for a in tm.alerts_history)

    def test_alert_callback(self, tmp_path):
        received = []
        tm = TrainingMonitor(
            log_dir=str(tmp_path),
            gpu_monitoring=False,
            alert_callbacks=[received.append],
        )
        tm.alert_thresholds["max_loss"] = 0.1
        tm.log_metrics(0, 0, 5.0, 1e-3)
        assert len(received) >= 1
        assert isinstance(received[0], TrainingAlert)

    def test_get_metrics_history(self, tmp_path):
        tm = TrainingMonitor(log_dir=str(tmp_path), gpu_monitoring=False)
        for i in range(5):
            tm.log_metrics(0, i, 1.0 / (i + 1), 1e-3)
        history = tm.get_metrics_history(limit=3)
        assert len(history) == 3

    def test_get_alerts_history(self, tmp_path):
        tm = TrainingMonitor(log_dir=str(tmp_path), gpu_monitoring=False)
        tm.alert_thresholds["max_loss"] = 0.1
        tm.log_metrics(0, 0, 5.0, 1e-3)
        alerts = tm.get_alerts_history()
        assert len(alerts) >= 1
        assert "alert_type" in alerts[0]

    def test_save_metrics_summary(self, tmp_path):
        log_dir = str(tmp_path)
        tm = TrainingMonitor(log_dir=log_dir, gpu_monitoring=False)
        tm.start_time = datetime.now()
        tm.log_metrics(0, 0, 0.8, 1e-3)
        tm.log_metrics(1, 10, 0.3, 5e-4)
        tm._save_metrics_summary()
        summary_path = os.path.join(log_dir, "training_summary.json")
        assert os.path.exists(summary_path)
        with open(summary_path) as f:
            summary = json.load(f)
        assert summary["total_steps"] == 2
        assert summary["loss_stats"]["min"] == 0.3

    def test_update_pair_progress(self, tmp_path):
        tm = TrainingMonitor(log_dir=str(tmp_path), gpu_monitoring=False)
        tm.update_pair_progress("XRP/USDC", "training", 0.5, 3, 0.4, 0.85)
        assert len(tm.metrics_history) == 1

    def test_start_stop_monitoring(self, tmp_path):
        tm = TrainingMonitor(log_dir=str(tmp_path), gpu_monitoring=False)
        tm.start_time = datetime.now()
        tm.start_monitoring()
        assert tm.monitoring_active is True
        tm.stop_monitoring()
        assert tm.monitoring_active is False


class TestGPUTrainingMonitor:

    def test_init(self, tmp_path):
        with patch("training_monitor.TrainingMonitor.__init__", return_value=None):
            gm = GPUTrainingMonitor(gpu_id=0)
            assert gm.gpu_id == 0


# =========================================================================
# grok_reasoning — GrokReasoningEngine (no API key → offline)
# =========================================================================

class TestGrokReasoning:

    def test_init_no_api_key(self):
        engine = GrokReasoningEngine(api_key=None)
        assert engine.client is None

    def test_analyze_no_client(self):
        engine = GrokReasoningEngine(api_key=None)
        result = _run(engine.analyze_arbitrage_opportunity({"pair": "XRP/USDC"}))
        assert "error" in result
        assert result["confidence"] == 0.0

    def test_plan_strategy_no_client(self):
        engine = GrokReasoningEngine(api_key=None)
        result = _run(engine.plan_trading_strategy({}, {}))
        assert "error" in result

    def test_risk_assessment_no_client(self):
        engine = GrokReasoningEngine(api_key=None)
        result = _run(engine.assess_risk_management({}, 0.5))
        assert "error" in result

    def test_health_check_no_client(self):
        engine = GrokReasoningEngine(api_key=None)
        assert _run(engine.health_check()) is False

    def test_format_opportunity_context(self):
        engine = GrokReasoningEngine(api_key=None)
        ctx = engine._format_opportunity_context({
            "pair": "XRP/USDC",
            "exchanges": ["binance", "coinbase"],
            "spread": 0.0123,
            "probability": 0.85,
        })
        assert "XRP/USDC" in ctx
        assert "binance" in ctx
        assert "0.0123" in ctx

    def test_parse_grok_response_high_risk(self):
        engine = GrokReasoningEngine(api_key=None)
        parsed = engine._parse_grok_response("High risk situation. Confidence: 75. Execute the trade. Profit: 250")
        assert parsed["risk_level"] == "High"
        assert parsed["confidence"] == 75
        assert parsed["action"] == "Execute"
        assert parsed["profit_estimate"] == 250.0

    def test_parse_grok_response_low_risk(self):
        engine = GrokReasoningEngine(api_key=None)
        parsed = engine._parse_grok_response("Low risk. Confidence: 90. Hold for now.")
        assert parsed["risk_level"] == "Low"
        assert parsed["action"] == "Hold"

    def test_parse_grok_response_medium_risk(self):
        engine = GrokReasoningEngine(api_key=None)
        parsed = engine._parse_grok_response("Medium risk environment. Monitor positions.")
        assert parsed["risk_level"] == "Medium"
        assert parsed["action"] == "Monitor"


# =========================================================================
# database — DatabaseManager (init-only, no postgres)
# =========================================================================

class TestDatabaseManager:

    def test_init_defaults(self):
        dm = DatabaseManager()
        assert dm.pool is None
        assert dm.engine is None
        assert "postgresql" in dm.database_url
        assert dm.pool_config["min_size"] == 5
        assert dm.pool_config["max_size"] == 20

    def test_init_custom_env(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://test:test@localhost/test",
            "DB_POOL_MIN_SIZE": "2",
            "DB_POOL_MAX_SIZE": "10",
        }):
            dm = DatabaseManager()
            assert "test" in dm.database_url
            assert dm.pool_config["min_size"] == 2
            assert dm.pool_config["max_size"] == 10


# =========================================================================
# exchange_rate_limiter — TokenBucket
# =========================================================================

class TestTokenBucket:

    def test_acquire_immediate(self):
        bucket = TokenBucket(rate=10.0, capacity=10)
        assert _run(bucket.acquire()) is True
        assert bucket.total_requests == 1

    def test_acquire_no_wait(self):
        bucket = TokenBucket(rate=1.0, capacity=1)
        _run(bucket.acquire())  # consume the only token
        result = _run(bucket.acquire(wait=False))
        assert result is False
        assert bucket.throttled_requests >= 1

    def test_stats(self):
        bucket = TokenBucket(rate=5.0, capacity=10)
        _run(bucket.acquire())
        s = bucket.stats()
        assert s["rate"] == 5.0
        assert s["capacity"] == 10
        assert s["total_requests"] == 1

    def test_available_property(self):
        bucket = TokenBucket(rate=100.0, capacity=100)
        assert bucket.available <= 100


# =========================================================================
# exchange_rate_limiter — ExchangeRateLimiter
# =========================================================================

class TestExchangeRateLimiter:

    def test_init_creates_buckets(self):
        limits = ExchangeLimits(name="test", rest_public=(10.0, 20))
        erl = ExchangeRateLimiter(limits)
        assert "rest_public" in erl._buckets
        assert "order" in erl._buckets

    def test_acquire_known_endpoint(self):
        limits = ExchangeLimits(name="test")
        erl = ExchangeRateLimiter(limits)
        assert _run(erl.acquire("rest_public")) is True

    def test_acquire_unknown_endpoint_fallback(self):
        limits = ExchangeLimits(name="test")
        erl = ExchangeRateLimiter(limits)
        assert _run(erl.acquire("bogus_endpoint")) is True

    def test_stats(self):
        limits = ExchangeLimits(name="test")
        erl = ExchangeRateLimiter(limits)
        s = erl.stats()
        assert s["exchange"] == "test"
        assert "buckets" in s


# =========================================================================
# exchange_rate_limiter — RateLimiterManager
# =========================================================================

class TestRateLimiterManager:

    def test_default_exchanges(self):
        mgr = RateLimiterManager()
        assert "binance" in mgr._limiters
        assert "coinbase" in mgr._limiters
        assert "kraken" in mgr._limiters

    def test_get_unknown_exchange(self):
        mgr = RateLimiterManager()
        limiter = mgr.get("unknown_exchange")
        assert limiter is not None
        assert "unknown_exchange" in mgr._limiters

    def test_acquire_via_manager(self):
        mgr = RateLimiterManager()
        assert _run(mgr.acquire("binance", "rest_public")) is True

    def test_health_report(self):
        mgr = RateLimiterManager()
        report = mgr.health_report()
        assert "binance" in report
        assert report["binance"]["healthy"] is True

    def test_stats(self):
        mgr = RateLimiterManager()
        s = mgr.stats()
        assert "binance" in s


# =========================================================================
# websocket_validator — dataclasses
# =========================================================================

class TestWebSocketValidatorDataclasses:

    def test_websocket_metrics_defaults(self):
        m = WebSocketMetrics()
        assert m.connection_attempts == 0
        assert m.messages_received == 0
        assert m.min_latency_ms == float("inf")

    def test_data_quality_metrics_defaults(self):
        dq = DataQualityMetrics()
        assert dq.total_messages == 0
        assert dq.price_anomalies == 0

    def test_exchange_connection_defaults(self):
        ec = ExchangeConnection(exchange="binance", url="wss://example.com", pairs=["BTC/USD"])
        assert ec.is_connected is False
        assert ec.connection is None


# =========================================================================
# websocket_validator — WebSocketValidator
# =========================================================================

class TestWebSocketValidator:

    def test_init_creates_connections(self):
        v = WebSocketValidator()
        assert "binance" in v.connections
        assert "coinbase" in v.connections
        assert "kraken" in v.connections

    def test_validate_binance_message_valid(self):
        v = WebSocketValidator()
        data = {"s": "BTCUSDT", "c": 50000.0, "v": 1000.0, "P": "1.5", "E": 123456}
        assert v._validate_binance_message(data) is True

    def test_validate_binance_message_missing_field(self):
        v = WebSocketValidator()
        data = {"s": "BTCUSDT", "c": 50000.0}
        assert v._validate_binance_message(data) is False

    def test_validate_binance_message_negative_price(self):
        v = WebSocketValidator()
        data = {"s": "BTCUSDT", "c": -1.0, "v": 1000.0, "P": "1.5", "E": 123}
        assert v._validate_binance_message(data) is False

    def test_validate_coinbase_ticker(self):
        v = WebSocketValidator()
        data = {"type": "ticker", "product_id": "BTC-USD", "price": "50000", "volume_24h": "1000"}
        assert v._validate_coinbase_message(data) is True

    def test_validate_coinbase_non_ticker(self):
        v = WebSocketValidator()
        data = {"type": "subscriptions"}
        assert v._validate_coinbase_message(data) is True

    def test_validate_coinbase_invalid_price(self):
        v = WebSocketValidator()
        data = {"type": "ticker", "product_id": "BTC-USD", "price": "abc", "volume_24h": "1000"}
        assert v._validate_coinbase_message(data) is False

    def test_validate_kraken_valid(self):
        v = WebSocketValidator()
        data = [0, {"c": ["50000"], "v": ["100", "1000"], "p": ["49000"], "t": [500]}, "ticker", "BTC/USD"]
        assert v._validate_kraken_message(data) is True

    def test_validate_kraken_invalid_structure(self):
        v = WebSocketValidator()
        assert v._validate_kraken_message({"event": "heartbeat"}) is False

    def test_validate_kraken_negative_price(self):
        v = WebSocketValidator()
        data = [0, {"c": ["-1"], "v": ["100", "1000"], "p": ["49000"], "t": [500]}, "ticker", "BTC/USD"]
        assert v._validate_kraken_message(data) is False

    def test_get_validation_report(self):
        v = WebSocketValidator()
        report = v.get_validation_report()
        assert "overall_status" in report
        assert "connections" in report
        assert report["summary"]["total_connections"] == 3

    def test_data_quality_score_no_messages(self):
        v = WebSocketValidator()
        conn = v.connections["binance"]
        score = v._calculate_data_quality_score(conn)
        assert score == 0.0

    def test_data_quality_score_with_messages(self):
        v = WebSocketValidator()
        conn = v.connections["binance"]
        conn.data_quality.total_messages = 100
        conn.data_quality.valid_messages = 90
        conn.data_quality.stale_messages = 5
        conn.data_quality.message_frequency_hz = 10.0
        score = v._calculate_data_quality_score(conn)
        assert score > 0

    def test_test_exchange_connectivity_unknown(self):
        v = WebSocketValidator()
        result = _run(v.test_exchange_connectivity("unknown_exchange"))
        assert "error" in result
