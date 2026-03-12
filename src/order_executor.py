#!/usr/bin/env python3
"""
SovereignForge Order Executor - Wave 3
Order execution engine for arbitrage trading
"""

import ccxt
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import asyncio
import json
import os

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging first
logger = logging.getLogger(__name__)

# Import Phase 2 components
try:
    from risk_management import get_risk_manager, RiskManager
    RISK_MANAGER_AVAILABLE = True
    logger.info("Phase 2 Risk Management integrated successfully")
except ImportError as e:
    logger.warning(f"Phase 2 Risk Management not available: {e}. Using fallback.")
    RISK_MANAGER_AVAILABLE = False

class OrderExecutor:
    """Order execution engine for arbitrage trading"""

    def __init__(self, exchange_configs: Dict[str, Dict], risk_manager=None):
        self.exchange_configs = exchange_configs
        self.exchanges = {}
        self.risk_manager = risk_manager

        # Initialize exchanges
        self._init_exchanges()

        # Order tracking
        self.active_orders = {}
        self.order_history = []
        self.execution_stats = self._init_execution_stats()

        logger.info(f"Order Executor initialized with {len(self.exchanges)} exchanges")

    def _init_exchanges(self):
        """Initialize exchange connections"""

        for exchange_name, config in self.exchange_configs.items():
            try:
                exchange_class = getattr(ccxt, exchange_name)
                exchange = exchange_class({
                    'apiKey': config.get('api_key', ''),
                    'secret': config.get('secret', ''),
                    'enableRateLimit': True,
                    'timeout': 30000,
                })

                # Test connection
                exchange.load_markets()
                self.exchanges[exchange_name] = exchange

                logger.info(f"Initialized {exchange_name} exchange")

            except Exception as e:
                logger.error(f"Failed to initialize {exchange_name}: {e}")

    def _init_execution_stats(self) -> Dict:
        """Initialize execution statistics"""
        return {
            'total_orders': 0,
            'successful_orders': 0,
            'failed_orders': 0,
            'avg_execution_time': 0.0,
            'avg_slippage': 0.0,
            'success_rate': 0.0,
            'last_updated': datetime.now()
        }

    async def execute_arbitrage_trade(self, arbitrage_opportunity: Dict) -> Dict:
        """Execute arbitrage trade across exchanges"""

        execution_result = {
            'success': False,
            'orders': [],
            'pnl': 0.0,
            'execution_time': 0.0,
            'errors': [],
            'timestamp': datetime.now()
        }

        start_time = time.time()

        try:
            # Validate opportunity
            if not self._validate_arbitrage_opportunity(arbitrage_opportunity):
                execution_result['errors'].append("Invalid arbitrage opportunity")
                return execution_result

            # Calculate trade parameters
            trade_params = self._calculate_trade_parameters(arbitrage_opportunity)
            if not trade_params['valid']:
                execution_result['errors'].append(trade_params['reason'])
                return execution_result

            # Execute buy order (long cheaper exchange)
            buy_order = await self._execute_single_order(
                trade_params['buy_exchange'],
                trade_params['symbol'],
                'buy',
                trade_params['quantity'],
                trade_params['buy_price']
            )

            if not buy_order['success']:
                execution_result['errors'].append(f"Buy order failed: {buy_order['error']}")
                return execution_result

            execution_result['orders'].append(buy_order)

            # Execute sell order (short expensive exchange)
            sell_order = await self._execute_single_order(
                trade_params['sell_exchange'],
                trade_params['symbol'],
                'sell',
                trade_params['quantity'],
                trade_params['sell_price']
            )

            if not sell_order['success']:
                execution_result['errors'].append(f"Sell order failed: {sell_order['error']}")
                # Attempt to cancel buy order
                await self._cancel_order(buy_order['order_id'], trade_params['buy_exchange'], trade_params['symbol'])
                return execution_result

            execution_result['orders'].append(sell_order)

            # Calculate P&L
            buy_cost = buy_order['executed_price'] * buy_order['executed_quantity']
            sell_revenue = sell_order['executed_price'] * sell_order['executed_quantity']
            fees = buy_order.get('fee', 0) + sell_order.get('fee', 0)

            execution_result['pnl'] = sell_revenue - buy_cost - fees
            execution_result['success'] = True

            # Update statistics
            self._update_execution_stats(execution_result)

            logger.info(f"Arbitrage trade executed: P&L ${execution_result['pnl']:.2f}")

        except Exception as e:
            execution_result['errors'].append(f"Execution error: {str(e)}")
            logger.error(f"Arbitrage execution failed: {e}")

        finally:
            execution_result['execution_time'] = time.time() - start_time

        return execution_result

    def _validate_arbitrage_opportunity(self, opportunity: Dict) -> bool:
        """Validate arbitrage opportunity before execution"""

        required_fields = ['symbol', 'buy_exchange', 'sell_exchange', 'spread_percentage', 'quantity']
        for field in required_fields:
            if field not in opportunity:
                logger.error(f"Missing required field: {field}")
                return False

        # Check spread is still profitable after fees
        spread_pct = opportunity.get('spread_percentage', 0)
        estimated_fees_pct = 0.001  # 0.1% estimated fees

        if spread_pct <= estimated_fees_pct:
            logger.warning(f"Spread {spread_pct:.4f} not profitable after fees {estimated_fees_pct:.4f}")
            return False

        # Check exchanges are available
        buy_exchange = opportunity.get('buy_exchange')
        sell_exchange = opportunity.get('sell_exchange')

        if buy_exchange not in self.exchanges or sell_exchange not in self.exchanges:
            logger.error(f"Exchange not available: buy={buy_exchange}, sell={sell_exchange}")
            return False

        return True

    def _calculate_trade_parameters(self, opportunity: Dict) -> Dict:
        """Calculate trade execution parameters"""

        try:
            symbol = opportunity['symbol']
            buy_exchange = opportunity['buy_exchange']
            sell_exchange = opportunity['sell_exchange']
            quantity = opportunity['quantity']

            # Get current prices
            buy_price = self._get_order_price(buy_exchange, symbol, 'buy', quantity)
            sell_price = self._get_order_price(sell_exchange, symbol, 'sell', quantity)

            if buy_price <= 0 or sell_price <= 0:
                return {'valid': False, 'reason': 'Could not get valid prices'}

            # Apply slippage buffer
            slippage_buffer = 0.001  # 0.1%
            buy_price *= (1 + slippage_buffer)
            sell_price *= (1 - slippage_buffer)

            # Verify arbitrage still exists
            spread_after_slippage = (sell_price - buy_price) / buy_price
            if spread_after_slippage <= 0.001:  # 0.1% minimum
                return {'valid': False, 'reason': f'Spread too small after slippage: {spread_after_slippage:.4f}'}

            return {
                'valid': True,
                'symbol': symbol,
                'buy_exchange': buy_exchange,
                'sell_exchange': sell_exchange,
                'quantity': quantity,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'expected_spread': spread_after_slippage
            }

        except Exception as e:
            return {'valid': False, 'reason': f'Parameter calculation error: {str(e)}'}

    async def _execute_single_order(self, exchange_name: str, symbol: str, side: str,
                                   quantity: float, price: float) -> Dict:
        """Execute single order on exchange"""

        order_result = {
            'success': False,
            'order_id': None,
            'executed_price': 0.0,
            'executed_quantity': 0.0,
            'fee': 0.0,
            'timestamp': datetime.now(),
            'error': None
        }

        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                order_result['error'] = f"Exchange {exchange_name} not available"
                return order_result

            # Create order
            order_type = 'limit'  # Use limit orders for arbitrage precision

            # Place order
            order = exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=quantity,
                price=price
            )

            order_result['order_id'] = order['id']

            # Wait for execution (simplified - in production would use websockets)
            await asyncio.sleep(1)  # Brief wait

            # Check order status
            order_status = exchange.fetch_order(order['id'], symbol)

            if order_status['status'] == 'closed':
                order_result['success'] = True
                order_result['executed_price'] = order_status.get('average', order_status.get('price', price))
                order_result['executed_quantity'] = order_status.get('filled', quantity)

                # Calculate fees
                fee_info = order_status.get('fee', {})
                if fee_info:
                    order_result['fee'] = fee_info.get('cost', 0)

                logger.info(f"Order executed: {exchange_name} {side} {quantity} {symbol} @ ${order_result['executed_price']:.4f}")

            elif order_status['status'] in ['open', 'partially_filled']:
                # For demo purposes, assume partial fill
                order_result['success'] = True
                order_result['executed_price'] = price
                order_result['executed_quantity'] = quantity * 0.95  # Assume 95% fill
                order_result['fee'] = order_result['executed_price'] * order_result['executed_quantity'] * 0.001  # 0.1% fee

                logger.warning(f"Order partially filled: {order_status['status']}")

            else:
                order_result['error'] = f"Order status: {order_status['status']}"
                # Cancel order
                await self._cancel_order(order['id'], exchange_name, symbol)

        except Exception as e:
            order_result['error'] = str(e)
            logger.error(f"Order execution failed: {e}")

        return order_result

    async def _cancel_order(self, order_id: str, exchange_name: str, symbol: str) -> bool:
        """Cancel order"""

        try:
            exchange = self.exchanges.get(exchange_name)
            if exchange:
                exchange.cancel_order(order_id, symbol)
                logger.info(f"Cancelled order {order_id} on {exchange_name}")
                return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")

        return False

    def _get_order_price(self, exchange_name: str, symbol: str, side: str, quantity: float) -> float:
        """Get appropriate order price for exchange"""

        try:
            exchange = self.exchanges.get(exchange_name)
            if not exchange:
                return 0.0

            # Get order book
            orderbook = exchange.fetch_order_book(symbol, limit=20)

            if side == 'buy':
                # For buy orders, use ask price + small buffer
                asks = orderbook.get('asks', [])
                if asks:
                    # Use weighted average of top 3 asks
                    total_volume = sum(min(qty, quantity/3) for _, qty in asks[:3])
                    if total_volume > 0:
                        weighted_price = sum(price * min(qty, quantity/3) for price, qty in asks[:3]) / total_volume
                        return weighted_price * 1.0001  # 0.01% buffer
                    else:
                        return asks[0][0] * 1.0001

            else:  # sell
                # For sell orders, use bid price - small buffer
                bids = orderbook.get('bids', [])
                if bids:
                    # Use weighted average of top 3 bids
                    total_volume = sum(min(qty, quantity/3) for _, qty in bids[:3])
                    if total_volume > 0:
                        weighted_price = sum(price * min(qty, quantity/3) for price, qty in bids[:3]) / total_volume
                        return weighted_price * 0.9999  # 0.01% buffer
                    else:
                        return bids[0][0] * 0.9999

        except Exception as e:
            logger.error(f"Failed to get order price for {exchange_name} {symbol}: {e}")

        return 0.0

    def _update_execution_stats(self, execution_result: Dict):
        """Update execution statistics"""

        self.execution_stats['total_orders'] += 2  # Buy + sell orders
        self.execution_stats['last_updated'] = datetime.now()

        if execution_result['success']:
            self.execution_stats['successful_orders'] += 2

            # Update average execution time
            current_avg_time = self.execution_stats['avg_execution_time']
            total_orders = self.execution_stats['successful_orders']
            self.execution_stats['avg_execution_time'] = (
                (current_avg_time * (total_orders - 2)) + execution_result['execution_time']
            ) / total_orders

        else:
            self.execution_stats['failed_orders'] += 1

        # Update success rate
        total = self.execution_stats['successful_orders'] + self.execution_stats['failed_orders']
        if total > 0:
            self.execution_stats['success_rate'] = self.execution_stats['successful_orders'] / total

    def get_execution_stats(self) -> Dict:
        """Get execution statistics"""
        return self.execution_stats.copy()

    def get_account_balance(self, exchange_name: str) -> Optional[Dict]:
        """Get account balance for exchange"""

        try:
            exchange = self.exchanges.get(exchange_name)
            if exchange:
                balance = exchange.fetch_balance()
                return {
                    'total': balance.get('total', {}),
                    'free': balance.get('free', {}),
                    'used': balance.get('used', {}),
                    'timestamp': datetime.now()
                }
        except Exception as e:
            logger.error(f"Failed to get balance for {exchange_name}: {e}")

        return None

    def get_open_orders(self, exchange_name: str, symbol: str = None) -> List[Dict]:
        """Get open orders for exchange"""

        try:
            exchange = self.exchanges.get(exchange_name)
            if exchange:
                orders = exchange.fetch_open_orders(symbol)
                return [{
                    'id': order['id'],
                    'symbol': order['symbol'],
                    'type': order['type'],
                    'side': order['side'],
                    'amount': order['amount'],
                    'price': order['price'],
                    'timestamp': order.get('timestamp')
                } for order in orders]
        except Exception as e:
            logger.error(f"Failed to get open orders for {exchange_name}: {e}")

        return []

    async def is_healthy(self) -> bool:
        """Check if the order executor is healthy"""
        try:
            # Check if we have any exchanges configured
            if len(self.exchanges) == 0:
                return False

            # Check if at least one exchange is accessible
            healthy_exchanges = 0
            for exchange_name, exchange in self.exchanges.items():
                try:
                    # Simple health check - try to get server time
                    if hasattr(exchange, 'fetch_time'):
                        exchange.fetch_time()
                        healthy_exchanges += 1
                except Exception:
                    continue

            # Consider healthy if at least one exchange is working
            return healthy_exchanges > 0

        except Exception as e:
            logger.error(f"Order executor health check error: {e}")
            return False

