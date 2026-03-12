"""
Wave 2 Unit Tests — cache_layer, exchange_rate_limiter, multi_channel_alerts

Run: pytest tests/test_wave2.py -v
"""
import os
import sys
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cache_layer import LRUCache, CacheManager, get_cache
from exchange_rate_limiter import TokenBucket, ExchangeRateLimiter, RateLimiterManager, get_rate_limiter
from multi_channel_alerts import (
    Alert, AlertPriority, AlertRouter, AlertRateLimiter,
    DeliveryResult, get_alert_router,
)


# ---------------------------------------------------------------------------
# LRUCache
# ---------------------------------------------------------------------------
class TestLRUCache:
    def test_set_and_get(self):
        cache = LRUCache(capacity=10)
        cache.set("k", "v")
        assert cache.get("k") == "v"

    def test_miss_returns_none(self):
        cache = LRUCache(capacity=10)
        assert cache.get("missing") is None

    def test_ttl_expiry(self):
        cache = LRUCache(capacity=10)
        cache.set("k", "v", ttl=0.01)
        time.sleep(0.05)
        assert cache.get("k") is None

    def test_lru_eviction(self):
        cache = LRUCache(capacity=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")          # "a" is recently used
        cache.set("c", 3)       # evicts "b"
        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3

    def test_delete(self):
        cache = LRUCache(capacity=10)
        cache.set("k", "v")
        cache.delete("k")
        assert cache.get("k") is None

    def test_delete_missing_is_noop(self):
        cache = LRUCache(capacity=10)
        cache.delete("nonexistent")  # must not raise

    def test_stats_hit_rate(self):
        cache = LRUCache(capacity=10)
        cache.set("k", "v")
        cache.get("k")   # hit
        cache.get("k")   # hit
        cache.get("x")   # miss
        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert abs(stats["hit_rate"] - 2/3) < 0.01

    def test_clear(self):
        cache = LRUCache(capacity=10)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None


# ---------------------------------------------------------------------------
# CacheManager
# ---------------------------------------------------------------------------
class TestCacheManager:
    def setup_method(self):
        self.cm = CacheManager()

    def test_set_and_get_lru_only(self):
        asyncio.run(self.cm.set("ns", "key", "value"))
        result = asyncio.run(self.cm.get("ns", "key"))
        assert result == "value"

    def test_domain_ttl_applied(self):
        asyncio.run(self.cm.set("ticker", "BTC", {"price": 50000}, ttl=1))
        result = asyncio.run(self.cm.get("ticker", "BTC"))
        assert result is not None

    def test_cache_ticker(self):
        asyncio.run(self.cm.cache_ticker("BTC/USDC", "binance", {"bid": 49000}))
        result = asyncio.run(self.cm.get_ticker("BTC/USDC", "binance"))
        assert result == {"bid": 49000}

    def test_cache_prediction(self):
        asyncio.run(self.cm.cache_prediction("BTC/USDC", {"signal": 0.8}))
        result = asyncio.run(self.cm.get_prediction("BTC/USDC"))
        assert result == {"signal": 0.8}

    def test_cache_opportunity(self):
        opp = {"pair": "BTC/USDC", "spread": 0.5}
        asyncio.run(self.cm.cache_opportunity("opp-1", opp))
        result = asyncio.run(self.cm.get_opportunity("opp-1"))
        assert result == opp

    def test_delete(self):
        asyncio.run(self.cm.set("ns", "k", "v"))
        asyncio.run(self.cm.delete("ns", "k"))
        assert asyncio.run(self.cm.get("ns", "k")) is None

    def test_stats_keys(self):
        stats = asyncio.run(self.cm.stats())
        assert "lru" in stats
        assert "hits" in stats["lru"]


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------
class TestTokenBucket:
    def test_acquire_available(self):
        tb = TokenBucket(rate=10, capacity=10)
        assert tb.acquire() is True

    def test_drain_tokens(self):
        tb = TokenBucket(rate=0.1, capacity=3)
        for _ in range(3):
            tb.acquire()
        assert tb.acquire() is False

    def test_fail_fast_false(self):
        tb = TokenBucket(rate=0.01, capacity=1)
        tb.acquire()
        # No tokens left, fail_fast should return False immediately
        result = tb.acquire(fail_fast=True)
        assert result is False

    def test_refill_over_time(self):
        tb = TokenBucket(rate=100, capacity=5)
        for _ in range(5):
            tb.acquire()
        # At rate=100/s, after 0.1s we should have ~10 tokens (capped at 5)
        time.sleep(0.1)
        assert tb.acquire() is True

    def test_stats_structure(self):
        tb = TokenBucket(rate=10, capacity=10)
        tb.acquire()
        stats = tb.stats()
        assert "tokens" in stats
        assert "rate" in stats
        assert "capacity" in stats


# ---------------------------------------------------------------------------
# ExchangeRateLimiter
# ---------------------------------------------------------------------------
class TestExchangeRateLimiter:
    def test_acquire_rest_public(self):
        limiter = ExchangeRateLimiter("binance")
        result = limiter.acquire("rest_public")
        assert result is True

    def test_unknown_endpoint_uses_fallback(self):
        limiter = ExchangeRateLimiter("binance")
        result = limiter.acquire("unknown_endpoint_type")
        assert isinstance(result, bool)

    def test_penalty_blocks_requests(self):
        limiter = ExchangeRateLimiter("binance")
        limiter.apply_penalty(duration=60)
        assert limiter.acquire("rest_public") is False

    def test_penalty_clears_after_duration(self):
        limiter = ExchangeRateLimiter("binance")
        limiter.apply_penalty(duration=0.01)
        time.sleep(0.05)
        assert limiter.acquire("rest_public") is True

    def test_stats_structure(self):
        limiter = ExchangeRateLimiter("binance")
        stats = limiter.stats()
        assert "exchange" in stats
        assert stats["exchange"] == "binance"


# ---------------------------------------------------------------------------
# RateLimiterManager
# ---------------------------------------------------------------------------
class TestRateLimiterManager:
    def test_known_exchange(self):
        mgr = RateLimiterManager()
        result = mgr.acquire("binance", "rest_public")
        assert isinstance(result, bool)

    def test_unknown_exchange_uses_defaults(self):
        mgr = RateLimiterManager()
        result = mgr.acquire("unknown_exchange_xyz", "rest_public")
        assert isinstance(result, bool)

    def test_health_report_structure(self):
        mgr = RateLimiterManager()
        report = mgr.health_report()
        assert isinstance(report, dict)

    def test_all_known_exchanges_present(self):
        mgr = RateLimiterManager()
        report = mgr.health_report()
        for exchange in ("binance", "coinbase", "kraken"):
            assert exchange in report

    def test_handle_429_propagates(self):
        mgr = RateLimiterManager()
        # Should not raise
        mgr.handle_429("binance", "rest_public")
        # After penalty, acquire should be False
        assert mgr.acquire("binance", "rest_public") is False


# ---------------------------------------------------------------------------
# AlertRateLimiter
# ---------------------------------------------------------------------------
class TestAlertRateLimiter:
    def test_allows_within_limit(self):
        rl = AlertRateLimiter(max_per_minute=10)
        assert rl.allow(AlertPriority.MEDIUM) is True

    def test_blocks_at_limit(self):
        rl = AlertRateLimiter(max_per_minute=2)
        rl.allow(AlertPriority.MEDIUM)
        rl.allow(AlertPriority.MEDIUM)
        assert rl.allow(AlertPriority.MEDIUM) is False

    def test_critical_never_blocked(self):
        rl = AlertRateLimiter(max_per_minute=0)
        assert rl.allow(AlertPriority.CRITICAL) is True


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------
class TestAlert:
    def test_auto_id_assigned(self):
        a = Alert(title="T", message="M", priority=AlertPriority.HIGH)
        assert a.id != ""

    def test_timestamp_set(self):
        a = Alert(title="T", message="M", priority=AlertPriority.HIGH)
        assert a.timestamp is not None

    def test_delivery_report_any_success(self):
        a = Alert(title="T", message="M", priority=AlertPriority.HIGH)
        a.delivery_results = [
            DeliveryResult(channel="telegram", success=True),
            DeliveryResult(channel="email", success=False),
        ]
        assert a.any_delivered is True

    def test_all_failed(self):
        a = Alert(title="T", message="M", priority=AlertPriority.HIGH)
        a.delivery_results = [
            DeliveryResult(channel="telegram", success=False),
            DeliveryResult(channel="email", success=False),
        ]
        assert a.any_delivered is False


# ---------------------------------------------------------------------------
# AlertRouter
# ---------------------------------------------------------------------------
class TestAlertRouter:
    def test_debug_not_sent(self):
        router = AlertRouter()
        alert = Alert(title="debug", message="x", priority=AlertPriority.DEBUG)
        results = asyncio.run(router.send(alert))
        assert results == []  # DEBUG is filtered before any channel

    def test_rate_limited_returns_empty(self):
        router = AlertRouter()
        router._rate_limiter = MagicMock()
        router._rate_limiter.allow.return_value = False
        alert = Alert(title="T", message="M", priority=AlertPriority.MEDIUM)
        results = asyncio.run(router.send(alert))
        assert results == []

    def test_delivery_callback_called(self):
        router = AlertRouter()
        received = []
        router.add_callback(lambda a: received.append(a))

        # Patch channels to succeed
        mock_channel = MagicMock()
        mock_channel.is_configured.return_value = True
        mock_channel.send = AsyncMock(return_value=DeliveryResult(channel="mock", success=True))
        router._channels = [mock_channel]
        router._rate_limiter = MagicMock()
        router._rate_limiter.allow.return_value = True

        alert = Alert(title="T", message="M", priority=AlertPriority.HIGH)
        asyncio.run(router.send(alert))
        assert len(received) == 1

    def test_critical_sends_to_all_channels(self):
        router = AlertRouter()
        calls = []

        async def fake_send(a):
            calls.append(a)
            return DeliveryResult(channel="mock", success=True)

        mock_ch = MagicMock()
        mock_ch.is_configured.return_value = True
        mock_ch.send = fake_send
        router._channels = [mock_ch, mock_ch]
        router._rate_limiter = MagicMock()
        router._rate_limiter.allow.return_value = True

        alert = Alert(title="CRIT", message="M", priority=AlertPriority.CRITICAL)
        asyncio.run(router.send(alert))
        assert len(calls) == 2

    def test_singleton_returns_same_instance(self):
        r1 = get_alert_router()
        r2 = get_alert_router()
        assert r1 is r2
