#!/usr/bin/env python3
"""
Basic test script for SovereignForge - avoids production dependencies
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_basic_components():
    """Test basic SovereignForge components"""
    print("Testing SovereignForge Basic Components")
    print("=" * 40)

    try:
        # Test arbitrage detector
        print("Testing arbitrage detector...")
        from arbitrage_detector import ArbitrageDetector, create_sample_data

        detector = ArbitrageDetector()
        sample_data = create_sample_data()
        result = detector.detect_opportunity(sample_data)
        print(f"[OK] Detector working: signal={result['arbitrage_signal']:.6f}")

        # Test database
        print("Testing database...")
        from arbitrage_detector import LocalDatabase

        db = LocalDatabase()
        db.save_opportunity(result, sample_data)
        recent = db.get_recent_opportunities(1)
        print(f"[OK] Database working: {len(recent)} records")

        # Test exchange connector
        print("Testing exchange connector...")
        from exchange_connector import create_demo_connector

        connector = create_demo_connector()
        market_data = connector.get_market_data('BTC/USDT')
        if market_data['exchanges']:
            print(f"[OK] Exchange connector working: {len(market_data['exchanges'])} exchanges")
        else:
            print("[WARN] Exchange connector returned no data (may be normal for demo)")

        # Test risk manager
        print("Testing risk manager...")
        from risk_manager import create_default_risk_manager

        risk_manager = create_default_risk_manager()
        position_calc = risk_manager.calculate_position_size({
            'spread_percentage': 0.003,
            'confidence': 0.8,
            'entry_price': 45000
        })
        print(f"[OK] Risk manager working: approved={position_calc['approved']}")

        # Test order executor
        print("Testing order executor...")
        from order_executor import create_demo_executor

        order_executor = create_demo_executor(risk_manager)
        balance = order_executor.get_paper_balance('binance')
        print(f"[OK] Order executor working: ${balance.get('USDT', 0):.2f} balance")

        print("\n[SUCCESS] All basic components working!")
        return True

    except Exception as e:
        print(f"\n[FAILED] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_basic_components()
    sys.exit(0 if success else 1)