#!/usr/bin/env python3
"""
Test Enhanced Arbitrage Detector with Smart Money Concepts
"""

import asyncio
import sys
import os
from datetime import datetime

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from enhanced_arbitrage_detector import EnhancedArbitrageDetector, DEFAULT_CONFIG

async def test_enhanced_arbitrage():
    """Test the enhanced arbitrage detector"""
    print("Testing Enhanced Arbitrage Detector with Smart Money Concepts")
    print("=" * 60)

    # Initialize detector with default config
    config = DEFAULT_CONFIG.copy()
    config.update({
        'exchanges': ['binance', 'kraken'],  # Test with available exchanges
        'mca_compliant_only': True
    })

    detector = EnhancedArbitrageDetector(config)

    # Test pairs (MiCA compliant)
    test_pairs = ['XRP/USDC', 'ADA/USDC', 'XLM/USDC']

    print(f"Testing arbitrage detection for pairs: {test_pairs}")
    print()

    try:
        # Detect arbitrage opportunities
        opportunities = await detector.detect_arbitrage_opportunities(test_pairs)

        print(f"Found {len(opportunities)} arbitrage opportunities")
        print()

        if opportunities:
            print("Top Opportunities:")
            print("-" * 40)

            for i, opp in enumerate(opportunities[:5], 1):  # Show top 5
                print(f"{i}. {opp['pair']} - {opp['buy_exchange']} -> {opp['sell_exchange']}")
                print(".2f")
                print(f"   SMC Confidence: {opp.get('smc_confidence', 'N/A')}")
                print(f"   Risk-Adjusted Return: {opp.get('risk_adjusted_return', 'N/A')}")
                print(f"   Market Bias: {opp.get('market_bias', {}).get('direction', 'N/A')}")

                smc_factors = opp.get('smc_factors', [])
                if smc_factors:
                    print(f"   SMC Factors: {', '.join(smc_factors)}")

                print()

        else:
            print("No arbitrage opportunities found")
            print("   This could be due to:")
            print("   - No price differences across exchanges")
            print("   - SMC filters rejecting opportunities")
            print("   - Insufficient market data")

        # Test SMC availability
        print("Smart Money Concepts Status:")
        print("-" * 30)

        # Test SMC on first pair
        if test_pairs:
            market_data = await detector._get_multi_exchange_data(test_pairs[0])
            if market_data:
                smc_signals = detector._analyze_smart_money_signals(market_data, test_pairs[0])

                if smc_signals.get('available'):
                    print("SMC Library: Available")
                    print("Indicators: Calculated")

                    market_bias = smc_signals.get('market_bias', {})
                    print(f"Market Bias: {market_bias.get('direction', 'unknown')} ({market_bias.get('strength', 'unknown')})")

                    indicators = smc_signals.get('indicators', {})
                    available_indicators = [k for k, v in indicators.items() if v is not None and not v.empty]
                    print(f"Available Indicators: {', '.join(available_indicators)}")

                else:
                    print("SMC Library: Not available")
                    reason = smc_signals.get('reason', 'unknown')
                    print(f"   Reason: {reason}")
            else:
                print("Market Data: Not available")
                print("   Cannot test SMC without market data")

        print()
        print("Test completed successfully!")

    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

async def test_smc_integration():
    """Test SMC library integration specifically"""
    print("\nTesting Smart Money Concepts Integration")
    print("=" * 50)

    try:
        # Test SMC import
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'smart-money-concepts'))
        from smartmoneyconcepts.smc import smc
        print("SMC Library: Successfully imported")

        # Test basic functionality with sample data
        import pandas as pd
        import numpy as np

        # Create sample OHLCV data
        dates = pd.date_range('2024-01-01', periods=100, freq='h')
        np.random.seed(42)

        sample_data = pd.DataFrame({
            'open': 100 + np.random.randn(100).cumsum(),
            'high': 105 + np.random.randn(100).cumsum(),
            'low': 95 + np.random.randn(100).cumsum(),
            'close': 100 + np.random.randn(100).cumsum(),
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)

        # Test FVG calculation
        fvg = smc.fvg(sample_data)
        print(f"FVG Calculation: {len(fvg)} signals generated")

        # Test swing highs/lows
        swing_hl = smc.swing_highs_lows(sample_data, swing_length=10)
        print(f"Swing Highs/Lows: {len(swing_hl)} signals generated")

        # Test BOS/CHOCH
        bos_choch = smc.bos_choch(sample_data, swing_hl)
        print(f"BOS/CHOCH: {len(bos_choch)} signals generated")

        print("SMC Integration: All tests passed!")

    except ImportError as e:
        print(f"SMC Import Failed: {e}")
        print("   Make sure smart-money-concepts is properly installed")
        return False
    except Exception as e:
        print(f"SMC Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

async def main():
    """Main test function"""
    print("SovereignForge Enhanced Arbitrage Detector Test Suite")
    print("=" * 60)
    print(f"Test Start: {datetime.utcnow()}")
    print()

    # Test SMC integration first
    smc_ok = await test_smc_integration()

    # Test enhanced arbitrage detector
    arb_ok = await test_enhanced_arbitrage()

    print()
    print("Test Results Summary:")
    print("-" * 25)
    print(f"SMC Integration: {'PASS' if smc_ok else 'FAIL'}")
    print(f"Arbitrage Detector: {'PASS' if arb_ok else 'FAIL'}")
    print()
    print(f"Test End: {datetime.utcnow()}")

    if smc_ok and arb_ok:
        print("All tests passed! Enhanced arbitrage system is ready.")
        return 0
    else:
        print("Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)