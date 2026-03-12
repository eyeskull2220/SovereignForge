#!/usr/bin/env python3
"""
SovereignForge Arbitrage Detector - Wave 1
Simple ML-based arbitrage opportunity detection for personal use
"""

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from datetime import datetime
import logging
import json
import os
from typing import Dict, List, Optional, Tuple, Any
import sqlite3

# Import advanced model architecture
try:
    from gpu_arbitrage_model import ArbitrageTransformer, ModelConfig
except ImportError:
    # Fallback to simple model if advanced not available
    ArbitrageTransformer = None
    ModelConfig = None

# Import Grok reasoning engine
try:
    from grok_reasoning import GrokReasoningWrapper
except ImportError:
    GrokReasoningWrapper = None

# Import compliance engine
from compliance import get_compliance_engine, ComplianceViolationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('arbitrage_detector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SimpleArbitrageDetector(nn.Module):
    """Simple neural network for arbitrage detection"""

    def __init__(self, input_size: int = 6):
        super(SimpleArbitrageDetector, self).__init__()
        self.network = nn.Sequential(
            nn.Linear(input_size, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )

    def forward(self, x):
        return self.network(x)

class LegacyArbitrageDetector(nn.Module):
    """Legacy LSTM-based arbitrage detector matching saved models"""

    def __init__(self, input_size: int = 22, hidden_size: int = 64, num_layers: int = 2):
        super(LegacyArbitrageDetector, self).__init__()

        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.1 if num_layers > 1 else 0
        )

        # Attention mechanism
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1)
        )

        # Classifier
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(16, 1)
        )

    def forward(self, x):
        # Handle different input shapes
        if x.dim() == 2:
            # Single time step: [batch_size, input_size] -> [batch_size, 1, input_size]
            x = x.unsqueeze(1)

        # x shape: [batch_size, seq_len, input_size]
        batch_size, seq_len, input_size = x.shape

        # LSTM processing
        lstm_out, (h_n, c_n) = self.lstm(x)  # [batch, seq_len, hidden_size]

        if seq_len == 1:
            # For single time step, use the LSTM output directly
            context = lstm_out.squeeze(1)  # [batch, hidden_size]
        else:
            # Attention mechanism for sequences
            attention_weights = self.attention(lstm_out)  # [batch, seq_len, 1]
            attention_weights = torch.softmax(attention_weights, dim=1)

            # Apply attention
            context = torch.sum(attention_weights * lstm_out, dim=1)  # [batch, hidden_size]

        # Classification
        output = self.classifier(context)  # [batch, 1]
        return output.squeeze(-1)  # Return scalar for single output

class MarketDataProcessor:
    """Process market data for arbitrage detection"""

    def __init__(self):
        self.feature_names = ['price_diff', 'volume_ratio', 'spread_avg', 'volatility', 'time_factor', 'liquidity_score']

    def extract_features(self, market_data: Dict) -> torch.Tensor:
        """Extract basic features from market data"""
        features = []

        exchanges = market_data.get('exchanges', {})

        if len(exchanges) >= 2:
            exch_list = list(exchanges.values())

            # Price difference (normalized)
            bid0 = exch_list[0].get('bid')
            ask1 = exch_list[1].get('ask')
            if bid0 is not None and ask1 is not None and bid0 > 0:
                price_diff = abs(bid0 - ask1) / bid0
                features.append(price_diff)
            else:
                features.append(0.0)

            # Volume ratio
            vol0 = exch_list[0].get('volume')
            vol1 = exch_list[1].get('volume')
            if vol0 is not None and vol1 is not None and vol1 > 0:
                vol_ratio = vol0 / vol1
                features.append(vol_ratio)
            else:
                features.append(1.0)

            # Average spread
            spreads = []
            for exch in exch_list:
                bid = exch.get('bid')
                ask = exch.get('ask')
                if bid is not None and ask is not None and bid > 0:
                    spread = (ask - bid) / bid
                    spreads.append(spread)
            if spreads:
                features.append(np.mean(spreads))
            else:
                features.append(0.001)

        else:
            features.extend([0.0, 1.0, 0.001])  # Default values

        # Volatility (simplified)
        price_history = market_data.get('price_history', [])
        if len(price_history) > 1:
            returns = np.diff(price_history) / price_history[:-1]
            volatility = np.std(returns)
            features.append(volatility)
        else:
            features.append(0.02)

        # Time factor (hour of day)
        timestamp = market_data.get('timestamp', datetime.now())
        time_factor = timestamp.hour / 24.0
        features.append(time_factor)

        # Liquidity score (simplified)
        total_volume = sum(exch.get('volume', 0) or 0 for exch in exchanges.values())
        liquidity_score = min(total_volume / 1000, 1.0)  # Normalize
        features.append(liquidity_score)

        return torch.tensor(features, dtype=torch.float32)

