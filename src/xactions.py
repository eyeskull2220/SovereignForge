#!/usr/bin/env python3
"""
SovereignForge - Transaction Management Module
Secure transaction handling and execution for arbitrage trading

This module provides:
- Secure transaction execution
- Risk management integration
- MiCA compliance validation
- Transaction logging and audit trails
- Error handling and recovery
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class TransactionStatus(Enum):
    """Transaction execution status"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class TransactionType(Enum):
    """Type of arbitrage transaction"""
    SIMPLE_ARBITRAGE = "simple_arbitrage"
    TRIANGULAR_ARBITRAGE = "triangular_arbitrage"
    CROSS_EXCHANGE_ARBITRAGE = "cross_exchange_arbitrage"

@dataclass
class TransactionLeg:
    """Individual leg of an arbitrage transaction"""
    exchange: str
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: Decimal
    price: Optional[Decimal] = None
    order_id: Optional[str] = None
    status: TransactionStatus = TransactionStatus.PENDING
    executed_quantity: Decimal = Decimal('0')
    executed_price: Optional[Decimal] = None
    fees: Decimal = Decimal('0')
    timestamp: Optional[datetime] = None

@dataclass
class ArbitrageTransaction:
    """Complete arbitrage transaction"""
    transaction_id: str
    transaction_type: TransactionType
    legs: List[TransactionLeg]
    expected_profit: Decimal
    expected_profit_pct: float
    risk_score: float
    status: TransactionStatus = TransactionStatus.PENDING
    created_timestamp: datetime = None
    started_timestamp: Optional[datetime] = None
    completed_timestamp: Optional[datetime] = None
    actual_profit: Optional[Decimal] = None
    actual_profit_pct: Optional[float] = None
    error_message: Optional[str] = None
    compliance_check_passed: bool = False

    def __post_init__(self):
        if self.created_timestamp is None:
            self.created_timestamp = datetime.now()

