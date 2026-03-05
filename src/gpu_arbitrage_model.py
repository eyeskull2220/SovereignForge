# SovereignForge GPU Arbitrage Model - Wave 7
# Advanced GPU-accelerated ML models for multi-pair arbitrage detection

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import TransformerEncoder, TransformerEncoderLayer
import math
import numpy as np
import time
from typing import Dict, List, Optional, Tuple, Any
import logging
from dataclasses import dataclass
from .gpu_manager import get_gpu_manager

logger = logging.getLogger(__name__)

@dataclass
class ArbitrageFeatures:
    """Features for arbitrage detection"""
    price_spread: float
    volume_ratio: float
    order_book_imbalance: float
    volatility_ratio: float
    exchange_correlation: float
    time_to_convergence: float
    transaction_costs: float
    liquidity_score: float

@dataclass
class ModelConfig:
    """Model configuration"""
    input_size: int = 64
    hidden_size: int = 512  # Increased for GPU Max
    num_layers: int = 12    # Doubled for GPU Max
    num_heads: int = 16     # Doubled for GPU Max
    dropout: float = 0.1
    max_seq_length: int = 200  # Doubled for GPU Max
    num_pairs: int = 7
    num_exchanges: int = 3
    gradient_accumulation_steps: int = 4  # Added for GPU Max

class MultiHeadAttention(nn.Module):
    """Multi-head attention for cross-exchange relationships"""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.attention = nn.MultiheadAttention(
            embed_dim=config.hidden_size,
            num_heads=config.num_heads,
            dropout=config.dropout,
            batch_first=True
        )
        self.norm = nn.LayerNorm(config.hidden_size)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        attn_output, _ = self.attention(x, x, x, attn_mask=mask)
        return self.norm(x + self.dropout(attn_output))

class TemporalFusionBlock(nn.Module):
    """Temporal fusion block for time-series processing"""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        # Local processing
        self.local_conv = nn.Conv1d(
            config.hidden_size, config.hidden_size,
            kernel_size=3, padding=1
        )

        # Global temporal attention
        self.temporal_attention = MultiHeadAttention(config)

        # Gating mechanism
        self.gate = nn.Sequential(
            nn.Linear(config.hidden_size * 2, config.hidden_size),
            nn.Sigmoid()
        )

        self.norm = nn.LayerNorm(config.hidden_size)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Local convolution
        x_conv = self.local_conv(x.transpose(1, 2)).transpose(1, 2)

        # Temporal attention
        x_attn = self.temporal_attention(x)

        # Gating
        gate_input = torch.cat([x_conv, x_attn], dim=-1)
        gate = self.gate(gate_input)

        # Combine local and global features
        output = gate * x_conv + (1 - gate) * x_attn

        return self.norm(x + self.dropout(output))

class CrossExchangeGNN(nn.Module):
    """Graph Neural Network for cross-exchange arbitrage modeling"""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        # Exchange embeddings
        self.exchange_embedding = nn.Embedding(config.num_exchanges, config.hidden_size)

        # Graph convolution layers
        self.graph_conv1 = nn.Linear(config.hidden_size, config.hidden_size)
        self.graph_conv2 = nn.Linear(config.hidden_size, config.hidden_size)

        # Attention for exchange relationships
        self.exchange_attention = MultiHeadAttention(config)

        self.norm1 = nn.LayerNorm(config.hidden_size)
        self.norm2 = nn.LayerNorm(config.hidden_size)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, exchange_features: torch.Tensor, exchange_ids: torch.Tensor) -> torch.Tensor:
        # Exchange embeddings
        exchange_emb = self.exchange_embedding(exchange_ids)

        # Combine with features
        x = exchange_features + exchange_emb

        # Graph convolution 1
        x_conv1 = self.graph_conv1(x)
        x = self.norm1(x + self.dropout(x_conv1))

        # Cross-exchange attention
        x_attn = self.exchange_attention(x)

        # Graph convolution 2
        x_conv2 = self.graph_conv2(x_attn)
        x = self.norm2(x_attn + self.dropout(x_conv2))

        return x

