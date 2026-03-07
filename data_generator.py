#!/usr/bin/env python3
"""
SovereignForge Training Data Generator
Generate realistic market data for ML model training
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os
from pathlib import Path
import random

class MarketDataGenerator:
    """Generate realistic cryptocurrency market data"""

    def __init__(self):
        self.exchanges = ['binance', 'coinbase', 'kraken']
        self.pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT']

    def generate_ohlcv_data(self, pair: str, days: int = 365, interval: str = '1h') -> pd.DataFrame:
        """Generate OHLCV (Open, High, Low, Close, Volume) data"""

        # Start from 2 years ago
        start_date = datetime.now() - timedelta(days=days)
        periods = days * 24 if interval == '1h' else days  # 24 hours per day

        dates = pd.date_range(start=start_date, periods=periods, freq='h')

        # Generate realistic price movements
        base_prices = {
            'BTC/USDT': 45000,
            'ETH/USDT': 3000,
            'XRP/USDT': 0.8,
            'ADA/USDT': 1.2,
            'XLM/USDT': 0.3,
            'HBAR/USDT': 0.15,
            'ALGO/USDT': 1.5
        }

        base_price = base_prices.get(pair, 100)

        # Generate price series with trend and volatility
        trend = np.random.normal(0.0001, 0.001, periods).cumsum()  # Random walk with slight upward trend
        volatility = np.random.normal(0, 0.02, periods)  # Daily volatility

        # Create price series
        price_changes = trend + volatility
        close_prices = base_price * np.exp(price_changes.cumsum())

        # Generate OHLC from close prices
        high_mult = np.random.uniform(1.001, 1.01, periods)
        low_mult = np.random.uniform(0.99, 0.999, periods)

        opens = np.roll(close_prices, 1)
        opens[0] = base_price

        highs = close_prices * high_mult
        lows = close_prices * low_mult

        # Ensure OHLC relationships are correct
        highs = np.maximum(highs, np.maximum(opens, close_prices))
        lows = np.minimum(lows, np.minimum(opens, close_prices))

        # Generate volume (log-normal distribution)
        volume_base = np.random.lognormal(10, 1, periods)
        # Scale volume by price (higher priced assets have lower volume)
        volume_scale = 1000000 / base_price
        volumes = volume_base * volume_scale

        # Create DataFrame
        df = pd.DataFrame({
            'timestamp': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': close_prices,
            'volume': volumes
        })

        return df

    def add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to the dataframe"""

        # Simple Moving Averages
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()

        # Exponential Moving Averages
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()

        # RSI (Relative Strength Index)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * 2)
        df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * 2)

        # Fibonacci Retracement Levels
        high_52w = df['high'].rolling(window=52*24).max()  # 52 weeks * 24 hours
        low_52w = df['low'].rolling(window=52*24).min()

        df['fib_0.236'] = low_52w + (high_52w - low_52w) * 0.236
        df['fib_0.382'] = low_52w + (high_52w - low_52w) * 0.382
        df['fib_0.5'] = low_52w + (high_52w - low_52w) * 0.5
        df['fib_0.618'] = low_52w + (high_52w - low_52w) * 0.618
        df['fib_0.786'] = low_52w + (high_52w - low_52w) * 0.786

        # Volatility (ATR - Average True Range)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(window=14).mean()

        # Volume indicators
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']

        # Fill NaN values
        df = df.bfill().ffill().fillna(0)

        return df

    def generate_strategy_targets(self, df: pd.DataFrame, strategy: str) -> pd.DataFrame:
        """Generate target labels for specific trading strategies"""

        if strategy == 'fib':
            # Fibonacci retracement targets
            df['fib_level'] = np.random.choice([0.236, 0.382, 0.5, 0.618, 0.786], len(df))
            df['direction'] = np.where(df['close'] > df['open'], 1, -1)  # Price direction
            df['strength'] = np.random.uniform(0, 1, len(df))  # Signal strength

        elif strategy == 'dca':
            # Dollar-cost averaging targets
            df['optimal_amount'] = np.random.uniform(10, 1000, len(df))
            df['optimal_timing'] = np.random.choice([0, 1], len(df))  # Buy timing signal
            df['expected_return'] = np.random.uniform(-0.1, 0.5, len(df))  # Expected return

        elif strategy == 'grid':
            # Grid trading targets
            df['grid_spacing'] = np.random.uniform(0.01, 0.1, len(df))  # Grid spacing percentage
            df['take_profit_levels'] = np.random.uniform(0.02, 0.1, len(df))  # Take profit levels
            df['stop_loss_levels'] = np.random.uniform(0.01, 0.05, len(df))  # Stop loss levels

        elif strategy == 'arbitrage':
            # Arbitrage targets
            df['arbitrage_opportunity'] = np.random.choice([0, 1], len(df))  # Opportunity exists
            df['profit_potential'] = np.random.uniform(0, 0.05, len(df))  # Profit potential
            df['risk_level'] = np.random.uniform(0, 1, len(df))  # Risk assessment

        return df

    def save_data(self, df: pd.DataFrame, exchange: str, pair: str):
        """Save generated data to appropriate directory structure"""

        # Create directory structure
        data_dir = Path("data/historical") / exchange
        data_dir.mkdir(parents=True, exist_ok=True)

        # Format pair for filename
        pair_filename = pair.replace('/', '_')
        filename = f"{pair_filename}_1h.csv"
        filepath = data_dir / filename

        # Save to CSV
        df.to_csv(filepath, index=False)
        print(f"💾 Saved {len(df)} records to {filepath}")

    def generate_all_data(self):
        """Generate data for all exchanges and pairs"""

        print("🎯 SovereignForge Training Data Generator")
        print("=" * 50)

        total_files = len(self.exchanges) * len(self.pairs)
        generated = 0

        for exchange in self.exchanges:
            for pair in self.pairs:
                print(f"📊 Generating data for {exchange}/{pair}...")

                # Generate base OHLCV data
                df = self.generate_ohlcv_data(pair, days=365)

                # Add technical indicators
                df = self.add_technical_indicators(df)

                # Add strategy-specific targets for each strategy
                for strategy in ['fib', 'dca', 'grid', 'arbitrage']:
                    df_strategy = df.copy()
                    df_strategy = self.generate_strategy_targets(df_strategy, strategy)
                    # Note: In real implementation, we'd save separate files per strategy
                    # For now, we'll use the base data with indicators

                # Save the data
                self.save_data(df, exchange, pair)
                generated += 1

                print(f"✅ Completed {generated}/{total_files}")

        print("\n" + "=" * 50)
        print("🎉 DATA GENERATION COMPLETE")
        print("=" * 50)
        print(f"📁 Generated {generated} data files")
        print("📊 Each file contains ~8760 hours (1 year) of market data")
        print("🔧 Includes technical indicators and price data")
        print("🎯 Ready for ML model training!")

def main():
    """Main entry point"""
    generator = MarketDataGenerator()
    generator.generate_all_data()

if __name__ == "__main__":
    main()