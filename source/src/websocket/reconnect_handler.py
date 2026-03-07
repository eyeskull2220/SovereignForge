#!/usr/bin/env python3
"""
WebSocket Reconnect Handler with Circuit Breaker Pattern
Implements advanced reconnection logic with exponential backoff and health monitoring
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable, Any, Union
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    """Connection state enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    CIRCUIT_OPEN = "circuit_open"

class CircuitBreakerState(Enum):
    """Circuit breaker state enumeration"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """Circuit breaker implementation for connection management"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0,
                 expected_exception: Exception = Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitBreakerState.CLOSED

    def should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt to reset"""
        if self.state != CircuitBreakerState.OPEN:
            return False

        if self.last_failure_time is None:
            return True

        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout

    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED

    def record_failure(self, exception: Exception):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

    def can_execute(self) -> bool:
        """Check if operation can be executed"""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if self.should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True
        return False

    def get_state_info(self) -> Dict[str, Any]:
        """Get circuit breaker state information"""
        return {
            'state': self.state.value,
            'failure_count': self.failure_count,
            'last_failure_time': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'can_execute': self.can_execute()
        }

class ReconnectHandler:
    """
    Advanced WebSocket reconnect handler with circuit breaker and health monitoring
    """

    def __init__(self, connection_manager, max_reconnect_attempts: int = 10,
                 base_delay: float = 1.0, max_delay: float = 300.0,
                 backoff_multiplier: float = 2.0):
        self.connection_manager = connection_manager
        self.max_reconnect_attempts = max_reconnect_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier

        self.current_attempt = 0
        self.is_reconnecting = False
        self.last_reconnect_time: Optional[datetime] = None

        # Circuit breaker for connection attempts
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=120.0  # 2 minutes
        )

        # Connection state tracking
        self.connection_state = ConnectionState.DISCONNECTED
        self.state_change_handlers: Dict[str, Callable] = {}

        # Health monitoring
        self.connection_start_time: Optional[datetime] = None
        self.total_uptime = 0.0
        self.successful_connections = 0
        self.failed_connections = 0

    def add_state_change_handler(self, event: str, handler: Callable):
        """Add handler for state change events"""
        self.state_change_handlers[event] = handler

    def _change_state(self, new_state: ConnectionState):
        """Change connection state and notify handlers"""
        old_state = self.connection_state
        self.connection_state = new_state

        logger.info(f"Connection state changed: {old_state.value} -> {new_state.value}")

        # Notify handlers
        for handler in self.state_change_handlers.values():
            try:
                handler(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state change handler: {e}")

    async def handle_connection_lost(self):
        """Handle connection loss and initiate reconnection"""
        if self.is_reconnecting:
            logger.debug("Reconnection already in progress")
            return

        logger.warning("Connection lost, initiating reconnection")
        self._change_state(ConnectionState.RECONNECTING)
        await self._start_reconnection()

    async def _start_reconnection(self):
        """Start reconnection process with exponential backoff"""
        self.is_reconnecting = True
        self.current_attempt = 0

        while self.is_reconnecting and self.current_attempt < self.max_reconnect_attempts:
            self.current_attempt += 1

            # Check circuit breaker
            if not self.circuit_breaker.can_execute():
                logger.warning("Circuit breaker is open, skipping reconnection attempt")
                self._change_state(ConnectionState.CIRCUIT_OPEN)
                await asyncio.sleep(30)  # Wait before checking again
                continue

            try:
                logger.info(f"Reconnection attempt {self.current_attempt}/{self.max_reconnect_attempts}")

                # Attempt reconnection
                success = await self._attempt_reconnection()

                if success:
                    logger.info("Reconnection successful")
                    self.circuit_breaker.record_success()
                    self.successful_connections += 1
                    self._change_state(ConnectionState.CONNECTED)
                    self.is_reconnecting = False
                    return

                else:
                    logger.warning(f"Reconnection attempt {self.current_attempt} failed")
                    self.circuit_breaker.record_failure(Exception("Reconnection failed"))
                    self.failed_connections += 1

                    # Calculate delay with exponential backoff
                    delay = min(
                        self.base_delay * (self.backoff_multiplier ** (self.current_attempt - 1)),
                        self.max_delay
                    )

                    logger.info(f"Waiting {delay:.1f}s before next reconnection attempt")
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"Error during reconnection attempt {self.current_attempt}: {e}")
                self.circuit_breaker.record_failure(e)
                self.failed_connections += 1

                # Shorter delay for exceptions
                await asyncio.sleep(min(self.base_delay * self.current_attempt, 30))

        # All reconnection attempts failed
        logger.error("All reconnection attempts failed")
        self._change_state(ConnectionState.FAILED)
        self.is_reconnecting = False

    async def _attempt_reconnection(self) -> bool:
        """Attempt a single reconnection"""
        try:
            # Check if connection manager has a reconnect method
            if hasattr(self.connection_manager, 'reconnect'):
                return await self.connection_manager.reconnect()
            elif hasattr(self.connection_manager, 'connect'):
                return await self.connection_manager.connect()
            else:
                logger.error("Connection manager has no reconnect or connect method")
                return False

        except Exception as e:
            logger.error(f"Reconnection attempt failed: {e}")
            return False

    def stop_reconnection(self):
        """Stop ongoing reconnection process"""
        logger.info("Stopping reconnection process")
        self.is_reconnecting = False
        self._change_state(ConnectionState.DISCONNECTED)

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get comprehensive connection statistics"""
        uptime = 0.0
        if self.connection_start_time and self.connection_state == ConnectionState.CONNECTED:
            uptime = (datetime.now() - self.connection_start_time).total_seconds()

        return {
            'current_state': self.connection_state.value,
            'is_reconnecting': self.is_reconnecting,
            'current_attempt': self.current_attempt,
            'max_attempts': self.max_reconnect_attempts,
            'successful_connections': self.successful_connections,
            'failed_connections': self.failed_connections,
            'success_rate': (
                self.successful_connections / max(1, self.successful_connections + self.failed_connections)
            ),
            'current_uptime_seconds': uptime,
            'total_uptime_seconds': self.total_uptime,
            'last_reconnect_time': self.last_reconnect_time.isoformat() if self.last_reconnect_time else None,
            'circuit_breaker': self.circuit_breaker.get_state_info()
        }

    def reset_stats(self):
        """Reset connection statistics"""
        self.successful_connections = 0
        self.failed_connections = 0
        self.total_uptime = 0.0
        logger.info("Connection statistics reset")