class ArbitrageTransformer(nn.Module):
    """Transformer-based arbitrage detection model"""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        # Input embedding
        self.input_embedding = nn.Linear(config.input_size, config.hidden_size)

        # Positional encoding
        self.pos_encoder = PositionalEncoding(config.hidden_size, config.dropout, config.max_seq_length)

        # Temporal fusion layers
        self.temporal_layers = nn.ModuleList([
            TemporalFusionBlock(config) for _ in range(config.num_layers // 2)
        ])

        # Cross-exchange GNN
        self.cross_exchange_gnn = CrossExchangeGNN(config)

        # Pair-specific attention
        self.pair_attention = MultiHeadAttention(config)

        # Output layers (logits for BCEWithLogitsLoss compatibility)
        self.arbitrage_head = nn.Sequential(
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_size // 2, 1)
        )

        self.confidence_head = nn.Sequential(
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_size // 2, 1)
        )

        self.spread_head = nn.Sequential(
            nn.Linear(config.hidden_size, config.hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_size // 2, 1)
        )

    def forward(self, market_data: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """
        Forward pass for arbitrage detection

        Args:
            market_data: Dictionary containing:
                - 'price_sequences': [batch, seq_len, num_exchanges, num_features]
                - 'exchange_ids': [batch, num_exchanges]
                - 'pair_ids': [batch]
        """
        price_sequences = market_data['price_sequences']  # [batch, seq_len, num_exchanges, features]
        exchange_ids = market_data['exchange_ids']        # [batch, num_exchanges]
        pair_ids = market_data['pair_ids']                # [batch]

        # Handle batched data from DataLoader
        if len(price_sequences.shape) == 5:  # [batch_size, 1, seq_len, num_exchanges, num_features]
            batch_size, _, seq_len, num_exchanges, num_features = price_sequences.shape
            price_sequences = price_sequences.squeeze(1)  # Remove the extra dimension
        else:
            batch_size, seq_len, num_exchanges, num_features = price_sequences.shape

        # Flatten exchange and feature dimensions for embedding
        x = price_sequences.view(batch_size * seq_len, num_exchanges * num_features)
        x = self.input_embedding(x)  # [batch * seq_len, hidden_size]
        x = x.view(batch_size, seq_len, -1)  # [batch, seq_len, hidden_size]

        # Add positional encoding
        x = self.pos_encoder(x)

        # Temporal fusion processing
        for layer in self.temporal_layers:
            x = layer(x)  # [batch, seq_len, hidden_size]

        # Aggregate temporal features
        temporal_features = x.mean(dim=1)  # [batch, hidden_size]

        # Cross-exchange processing
        # Create exchange feature matrix
        exchange_features = temporal_features.unsqueeze(1).expand(-1, num_exchanges, -1)
        exchange_features = self.cross_exchange_gnn(exchange_features, exchange_ids)

        # Pair-specific attention across exchanges
        pair_representation = self.pair_attention(exchange_features)

        # Global average pooling across exchanges
        arbitrage_features = pair_representation.mean(dim=1)  # [batch, hidden_size]

        # Generate predictions
        arbitrage_probability = self.arbitrage_head(arbitrage_features).squeeze(-1)
        confidence_score = self.confidence_head(arbitrage_features).squeeze(-1)
        spread_prediction = self.spread_head(arbitrage_features).squeeze(-1)

        return {
            'arbitrage_probability': arbitrage_probability,
            'confidence_score': confidence_score,
            'spread_prediction': spread_prediction,
            'features': arbitrage_features
        }

class PositionalEncoding(nn.Module):
    """Positional encoding for transformer"""

    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        pe = torch.zeros(max_len, 1, d_model)
        pe[:, 0, 0::2] = torch.sin(position * div_term)
        pe[:, 0, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:x.size(0)]
        return self.dropout(x)

class MultiPairArbitrageTrainer:
    """GPU-accelerated trainer for multi-pair arbitrage models"""

    def __init__(self, config: ModelConfig, pairs: List[str], exchanges: List[str]):
        self.config = config
        self.pairs = pairs
        self.exchanges = exchanges
        self.gpu_manager = get_gpu_manager()

        # Initialize models for each pair
        self.models = {}
        self.optimizers = {}
        self.schedulers = {}

        for pair in pairs:
            model = ArbitrageTransformer(config)
            if self.gpu_manager and self.gpu_manager.is_available():
                model = model.to(self.gpu_manager.get_device())

            self.models[pair] = model
            self.optimizers[pair] = torch.optim.AdamW(
                model.parameters(),
                lr=1e-4,
                weight_decay=1e-5,
                betas=(0.9, 0.999)
            )
            self.schedulers[pair] = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
                self.optimizers[pair], T_0=10, T_mult=2
            )

        # Training state
        self.training_stats = {}
        self.best_models = {}

    def train_epoch(self, pair: str, train_loader: torch.utils.data.DataLoader,
                   val_loader: Optional[torch.utils.data.DataLoader] = None) -> Dict[str, float]:
        """Train one epoch for a specific pair"""

        model = self.models[pair]
        optimizer = self.optimizers[pair]
        scheduler = self.schedulers[pair]

        model.train()
        epoch_stats = {
            'train_loss': 0.0,
            'train_arbitrage_acc': 0.0,
            'val_loss': 0.0,
            'val_arbitrage_acc': 0.0
        }

        num_batches = len(train_loader)

        for batch_idx, batch in enumerate(train_loader):
            try:
                # Move batch to GPU if available
                if self.gpu_manager and self.gpu_manager.is_available():
                    batch = {k: v.to(self.gpu_manager.get_device()) for k, v in batch.items()}

                # Forward pass
                with torch.amp.autocast('cuda', enabled=self.gpu_manager.is_available()):
                    outputs = model(batch)

                    # Compute losses (using BCEWithLogitsLoss for autocast compatibility)
                    arbitrage_loss = F.binary_cross_entropy_with_logits(
                        outputs['arbitrage_probability'],
                        batch['arbitrage_label'].float()
                    )

                    confidence_loss = F.mse_loss(
                        outputs['confidence_score'],
                        batch['confidence_label'].squeeze(-1)
                    )

                    spread_loss = F.mse_loss(
                        outputs['spread_prediction'],
                        batch['spread_label'].squeeze(-1)
                    )

                    total_loss = arbitrage_loss + 0.5 * confidence_loss + 0.3 * spread_loss

                # Backward pass with gradient scaling
                optimizer.zero_grad()

                if self.gpu_manager and self.gpu_manager.scaler:
                    self.gpu_manager.scaler.scale(total_loss).backward()
                    self.gpu_manager.scaler.step(optimizer)
                    self.gpu_manager.scaler.update()
                else:
                    total_loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                    optimizer.step()

                # Update statistics
                epoch_stats['train_loss'] += total_loss.item()

                # Arbitrage accuracy (apply sigmoid to logits)
                arbitrage_prob = torch.sigmoid(outputs['arbitrage_probability'])
                arbitrage_pred = (arbitrage_prob > 0.5).float()
                arbitrage_acc = (arbitrage_pred == batch['arbitrage_label']).float().mean()
                epoch_stats['train_arbitrage_acc'] += arbitrage_acc.item()

                # Log progress
                if batch_idx % 10 == 0:
                    logger.info(f"Pair {pair} - Batch {batch_idx}/{num_batches} - Loss: {total_loss.item():.4f}")

            except Exception as e:
                logger.error(f"Training error for pair {pair}, batch {batch_idx}: {e}")
                continue

        # Average statistics
        epoch_stats['train_loss'] /= num_batches
        epoch_stats['train_arbitrage_acc'] /= num_batches

        # Validation
        if val_loader:
            val_stats = self.validate(pair, val_loader)
            epoch_stats.update(val_stats)

        # Update learning rate
        scheduler.step()

        return epoch_stats

    def validate(self, pair: str, val_loader: torch.utils.data.DataLoader) -> Dict[str, float]:
        """Validate model for a specific pair"""

        model = self.models[pair]
        model.eval()

        val_stats = {'val_loss': 0.0, 'val_arbitrage_acc': 0.0}
        num_batches = len(val_loader)

        with torch.no_grad():
            for batch in val_loader:
                try:
                    # Move batch to GPU if available
                    if self.gpu_manager and self.gpu_manager.is_available():
                        batch = {k: v.to(self.gpu_manager.get_device()) for k, v in batch.items()}

                    outputs = model(batch)

                    # Compute losses (using BCEWithLogitsLoss for autocast compatibility)
                    arbitrage_loss = F.binary_cross_entropy_with_logits(
                        outputs['arbitrage_probability'],
                        batch['arbitrage_label'].float()
                    )

                    confidence_loss = F.mse_loss(
                        outputs['confidence_score'],
                        batch['confidence_label'].squeeze(-1)
                    )

                    spread_loss = F.mse_loss(
                        outputs['spread_prediction'],
                        batch['spread_label'].squeeze(-1)
                    )

                    total_loss = arbitrage_loss + 0.5 * confidence_loss + 0.3 * spread_loss

                    val_stats['val_loss'] += total_loss.item()

                    # Arbitrage accuracy (apply sigmoid to logits)
                    arbitrage_prob = torch.sigmoid(outputs['arbitrage_probability'])
                    arbitrage_pred = (arbitrage_prob > 0.5).float()
                    arbitrage_acc = (arbitrage_pred == batch['arbitrage_label']).float().mean()
                    val_stats['val_arbitrage_acc'] += arbitrage_acc.item()

                except Exception as e:
                    logger.error(f"Validation error for pair {pair}: {e}")
                    continue

        val_stats['val_loss'] /= num_batches
        val_stats['val_arbitrage_acc'] /= num_batches

        return val_stats

    def train_all_pairs(self, train_loaders: Dict[str, torch.utils.data.DataLoader],
                       val_loaders: Optional[Dict[str, torch.utils.data.DataLoader]] = None,
                       num_epochs: int = 50) -> Dict[str, List[Dict[str, float]]]:
        """Train all pairs concurrently"""

        training_history = {pair: [] for pair in self.pairs}

        logger.info(f"Starting multi-pair training for {len(self.pairs)} pairs on GPU")

        for epoch in range(num_epochs):
            epoch_start = torch.cuda.Event(enable_timing=True) if torch.cuda.is_available() else None
            if epoch_start:
                epoch_start.record()

            logger.info(f"Epoch {epoch + 1}/{num_epochs}")

            # Train each pair
            for pair in self.pairs:
                if pair in train_loaders:
                    epoch_stats = self.train_epoch(
                        pair,
                        train_loaders[pair],
                        val_loaders.get(pair) if val_loaders else None
                    )
                    training_history[pair].append(epoch_stats)

                    # Save best model
                    if not self.best_models.get(pair) or epoch_stats['val_arbitrage_acc'] > self.best_models[pair]['accuracy']:
                        self.best_models[pair] = {
                            'epoch': epoch,
                            'accuracy': epoch_stats['val_arbitrage_acc'],
                            'loss': epoch_stats['val_loss']
                        }
                        self.save_model(pair, f"best_{pair.replace('/', '_')}_epoch_{epoch}")

            # GPU memory cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Timing
            if epoch_start and torch.cuda.is_available():
                epoch_end = torch.cuda.Event(enable_timing=True)
                epoch_end.record()
                torch.cuda.synchronize()
                epoch_time = epoch_start.elapsed_time(epoch_end) / 1000  # seconds
                logger.info(".2f")

        logger.info("Multi-pair training completed")
        return training_history

    def save_model(self, pair: str, filename: str):
        """Save model checkpoint"""
        model = self.models[pair]
        optimizer = self.optimizers[pair]

        checkpoint = {
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'config': self.config,
            'pair': pair,
            'timestamp': time.time()
        }

        torch.save(checkpoint, f"E:\\Users\\Gino\\Downloads\\SovereignForge\\models\\{filename}.pth")
        logger.info(f"Saved model checkpoint: {filename}")

    def load_model(self, pair: str, filename: str):
        """Load model checkpoint"""
        checkpoint = torch.load(f"E:\\Users\\Gino\\Downloads\\SovereignForge\\models\\{filename}.pth")

        model = self.models[pair]
        optimizer = self.optimizers[pair]

        model.load_state_dict(checkpoint['model_state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])

        logger.info(f"Loaded model checkpoint: {filename}")

    def predict_arbitrage(self, pair: str, market_data: Dict[str, torch.Tensor]) -> Dict[str, float]:
        """Predict arbitrage opportunity for a pair"""

        model = self.models[pair]
        model.eval()

        with torch.no_grad():
            if self.gpu_manager and self.gpu_manager.is_available():
                market_data = {k: v.to(self.gpu_manager.get_device()) for k, v in market_data.items()}

            outputs = model(market_data)

            return {
                'arbitrage_probability': outputs['arbitrage_probability'].item(),
                'confidence_score': outputs['confidence_score'].item(),
                'spread_prediction': outputs['spread_prediction'].item()
            }

# Utility functions for GPU optimization

def create_arbitrage_dataset(pairs: List[str], exchanges: List[str], sequence_length: int = 100):
    """Create dataset for arbitrage training"""

    class ArbitrageDataset(torch.utils.data.Dataset):
        def __init__(self, pairs, exchanges, seq_len):
            self.pairs = pairs
            self.exchanges = exchanges
            self.seq_len = seq_len
            # In real implementation, load from database/cache
            self.data = self._generate_sample_data()

        def _generate_sample_data(self):
            # Generate sample data for demonstration (GPU Max: larger dataset)
            num_samples = 25000  # Increased for GPU Max
            data = []

            # Always generate on CPU for DataLoader compatibility
            device = torch.device('cpu')

            for _ in range(num_samples):
                sample = {
                    'price_sequences': torch.randn(1, self.seq_len, len(self.exchanges), 16, device=device),  # [batch=1, seq_len, exchanges, features]
                    'exchange_ids': torch.tensor([i for i in range(len(self.exchanges))], device=device),
                    'pair_ids': torch.tensor(np.random.randint(0, len(self.pairs)), device=device),
                    'arbitrage_label': torch.tensor(np.random.choice([0, 1], p=[0.7, 0.3]), device=device),  # 30% arbitrage opportunities
                    'confidence_label': torch.rand(1, device=device),
                    'spread_label': torch.randn(1, device=device) * 0.01  # Small spread
                }
                data.append(sample)

            return data

        def __len__(self):
            return len(self.data)

        def __getitem__(self, idx):
            return self.data[idx]

    return ArbitrageDataset(pairs, exchanges, sequence_length)

def setup_gpu_training():
    """Setup optimal GPU training configuration"""

    gpu_manager = get_gpu_manager()

    if gpu_manager and gpu_manager.is_available():
        device = gpu_manager.get_device()

        # Enable cuDNN optimization
        torch.backends.cudnn.benchmark = True

        # Set memory efficient options
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

        # Gradient checkpointing for memory efficiency (disabled for compatibility)
        # torch.utils.checkpoint.checkpoint uses reentrant=False by default in newer versions

        logger.info(f"GPU training setup complete on {torch.cuda.get_device_name(device)}")
        return True
    else:
        logger.warning("GPU not available, using CPU training")
        return False

# Training pipeline
def run_gpu_arbitrage_training(pairs: List[str] = None, exchanges: List[str] = None,
                              num_epochs: int = 50, batch_size: int = 64):
    """Run complete GPU-accelerated arbitrage training pipeline"""

    if pairs is None:
        pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT']

    if exchanges is None:
        exchanges = ['binance', 'coinbase', 'kraken']

    # Setup GPU
    gpu_available = setup_gpu_training()

    # Model configuration
    config = ModelConfig(
        input_size=48,  # 3 exchanges * 16 features each = 48
        hidden_size=256,
        num_layers=6,
        num_heads=8,
        num_pairs=len(pairs),
        num_exchanges=len(exchanges)
    )

    # Initialize trainer
    trainer = MultiPairArbitrageTrainer(config, pairs, exchanges)

    # Create datasets
    train_datasets = {}
    val_datasets = {}

    for pair in pairs:
        dataset = create_arbitrage_dataset([pair], exchanges, sequence_length=200)

        # Split into train/val
        train_size = int(0.8 * len(dataset))
        val_size = len(dataset) - train_size

        train_dataset, val_dataset = torch.utils.data.random_split(
            dataset, [train_size, val_size]
        )

        train_datasets[pair] = train_dataset
        val_datasets[pair] = val_dataset

    # Create data loaders
    train_loaders = {}
    val_loaders = {}

    gpu_manager = get_gpu_manager()

    for pair in pairs:
        train_loaders[pair] = gpu_manager.create_data_loader(
            train_datasets[pair], batch_size=batch_size, shuffle=True
        ) if gpu_manager else torch.utils.data.DataLoader(
            train_datasets[pair], batch_size=batch_size, shuffle=True
        )

        val_loaders[pair] = gpu_manager.create_data_loader(
            val_datasets[pair], batch_size=batch_size, shuffle=False
        ) if gpu_manager else torch.utils.data.DataLoader(
            val_datasets[pair], batch_size=batch_size, shuffle=False
        )

    # Train all pairs
    logger.info(f"Starting GPU training for {len(pairs)} pairs with {num_epochs} epochs")

    training_history = trainer.train_all_pairs(
        train_loaders, val_loaders, num_epochs
    )

    # Save final models
    for pair in pairs:
        trainer.save_model(pair, f"final_{pair.replace('/', '_')}")

    logger.info("GPU arbitrage training completed successfully")

    return training_history

if __name__ == "__main__":
    # Example usage
    training_results = run_gpu_arbitrage_training(num_epochs=10)
    print("Training completed!")
    print(f"Results: {len(training_results)} pairs trained")