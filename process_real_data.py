#!/usr/bin/env python3
"""
Process and Validate Real Historical Data for MiCA Compliant Pairs
Clean data, add technical indicators, ensure MiCA compliance
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RealDataProcessor:
    """
    Process and validate real historical data for MiCA compliance
    """

    def __init__(self):
        self.raw_data_dir = Path('data/real_historical')
        self.processed_data_dir = Path('data/processed_real')
        self.processed_data_dir.mkdir(parents=True, exist_ok=True)

        # All 10 MiCA-compliant USDC pairs (BTC/ETH allowed in personal deployment)
        self.mica_pairs = [
            'BTC/USDC', 'ETH/USDC',
            'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC',
            'LINK/USDC', 'IOTA/USDC', 'VET/USDC',
        ]

    def load_raw_data(self, exchange: str, pair: str) -> Optional[pd.DataFrame]:
        """Load raw data for a specific exchange and pair"""
        try:
            pair_filename = pair.replace('/', '_')
            filepath = self.raw_data_dir / exchange / f"{pair_filename}_1h.csv"

            if not filepath.exists():
                logger.warning(f"Raw data file not found: {filepath}")
                return None

            df = pd.read_csv(filepath)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp').sort_index()

            logger.info(f"Loaded {len(df)} records for {pair} from {exchange}")
            return df

        except Exception as e:
            logger.error(f"Failed to load data for {pair} from {exchange}: {e}")
            return None

    def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and validate the data"""
        try:
            # Remove duplicates
            df = df[~df.index.duplicated(keep='first')]

            # Ensure OHLC relationships
            df['high'] = np.maximum(df['high'], df[['open', 'close']].max(axis=1))
            df['low'] = np.minimum(df['low'], df[['open', 'close']].min(axis=1))

            # Remove invalid data
            df = df.dropna()
            df = df[df['volume'] > 0]
            df = df[df['open'] > 0]
            df = df[df['high'] > 0]
            df = df[df['low'] > 0]
            df = df[df['close'] > 0]

            # Remove extreme data errors (>90% single-candle move — data corruption, not volatility)
            # Using close only to avoid dropping valid wick spikes on open/high/low
            pct_change = df['close'].pct_change().abs()
            df = df[pct_change < 0.9]

            # Fill small gaps (up to 3 hours) with interpolation
            df = df.resample('1h').asfreq()
            df = df.interpolate(method='linear', limit=3)

            # Remove remaining NaN values
            df = df.dropna()

            return df

        except Exception as e:
            logger.error(f"Failed to clean data: {e}")
            return df

    def add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add comprehensive technical indicators"""
        try:
            # Simple Moving Averages
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['sma_50'] = df['close'].rolling(window=50).mean()
            df['sma_200'] = df['close'].rolling(window=200).mean()

            # Exponential Moving Averages
            df['ema_12'] = df['close'].ewm(span=12).mean()
            df['ema_26'] = df['close'].ewm(span=26).mean()
            df['ema_50'] = df['close'].ewm(span=50).mean()

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
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

            # ATR (Average True Range)
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['atr'] = true_range.rolling(window=14).mean()

            # Volume indicators
            df['volume_sma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']

            # Price momentum
            df['roc_1'] = df['close'].pct_change(1)  # 1-period rate of change
            df['roc_5'] = df['close'].pct_change(5)  # 5-period rate of change
            df['momentum'] = df['close'] - df['close'].shift(10)

            # Volatility
            df['volatility'] = df['close'].rolling(window=20).std()
            df['volatility_ratio'] = df['volatility'] / df['close']

            # Fibonacci Retracement Levels (52-week)
            high_52w = df['high'].rolling(window=52*24).max()
            low_52w = df['low'].rolling(window=52*24).min()

            df['fib_0.236'] = low_52w + (high_52w - low_52w) * 0.236
            df['fib_0.382'] = low_52w + (high_52w - low_52w) * 0.382
            df['fib_0.5'] = low_52w + (high_52w - low_52w) * 0.5
            df['fib_0.618'] = low_52w + (high_52w - low_52w) * 0.618
            df['fib_0.786'] = low_52w + (high_52w - low_52w) * 0.786

            # Support and Resistance levels
            df['support_20'] = df['low'].rolling(window=20).min()
            df['resistance_20'] = df['high'].rolling(window=20).max()

            # Fill NaN values
            df = df.bfill().ffill().fillna(0)

            return df

        except Exception as e:
            logger.error(f"Failed to add technical indicators: {e}")
            return df

    def validate_mica_compliance(self, df: pd.DataFrame, pair: str) -> bool:
        """Validate MiCA compliance for the data"""
        try:
            # Check if pair is in MiCA whitelist
            if pair not in self.mica_pairs:
                logger.warning(f"Pair {pair} is not MiCA compliant")
                return False

            # Check for USDT references (should not exist in MiCA data)
            if 'USDT' in pair:
                logger.error(f"USDT pair {pair} violates MiCA compliance")
                return False

            # Check data quality
            if len(df) < 1000:  # Minimum 1000 hours of data
                logger.warning(f"Insufficient data for {pair}: {len(df)} records")
                return False

            # Check for realistic volumes
            avg_volume = df['volume'].mean()
            if avg_volume < 1000:  # Minimum average volume
                logger.warning(f"Low volume for {pair}: {avg_volume}")
                return False

            return True

        except Exception as e:
            logger.error(f"MiCA compliance validation failed for {pair}: {e}")
            return False

    def generate_quality_report(self, df: pd.DataFrame, exchange: str, pair: str) -> Dict[str, Any]:
        """Generate data quality report"""
        try:
            report = {
                'exchange': exchange,
                'pair': pair,
                'total_records': len(df),
                'date_range': {
                    'start': df.index.min().isoformat() if len(df) > 0 else None,
                    'end': df.index.max().isoformat() if len(df) > 0 else None
                },
                'data_quality': {
                    'missing_values': df.isnull().sum().sum(),
                    'duplicate_timestamps': df.index.duplicated().sum(),
                    'zero_volume_records': (df['volume'] == 0).sum(),
                    'negative_prices': ((df[['open', 'high', 'low', 'close']] <= 0).any(axis=1)).sum()
                },
                'statistics': {
                    'price_range': {
                        'min': df['close'].min(),
                        'max': df['close'].max(),
                        'mean': df['close'].mean(),
                        'std': df['close'].std()
                    },
                    'volume_stats': {
                        'total_volume': df['volume'].sum(),
                        'avg_volume': df['volume'].mean(),
                        'volume_std': df['volume'].std()
                    },
                    'returns': {
                        'daily_returns_mean': df['close'].pct_change().mean(),
                        'daily_returns_std': df['close'].pct_change().std(),
                        'sharpe_ratio': df['close'].pct_change().mean() / df['close'].pct_change().std() * np.sqrt(365)
                    }
                },
                'technical_indicators': {
                    'indicators_added': [
                        'sma_20', 'sma_50', 'sma_200',
                        'ema_12', 'ema_26', 'ema_50',
                        'rsi', 'macd', 'macd_signal', 'macd_hist',
                        'bb_upper', 'bb_middle', 'bb_lower', 'bb_width',
                        'atr', 'volume_sma', 'volume_ratio',
                        'roc_1', 'roc_5', 'momentum',
                        'volatility', 'volatility_ratio',
                        'fib_0.236', 'fib_0.382', 'fib_0.5', 'fib_0.618', 'fib_0.786',
                        'support_20', 'resistance_20'
                    ]
                },
                'mica_compliance': self.validate_mica_compliance(df, pair)
            }

            return report

        except Exception as e:
            logger.error(f"Failed to generate quality report for {pair}: {e}")
            return {}

    def process_pair_data(self, exchange: str, pair: str) -> bool:
        """Process data for a specific exchange and pair"""
        try:
            # Load raw data
            df = self.load_raw_data(exchange, pair)
            if df is None:
                return False

            # Clean data
            df = self.clean_data(df)

            # Add technical indicators
            df = self.add_technical_indicators(df)

            # Generate quality report
            quality_report = self.generate_quality_report(df, exchange, pair)

            # Save processed data
            exchange_dir = self.processed_data_dir / exchange
            exchange_dir.mkdir(exist_ok=True)

            pair_filename = pair.replace('/', '_')
            output_path = exchange_dir / f"{pair_filename}_processed.csv"
            df.to_csv(output_path)

            # Save quality report
            report_path = exchange_dir / f"{pair_filename}_quality.json"
            with open(report_path, 'w') as f:
                json.dump(quality_report, f, indent=2, default=str)

            logger.info(f"Processed and saved data for {pair} from {exchange}")
            return True

        except Exception as e:
            logger.error(f"Failed to process data for {pair} from {exchange}: {e}")
            return False

    def discover_raw_files(self) -> List[Tuple[str, str]]:
        """
        Auto-discover all raw CSV files that were actually fetched.
        Returns list of (exchange, pair) tuples.
        """
        found = []
        if not self.raw_data_dir.exists():
            return found
        for ex_dir in sorted(self.raw_data_dir.iterdir()):
            if not ex_dir.is_dir():
                continue
            exchange = ex_dir.name
            for csv_file in sorted(ex_dir.glob("*_1h.csv")):
                # Convert filename back to pair: XRP_USDC_1h.csv → XRP/USDC
                stem = csv_file.stem.replace("_1h", "")
                # Handle both XRP_USDC and XRPUSDC formats
                if "_" in stem:
                    pair = stem.replace("_", "/", 1)
                else:
                    # Try to split at known stablecoins
                    for stable in ("USDC", "RLUSD", "USDT"):
                        if stem.endswith(stable):
                            pair = stem[: -len(stable)] + "/" + stable
                            break
                    else:
                        pair = stem
                found.append((exchange, pair))
        return found

    def process_all_data(self):
        """Process all available raw data (auto-discovers fetched files)."""
        logger.info("Starting data processing — discovering available raw files...")

        available = self.discover_raw_files()
        if not available:
            logger.warning(
                f"No raw CSV files found in {self.raw_data_dir}. "
                "Run fetch_real_historical_data.py first."
            )
            return

        logger.info(f"Found {len(available)} raw files to process")
        total_processed = 0

        for i, (exchange, pair) in enumerate(available, 1):
            logger.info(f"[{i}/{len(available)}] {exchange} {pair}")
            if self.process_pair_data(exchange, pair):
                total_processed += 1

        logger.info(
            f"Data processing complete: {total_processed}/{len(available)} pairs processed"
        )

    def generate_summary_report(self):
        """Generate overall summary report"""
        summary = {
            'processing_timestamp': datetime.now().isoformat(),
            'total_pairs_processed': 0,
            'total_records': 0,
            'exchanges': {},
            'quality_summary': {
                'mica_compliant_pairs': 0,
                'data_quality_issues': 0
            }
        }

        for exchange_dir in self.processed_data_dir.iterdir():
            if exchange_dir.is_dir():
                exchange = exchange_dir.name
                summary['exchanges'][exchange] = {'pairs': [], 'total_records': 0}

                for json_file in exchange_dir.glob('*_quality.json'):
                    try:
                        with open(json_file, 'r') as f:
                            report = json.load(f)

                        summary['exchanges'][exchange]['pairs'].append({
                            'pair': report['pair'],
                            'records': report['total_records'],
                            'mica_compliant': report['mica_compliance']
                        })

                        summary['exchanges'][exchange]['total_records'] += report['total_records']
                        summary['total_records'] += report['total_records']
                        summary['total_pairs_processed'] += 1

                        if report['mica_compliance']:
                            summary['quality_summary']['mica_compliant_pairs'] += 1

                    except Exception as e:
                        logger.warning(f"Could not read quality report {json_file}: {e}")

        # Save summary
        summary_path = self.processed_data_dir / 'processing_summary.json'
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(f"Summary report saved to {summary_path}")
        logger.info(f"Total pairs processed: {summary['total_pairs_processed']}")
        logger.info(f"Total records: {summary['total_records']}")
        logger.info(f"MiCA compliant pairs: {summary['quality_summary']['mica_compliant_pairs']}")

        return summary

def main():
    """Main entry point"""
    processor = RealDataProcessor()
    processor.process_all_data()
    processor.generate_summary_report()

if __name__ == "__main__":
    main()