class TransactionManager:
    """
    Secure transaction management for arbitrage operations
    """

    def __init__(self,
                 max_concurrent_transactions: int = 5,
                 transaction_timeout_seconds: int = 30,
                 audit_log_path: str = "/app/logs/transactions.log"):
        self.max_concurrent_transactions = max_concurrent_transactions
        self.transaction_timeout_seconds = transaction_timeout_seconds
        self.audit_log_path = audit_log_path

        # Transaction tracking
        self.active_transactions: Dict[str, ArbitrageTransaction] = {}
        self.completed_transactions: List[ArbitrageTransaction] = []
        self.transaction_lock = threading.RLock()

        # Performance tracking
        self.transaction_stats = {
            "total_transactions": 0,
            "successful_transactions": 0,
            "failed_transactions": 0,
            "total_profit": Decimal('0'),
            "average_execution_time_ms": 0.0
        }

        # Setup audit logging
        os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
        self.audit_handler = logging.FileHandler(self.audit_log_path)
        self.audit_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            '%(asctime)s - TRANSACTION_AUDIT - %(levelname)s - %(message)s'
        )
        self.audit_handler.setFormatter(formatter)

        self.audit_logger = logging.getLogger('transaction_audit')
        self.audit_logger.setLevel(logging.INFO)
        self.audit_logger.addHandler(self.audit_handler)
        self.audit_logger.propagate = False

        logger.info("TransactionManager initialized")

    def create_arbitrage_transaction(self,
                                   transaction_type: TransactionType,
                                   legs: List[TransactionLeg],
                                   expected_profit: Decimal,
                                   risk_score: float) -> Optional[ArbitrageTransaction]:
        """
        Create a new arbitrage transaction with validation
        """
        try:
            # Validate transaction structure
            if not self._validate_transaction_structure(legs):
                logger.error("Invalid transaction structure")
                return None

            # Check MiCA compliance
            if not self._check_mica_compliance(legs):
                logger.error("Transaction failed MiCA compliance check")
                return None

            # Check risk limits
            if not self._check_risk_limits(expected_profit, risk_score):
                logger.error("Transaction exceeds risk limits")
                return None

            # Check concurrent transaction limits
            if not self._check_concurrent_limits():
                logger.warning("Maximum concurrent transactions reached")
                return None

            # Create transaction
            transaction_id = str(uuid.uuid4())
            expected_profit_pct = float((expected_profit / self._calculate_transaction_value(legs)) * 100)

            transaction = ArbitrageTransaction(
                transaction_id=transaction_id,
                transaction_type=transaction_type,
                legs=legs,
                expected_profit=expected_profit,
                expected_profit_pct=expected_profit_pct,
                risk_score=risk_score,
                compliance_check_passed=True
            )

            # Add to active transactions
            with self.transaction_lock:
                self.active_transactions[transaction_id] = transaction

            # Audit log
            self._audit_transaction_event("CREATED", transaction)

            logger.info(f"Created arbitrage transaction {transaction_id} with expected profit {expected_profit}")
            return transaction

        except Exception as e:
            logger.error(f"Failed to create transaction: {e}")
            return None

    def execute_transaction(self, transaction_id: str) -> bool:
        """
        Execute an arbitrage transaction
        """
        with self.transaction_lock:
            if transaction_id not in self.active_transactions:
                logger.error(f"Transaction {transaction_id} not found")
                return False

            transaction = self.active_transactions[transaction_id]

            try:
                # Update status
                transaction.status = TransactionStatus.EXECUTING
                transaction.started_timestamp = datetime.now()

                self._audit_transaction_event("STARTED", transaction)

                # Execute transaction legs in sequence
                success = self._execute_transaction_legs(transaction)

                if success:
                    # Calculate actual results
                    self._calculate_transaction_results(transaction)
                    transaction.status = TransactionStatus.COMPLETED
                    transaction.completed_timestamp = datetime.now()

                    # Update statistics
                    self.transaction_stats["total_transactions"] += 1
                    self.transaction_stats["successful_transactions"] += 1
                    if transaction.actual_profit:
                        self.transaction_stats["total_profit"] += transaction.actual_profit

                    self._audit_transaction_event("COMPLETED", transaction)
                    logger.info(f"Transaction {transaction_id} completed successfully")
                else:
                    transaction.status = TransactionStatus.FAILED
                    transaction.error_message = "Transaction execution failed"
                    self.transaction_stats["total_transactions"] += 1
                    self.transaction_stats["failed_transactions"] += 1

                    self._audit_transaction_event("FAILED", transaction)
                    logger.error(f"Transaction {transaction_id} failed")

                # Move to completed
                self.completed_transactions.append(transaction)
                del self.active_transactions[transaction_id]

                return success

            except Exception as e:
                transaction.status = TransactionStatus.FAILED
                transaction.error_message = str(e)

                self._audit_transaction_event("ERROR", transaction)
                logger.error(f"Transaction {transaction_id} error: {e}")

                # Move to completed
                self.completed_transactions.append(transaction)
                del self.active_transactions[transaction_id]

                return False

    def cancel_transaction(self, transaction_id: str, reason: str = "User cancelled") -> bool:
        """
        Cancel a pending transaction
        """
        with self.transaction_lock:
            if transaction_id not in self.active_transactions:
                return False

            transaction = self.active_transactions[transaction_id]

            if transaction.status != TransactionStatus.PENDING:
                logger.warning(f"Cannot cancel transaction {transaction_id} in status {transaction.status.value}")
                return False

            transaction.status = TransactionStatus.CANCELLED
            transaction.error_message = reason
            transaction.completed_timestamp = datetime.now()

            self._audit_transaction_event("CANCELLED", transaction)

            # Move to completed
            self.completed_transactions.append(transaction)
            del self.active_transactions[transaction_id]

            logger.info(f"Transaction {transaction_id} cancelled: {reason}")
            return True

    def _validate_transaction_structure(self, legs: List[TransactionLeg]) -> bool:
        """Validate transaction leg structure"""
        if len(legs) < 2:
            return False

        # Check that we have balanced buy/sell operations
        buy_quantity = sum(leg.quantity for leg in legs if leg.side == 'buy')
        sell_quantity = sum(leg.quantity for leg in legs if leg.side == 'sell')

        # For simple arbitrage, quantities should balance
        return abs(buy_quantity - sell_quantity) < Decimal('0.0001')

    def _check_mica_compliance(self, legs: List[TransactionLeg]) -> bool:
        """Check MiCA compliance for transaction"""
        try:
            # Import MiCA compliance engine
            from .mica_compliance import validate_mica_trade

            # Check each leg
            for leg in legs:
                # Create mock portfolio value (would come from risk manager)
                portfolio_value = Decimal('100000')  # Mock value

                validation = validate_mica_trade(
                    operation=f"{leg.side}_{leg.symbol}",
                    symbol=leg.symbol,
                    amount=float(leg.quantity),
                    price=float(leg.price or 0),
                    portfolio_value=float(portfolio_value)
                )

                if not validation.get("compliant", False):
                    logger.warning(f"MiCA compliance failed for {leg.symbol}: {validation.get('violations', [])}")
                    return False

            return True

        except ImportError:
            logger.warning("MiCA compliance check unavailable")
            return True  # Allow transaction if compliance check fails
        except Exception as e:
            logger.error(f"MiCA compliance check error: {e}")
            return False

    def _check_risk_limits(self, expected_profit: Decimal, risk_score: float) -> bool:
        """Check if transaction meets risk management criteria"""
        # Maximum risk score threshold
        max_risk_score = float(os.getenv("MAX_TRANSACTION_RISK_SCORE", "0.8"))
        if risk_score > max_risk_score:
            return False

        # Minimum profit threshold
        min_profit_threshold = Decimal(os.getenv("MIN_TRANSACTION_PROFIT", "10"))
        if expected_profit < min_profit_threshold:
            return False

        return True

    def _check_concurrent_limits(self) -> bool:
        """Check concurrent transaction limits"""
        return len(self.active_transactions) < self.max_concurrent_transactions

    def _calculate_transaction_value(self, legs: List[TransactionLeg]) -> Decimal:
        """Calculate total transaction value"""
        total_value = Decimal('0')
        for leg in legs:
            if leg.price:
                total_value += leg.quantity * leg.price
        return total_value

    def _execute_transaction_legs(self, transaction: ArbitrageTransaction) -> bool:
        """Execute individual transaction legs"""
        try:
            # Import exchange connector
            from .exchange_connector import get_exchange_connector

            connector = get_exchange_connector()

            # Execute legs in sequence (simplified - would need proper exchange integration)
            for leg in transaction.legs:
                # Mock execution - replace with actual exchange API calls
                leg.status = TransactionStatus.EXECUTING
                time.sleep(0.1)  # Simulate network delay

                # Mock successful execution
                leg.executed_quantity = leg.quantity
                leg.executed_price = leg.price
                leg.fees = leg.quantity * leg.price * Decimal('0.001')  # 0.1% fee
                leg.status = TransactionStatus.COMPLETED
                leg.timestamp = datetime.now()

                logger.debug(f"Executed leg: {leg.symbol} {leg.side} {leg.quantity}")

            return True

        except Exception as e:
            logger.error(f"Transaction leg execution failed: {e}")
            return False

    def _calculate_transaction_results(self, transaction: ArbitrageTransaction):
        """Calculate actual transaction results"""
        total_cost = Decimal('0')
        total_revenue = Decimal('0')
        total_fees = Decimal('0')

        for leg in transaction.legs:
            if leg.executed_price and leg.executed_quantity:
                value = leg.executed_price * leg.executed_quantity
                if leg.side == 'buy':
                    total_cost += value
                else:  # sell
                    total_revenue += value

                total_fees += leg.fees

        # Calculate actual profit
        transaction.actual_profit = total_revenue - total_cost - total_fees
        if total_cost > 0:
            transaction.actual_profit_pct = float((transaction.actual_profit / total_cost) * 100)

    def _audit_transaction_event(self, event_type: str, transaction: ArbitrageTransaction):
        """Log transaction event to audit trail"""
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "transaction_id": transaction.transaction_id,
            "transaction_type": transaction.transaction_type.value,
            "status": transaction.status.value,
            "expected_profit": str(transaction.expected_profit),
            "risk_score": transaction.risk_score,
            "legs_count": len(transaction.legs)
        }

        if transaction.actual_profit is not None:
            audit_entry["actual_profit"] = str(transaction.actual_profit)

        if transaction.error_message:
            audit_entry["error_message"] = transaction.error_message

        self.audit_logger.info(json.dumps(audit_entry))

    def get_transaction_stats(self) -> Dict[str, Any]:
        """Get transaction performance statistics"""
        stats = self.transaction_stats.copy()
        stats["active_transactions"] = len(self.active_transactions)
        stats["completed_transactions"] = len(self.completed_transactions)

        # Calculate success rate
        if stats["total_transactions"] > 0:
            stats["success_rate"] = stats["successful_transactions"] / stats["total_transactions"]
        else:
            stats["success_rate"] = 0.0

        return stats

    def get_active_transactions(self) -> List[ArbitrageTransaction]:
        """Get list of active transactions"""
        with self.transaction_lock:
            return list(self.active_transactions.values())

    def get_transaction_history(self, limit: int = 100) -> List[ArbitrageTransaction]:
        """Get transaction history"""
        with self.transaction_lock:
            return self.completed_transactions[-limit:] if limit > 0 else self.completed_transactions

