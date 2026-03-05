# SovereignForge Cache Manager - Wave 6
# Redis-based caching for production performance optimization

import asyncio
import logging
import json
import pickle
from typing import Any, Optional, Dict
import os
from datetime import datetime, timedelta

import redis.asyncio as redis
import aiocache
from aiocache import Cache
from aiocache.serializers import JsonSerializer, PickleSerializer

logger = logging.getLogger(__name__)

class CacheManager:
    """Redis-based cache manager for SovereignForge"""

    def __init__(self):
        self.redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
        self.redis_password = os.getenv('REDIS_PASSWORD', 'sovereignforge_cache')
        self.cache_ttl = int(os.getenv('CACHE_TTL', '3600'))  # 1 hour default
        self.max_memory = os.getenv('CACHE_MAX_MEMORY', '512mb')

        # Initialize aiocache with Redis backend
        self.cache = Cache(
            Cache.REDIS,
            endpoint=self.redis_url.split('://')[1].split(':')[0],
            port=int(self.redis_url.split(':')[-1]),
            password=self.redis_password if self.redis_password != 'sovereignforge_cache' else None,
            serializer=JsonSerializer(),
            ttl=self.cache_ttl
        )

        # Raw Redis client for advanced operations
        self.redis_client = None

        # Cache namespaces
        self.namespaces = {
            'market_data': 'market',
            'arbitrage_results': 'arbitrage',
            'trading_signals': 'signals',
            'risk_metrics': 'risk',
            'performance_data': 'performance',
            'system_metrics': 'system'
        }

    async def initialize(self):
        """Initialize cache connections"""
        try:
            # Initialize aiocache
            await self.cache.clear()

            # Initialize raw Redis client
            redis_config = redis.from_url(self.redis_url)
            if self.redis_password and self.redis_password != 'sovereignforge_cache':
                redis_config = redis.from_url(self.redis_url, password=self.redis_password)

            self.redis_client = redis_config

            # Test connection
            await self.redis_client.ping()

            # Configure Redis memory policy
            await self.redis_client.config_set('maxmemory', self.max_memory)
            await self.redis_client.config_set('maxmemory-policy', 'allkeys-lru')

            logger.info("Cache manager initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize cache: {e}")
            return False

    async def close(self):
        """Close cache connections"""
        try:
            if self.cache:
                await self.cache.close()
            if self.redis_client:
                await self.redis_client.close()
        except Exception as e:
            logger.error(f"Error closing cache connections: {e}")

    async def health_check(self) -> bool:
        """Check cache connectivity"""
        try:
            if self.redis_client:
                await self.redis_client.ping()
                return True
            return False
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return False

    async def get(self, key: str, namespace: str = None) -> Optional[Any]:
        """Get value from cache"""
        try:
            full_key = self._make_key(key, namespace)
            value = await self.cache.get(full_key)
            if value is not None:
                logger.debug(f"Cache hit for key: {full_key}")
                return value
            logger.debug(f"Cache miss for key: {full_key}")
            return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = None, namespace: str = None):
        """Set value in cache"""
        try:
            full_key = self._make_key(key, namespace)
            ttl_value = ttl or self.cache_ttl
            await self.cache.set(full_key, value, ttl=ttl_value)
            logger.debug(f"Cached value for key: {full_key} (TTL: {ttl_value}s)")
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")

    async def delete(self, key: str, namespace: str = None):
        """Delete value from cache"""
        try:
            full_key = self._make_key(key, namespace)
            await self.cache.delete(full_key)
            logger.debug(f"Deleted cache key: {full_key}")
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")

    async def exists(self, key: str, namespace: str = None) -> bool:
        """Check if key exists in cache"""
        try:
            full_key = self._make_key(key, namespace)
            return await self.cache.exists(full_key)
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False

    async def clear_namespace(self, namespace: str):
        """Clear all keys in a namespace"""
        try:
            if namespace in self.namespaces:
                pattern = f"{self.namespaces[namespace]}:*"
                keys = await self.redis_client.keys(pattern)
                if keys:
                    await self.redis_client.delete(*keys)
                    logger.info(f"Cleared {len(keys)} keys in namespace {namespace}")
        except Exception as e:
            logger.error(f"Error clearing namespace {namespace}: {e}")

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            info = await self.redis_client.info()
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory_human', '0B'),
                'total_connections_received': info.get('total_connections_received', 0),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'evicted_keys': info.get('evicted_keys', 0),
                'expired_keys': info.get('expired_keys', 0)
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}

    def _make_key(self, key: str, namespace: str = None) -> str:
        """Create full cache key with namespace"""
        if namespace and namespace in self.namespaces:
            return f"{self.namespaces[namespace]}:{key}"
        return key

    # Specialized caching methods for SovereignForge

    async def cache_market_data(self, symbol: str, exchange: str, data: dict, ttl: int = 30):
        """Cache market data with short TTL"""
        key = f"{symbol}:{exchange}"
        await self.set(key, data, ttl=ttl, namespace='market_data')

    async def get_market_data(self, symbol: str, exchange: str) -> Optional[dict]:
        """Get cached market data"""
        key = f"{symbol}:{exchange}"
        return await self.get(key, namespace='market_data')

    async def cache_arbitrage_result(self, symbol: str, result: dict, ttl: int = 60):
        """Cache arbitrage detection results"""
        await self.set(symbol, result, ttl=ttl, namespace='arbitrage_results')

    async def get_arbitrage_result(self, symbol: str) -> Optional[dict]:
        """Get cached arbitrage results"""
        return await self.get(symbol, namespace='arbitrage_results')

    async def cache_trading_signal(self, signal_id: str, signal: dict, ttl: int = 300):
        """Cache trading signals"""
        await self.set(signal_id, signal, ttl=ttl, namespace='trading_signals')

    async def get_trading_signal(self, signal_id: str) -> Optional[dict]:
        """Get cached trading signal"""
        return await self.get(signal_id, namespace='trading_signals')

    async def cache_risk_metrics(self, portfolio_id: str, metrics: dict, ttl: int = 600):
        """Cache risk metrics"""
        await self.set(portfolio_id, metrics, ttl=ttl, namespace='risk_metrics')

    async def get_risk_metrics(self, portfolio_id: str) -> Optional[dict]:
        """Get cached risk metrics"""
        return await self.get(portfolio_id, namespace='risk_metrics')

    async def cache_performance_data(self, period: str, data: dict, ttl: int = 3600):
        """Cache performance data"""
        await self.set(period, data, ttl=ttl, namespace='performance_data')

    async def get_performance_data(self, period: str) -> Optional[dict]:
        """Get cached performance data"""
        return await self.get(period, namespace='performance_data')

    async def cache_system_metrics(self, component: str, metrics: dict, ttl: int = 60):
        """Cache system metrics"""
        await self.set(component, metrics, ttl=ttl, namespace='system_metrics')

    async def get_system_metrics(self, component: str) -> Optional[dict]:
        """Get cached system metrics"""
        return await self.get(component, namespace='system_metrics')

    # Bulk operations

    async def set_multiple(self, key_value_pairs: Dict[str, Any], ttl: int = None, namespace: str = None):
        """Set multiple key-value pairs"""
        try:
            tasks = []
            for key, value in key_value_pairs.items():
                task = self.set(key, value, ttl=ttl, namespace=namespace)
                tasks.append(task)
            await asyncio.gather(*tasks)
            logger.debug(f"Set {len(key_value_pairs)} keys in cache")
        except Exception as e:
            logger.error(f"Error setting multiple keys: {e}")

    async def get_multiple(self, keys: list, namespace: str = None) -> Dict[str, Any]:
        """Get multiple values from cache"""
        try:
            tasks = []
            for key in keys:
                task = self.get(key, namespace=namespace)
                tasks.append(task)

            results = await asyncio.gather(*tasks)
            return dict(zip(keys, results))
        except Exception as e:
            logger.error(f"Error getting multiple keys: {e}")
            return {}

    # Pub/Sub functionality

    async def publish_message(self, channel: str, message: Any):
        """Publish message to Redis channel"""
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
            await self.redis_client.publish(channel, message)
            logger.debug(f"Published message to channel {channel}")
        except Exception as e:
            logger.error(f"Error publishing message to {channel}: {e}")

    async def subscribe_to_channel(self, channel: str):
        """Subscribe to Redis channel (returns pubsub object)"""
        try:
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to channel {channel}")
            return pubsub
        except Exception as e:
            logger.error(f"Error subscribing to {channel}: {e}")
            return None

    # Cache warming utilities

    async def warm_market_data_cache(self, symbols: list, exchanges: list):
        """Pre-populate market data cache"""
        logger.info("Warming market data cache...")
        # This would typically fetch data from exchanges
        # For now, just log the intent
        pass

    async def warm_arbitrage_cache(self, symbols: list):
        """Pre-populate arbitrage results cache"""
        logger.info("Warming arbitrage cache...")
        # This would run initial arbitrage detection
        pass

    # Cache invalidation strategies

    async def invalidate_market_data(self, symbol: str = None, exchange: str = None):
        """Invalidate market data cache"""
        try:
            if symbol and exchange:
                key = f"{symbol}:{exchange}"
                await self.delete(key, namespace='market_data')
            elif symbol:
                # Invalidate all exchanges for this symbol
                pattern = f"{self.namespaces['market_data']}:{symbol}:*"
                keys = await self.redis_client.keys(pattern)
                if keys:
                    await self.redis_client.delete(*keys)
            else:
                # Clear entire market data namespace
                await self.clear_namespace('market_data')

            logger.info(f"Invalidated market data cache for symbol={symbol}, exchange={exchange}")
        except Exception as e:
            logger.error(f"Error invalidating market data cache: {e}")

    async def invalidate_stale_data(self, max_age_seconds: int = 300):
        """Invalidate cache entries older than specified age"""
        try:
            # This is a simplified implementation
            # In production, you might want to use Redis TTL or custom logic
            logger.info(f"Invalidating cache entries older than {max_age_seconds} seconds")
            # Implementation would depend on your specific caching strategy
        except Exception as e:
            logger.error(f"Error invalidating stale data: {e}")

    # Monitoring and analytics

    async def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        try:
            stats = await self.get_cache_stats()
            hits = stats.get('keyspace_hits', 0)
            misses = stats.get('keyspace_misses', 0)
            total = hits + misses
            return (hits / total * 100) if total > 0 else 0.0
        except Exception as e:
            logger.error(f"Error calculating cache hit rate: {e}")
            return 0.0

    async def get_memory_usage(self) -> str:
        """Get cache memory usage"""
        try:
            stats = await self.get_cache_stats()
            return stats.get('used_memory', '0B')
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return '0B'