class ArbitrageDetector:
    """Main arbitrage detection system"""

    def __init__(self, model_path: str = None, enable_grok_reasoning: bool = True):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.processor = MarketDataProcessor()

        # Initialize model architecture (will be determined by loaded model)
        self.model = None
        self.model_type = 'none'
        self.model_config = None

        # Initialize Grok reasoning engine
        self.grok_reasoner = None
        if enable_grok_reasoning and GrokReasoningWrapper is not None:
            try:
                self.grok_reasoner = GrokReasoningWrapper()
                if self.grok_reasoner.is_operational():
                    logger.info("🧠 Grok reasoning engine initialized and operational")
                else:
                    logger.warning("🧠 Grok reasoning engine initialized but not operational (API key required)")
            except Exception as e:
                logger.warning(f"🧠 Failed to initialize Grok reasoning engine: {e}")
        else:
            logger.info("🧠 Grok reasoning disabled or not available")

        # Try to load models in order of preference
        model_paths = [
            model_path,
            "E:\\Users\\Gino\\Downloads\\SovereignForge\\models\\advanced_arbitrage_detector_v2.0.pth",
            "E:\\Users\\Gino\\Downloads\\SovereignForge\\models\\arbitrage_predictor_v1.0.pth"
        ]

        loaded = False
        for path in model_paths:
            if path and os.path.exists(path):
                try:
                    if self.load_model(path):
                        loaded = True
                        break
                except Exception as e:
                    logger.warning(f"Failed to load model {path}: {e}")
                    continue

        # If no model loaded, create a simple fallback
        if not loaded:
            self.model = SimpleArbitrageDetector(input_size=len(self.processor.feature_names))
            self.model_type = 'simple'
            self.model.to(self.device)
            logger.info("No trained model found, using untrained simple model")

        self.model.eval()

    def load_model(self, model_path: str) -> bool:
        """Load trained model and determine architecture"""
        try:
            checkpoint = torch.load(model_path, map_location=self.device, weights_only=True)
            state_dict = checkpoint['model_state_dict']

            # Determine model type from state_dict keys
            if any('lstm' in key for key in state_dict.keys()):
                # Legacy LSTM-based model
                self.model = LegacyArbitrageDetector(input_size=22, hidden_size=64, num_layers=2)
                self.model_type = 'legacy'
                logger.info("Detected legacy LSTM model architecture")
            elif any('input_embedding' in key for key in state_dict.keys()):
                # Advanced transformer model
                if ArbitrageTransformer is not None:
                    config = ModelConfig(
                        input_size=64,
                        hidden_size=256,
                        num_layers=6,
                        num_heads=8,
                        num_exchanges=3
                    )
                    self.model = ArbitrageTransformer(config)
                    self.model_config = config
                    self.model_type = 'advanced'
                    logger.info("Detected advanced transformer model architecture")
                else:
                    logger.warning("Advanced model detected but ArbitrageTransformer not available")
                    return False
            else:
                # Simple sequential model
                self.model = SimpleArbitrageDetector(input_size=len(self.processor.feature_names))
                self.model_type = 'simple'
                logger.info("Detected simple sequential model architecture")

            # Load the state dict
            self.model.load_state_dict(state_dict)
            self.model.to(self.device)
            self.model.eval()

            logger.info(f"Successfully loaded {self.model_type} model from {model_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model from {model_path}: {e}")
            return False

    def detect_opportunity(self, market_data: Dict) -> Dict:
        """Detect arbitrage opportunity"""
        try:
            # MiCA Compliance Check - Hard enforcement
            compliance_engine = get_compliance_engine()

            # Check if market data contains compliant pairs
            pair = market_data.get('pair')
            if pair:
                if not compliance_engine.is_pair_compliant(pair):
                    raise ComplianceViolationError(f"Non-compliant pair: {pair}")

            # Validate all exchanges in market data
            exchanges = market_data.get('exchanges', {})
            for exch_name, exch_data in exchanges.items():
                # Extract pair from exchange data if not in main market_data
                if not pair and 'pair' in exch_data:
                    pair = exch_data['pair']
                    if not compliance_engine.is_pair_compliant(pair):
                        raise ComplianceViolationError(f"Non-compliant pair in exchange data: {pair}")
            if self.model_type == 'legacy':
                # Legacy LSTM model expects sequence input
                features = self._prepare_legacy_features(market_data)
                features = features.unsqueeze(0).to(self.device)  # Add batch dimension

                with torch.no_grad():
                    prediction = self.model(features).item()

                # Calculate confidence (simplified)
                confidence = min(abs(prediction) * 5, 1.0)

            elif self.model_type == 'advanced':
                # Advanced transformer model
                model_input = self._prepare_advanced_model_input(market_data)

                with torch.no_grad():
                    outputs = self.model(model_input)
                    prediction = outputs['arbitrage_probability'].item()
                    confidence = outputs['confidence_score'].item()

            else:
                # Simple sequential model
                features = self.processor.extract_features(market_data)
                features = features.unsqueeze(0).to(self.device)

                with torch.no_grad():
                    prediction = self.model(features).item()

                # Calculate confidence (simplified)
                confidence = min(abs(prediction) * 5, 1.0)

            opportunity_detected = confidence > 0.7

            result = {
                'arbitrage_signal': prediction,
                'confidence': confidence,
                'opportunity_detected': opportunity_detected,
                'timestamp': datetime.now().isoformat(),
                'exchanges_checked': len(market_data.get('exchanges', {})),
                'model_type': self.model_type
            }

            # Add Grok reasoning analysis if opportunity detected and Grok is available
            if opportunity_detected and self.grok_reasoner and self.grok_reasoner.is_operational():
                try:
                    logger.info("🧠 Analyzing opportunity with Grok reasoning...")

                    # Prepare opportunity data for Grok analysis
                    grok_opportunity_data = self._prepare_grok_opportunity_data(market_data, result)

                    # Get Grok analysis
                    grok_analysis = self.grok_reasoner.analyze_opportunity(grok_opportunity_data)

                    # Add Grok analysis to result
                    result['grok_analysis'] = grok_analysis
                    result['grok_reasoning_available'] = True

                    logger.info(f"🧠 Grok analysis complete - Risk: {grok_analysis.get('parsed', {}).get('risk_level', 'Unknown')}")

                except Exception as e:
                    logger.warning(f"🧠 Grok analysis failed: {e}")
                    result['grok_analysis'] = {'error': str(e)}
                    result['grok_reasoning_available'] = False
            else:
                result['grok_reasoning_available'] = False
                if opportunity_detected and self.grok_reasoner:
                    logger.info("🧠 Opportunity detected but Grok reasoning not operational")

            return result

        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return {
                'error': str(e),
                'arbitrage_signal': 0.0,
                'confidence': 0.0,
                'opportunity_detected': False,
                'timestamp': datetime.now().isoformat(),
                'model_type': 'error'
            }

    def _prepare_legacy_features(self, market_data: Dict) -> torch.Tensor:
        """Prepare features for legacy LSTM model (expects 22 features)"""
        exchanges = market_data.get('exchanges', {})
        price_history = market_data.get('price_history', [])

        features = []

        # Basic exchange features (2 exchanges × 8 features = 16)
        for exch_name in ['binance', 'coinbase']:
            if exch_name in exchanges:
                exch = exchanges[exch_name]
                bid = exch.get('bid', 0) or 0
                ask = exch.get('ask', 0) or 0
                volume = exch.get('volume', 0) or 0

                features.extend([
                    bid, ask, (ask + bid) / 2,  # Price features
                    volume, volume * bid,       # Volume features
                    (ask - bid) / bid if bid > 0 else 0,  # Spread
                    bid * volume,               # Market cap proxy
                    np.log(bid) if bid > 0 else 0  # Log price
                ])
            else:
                features.extend([0.0] * 8)  # Default values

        # Time-based features (6 features)
        timestamp = market_data.get('timestamp', datetime.now())
        features.extend([
            timestamp.hour / 24.0,      # Hour of day
            timestamp.minute / 60.0,    # Minute of hour
            timestamp.weekday() / 7.0,  # Day of week
            timestamp.month / 12.0,     # Month of year
            1.0 if timestamp.hour >= 9 and timestamp.hour <= 17 else 0.0,  # Trading hours
            len(exchanges) / 3.0        # Exchange coverage
        ])

        # Ensure exactly 22 features
        while len(features) < 22:
            features.append(0.0)

        return torch.tensor(features[:22], dtype=torch.float32)

    def _prepare_grok_opportunity_data(self, market_data: Dict, detection_result: Dict) -> Dict[str, Any]:
        """Prepare opportunity data for Grok analysis"""
        exchanges = market_data.get('exchanges', {})

        # Calculate spread and other metrics
        if len(exchanges) >= 2:
            exch_list = list(exchanges.values())
            bid0 = exch_list[0].get('bid')
            ask1 = exch_list[1].get('ask')
            if bid0 is not None and ask1 is not None and bid0 > 0:
                spread = abs(bid0 - ask1) / bid0
            else:
                spread = 0.0
        else:
            spread = 0.0

        # Extract volumes
        volumes = {}
        fees = {}
        for exch_name, exch_data in exchanges.items():
            volumes[exch_name] = exch_data.get('volume', 0) or 0
            # Estimate fees (simplified)
            if 'binance' in exch_name.lower():
                fees[exch_name] = 0.001
            elif 'coinbase' in exch_name.lower():
                fees[exch_name] = 0.002
            else:
                fees[exch_name] = 0.0015

        # Prepare opportunity data for Grok
        grok_data = {
            'pair': 'BTC/USDT',  # Default pair
            'exchanges': list(exchanges.keys()),
            'spread': spread,
            'probability': detection_result.get('confidence', 0.0),
            'volumes': volumes,
            'fees': fees
        }

        return grok_data

    def _prepare_advanced_model_input(self, market_data: Dict) -> Dict[str, torch.Tensor]:
        """Prepare input data for advanced ArbitrageTransformer model"""
        exchanges = market_data.get('exchanges', {})
        price_history = market_data.get('price_history', [])

        # Exchange mappings
        exchange_names = list(exchanges.keys())
        exchange_ids = [0, 1, 2]  # Default mapping for binance, coinbase, kraken

        # Create price sequences (batch_size=1, seq_len=100, num_exchanges=3, features=16)
        seq_len = 100
        num_exchanges = 3
        features_per_exchange = 16

        price_sequences = torch.zeros(1, seq_len, num_exchanges, features_per_exchange)

        # Fill price sequences with available data
        for i, exch_name in enumerate(['binance', 'coinbase', 'kraken'][:len(exchange_names)]):
            if exch_name in exchanges:
                exch_data = exchanges[exch_name]

                # Basic price features
                bid = exch_data.get('bid', 0) or 0
                ask = exch_data.get('ask', 0) or 0
                volume = exch_data.get('volume', 0) or 0

                # Create feature vector for this exchange
                features = [
                    bid, ask, (ask + bid) / 2,  # Price features
                    volume, volume * bid,  # Volume features
                    (ask - bid) / bid if bid > 0 else 0,  # Spread
                    bid * volume,  # Market cap proxy
                    np.log(bid) if bid > 0 else 0,  # Log price
                    volume / bid if bid > 0 else 0,  # Volume/price ratio
                ]

                # Add price history features if available
                if price_history:
                    returns = np.diff(price_history) / price_history[:-1] if len(price_history) > 1 else [0]
                    features.extend([
                        np.mean(returns[-10:]) if len(returns) >= 10 else 0,  # Short-term return
                        np.std(returns[-10:]) if len(returns) >= 10 else 0,   # Short-term volatility
                        np.mean(returns[-50:]) if len(returns) >= 50 else 0,  # Medium-term return
                        np.std(returns[-50:]) if len(returns) >= 50 else 0,   # Medium-term volatility
                        np.mean(returns) if returns.size > 0 else 0,          # Long-term return
                        np.std(returns) if returns.size > 0 else 0,           # Long-term volatility
                    ])

                # Pad features to 16
                while len(features) < features_per_exchange:
                    features.append(0.0)

                # Fill sequence with this feature vector (repeated for simplicity)
                for t in range(seq_len):
                    price_sequences[0, t, i, :] = torch.tensor(features[:features_per_exchange])

        # Exchange IDs tensor
        exchange_ids_tensor = torch.tensor(exchange_ids, dtype=torch.long).unsqueeze(0)

        # Pair ID (default to 0 for BTC/USDT)
        pair_ids = torch.tensor([0], dtype=torch.long)

        return {
            'price_sequences': price_sequences.to(self.device),
            'exchange_ids': exchange_ids_tensor.to(self.device),
            'pair_ids': pair_ids.to(self.device)
        }

