#!/usr/bin/env python3
"""
Check available USDC pairs on Binance
"""

import requests
import json

def check_binance_usdc_pairs():
    """Check which USDC pairs are available on Binance"""

    print("Checking Binance USDC pairs...")
    print("=" * 50)

    try:
        # Get exchange info from Binance
        response = requests.get('https://api.binance.com/api/v3/exchangeInfo')
        data = response.json()

        # Filter for USDC pairs
        usdc_pairs = []
        for symbol_info in data['symbols']:
            if symbol_info['symbol'].endswith('USDC') and symbol_info['status'] == 'TRADING':
                usdc_pairs.append(symbol_info['symbol'])

        print(f"Found {len(usdc_pairs)} USDC trading pairs on Binance")
        print("\nUSDC Pairs:")
        for pair in sorted(usdc_pairs):
            print(f"  {pair}")

        # Check our MiCA pairs
        mica_pairs = [
            'XRPUSDC', 'XLMUSDC', 'HBARUSDC', 'ALGOUSDC', 'ADAUSDC',
            'LINKUSDC', 'IOTAUSDC', 'XDCUSDC', 'ONDOUSDC', 'VETUSDC'
        ]

        print(f"\nChecking MiCA pairs:")
        available = []
        not_available = []

        for pair in mica_pairs:
            if pair in usdc_pairs:
                available.append(pair)
                print(f"  ✅ {pair} - Available")
            else:
                not_available.append(pair)
                print(f"  ❌ {pair} - Not Available")

        print("\nSummary:")
        print(f"  Available: {len(available)}/{len(mica_pairs)}")
        print(f"  Not Available: {len(not_available)}/{len(mica_pairs)}")

        if not_available:
            print(f"\nNot available: {not_available}")

        return available, not_available

    except Exception as e:
        print(f"Error checking Binance pairs: {e}")
        return [], []

if __name__ == '__main__':
    check_binance_usdc_pairs()