#!/usr/bin/env python3
"""
Test position sizing fix
"""

from comprehensive_backtest import ComprehensiveBacktester
import pandas as pd

def test_position_sizing():
    backtester = ComprehensiveBacktester()

    # Test position sizing calculation
    capital = 10000
    max_position_size = 0.1  # 10%
    entry_price = 1.0  # $1 per unit

    max_position_value = capital * max_position_size  # $1000
    position_size = max_position_value / entry_price  # 1000 units

    print(f"Capital: ${capital}")
    print(f"Max position size: {max_position_size*100}%")
    print(f"Entry price: ${entry_price}")
    print(f"Max position value: ${max_position_value}")
    print(f"Position size (units): {position_size}")

    # Test with real data
    df = backtester.load_processed_data('kraken', 'XRP/USDC')
    if df is not None:
        opportunities = backtester.detect_arbitrage_opportunities(df)
        print(f"\nFound {len(opportunities)} opportunities")

        if len(opportunities) > 0:
            opp = opportunities.iloc[0]
            print(f"First opportunity entry price: ${opp['entry_price']:.4f}")
            print(f"Expected return: {opp['expected_return']:.2%}")

            # Test position sizing for this opportunity
            max_pos_value = capital * backtester.max_position_size
            pos_size = max_pos_value / opp['entry_price']
            print(f"Position size for this trade: {pos_size:.2f} units (${max_pos_value:.2f})")

if __name__ == "__main__":
    test_position_sizing()