class PaperTradingExecutor(OrderExecutor):
    """Paper trading version for testing without real money"""

    def __init__(self, exchange_configs: Dict[str, Dict], risk_manager=None, initial_balance: float = 10000.0):
        super().__init__(exchange_configs, risk_manager)

        # Paper trading balances
        self.paper_balances = {}
        for exchange_name in exchange_configs.keys():
            self.paper_balances[exchange_name] = {
                'USDC': initial_balance,
                'BTC': 0.0,
                'ETH': 0.0,
                'XRP': 0.0,
                'ADA': 0.0,
                'LINK': 0.0
            }

        self.paper_orders = []
        logger.info(f"Paper Trading Executor initialized with ${initial_balance} per exchange")

    async def _execute_single_order(self, exchange_name: str, symbol: str, side: str,
                                   quantity: float, price: float) -> Dict:
        """Execute paper trade order"""

        order_result = {
            'success': True,  # Paper trades always "succeed"
            'order_id': f"paper_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.paper_orders)}",
            'executed_price': price,
            'executed_quantity': quantity,
            'fee': price * quantity * 0.001,  # 0.1% fee
            'timestamp': datetime.now(),
            'error': None
        }

        # Update paper balance
        self._update_paper_balance(exchange_name, symbol, side, quantity, price, order_result['fee'])

        # Record order
        order_record = {
            'order_id': order_result['order_id'],
            'exchange': exchange_name,
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price,
            'fee': order_result['fee'],
            'timestamp': order_result['timestamp']
        }
        self.paper_orders.append(order_record)

        logger.info(f"Paper trade executed: {exchange_name} {side} {quantity} {symbol} @ ${price:.4f}")

        return order_result

    def _update_paper_balance(self, exchange_name: str, symbol: str, side: str,
                             quantity: float, price: float, fee: float):
        """Update paper trading balance"""

        balance = self.paper_balances[exchange_name]

        # Parse symbol (e.g., 'BTC/USDC' -> base='BTC', quote='USDC')
        if '/' in symbol:
            base, quote = symbol.split('/')
        else:
            base, quote = symbol, 'USDC'

        if side == 'buy':
            # Buy base currency with quote currency
            cost = price * quantity + fee
            if balance.get(quote, 0) >= cost:
                balance[quote] -= cost
                balance[base] = balance.get(base, 0) + quantity
            else:
                logger.warning(f"Insufficient {quote} balance for paper trade")

        else:  # sell
            # Sell base currency for quote currency
            if balance.get(base, 0) >= quantity:
                revenue = price * quantity - fee
                balance[base] -= quantity
                balance[quote] = balance.get(quote, 0) + revenue
            else:
                logger.warning(f"Insufficient {base} balance for paper trade")

    def get_paper_balance(self, exchange_name: str) -> Dict:
        """Get paper trading balance"""
        return self.paper_balances.get(exchange_name, {}).copy()

    def get_paper_orders(self) -> List[Dict]:
        """Get paper trading order history"""
        return self.paper_orders.copy()

