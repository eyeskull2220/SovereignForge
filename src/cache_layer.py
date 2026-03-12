#!/usr/bin/env python3
"""
SovereignForge - Redis Caching Layer
Wave 2 - Category 4: High-frequency market data caching with in-memory fallback.

Features:
- Redis as primary cache (TTL-based, JSON serialisation)
- Thread-safe in-memory LRU fallback when Redis is unavailable
- Async API throughout
- Cache domains: market_data, model_predictions, arbitrage_opportunities
- Metrics: hit rate, miss rate, eviction count
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL defaults per cache domain (seconds)
# ---------------------------------------------------------------------------
DEFAULT_TTL: Dict[str, int] = {
    "market_data":             2,    # tick data — very short-lived
    "orderbook":               1,
    "model_predictions":      10,    # inference results
    "arbitrage_opportunities": 5,
    "exchange_status":        60,
    "compliance_check":      300,    # compliance results change rarely
    "default":                30,
}


# ---------------------------------------------------------------------------
# In-memory LRU cache (fallback)
# ---------------------------------------------------------------------------

class LRUCache:
    """Thread-safe LRU cache with per-entry TTL."""

    def __init__(self, max_size: int = 4096):
        self._max_size = max_size
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._store:
                self.misses += 1
                return None
            value, expires_at = self._store[key]
            if time.monotonic() > expires_at:
                del self._store[key]
                self.misses += 1
                self.evictions += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return value

    async def set(self, key: str, value: Any, ttl: int = 30) -> None:
        async with self._lock:
            expires_at = time.monotonic() + ttl
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, expires_at)
            # Evict oldest entries if over capacity
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)
                self.evictions += 1

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "backend": "lru_memory",
            "size": len(self._store),
            "max_size": self._max_size,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": self.hits / total if total else 0.0,
        }


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------

class RedisCache:
    """
    Async Redis-backed cache.
    Requires `redis[asyncio]` package. Falls back gracefully if unavailable.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        key_prefix: str = "sf:",
        max_connections: int = 20,
    ):
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._prefix = key_prefix
        self._max_connections = max_connections
        self._client = None
        self._available = False
        self.hits = 0
        self.misses = 0

    async def connect(self) -> bool:
        try:
            import redis.asyncio as aioredis  # type: ignore
            self._client = aioredis.Redis(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password,
                max_connections=self._max_connections,
                decode_responses=True,
            )
            await self._client.ping()
            self._available = True
            logger.info(f"Redis connected at {self._host}:{self._port}")
            return True
        except Exception as e:
            logger.warning(f"Redis not available ({e}) — will use in-memory fallback")
            self._available = False
            return False

    async def disconnect(self) -> None:
        if self._client and self._available:
            await self._client.aclose()
            self._available = False

    async def get(self, key: str) -> Optional[Any]:
        if not self._available or not self._client:
            return None
        try:
            raw = await self._client.get(self._prefix + key)
            if raw is None:
                self.misses += 1
                return None
            self.hits += 1
            return json.loads(raw)
        except Exception as e:
            logger.debug(f"Redis get error: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 30) -> None:
        if not self._available or not self._client:
            return
        try:
            await self._client.setex(
                self._prefix + key, ttl, json.dumps(value, default=str)
            )
        except Exception as e:
            logger.debug(f"Redis set error: {e}")

    async def delete(self, key: str) -> bool:
        if not self._available or not self._client:
            return False
        try:
            return bool(await self._client.delete(self._prefix + key))
        except Exception:
            return False

    async def clear_pattern(self, pattern: str) -> int:
        if not self._available or not self._client:
            return 0
        try:
            keys = await self._client.keys(self._prefix + pattern)
            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception:
            return 0

    def stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "backend": "redis",
            "available": self._available,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total if total else 0.0,
        }


# ---------------------------------------------------------------------------
# Unified CacheManager (primary + fallback)
# ---------------------------------------------------------------------------

class CacheManager:
    """
    Transparent two-tier cache:
      1. Redis (primary) — fast, shared across processes
      2. LRU in-memory (fallback) — always available

    Usage:
        cache = CacheManager()
        await cache.connect()
        await cache.set("market_data", "BTC/USDC:binance", ticker_dict)
        data = await cache.get("market_data", "BTC/USDC:binance")
    """

    def __init__(
        self,
        redis_host: Optional[str] = None,
        redis_port: int = 6379,
        redis_password: Optional[str] = None,
        lru_max_size: int = 8192,
        key_prefix: str = "sf:",
    ):
        host = redis_host or os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", str(redis_port)))
        password = redis_password or os.getenv("REDIS_PASSWORD")

        self._redis = RedisCache(
            host=host, port=port, password=password, key_prefix=key_prefix
        )
        self._lru = LRUCache(max_size=lru_max_size)
        self._redis_available = False

    async def connect(self) -> None:
        self._redis_available = await self._redis.connect()
        if not self._redis_available:
            logger.info("CacheManager using in-memory LRU cache only")

    async def disconnect(self) -> None:
        await self._redis.disconnect()

    def _build_key(self, domain: str, key: str) -> str:
        return f"{domain}:{key}"

    def _ttl(self, domain: str) -> int:
        return DEFAULT_TTL.get(domain, DEFAULT_TTL["default"])

    async def get(self, domain: str, key: str) -> Optional[Any]:
        full_key = self._build_key(domain, key)

        # Try Redis first
        if self._redis_available:
            value = await self._redis.get(full_key)
            if value is not None:
                return value

        # Fallback to LRU
        return await self._lru.get(full_key)

    async def set(
        self, domain: str, key: str, value: Any, ttl: Optional[int] = None
    ) -> None:
        full_key = self._build_key(domain, key)
        effective_ttl = ttl if ttl is not None else self._ttl(domain)

        if self._redis_available:
            await self._redis.set(full_key, value, ttl=effective_ttl)

        # Always write to LRU as well (serves as L1)
        await self._lru.set(full_key, value, ttl=effective_ttl)

    async def delete(self, domain: str, key: str) -> None:
        full_key = self._build_key(domain, key)
        await self._redis.delete(full_key)
        await self._lru.delete(full_key)

    async def invalidate_domain(self, domain: str) -> None:
        """Clear all keys in a domain from Redis (LRU will expire naturally)."""
        await self._redis.clear_pattern(f"{domain}:*")

    # ------------------------------------------------------------------
    # Market data helpers
    # ------------------------------------------------------------------

    async def cache_ticker(self, exchange: str, pair: str, ticker: Dict) -> None:
        await self.set("market_data", f"{pair}:{exchange}", ticker)

    async def get_ticker(self, exchange: str, pair: str) -> Optional[Dict]:
        return await self.get("market_data", f"{pair}:{exchange}")

    async def cache_prediction(
        self, pair: str, prediction: Dict, ttl: int = 10
    ) -> None:
        await self.set("model_predictions", pair, prediction, ttl=ttl)

    async def get_prediction(self, pair: str) -> Optional[Dict]:
        return await self.get("model_predictions", pair)

    async def cache_opportunity(self, opp_id: str, opp: Dict) -> None:
        await self.set("arbitrage_opportunities", opp_id, opp)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        return {
            "redis": self._redis.stats(),
            "lru": self._lru.stats(),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_cache: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache


async def init_cache() -> CacheManager:
    cache = get_cache()
    await cache.connect()
    return cache
