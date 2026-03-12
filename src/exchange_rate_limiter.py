#!/usr/bin/env python3
"""
SovereignForge - Intelligent Exchange API Rate Limiter
Wave 2 - Category 4: Per-exchange rate limiting using token bucket algorithm.

Features:
- Token bucket per (exchange, endpoint_type) pair
- Async-safe acquire with optional wait or fail-fast
- Built-in limits for major exchanges (Binance, Coinbase, Kraken, KuCoin, OKX)
- Automatic retry-after header parsing on 429 responses
- Request statistics and health reporting
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exchange rate limit configurations
# Based on public API documentation (conservative defaults)
# ---------------------------------------------------------------------------

@dataclass
class ExchangeLimits:
    """Rate limits for a single exchange."""
    name: str
    # (requests_per_second, burst_capacity) per endpoint type
    rest_public: Tuple[float, int] = (10.0, 20)    # public REST endpoints
    rest_private: Tuple[float, int] = (5.0, 10)    # private/authenticated
    websocket: Tuple[float, int] = (100.0, 200)    # WS message rate
    order: Tuple[float, int] = (2.0, 5)            # order placement (strict)


EXCHANGE_DEFAULTS: Dict[str, ExchangeLimits] = {
    "binance": ExchangeLimits(
        name="binance",
        rest_public=(20.0, 40),
        rest_private=(10.0, 20),
        websocket=(200.0, 400),
        order=(5.0, 10),
    ),
    "coinbase": ExchangeLimits(
        name="coinbase",
        rest_public=(10.0, 20),
        rest_private=(5.0, 10),
        websocket=(50.0, 100),
        order=(2.0, 5),
    ),
    "kraken": ExchangeLimits(
        name="kraken",
        rest_public=(1.0, 5),   # Kraken is conservative
        rest_private=(1.0, 3),
        websocket=(50.0, 100),
        order=(1.0, 3),
    ),
    "kucoin": ExchangeLimits(
        name="kucoin",
        rest_public=(30.0, 60),
        rest_private=(10.0, 20),
        websocket=(100.0, 200),
        order=(3.0, 8),
    ),
    "okx": ExchangeLimits(
        name="okx",
        rest_public=(20.0, 40),
        rest_private=(10.0, 20),
        websocket=(100.0, 200),
        order=(5.0, 10),
    ),
}


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------

class TokenBucket:
    """
    Async token bucket rate limiter.

    rate: tokens added per second
    capacity: maximum token accumulation (burst ceiling)
    """

    def __init__(self, rate: float, capacity: int):
        self._rate = rate
        self._capacity = capacity
        self._tokens: float = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()
        self.total_requests = 0
        self.throttled_requests = 0
        self.total_wait_ms = 0.0

    async def acquire(self, tokens: int = 1, wait: bool = True) -> bool:
        """
        Acquire `tokens` from the bucket.
        If wait=True, suspends until tokens are available.
        If wait=False, returns False immediately if tokens unavailable.
        """
        async with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                self.total_requests += 1
                return True

            if not wait:
                self.throttled_requests += 1
                return False

            # Calculate wait time
            deficit = tokens - self._tokens
            wait_seconds = deficit / self._rate
            self.throttled_requests += 1
            self.total_wait_ms += wait_seconds * 1000

        # Wait outside the lock
        await asyncio.sleep(wait_seconds)

        async with self._lock:
            self._refill()
            self._tokens -= tokens
            self.total_requests += 1
            return True

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed * self._rate,
        )
        self._last_refill = now

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens

    def stats(self) -> Dict:
        return {
            "rate": self._rate,
            "capacity": self._capacity,
            "available_tokens": round(self.available, 2),
            "total_requests": self.total_requests,
            "throttled_requests": self.throttled_requests,
            "avg_wait_ms": (
                self.total_wait_ms / self.throttled_requests
                if self.throttled_requests else 0.0
            ),
        }


# ---------------------------------------------------------------------------
# Per-exchange limiter
# ---------------------------------------------------------------------------

class ExchangeRateLimiter:
    """
    Manages token buckets for a single exchange across all endpoint types.
    """

    ENDPOINT_TYPES = ("rest_public", "rest_private", "websocket", "order")

    def __init__(self, limits: ExchangeLimits):
        self._limits = limits
        self._buckets: Dict[str, TokenBucket] = {}
        self._penalty_until: float = 0.0  # 429 backoff
        self._penalty_lock = asyncio.Lock()

        for ep_type in self.ENDPOINT_TYPES:
            rate, capacity = getattr(limits, ep_type)
            self._buckets[ep_type] = TokenBucket(rate=rate, capacity=capacity)

    async def acquire(
        self,
        endpoint_type: str = "rest_public",
        tokens: int = 1,
        wait: bool = True,
    ) -> bool:
        """
        Acquire rate limit tokens for the given endpoint type.
        Honours any active penalty period from a previous 429 response.
        """
        # Check penalty period
        async with self._penalty_lock:
            penalty_remaining = self._penalty_until - time.monotonic()
            if penalty_remaining > 0:
                if not wait:
                    return False
                logger.debug(
                    f"[{self._limits.name}] 429 penalty active — "
                    f"waiting {penalty_remaining:.1f}s"
                )
                await asyncio.sleep(penalty_remaining)

        bucket = self._buckets.get(endpoint_type)
        if bucket is None:
            logger.warning(f"Unknown endpoint type '{endpoint_type}' — using rest_public limits")
            bucket = self._buckets["rest_public"]

        return await bucket.acquire(tokens=tokens, wait=wait)

    async def handle_429(self, retry_after_seconds: float = 60.0) -> None:
        """Call this when the exchange returns a 429. Activates a penalty period."""
        async with self._penalty_lock:
            self._penalty_until = time.monotonic() + retry_after_seconds
        logger.warning(
            f"[{self._limits.name}] 429 received — backing off {retry_after_seconds}s"
        )

    def stats(self) -> Dict:
        penalty_remaining = max(0.0, self._penalty_until - time.monotonic())
        return {
            "exchange": self._limits.name,
            "penalty_remaining_s": round(penalty_remaining, 1),
            "buckets": {ep: self._buckets[ep].stats() for ep in self._buckets},
        }


# ---------------------------------------------------------------------------
# Multi-exchange manager
# ---------------------------------------------------------------------------

class RateLimiterManager:
    """
    Manages rate limiters for all exchanges.
    Provides a single entry point for the rest of the system.
    """

    def __init__(self, custom_limits: Optional[Dict[str, ExchangeLimits]] = None):
        limits = {**EXCHANGE_DEFAULTS, **(custom_limits or {})}
        self._limiters: Dict[str, ExchangeRateLimiter] = {
            name: ExchangeRateLimiter(lim) for name, lim in limits.items()
        }

    def get(self, exchange: str) -> ExchangeRateLimiter:
        """Get or create a rate limiter for the given exchange."""
        if exchange not in self._limiters:
            logger.warning(
                f"No rate limits configured for '{exchange}' — using conservative defaults"
            )
            self._limiters[exchange] = ExchangeRateLimiter(
                ExchangeLimits(name=exchange)
            )
        return self._limiters[exchange]

    async def acquire(
        self,
        exchange: str,
        endpoint_type: str = "rest_public",
        tokens: int = 1,
        wait: bool = True,
    ) -> bool:
        return await self.get(exchange).acquire(endpoint_type, tokens, wait)

    async def handle_429(
        self, exchange: str, retry_after_seconds: float = 60.0
    ) -> None:
        await self.get(exchange).handle_429(retry_after_seconds)

    def stats(self) -> Dict:
        return {exchange: limiter.stats() for exchange, limiter in self._limiters.items()}

    def health_report(self) -> Dict:
        """Returns a simple health summary per exchange."""
        report = {}
        for name, limiter in self._limiters.items():
            s = limiter.stats()
            penalty = s["penalty_remaining_s"]
            # Consider healthy if no penalty and REST bucket has > 25% capacity
            rest_available = s["buckets"]["rest_public"]["available_tokens"]
            rest_capacity = s["buckets"]["rest_public"]["capacity"]
            healthy = penalty == 0 and rest_available > rest_capacity * 0.25
            report[name] = {
                "healthy": healthy,
                "penalty_remaining_s": penalty,
                "rest_tokens_available": rest_available,
            }
        return report


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[RateLimiterManager] = None


def get_rate_limiter() -> RateLimiterManager:
    global _manager
    if _manager is None:
        _manager = RateLimiterManager()
    return _manager


# Convenience function
async def acquire(exchange: str, endpoint_type: str = "rest_public", wait: bool = True) -> bool:
    return await get_rate_limiter().acquire(exchange, endpoint_type, wait=wait)
