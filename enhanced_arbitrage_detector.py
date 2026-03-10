#!/usr/bin/env python3
"""
Enhanced Arbitrage Detector with Smart Money Concepts
Integrates SMC indicators for sophisticated arbitrage detection
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import sys
import os

# Add smart-money-concepts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'smart-money-concepts'))

try:
    # Handle Windows encoding issues with SMC library
    import io
    import sys
    original_stdout = sys.stdout
    sys.stdout = io.StringIO()

    from smartmoneyconcepts.smc import smc

    # Restore stdout and suppress the welcome message
    output = sys.stdout.getvalue()
    sys.stdout = original_stdout

    SMC_AVAILABLE = True
    logging.info("Smart Money Concepts library loaded successfully")
except (ImportError, UnicodeEncodeError) as e:
    SMC_AVAILABLE = False
    logging.warning(f"Smart Money Concepts library not available: {e}")
except Exception as e:
    SMC_AVAILABLE = False
    logging.warning(f"Error loading Smart Money Concepts: {e}")

from multi_exchange_integration import MultiExchangeManager
from risk_management import RiskManager

class EnhancedArbitrageDetector:
    """Enhanced arbitrage detector with smart money concepts integration"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.exchange_integration = MultiExchangeManager()
        self.risk_manager = RiskManager(config)

        # SMC parameters
        self.swing_length = config.get('smc_swing_length', 50)
        self.fvg_join_consecutive = config.get('fvg_join_consecutive', False)
        self.liquidity_range_percent = config.get('liquidity_range_percent', 0.01)

        # Arbitrage parameters
        self.min_spread_pct = config.get('min_spread_pct', 0.1)
        self.max_spread_pct = config.get('max_spread_pct', 2.0)
        self.min_volume_threshold = config.get('min_volume_threshold', 1000)
        self.max_execution_time = config.get('max_execution_time', 30)

        # Smart money filters
        self.require_fvg_alignment = config.get('require_fvg_alignment', True)
        self.require_bos_confirmation = config.get('require_bos_confirmation', False)
        self.liquidity_filter_enabled = config.get('liquidity_filter_enabled', True)

        # Cache for SMC calculations
        self.smc_cache = {}
        self.last_update = {}

    async def detect_arbitrage_opportunities(self, pairs: List[str]) -> List[Dict[str, Any]]:
        """
        Detect arbitrage opportunities using smart money concepts

        Args:
            pairs: List of trading pairs to analyze

        Returns:
            List of arbitrage opportunities with SMC analysis
        """
        opportunities = []

        for pair in pairs:
            try:
                # Get market data from all exchanges
                market_data = await self._get_multi_exchange_data(pair)

                if not market_data:
                    continue

                # Apply smart money analysis
                smc_signals = self._analyze_smart_money_signals(market_data, pair)

                # Detect traditional arbitrage
                traditional_arbs = self._detect_traditional_arbitrage(market_data, pair)

                # Filter and enhance with SMC
                enhanced_opportunities = self._enhance_with_smc_signals(
                    traditional_arbs, smc_signals, pair
                )

                opportunities.extend(enhanced_opportunities)

            except Exception as e:
                self.logger.error(f"Error analyzing {pair}: {e}")
                continue

        # Sort by expected profit and risk-adjusted return
        opportunities.sort(key=lambda x: x.get('risk_adjusted_return', 0), reverse=True)

        return opportunities

    async def _get_multi_exchange_data(self, pair: str) -> Optional[Dict[str, Any]]:
        """Get market data from all configured exchanges"""
        try:
            # Get price data from all exchanges
            all_prices = await self.exchange_integration.get_all_prices([pair])

            if not all_prices or pair not in all_prices:
                return None

            prices = all_prices[pair]

            # Structure the data for SMC analysis
            market_data = {
                'pair': pair,
                'timestamp': datetime.utcnow(),
                'prices': prices,
                'exchanges': list(prices.keys())
            }

            return market_data

        except Exception as e:
            self.logger.error(f"Error getting market data for {pair}: {e}")
            return None

    def _analyze_smart_money_signals(self, market_data: Dict[str, Any], pair: str) -> Dict[str, Any]:
        """
        Analyze smart money concepts for the trading pair

        Args:
            market_data: Multi-exchange market data
            pair: Trading pair

        Returns:
            Dictionary with SMC analysis results
        """
        if not SMC_AVAILABLE:
            return {'available': False}

        try:
            # Get OHLCV data for SMC analysis (use primary exchange)
            primary_exchange = market_data['exchanges'][0]
            ohlcv_data = self._get_ohlcv_for_smc(market_data, primary_exchange)

            if ohlcv_data is None or len(ohlcv_data) < 100:
                return {'available': False, 'reason': 'insufficient_data'}

            # Calculate SMC indicators
            smc_results = {}

            # Fair Value Gaps
            smc_results['fvg'] = smc.fvg(ohlcv_data, join_consecutive=self.fvg_join_consecutive)

            # Swing Highs and Lows
            smc_results['swing_hl'] = smc.swing_highs_lows(ohlcv_data, swing_length=self.swing_length)

            # Break of Structure / Change of Character
            if not smc_results['swing_hl'].empty:
                smc_results['bos_choch'] = smc.bos_choch(ohlcv_data, smc_results['swing_hl'])

            # Order Blocks
            if not smc_results['swing_hl'].empty:
                smc_results['order_blocks'] = smc.ob(ohlcv_data, smc_results['swing_hl'])

            # Liquidity Analysis
            if not smc_results['swing_hl'].empty:
                smc_results['liquidity'] = smc.liquidity(
                    ohlcv_data, smc_results['swing_hl'],
                    range_percent=self.liquidity_range_percent
                )

            # Current market bias based on SMC
            market_bias = self._calculate_market_bias(smc_results)

            return {
                'available': True,
                'indicators': smc_results,
                'market_bias': market_bias,
                'last_update': datetime.utcnow()
            }

        except Exception as e:
            self.logger.error(f"Error in SMC analysis for {pair}: {e}")
            return {'available': False, 'error': str(e)}

    def _get_ohlcv_for_smc(self, market_data: Dict[str, Any], exchange: str) -> Optional[pd.DataFrame]:
        """Get OHLCV data formatted for SMC analysis"""
        try:
            # This would typically come from historical data storage
            # For now, create synthetic data from order book snapshots
            # In production, this should pull from your historical database

            # Placeholder - return None to indicate real implementation needed
            return None

        except Exception as e:
            self.logger.error(f"Error getting OHLCV data: {e}")
            return None

    def _calculate_market_bias(self, smc_results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall market bias from SMC indicators"""
        bias_score = 0
        signals = []

        try:
            # Analyze recent FVG (last 5 candles)
            if 'fvg' in smc_results and not smc_results['fvg'].empty:
                recent_fvg = smc_results['fvg'].tail(5)
                bullish_fvg = (recent_fvg['FVG'] == 1).sum()
                bearish_fvg = (recent_fvg['FVG'] == -1).sum()

                if bullish_fvg > bearish_fvg:
                    bias_score += 1
                    signals.append('bullish_fvg_dominance')
                elif bearish_fvg > bullish_fvg:
                    bias_score -= 1
                    signals.append('bearish_fvg_dominance')

            # Analyze BOS/CHOCH
            if 'bos_choch' in smc_results and not smc_results['bos_choch'].empty:
                recent_bos = smc_results['bos_choch'].tail(3)
                bullish_bos = (recent_bos['BOS'] == 1).sum()
                bearish_bos = (recent_bos['BOS'] == -1).sum()

                if bullish_bos > bearish_bos:
                    bias_score += 2
                    signals.append('bullish_bos')
                elif bearish_bos > bullish_bos:
                    bias_score -= 2
                    signals.append('bearish_bos')

            # Analyze Order Blocks
            if 'order_blocks' in smc_results and not smc_results['order_blocks'].empty:
                recent_ob = smc_results['order_blocks'].tail(5)
                bullish_ob = (recent_ob['OB'] == 1).sum()
                bearish_ob = (recent_ob['OB'] == -1).sum()

                if bullish_ob > bearish_ob:
                    bias_score += 1
                    signals.append('bullish_order_blocks')
                elif bearish_ob > bullish_ob:
                    bias_score -= 1
                    signals.append('bearish_order_blocks')

        except Exception as e:
            self.logger.error(f"Error calculating market bias: {e}")

        # Determine bias strength
        if abs(bias_score) >= 3:
            strength = 'strong'
        elif abs(bias_score) >= 2:
            strength = 'moderate'
        elif abs(bias_score) >= 1:
            strength = 'weak'
        else:
            strength = 'neutral'

        direction = 'bullish' if bias_score > 0 else 'bearish' if bias_score < 0 else 'neutral'

        return {
            'direction': direction,
            'strength': strength,
            'score': bias_score,
            'signals': signals
        }

    def _detect_traditional_arbitrage(self, market_data: Dict[str, Any], pair: str) -> List[Dict[str, Any]]:
        """Detect traditional cross-exchange arbitrage opportunities"""
        opportunities = []

        try:
            exchanges = market_data['exchanges']
            prices = market_data['prices']

            if len(exchanges) < 2:
                return opportunities

            # Get all price points
            price_list = [(ex, prices[ex]) for ex in exchanges if ex in prices]

            if len(price_list) < 2:
                return opportunities

            # Sort by price to find min and max
            price_list.sort(key=lambda x: x[1])

            # Find arbitrage opportunities
            for i, (low_exchange, low_price) in enumerate(price_list):
                for high_exchange, high_price in price_list[i+1:]:
                    # Calculate spread (buy low, sell high)
                    spread_pct = ((high_price - low_price) / low_price) * 100

                    if spread_pct > self.min_spread_pct:
                        opportunities.append({
                            'type': 'traditional',
                            'pair': pair,
                            'buy_exchange': low_exchange,
                            'sell_exchange': high_exchange,
                            'buy_price': low_price,
                            'sell_price': high_price,
                            'spread_pct': spread_pct,
                            'direction': 'buy_low_sell_high',
                            'timestamp': market_data['timestamp']
                        })

        except Exception as e:
            self.logger.error(f"Error in traditional arbitrage detection: {e}")

        return opportunities

    def _enhance_with_smc_signals(self, traditional_arbs: List[Dict[str, Any]],
                                smc_signals: Dict[str, Any], pair: str) -> List[Dict[str, Any]]:
        """Enhance traditional arbitrage with smart money signals"""
        enhanced_opportunities = []

        for arb in traditional_arbs:
            try:
                # Start with base opportunity
                enhanced_arb = arb.copy()
                enhanced_arb['smc_analysis'] = {}

                if not smc_signals.get('available', False):
                    enhanced_arb['smc_confidence'] = 0.5  # Neutral
                    enhanced_opportunities.append(enhanced_arb)
                    continue

                confidence_score = 0.5  # Base confidence
                smc_factors = []

                # Check market bias alignment
                market_bias = smc_signals.get('market_bias', {})
                if market_bias.get('direction') == 'bullish' and arb.get('direction') == 'ab':
                    confidence_score += 0.2
                    smc_factors.append('bullish_bias_alignment')
                elif market_bias.get('direction') == 'bearish' and arb.get('direction') == 'ba':
                    confidence_score += 0.2
                    smc_factors.append('bearish_bias_alignment')

                # Check for FVG alignment (if required)
                if self.require_fvg_alignment:
                    fvg_alignment = self._check_fvg_alignment(arb, smc_signals)
                    if fvg_alignment['aligned']:
                        confidence_score += 0.15
                        smc_factors.append('fvg_aligned')
                    else:
                        confidence_score -= 0.1
                        smc_factors.append('fvg_misaligned')

                # Check BOS confirmation (if required)
                if self.require_bos_confirmation:
                    bos_confirmation = self._check_bos_confirmation(arb, smc_signals)
                    if bos_confirmation['confirmed']:
                        confidence_score += 0.25
                        smc_factors.append('bos_confirmed')
                    else:
                        confidence_score -= 0.15
                        smc_factors.append('bos_not_confirmed')

                # Liquidity filter
                if self.liquidity_filter_enabled:
                    liquidity_check = self._check_liquidity_conditions(arb, smc_signals)
                    if liquidity_check['favorable']:
                        confidence_score += 0.1
                        smc_factors.append('favorable_liquidity')
                    else:
                        confidence_score -= 0.1
                        smc_factors.append('unfavorable_liquidity')

                # Calculate risk-adjusted return
                risk_adjusted_return = self._calculate_risk_adjusted_return(
                    arb, confidence_score, smc_signals
                )

                # Update enhanced opportunity
                enhanced_arb['smc_confidence'] = min(max(confidence_score, 0.0), 1.0)
                enhanced_arb['smc_factors'] = smc_factors
                enhanced_arb['risk_adjusted_return'] = risk_adjusted_return
                enhanced_arb['market_bias'] = market_bias

                # Only include if confidence is above threshold
                if confidence_score >= 0.4:
                    enhanced_opportunities.append(enhanced_arb)

            except Exception as e:
                self.logger.error(f"Error enhancing arbitrage opportunity: {e}")
                # Include basic opportunity if enhancement fails
                enhanced_opportunities.append(arb)

        return enhanced_opportunities

    def _check_fvg_alignment(self, arb: Dict[str, Any], smc_signals: Dict[str, Any]) -> Dict[str, bool]:
        """Check if arbitrage direction aligns with Fair Value Gaps"""
        try:
            fvg_data = smc_signals.get('indicators', {}).get('fvg')
            if fvg_data is None or fvg_data.empty:
                return {'aligned': False}

            # Check recent FVG (last 10 candles)
            recent_fvg = fvg_data.tail(10)

            # Count bullish vs bearish FVG
            bullish_fvg = (recent_fvg['FVG'] == 1).sum()
            bearish_fvg = (recent_fvg['FVG'] == -1).sum()

            direction = arb.get('direction')
            if direction == 'ab' and bullish_fvg > bearish_fvg:
                return {'aligned': True}
            elif direction == 'ba' and bearish_fvg > bullish_fvg:
                return {'aligned': True}

            return {'aligned': False}

        except Exception as e:
            self.logger.error(f"Error checking FVG alignment: {e}")
            return {'aligned': False}

    def _check_bos_confirmation(self, arb: Dict[str, Any], smc_signals: Dict[str, Any]) -> Dict[str, bool]:
        """Check if arbitrage aligns with Break of Structure signals"""
        try:
            bos_data = smc_signals.get('indicators', {}).get('bos_choch')
            if bos_data is None or bos_data.empty:
                return {'confirmed': False}

            # Check recent BOS/CHOCH signals
            recent_signals = bos_data.tail(5)

            direction = arb.get('direction')
            if direction == 'ab':
                # Look for bullish BOS/CHOCH
                bullish_signals = ((recent_signals['BOS'] == 1) | (recent_signals['CHOCH'] == 1)).sum()
                return {'confirmed': bullish_signals > 0}
            elif direction == 'ba':
                # Look for bearish BOS/CHOCH
                bearish_signals = ((recent_signals['BOS'] == -1) | (recent_signals['CHOCH'] == -1)).sum()
                return {'confirmed': bearish_signals > 0}

            return {'confirmed': False}

        except Exception as e:
            self.logger.error(f"Error checking BOS confirmation: {e}")
            return {'confirmed': False}

    def _check_liquidity_conditions(self, arb: Dict[str, Any], smc_signals: Dict[str, Any]) -> Dict[str, bool]:
        """Check liquidity conditions for arbitrage execution"""
        try:
            liquidity_data = smc_signals.get('indicators', {}).get('liquidity')
            if liquidity_data is None or liquidity_data.empty:
                return {'favorable': True}  # Neutral if no data

            # Check if there are unfilled liquidity levels that could help execution
            recent_liquidity = liquidity_data.tail(10)

            # Look for liquidity that hasn't been swept yet
            unswept_liquidity = recent_liquidity[recent_liquidity['Swept'].isna()]

            return {'favorable': len(unswept_liquidity) > 0}

        except Exception as e:
            self.logger.error(f"Error checking liquidity conditions: {e}")
            return {'favorable': True}

    def _calculate_risk_adjusted_return(self, arb: Dict[str, Any],
                                       confidence_score: float,
                                       smc_signals: Dict[str, Any]) -> float:
        """Calculate risk-adjusted return incorporating SMC confidence"""
        try:
            base_return = arb.get('spread_pct', 0)

            # Adjust for SMC confidence
            risk_multiplier = confidence_score

            # Factor in market bias strength
            market_bias = smc_signals.get('market_bias', {})
            bias_strength = market_bias.get('strength', 'neutral')

            strength_multipliers = {
                'strong': 1.2,
                'moderate': 1.1,
                'weak': 1.0,
                'neutral': 0.9
            }

            strength_multiplier = strength_multipliers.get(bias_strength, 1.0)

            # Calculate risk-adjusted return
            risk_adjusted_return = base_return * risk_multiplier * strength_multiplier

            return risk_adjusted_return

        except Exception as e:
            self.logger.error(f"Error calculating risk-adjusted return: {e}")
            return arb.get('spread_pct', 0)

    async def execute_arbitrage(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an arbitrage trade with SMC-enhanced risk management"""
        try:
            # Validate opportunity
            if not self._validate_opportunity(opportunity):
                return {'success': False, 'reason': 'validation_failed'}

            # Get SMC confidence for position sizing
            smc_confidence = opportunity.get('smc_confidence', 0.5)

            # Calculate position size based on risk management
            position_size = self.risk_manager.calculate_position_size(
                opportunity, smc_confidence
            )

            if position_size <= 0:
                return {'success': False, 'reason': 'position_size_zero'}

            # Execute the arbitrage trade
            execution_result = await self._execute_cross_exchange_trade(
                opportunity, position_size
            )

            return execution_result

        except Exception as e:
            self.logger.error(f"Error executing arbitrage: {e}")
            return {'success': False, 'error': str(e)}

    def _validate_opportunity(self, opportunity: Dict[str, Any]) -> bool:
        """Validate arbitrage opportunity before execution"""
        try:
            # Check spread is still profitable
            current_spread = opportunity.get('spread_pct', 0)
            if current_spread < self.min_spread_pct:
                return False

            # Check SMC confidence
            smc_confidence = opportunity.get('smc_confidence', 0.5)
            if smc_confidence < 0.4:
                return False

            # Check execution time constraint
            timestamp = opportunity.get('timestamp')
            if timestamp and (datetime.utcnow() - timestamp).seconds > self.max_execution_time:
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error validating opportunity: {e}")
            return False

    async def _execute_cross_exchange_trade(self, opportunity: Dict[str, Any],
                                          position_size: float) -> Dict[str, Any]:
        """Execute the actual cross-exchange arbitrage trade"""
        try:
            buy_exchange = opportunity['buy_exchange']
            sell_exchange = opportunity['sell_exchange']
            pair = opportunity['pair']

            # Place buy order
            buy_result = await self.exchange_integration.place_order(
                buy_exchange, pair, 'buy', position_size,
                opportunity['buy_price']
            )

            if not buy_result.get('success'):
                return {'success': False, 'reason': 'buy_failed', 'details': buy_result}

            # Place sell order
            sell_result = await self.exchange_integration.place_order(
                sell_exchange, pair, 'sell', position_size,
                opportunity['sell_price']
            )

            if not sell_result.get('success'):
                # Cancel buy order if sell failed
                await self.exchange_integration.cancel_order(
                    buy_exchange, buy_result.get('order_id')
                )
                return {'success': False, 'reason': 'sell_failed', 'details': sell_result}

            return {
                'success': True,
                'buy_order': buy_result,
                'sell_order': sell_result,
                'profit': opportunity.get('spread_pct', 0) * position_size,
                'execution_time': datetime.utcnow()
            }

        except Exception as e:
            self.logger.error(f"Error executing cross-exchange trade: {e}")
            return {'success': False, 'error': str(e)}


# Configuration for enhanced arbitrage detector
DEFAULT_CONFIG = {
    # SMC Parameters
    'smc_swing_length': 50,
    'fvg_join_consecutive': False,
    'liquidity_range_percent': 0.01,

    # Arbitrage Parameters
    'min_spread_pct': 0.1,
    'max_spread_pct': 2.0,
    'min_volume_threshold': 1000,
    'max_execution_time': 30,

    # Smart Money Filters
    'require_fvg_alignment': True,
    'require_bos_confirmation': False,
    'liquidity_filter_enabled': True,

    # Exchanges
    'exchanges': ['binance', 'coinbase', 'kraken'],
    'mca_compliant_only': True
}