class WebSocketReconnectManager:
    """
    High-level WebSocket reconnection manager coordinating multiple connections
    """

    def __init__(self):
        self.handlers: Dict[str, ReconnectHandler] = {}
        self.global_stats = {
            'total_connections': 0,
            'active_connections': 0,
            'failed_connections': 0,
            'total_uptime': 0.0
        }

    def add_connection(self, name: str, connection_manager, **reconnect_kwargs):
        """Add a connection to be managed"""
        handler = ReconnectHandler(connection_manager, **reconnect_kwargs)
        self.handlers[name] = handler
        self.global_stats['total_connections'] += 1

        logger.info(f"Added connection '{name}' to reconnect manager")

    def remove_connection(self, name: str):
        """Remove a connection from management"""
        if name in self.handlers:
            self.handlers[name].stop_reconnection()
            del self.handlers[name]
            logger.info(f"Removed connection '{name}' from reconnect manager")

    async def handle_connection_failure(self, connection_name: str):
        """Handle connection failure for specific connection"""
        if connection_name in self.handlers:
            await self.handlers[connection_name].handle_connection_lost()
        else:
            logger.warning(f"Unknown connection: {connection_name}")

    def get_connection_status(self, connection_name: str = None) -> Dict[str, Any]:
        """Get status for specific connection or all connections"""
        if connection_name:
            if connection_name in self.handlers:
                return {
                    connection_name: self.handlers[connection_name].get_connection_stats()
                }
            else:
                return {connection_name: {'error': 'Connection not found'}}
        else:
            # Return status for all connections
            status = {}
            for name, handler in self.handlers.items():
                status[name] = handler.get_connection_stats()
            return status

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global connection statistics"""
        active_count = sum(1 for h in self.handlers.values()
                          if h.connection_state == ConnectionState.CONNECTED)

        self.global_stats['active_connections'] = active_count
        self.global_stats['failed_connections'] = sum(
            h.failed_connections for h in self.handlers.values()
        )

        return self.global_stats.copy()

    async def graceful_shutdown(self):
        """Gracefully shutdown all connections"""
        logger.info("Initiating graceful shutdown of all connections")

        shutdown_tasks = []
        for name, handler in self.handlers.items():
            logger.info(f"Stopping reconnection for {name}")
            handler.stop_reconnection()
            shutdown_tasks.append(self._shutdown_connection(name, handler))

        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        logger.info("Graceful shutdown completed")

    async def _shutdown_connection(self, name: str, handler: ReconnectHandler):
        """Shutdown individual connection"""
        try:
            # Attempt clean disconnect
            if hasattr(handler.connection_manager, 'disconnect'):
                await handler.connection_manager.disconnect()
            logger.info(f"Successfully shutdown connection {name}")
        except Exception as e:
            logger.error(f"Error shutting down connection {name}: {e}")

# Global reconnect manager instance
_global_reconnect_manager = None

def get_reconnect_manager() -> WebSocketReconnectManager:
    """Get global reconnect manager instance"""
    global _global_reconnect_manager
    if _global_reconnect_manager is None:
        _global_reconnect_manager = WebSocketReconnectManager()
    return _global_reconnect_manager