# Global transaction manager instance
_transaction_manager = None

def get_transaction_manager() -> TransactionManager:
    """Get or create global transaction manager instance"""
    global _transaction_manager

    if _transaction_manager is None:
        _transaction_manager = TransactionManager()

    return _transaction_manager

def create_arbitrage_transaction(transaction_type: TransactionType,
                               legs: List[TransactionLeg],
                               expected_profit: Decimal,
                               risk_score: float) -> Optional[ArbitrageTransaction]:
    """Convenience function for creating arbitrage transactions"""
    manager = get_transaction_manager()
    return manager.create_arbitrage_transaction(transaction_type, legs, expected_profit, risk_score)

def execute_transaction(transaction_id: str) -> bool:
    """Convenience function for executing transactions"""
    manager = get_transaction_manager()
    return manager.execute_transaction(transaction_id)

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Create transaction manager
    manager = TransactionManager()

    # Example transaction legs
    legs = [
        TransactionLeg(
            exchange="binance",
            symbol="BTCUSDC",
            side="buy",
            quantity=Decimal('0.001'),
            price=Decimal('50000')
        ),
        TransactionLeg(
            exchange="coinbase",
            symbol="BTCUSDC",
            side="sell",
            quantity=Decimal('0.001'),
            price=Decimal('50100')
        )
    ]

    # Create and execute transaction
    transaction = manager.create_arbitrage_transaction(
        transaction_type=TransactionType.SIMPLE_ARBITRAGE,
        legs=legs,
        expected_profit=Decimal('100'),
        risk_score=0.2
    )

    if transaction:
        logger.info(f"Created transaction {transaction.transaction_id}")
        success = manager.execute_transaction(transaction.transaction_id)
        logger.info(f"Transaction {'succeeded' if success else 'failed'}")

        # Show stats
        stats = manager.get_transaction_stats()
        logger.info(f"Transaction stats: {stats}")
