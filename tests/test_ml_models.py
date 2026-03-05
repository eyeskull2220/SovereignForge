#!/usr/bin/env python3
"""
Comprehensive unit tests for SovereignForge ML models and training pipeline
"""

import unittest
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from multi_strategy_training import (
    TradingLSTM, create_lstm_model, create_gru_model,
    create_transformer_model, create_attention_model
)

class TestMLModels(unittest.TestCase):
    """Test ML model architectures and functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.batch_size = 32
        self.seq_length = 24
        self.input_size = 10
        self.output_size = 3
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def test_lstm_model_creation(self):
        """Test LSTM model creation and forward pass"""
        model = create_lstm_model(self.input_size, self.output_size)

        # Test model structure
        self.assertIsInstance(model, nn.Module)
        self.assertTrue(hasattr(model, 'lstm'))
        self.assertTrue(hasattr(model, 'fc'))

        # Test forward pass
        x = torch.randn(self.batch_size, self.seq_length, self.input_size)
        output = model(x)

        self.assertEqual(output.shape, (self.batch_size, self.output_size))

    def test_lstm_model_training(self):
        """Test LSTM model training loop"""
        model = create_lstm_model(self.input_size, self.output_size)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()

        # Training data
        x = torch.randn(self.batch_size, self.seq_length, self.input_size)
        y = torch.randn(self.batch_size, self.output_size)

        # Training step
        optimizer.zero_grad()
        output = model(x)
        loss = criterion(output, y)
        loss.backward()
        optimizer.step()

        # Verify loss decreased
        self.assertTrue(loss.item() > 0)
        self.assertTrue(torch.isfinite(loss))

    def test_gru_model_creation(self):
        """Test GRU model creation and forward pass"""
        model = create_gru_model(self.input_size, self.output_size)

        self.assertIsInstance(model, nn.Module)
        self.assertTrue(hasattr(model, 'gru'))
        self.assertTrue(hasattr(model, 'fc1'))
        self.assertTrue(hasattr(model, 'fc2'))

        # Test forward pass
        x = torch.randn(self.batch_size, self.seq_length, self.input_size)
        output = model(x)

        self.assertEqual(output.shape, (self.batch_size, self.output_size))

    def test_transformer_model_creation(self):
        """Test Transformer model creation and forward pass"""
        model = create_transformer_model(self.input_size, self.output_size)

        self.assertIsInstance(model, nn.Module)
        self.assertTrue(hasattr(model, 'input_projection'))
        self.assertTrue(hasattr(model, 'transformer'))

        # Test forward pass
        x = torch.randn(self.batch_size, self.seq_length, self.input_size)
        output = model(x)

        self.assertEqual(output.shape, (self.batch_size, self.output_size))

    def test_attention_model_creation(self):
        """Test Attention model creation and forward pass"""
        model = create_attention_model(self.input_size, self.output_size)

        self.assertIsInstance(model, nn.Module)
        self.assertTrue(hasattr(model, 'encoder'))
        self.assertTrue(hasattr(model, 'attention'))

        # Test forward pass
        x = torch.randn(self.batch_size, self.seq_length, self.input_size)
        output = model(x)

        self.assertEqual(output.shape, (self.batch_size, self.output_size))

    def test_model_gpu_compatibility(self):
        """Test models work on GPU if available"""
        if torch.cuda.is_available():
            model = create_lstm_model(self.input_size, self.output_size)
            model = model.to(self.device)

            x = torch.randn(self.batch_size, self.seq_length, self.input_size).to(self.device)
            output = model(x)

            self.assertEqual(output.device, self.device)
            self.assertEqual(output.shape, (self.batch_size, self.output_size))

    def test_model_serialization(self):
        """Test model save and load functionality"""
        model = create_lstm_model(self.input_size, self.output_size)

        # Save model
        save_path = Path("test_model.pth")
        torch.save(model.state_dict(), save_path)
        self.assertTrue(save_path.exists())

        # Load model
        new_model = create_lstm_model(self.input_size, self.output_size)
        new_model.load_state_dict(torch.load(save_path))

        # Test loaded model
        x = torch.randn(self.batch_size, self.seq_length, self.input_size)
        original_output = model(x)
        loaded_output = new_model(x)

        self.assertTrue(torch.allclose(original_output, loaded_output))

        # Cleanup
        save_path.unlink()

    def test_model_gradient_flow(self):
        """Test that gradients flow properly through models"""
        model = create_lstm_model(self.input_size, self.output_size)
        x = torch.randn(self.batch_size, self.seq_length, self.input_size)
        y = torch.randn(self.batch_size, self.output_size)

        # Forward pass
        output = model(x)
        loss = nn.MSELoss()(output, y)

        # Backward pass
        loss.backward()

        # Check gradients
        for name, param in model.named_parameters():
            self.assertIsNotNone(param.grad)
            self.assertTrue(torch.isfinite(param.grad).all())

    def test_model_memory_efficiency(self):
        """Test models don't have excessive memory usage"""
        model = create_lstm_model(self.input_size, self.output_size)

        # Count parameters
        total_params = sum(p.numel() for p in model.parameters())
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

        # Reasonable parameter counts for trading models
        self.assertLess(total_params, 1000000)  # Less than 1M parameters
        self.assertGreater(total_params, 1000)  # More than 1K parameters
        self.assertEqual(total_params, trainable_params)  # All params trainable

class TestTrainingPipeline(unittest.TestCase):
    """Test training pipeline components"""

    def test_data_generation(self):
        """Test synthetic data generation"""
        from data_generator import MarketDataGenerator

        gen = MarketDataGenerator()
        df = gen.generate_ohlcv_data('BTC/USDT', days=1)

        # Check required columns
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            self.assertIn(col, df.columns)

        # Check data integrity
        self.assertGreater(len(df), 0)
        self.assertTrue((df['high'] >= df['low']).all())
        self.assertTrue((df['close'] >= df['low']).all())
        self.assertTrue((df['close'] <= df['high']).all())

    def test_technical_indicators(self):
        """Test technical indicator calculations"""
        from data_generator import MarketDataGenerator

        gen = MarketDataGenerator()
        df = gen.generate_ohlcv_data('BTC/USDT', days=30)  # Need more data for indicators
        df_with_indicators = gen.add_technical_indicators(df)

        # Check indicator columns exist
        indicator_cols = ['sma_20', 'ema_12', 'rsi', 'macd', 'bb_upper', 'bb_lower']
        for col in indicator_cols:
            self.assertIn(col, df_with_indicators.columns)

        # Check no NaN values (should be filled)
        self.assertFalse(df_with_indicators.isnull().any().any())

if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)