#!/usr/bin/env python3
"""
SovereignForge CLI - Basic Commands Only
Avoids production dependencies for core functionality
"""

import argparse
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description='SovereignForge Basic CLI')
    parser.add_argument('command', choices=['detect', 'history', 'stats', 'test'],
                       help='Command to run')
    parser.add_argument('--symbol', default='BTC/USDT',
                       help='Trading symbol (default: BTC/USDT)')
    parser.add_argument('--continuous', action='store_true',
                       help='Run continuous detection')
    parser.add_argument('--interval', type=int, default=60,
                       help='Check interval in seconds (default: 60)')
    parser.add_argument('--limit', type=int, default=10,
                       help='Number of records to show (default: 10)')

    args = parser.parse_args()

    # Import basic components
    from arbitrage_detector import ArbitrageDetector, LocalDatabase, create_sample_data
    from exchange_connector import create_demo_connector
    from risk_manager import create_default_risk_manager
    from order_executor import create_demo_executor

    # Make create_sample_data available globally for the functions
    global create_sample_data_func
    create_sample_data_func = create_sample_data

    # Initialize components
    detector = ArbitrageDetector()
    database = LocalDatabase()
    connector = create_demo_connector()
    risk_manager = create_default_risk_manager()
    order_executor = create_demo_executor(risk_manager)

    if args.command == 'detect':
        run_detection(detector, database, connector, create_sample_data, args.symbol, args.continuous, args.interval)
    elif args.command == 'history':
        show_history(database, args.limit)
    elif args.command == 'stats':
        show_stats(database)
    elif args.command == 'test':
        run_test(detector, database, connector, risk_manager, order_executor, create_sample_data)

def run_detection(detector, database, connector, create_sample_data, symbol, continuous, interval):
    """Run arbitrage detection"""
    import time
    from datetime import datetime

    print(f"SovereignForge Arbitrage Detector")
    print(f"Symbol: {symbol}")
    print(f"Continuous mode: {continuous}")
    if continuous:
        print(f"Check interval: {interval} seconds")
    print("-" * 50)

    try:
        while True:
            # Get market data
            market_data = connector.get_market_data(symbol)

            if not market_data['exchanges']:
                print("No market data available, using sample data...")
                market_data = create_sample_data()

            # Add price history
            market_data['price_history'] = connector.get_price_history(symbol)

            # Detect opportunities
            result = detector.detect_opportunity(market_data)

            # Display results
            timestamp = datetime.fromisoformat(result['timestamp'])
            print(f"[{timestamp.strftime('%H:%M:%S')}] Signal: {result['arbitrage_signal']:.6f}, "
                  f"Confidence: {result['confidence']:.2f}, "
                  f"Opportunity: {'YES' if result['opportunity_detected'] else 'NO'}")

            # Save to database
            database.save_opportunity(result, market_data)

            if not continuous:
                break

            # Wait for next check
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nStopping detection...")

def show_history(database, limit):
    """Show detection history"""
    from datetime import datetime

    print(f"Recent Arbitrage Detection Results (last {limit})")
    print("-" * 60)

    opportunities = database.get_recent_opportunities(limit)

    if not opportunities:
        print("No detection history found.")
        return

    for opp in opportunities:
        timestamp = datetime.fromisoformat(opp['timestamp'])
        print(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
              f"Signal: {opp['arbitrage_signal']:.6f} | "
              f"Confidence: {opp['confidence']:.2f} | "
              f"Opportunity: {'YES' if opp['opportunity_detected'] else 'NO'} | "
              f"Exchanges: {', '.join(opp['exchanges'])}")

def show_stats(database):
    """Show detection statistics"""
    print("Arbitrage Detection Statistics")
    print("-" * 40)

    opportunities = database.get_recent_opportunities(1000)  # Last 1000

    if not opportunities:
        print("No data available.")
        return

    total = len(opportunities)
    opportunities_found = sum(1 for opp in opportunities if opp['opportunity_detected'])
    avg_confidence = sum(opp['confidence'] for opp in opportunities) / total
    avg_signal = sum(opp['arbitrage_signal'] for opp in opportunities) / total

    print(f"Total detections: {total}")
    print(f"Opportunities found: {opportunities_found}")
    print(f"Success rate: {opportunities_found/total*100:.1f}%")
    print(f"Average confidence: {avg_confidence:.3f}")
    print(f"Average signal: {avg_signal:.6f}")

def run_test(detector, database, connector, risk_manager, order_executor, create_sample_data):
    """Run system tests"""
    print("Running SovereignForge System Tests")
    print("-" * 40)

    # Test detector
    print("Testing arbitrage detector...")
    sample_data = create_sample_data()
    result = detector.detect_opportunity(sample_data)
    print(f"[OK] Detector working: {result['arbitrage_signal']:.6f}")

    # Test database
    print("Testing database...")
    database.save_opportunity(result, sample_data)
    recent = database.get_recent_opportunities(1)
    print(f"[OK] Database working: {len(recent)} records")

    # Test exchange connector
    print("Testing exchange connector...")
    market_data = connector.get_market_data('BTC/USDT')
    if market_data['exchanges']:
        print(f"[OK] Exchange connector working: {len(market_data['exchanges'])} exchanges")
    else:
        print("[WARN] Exchange connector returned no data (may be normal for demo)")

    # Test risk manager
    print("Testing risk manager...")
    position_calc = risk_manager.calculate_position_size({
        'spread_percentage': 0.003,
        'confidence': 0.8,
        'entry_price': 45000
    })
    print(f"[OK] Risk manager working: {position_calc['approved']}")

    # Test order executor
    print("Testing order executor...")
    balance = order_executor.get_paper_balance('binance')
    print(f"[OK] Order executor working: ${balance.get('USDT', 0):.2f} balance")

    print("System tests completed!")

if __name__ == "__main__":
    main()