class LocalDatabase:
    """Simple SQLite database for local storage"""

    def __init__(self, db_path: str = 'arbitrage_data.db'):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    arbitrage_signal REAL,
                    confidence REAL,
                    opportunity_detected BOOLEAN,
                    exchanges TEXT,
                    features TEXT
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS market_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    exchange TEXT,
                    bid REAL,
                    ask REAL,
                    volume REAL
                )
            ''')

    def save_opportunity(self, result: Dict, market_data: Dict):
        """Save detection result"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO opportunities
                (timestamp, arbitrage_signal, confidence, opportunity_detected, exchanges, features)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                result['timestamp'],
                result['arbitrage_signal'],
                result['confidence'],
                result['opportunity_detected'],
                json.dumps(list(market_data.get('exchanges', {}).keys())),
                json.dumps(result)
            ))

    def get_recent_opportunities(self, limit: int = 10) -> List[Dict]:
        """Get recent opportunities"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM opportunities
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

            columns = [desc[0] for desc in cursor.description]
            opportunities = []

            for row in cursor.fetchall():
                opp = dict(zip(columns, row))
                opp['exchanges'] = json.loads(opp['exchanges'])
                opp['features'] = json.loads(opp['features'])
                opportunities.append(opp)

            return opportunities

def create_sample_data() -> Dict:
    """Create sample market data for testing"""
    return {
        'exchanges': {
            'binance': {
                'bid': 45000.0,
                'ask': 45010.0,
                'volume': 100.0
            },
            'coinbase': {
                'bid': 44990.0,
                'ask': 45000.0,
                'volume': 95.0
            }
        },
        'price_history': [45000 + i * 0.1 for i in range(100)],
        'timestamp': datetime.now()
    }

def main():
    """Main function for arbitrage detection"""
    print("SovereignForge Arbitrage Detector - Wave 1")
    print("=" * 45)

    # Initialize components
    detector = ArbitrageDetector()
    database = LocalDatabase()

    print(f"Using device: {detector.device}")
    print(f"Model parameters: {sum(p.numel() for p in detector.model.parameters())}")

    # Test with sample data
    print("\nTesting with sample data...")
    sample_data = create_sample_data()

    result = detector.detect_opportunity(sample_data)
    print(f"Arbitrage signal: {result['arbitrage_signal']:.6f}")
    print(f"Confidence: {result['confidence']:.4f}")
    print(f"Opportunity detected: {result['opportunity_detected']}")

    # Save result
    database.save_opportunity(result, sample_data)
    print("Result saved to database")

    # Show recent opportunities
    recent = database.get_recent_opportunities(5)
    print(f"\nRecent opportunities: {len(recent)}")

    print("\nArbitrage detector ready for use!")

if __name__ == "__main__":
    main()