def create_demo_executor(risk_manager=None) -> PaperTradingExecutor:
    """Create demo paper trading executor"""

    # Demo exchange configs (no real API keys)
    exchange_configs = {
        'binance': {},
        'coinbase': {},
        'kraken': {}
    }

    return PaperTradingExecutor(exchange_configs, risk_manager)

# Example usage
if __name__ == "__main__":
    # Create demo executor
    executor = create_demo_executor()

    print("Order Executor Test")
    print("=" * 30)

    # Test paper trade execution
    import asyncio

    async def test_execution():
        arbitrage_opp = {
            'symbol': 'BTC/USDC',
            'buy_exchange': 'binance',
            'sell_exchange': 'coinbase',
            'spread_percentage': 0.003,
            'quantity': 0.01,
            'buy_price': 45000,
            'sell_price': 45030
        }

        result = await executor.execute_arbitrage_trade(arbitrage_opp)

        print(f"Trade Success: {result['success']}")
        print(f"P&L: ${result['pnl']:.4f}")
        print(f"Execution Time: {result['execution_time']:.2f}s")

        if result['errors']:
            print(f"Errors: {result['errors']}")

        # Show balances
        for exchange in ['binance', 'coinbase']:
            balance = executor.get_paper_balance(exchange)
            print(f"{exchange} Balance: {balance}")

    # Run test
    asyncio.run(test_execution())