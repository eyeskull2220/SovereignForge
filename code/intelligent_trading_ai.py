"""
SovereignForge v1 - Intelligent Trading AI
Reinforcement learning and AI-driven trading strategies
"""

import logging
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from stable_baselines3 import PPO, A2C, SAC
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from gym import spaces
import gym
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from database import get_database
from trading import TradingEngine, TradingConfig, ArbitrageOpportunity
from gpu_accelerated_analysis import TimeSeriesFeatures, ArbitrageFeatures
from agents import CEOManager

logging.basicConfig(level=logging.INFO)

@dataclass
class MarketState:
    """Current market state for RL agent"""
    coin_prices: Dict[str, float]
    spreads: Dict[str, float]
    volumes: Dict[str, float]
    session: str
    timestamp: datetime
    features: TimeSeriesFeatures

@dataclass
class TradingAction:
    """Action taken by RL agent"""
    action_type: str  # 'BUY', 'SELL', 'HOLD'
    coin: str
    exchange_buy: str
    exchange_sell: str
    position_size: float
    confidence: float

@dataclass
class MarketRegime:
    """Market regime classification"""
    regime: str  # 'TRENDING_UP', 'TRENDING_DOWN', 'RANGING', 'VOLATILE', 'SIDEWAYS'
    confidence: float
    features: Dict[str, float]

class TradingEnvironment(gym.Env):
    """Custom Gym environment for arbitrage trading"""

    def __init__(self, initial_balance: float = 10000):
        super().__init__()

        # Action space: [action_type, coin_idx, exchange_buy_idx, exchange_sell_idx, position_size]
        # action_type: 0=HOLD, 1=BUY/SELL arbitrage
        self.action_space = spaces.MultiDiscrete([2, 12, 5, 5, 10])  # 12 coins, 5 exchanges, 10 position sizes

        # Observation space: market state features
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(50,), dtype=np.float32
        )

        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = {}
        self.episode_steps = 0
        self.max_steps = 1000

        # Market data
        self.market_data = []
        self.current_step = 0

        # Performance tracking
        self.trades = []
        self.portfolio_values = [initial_balance]

    def reset(self):
        """Reset environment"""
        self.current_balance = self.initial_balance
        self.position = {}
        self.episode_steps = 0
        self.current_step = 0
        self.trades = []
        self.portfolio_values = [self.initial_balance]

        return self._get_observation()

    def step(self, action):
        """Execute one step in the environment"""
        self.episode_steps += 1

        # Parse action
        action_type, coin_idx, buy_ex_idx, sell_ex_idx, size_idx = action

        # Coin and exchange mapping
        coins = ['XRP', 'XLM', 'HBAR', 'ALGO', 'ADA', 'LINK', 'IOTA', 'XDC', 'ONDO', 'VET', 'USDC', 'RLUSD']
        exchanges = ['binance', 'kraken', 'coinbase', 'okx']

        coin = coins[coin_idx]
        buy_exchange = exchanges[buy_ex_idx]
        sell_exchange = exchanges[sell_ex_idx]

        # Position size (0.01 to 1.0)
        position_size_pct = (size_idx + 1) / 10.0

        reward = 0
        done = False

        if action_type == 1 and self._is_valid_arbitrage(coin, buy_exchange, sell_exchange):
            # Execute arbitrage trade
            success, pnl = self._execute_arbitrage_trade(coin, buy_exchange, sell_exchange, position_size_pct)

            if success:
                reward = pnl * 100  # Scale reward
                self.trades.append({
                    'step': self.episode_steps,
                    'coin': coin,
                    'pnl': pnl,
                    'balance_after': self.current_balance
                })

        # Update portfolio value
        self.portfolio_values.append(self.current_balance)

        # Check if episode is done
        if self.episode_steps >= self.max_steps:
            done = True

        # Calculate Sharpe ratio reward component
        if len(self.portfolio_values) > 10:
            returns = np.diff(self.portfolio_values[-20:]) / self.portfolio_values[-21:-1]
            if len(returns) > 1:
                sharpe = np.mean(returns) / (np.std(returns) + 1e-8)
                reward += sharpe * 10  # Sharpe ratio bonus

        return self._get_observation(), reward, done, {}

    def _is_valid_arbitrage(self, coin: str, buy_exchange: str, sell_exchange: str) -> bool:
        """Check if arbitrage opportunity is valid"""
        # Simplified validation - in practice would check real spreads
        return buy_exchange != sell_exchange

    def _execute_arbitrage_trade(self, coin: str, buy_exchange: str, sell_exchange: str, size_pct: float) -> Tuple[bool, float]:
        """Execute arbitrage trade (simplified simulation)"""
        # Simulate trade execution with random success
        success_probability = 0.7  # 70% success rate
        success = np.random.random() < success_probability

        if success:
            # Random PnL between -2% and +5%
            pnl_pct = np.random.uniform(-0.02, 0.05)
            trade_amount = self.current_balance * size_pct * 0.1  # Max 10% of balance per trade
            pnl = trade_amount * pnl_pct
            self.current_balance += pnl
            return True, pnl
        else:
            # Small loss on failed trade
            loss = self.current_balance * size_pct * 0.005
            self.current_balance -= loss
            return False, -loss

    def _get_observation(self) -> np.ndarray:
        """Get current observation"""
        # Simplified observation - in practice would include real market data
        obs = np.random.normal(0, 1, 50).astype(np.float32)

        # Add some structure
        obs[0] = self.current_balance / self.initial_balance  # Normalized balance
        obs[1] = len(self.position)  # Number of positions
        obs[2] = self.episode_steps / self.max_steps  # Episode progress

        return obs

    def render(self, mode='human'):
        """Render environment"""
        print(f"Step: {self.episode_steps}, Balance: ${self.current_balance:.2f}, Trades: {len(self.trades)}")

class MarketRegimeDetector:
    """AI-powered market regime detection"""

    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Simple regime classification model
        self.model = nn.Sequential(
            nn.Linear(20, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 5)  # 5 regime classes
        ).to(self.device)

        self.regime_classes = ['TRENDING_UP', 'TRENDING_DOWN', 'RANGING', 'VOLATILE', 'SIDEWAYS']

    def detect_regime(self, features: TimeSeriesFeatures) -> MarketRegime:
        """Detect current market regime"""
        # Extract features for regime detection
        feature_vector = np.array([
            features.volatility,
            features.trend_strength,
            features.mean_reversion,
            features.momentum,
            np.mean(features.returns) if len(features.returns) > 0 else 0,
            np.std(features.returns) if len(features.returns) > 0 else 0,
        ] * 3)  # Repeat to fill 20 features

        # Normalize
        feature_vector = (feature_vector - np.mean(feature_vector)) / (np.std(feature_vector) + 1e-8)

        # Convert to tensor
        input_tensor = torch.tensor(feature_vector, dtype=torch.float32, device=self.device).unsqueeze(0)

        # Predict regime
        with torch.no_grad():
            outputs = self.model(input_tensor)
            probabilities = torch.softmax(outputs, dim=1)
            predicted_class = torch.argmax(probabilities, dim=1).item()
            confidence = probabilities[0, predicted_class].item()

        regime = self.regime_classes[predicted_class]

        return MarketRegime(
            regime=regime,
            confidence=confidence,
            features={f'feature_{i}': float(feature_vector[i]) for i in range(len(feature_vector))}
        )

class ReinforcementLearningTrader:
    """Reinforcement learning-based trading agent"""

    def __init__(self, model_path: Optional[str] = None):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Create environment
        self.env = TradingEnvironment()

        # Initialize RL model
        self.model = PPO(
            "MlpPolicy",
            self.env,
            verbose=0,
            device=self.device,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01
        )

        if model_path and torch.cuda.is_available():
            try:
                self.model.load(model_path)
                logging.info(f"Loaded RL model from {model_path}")
            except Exception as e:
                logging.warning(f"Could not load model: {e}")

        # Training history
        self.training_rewards = []

    def train(self, total_timesteps: int = 10000):
        """Train the RL agent"""
        logging.info("Starting RL training...")

        # Custom callback for logging
        class TrainingCallback(BaseCallback):
            def __init__(self, verbose=0):
                super().__init__(verbose)

            def _on_step(self) -> bool:
                if self.n_calls % 1000 == 0:
                    logging.info(f"Training step {self.n_calls}")
                return True

        callback = TrainingCallback()

        # Train the model
        self.model.learn(total_timesteps=total_timesteps, callback=callback)

        # Save the model
        model_path = f"models/rl_trader_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.model.save(model_path)
        logging.info(f"Model saved to {model_path}")

    def predict_action(self, observation: np.ndarray) -> np.ndarray:
        """Predict trading action"""
        action, _ = self.model.predict(observation, deterministic=True)
        return action

    def evaluate_performance(self, n_episodes: int = 10) -> Dict:
        """Evaluate trained model performance"""
        episode_rewards = []
        episode_lengths = []
        win_rates = []

        for episode in range(n_episodes):
            obs = self.env.reset()
            done = False
            episode_reward = 0
            episode_length = 0
            wins = 0
            total_trades = 0

            while not done:
                action = self.predict_action(obs)
                obs, reward, done, info = self.env.step(action)

                episode_reward += reward
                episode_length += 1

                # Count winning trades
                if hasattr(self.env, 'trades') and self.env.trades:
                    last_trade = self.env.trades[-1]
                    if last_trade['pnl'] > 0:
                        wins += 1
                    total_trades += 1

            episode_rewards.append(episode_reward)
            episode_lengths.append(episode_length)

            if total_trades > 0:
                win_rates.append(wins / total_trades)
            else:
                win_rates.append(0)

        return {
            'mean_reward': np.mean(episode_rewards),
            'std_reward': np.std(episode_rewards),
            'mean_length': np.mean(episode_lengths),
            'mean_win_rate': np.mean(win_rates),
            'episodes': n_episodes
        }

class IntelligentTradingOrchestrator:
    """Orchestrates intelligent AI-driven trading"""

    def __init__(self):
        self.rl_trader = ReinforcementLearningTrader()
        self.regime_detector = MarketRegimeDetector()
        self.db = get_database()
        self.engine = TradingEngine(TradingConfig())
        self.ceo = CEOManager()

        # AI state
        self.current_regime = None
        self.confidence_threshold = 0.6
        self.is_ai_active = False

    async def initialize_ai_trading(self):
        """Initialize AI trading system"""
        logging.info("Initializing Intelligent Trading AI...")

        # Load or train RL model
        await self._load_or_train_model()

        # Initialize regime detector
        self.regime_detector = MarketRegimeDetector()

        self.is_ai_active = True
        logging.info("AI Trading system initialized")

    async def _load_or_train_model(self):
        """Load existing model or train new one"""
        # For demo, we'll train a small model
        # In production, load pre-trained model
        logging.info("Training RL model (this may take a while)...")
        self.rl_trader.train(total_timesteps=5000)  # Reduced for demo

    async def analyze_market_with_ai(self, coin: str, exchange: str) -> Dict:
        """AI-powered market analysis"""
        # Get market data
        market_data = await self._get_recent_market_data(coin, exchange, days=7)

        if market_data.empty:
            return {"error": "No market data available"}

        # Extract time series features using GPU acceleration
        from gpu_accelerated_analysis import get_gpu_orchestrator
        gpu_orchestrator = get_gpu_orchestrator()

        # Convert market data to expected format
        data_dict = {f"{coin}_{exchange}": market_data}

        # Analyze with GPU acceleration
        analysis_result = await gpu_orchestrator.run_accelerated_analysis(days=7)

        if not analysis_result['time_series_features']:
            return {"error": "Could not extract features"}

        # Get features
        features_key = list(analysis_result['time_series_features'].keys())[0]
        features = analysis_result['time_series_features'][features_key]

        # Detect market regime
        regime = self.regime_detector.detect_regime(features)

        # Generate AI trading signal
        signal = await self._generate_ai_signal(coin, features, regime)

        return {
            'coin': coin,
            'exchange': exchange,
            'regime': regime.regime,
            'regime_confidence': regime.confidence,
            'features': {
                'volatility': features.volatility,
                'trend_strength': features.trend_strength,
                'momentum': features.momentum,
                'mean_reversion': features.mean_reversion
            },
            'ai_signal': signal,
            'timestamp': datetime.utcnow()
        }

    async def _generate_ai_signal(self, coin: str, features: TimeSeriesFeatures, regime: MarketRegime) -> Dict:
        """Generate AI trading signal"""
        # Create observation for RL model
        observation = self._create_observation(coin, features, regime)

        # Get RL action
        action = self.rl_trader.predict_action(observation)

        # Interpret action
        action_type, coin_idx, buy_ex_idx, sell_ex_idx, size_idx = action

        coins = ['XRP', 'XLM', 'HBAR', 'ALGO', 'ADA', 'LINK', 'IOTA', 'XDC', 'ONDO', 'VET', 'USDC', 'RLUSD']
        exchanges = ['binance', 'kraken', 'coinbase', 'okx']

        signal = {
            'action': 'HOLD' if action_type == 0 else 'TRADE',
            'coin': coins[coin_idx],
            'buy_exchange': exchanges[buy_ex_idx],
            'sell_exchange': exchanges[sell_ex_idx],
            'position_size_pct': (size_idx + 1) / 10.0,
            'confidence': 0.5 + np.random.random() * 0.4,  # Simulated confidence
            'reasoning': self._generate_signal_reasoning(action, regime, features)
        }

        return signal

    def _create_observation(self, coin: str, features: TimeSeriesFeatures, regime: MarketRegime) -> np.ndarray:
        """Create observation vector for RL model"""
        # Simplified observation creation
        obs = np.zeros(50, dtype=np.float32)

        # Add feature data
        obs[0] = features.volatility
        obs[1] = features.trend_strength
        obs[2] = features.momentum
        obs[3] = features.mean_reversion

        # Add regime data
        regime_idx = ['TRENDING_UP', 'TRENDING_DOWN', 'RANGING', 'VOLATILE', 'SIDEWAYS'].index(regime.regime)
        obs[4 + regime_idx] = regime.confidence

        # Add coin encoding
        coin_idx = ['XRP', 'XLM', 'HBAR', 'ALGO', 'ADA', 'LINK', 'IOTA', 'XDC', 'ONDO', 'VET', 'USDC', 'RLUSD'].index(coin)
        obs[10 + coin_idx] = 1.0

        return obs

    def _generate_signal_reasoning(self, action: np.ndarray, regime: MarketRegime, features: TimeSeriesFeatures) -> str:
        """Generate human-readable reasoning for AI signal"""
        action_type, coin_idx, buy_ex_idx, sell_ex_idx, size_idx = action

        if action_type == 0:
            return f"HOLD: Market regime '{regime.regime}' with {regime.confidence:.1%} confidence suggests waiting"

        reasoning_parts = [
            f"TRADE: Detected {regime.regime} regime",
            f"Volatility: {features.volatility:.3f}",
            f"Momentum: {features.momentum:.2f}",
            f"AI confidence: {regime.confidence:.1%}"
        ]

        return " | ".join(reasoning_parts)

    async def _get_recent_market_data(self, coin: str, exchange: str, days: int) -> pd.DataFrame:
        """Get recent market data from database"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        session = self.db.get_session()
        try:
            from database import PriceData as PriceDataModel
            prices = session.query(PriceDataModel)\
                .filter_by(coin=coin, exchange=exchange)\
                .filter(PriceDataModel.timestamp >= start_date)\
                .filter(PriceDataModel.timestamp <= end_date)\
                .order_by(PriceDataModel.timestamp)\
                .all()

            if not prices:
                # Return empty DataFrame with correct structure
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'coin', 'exchange'])

            # Convert to DataFrame
            data = []
            for price in prices:
                data.append({
                    'timestamp': price.timestamp,
                    'open': price.price,
                    'high': price.price,
                    'low': price.price,
                    'close': price.price,
                    'volume': price.volume or 0,
                    'coin': coin,
                    'exchange': exchange
                })

            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)

            return df

        finally:
            session.close()

    async def get_ai_status(self) -> Dict:
        """Get AI system status"""
        return {
            'ai_active': self.is_ai_active,
            'current_regime': self.current_regime.regime if self.current_regime else None,
            'rl_model_loaded': self.rl_trader.model is not None,
            'gpu_accelerated': torch.cuda.is_available(),
            'confidence_threshold': self.confidence_threshold
        }

# Global AI orchestrator instance
ai_orchestrator = None

def init_intelligent_trading_ai() -> IntelligentTradingOrchestrator:
    """Initialize global AI trading orchestrator"""
    global ai_orchestrator
    if ai_orchestrator is None:
        ai_orchestrator = IntelligentTradingOrchestrator()
    return ai_orchestrator

def get_ai_orchestrator() -> IntelligentTradingOrchestrator:
    """Get global AI trading orchestrator"""
    global ai_orchestrator
    if ai_orchestrator is None:
        raise RuntimeError("AI trading not initialized. Call init_intelligent_trading_ai() first.")
    return ai_orchestrator

# Convenience functions
async def initialize_ai_system():
    """Initialize the complete AI trading system"""
    orchestrator = get_ai_orchestrator()
    await orchestrator.initialize_ai_trading()

async def analyze_with_ai(coin: str, exchange: str) -> Dict:
    """Analyze market with AI"""
    orchestrator = get_ai_orchestrator()
    return await orchestrator.analyze_market_with_ai(coin, exchange)

def get_ai_system_status() -> Dict:
    """Get AI system status"""
    orchestrator = get_ai_orchestrator()
    import asyncio
    # Create event loop if needed
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, we need to handle this differently
            return {"error": "Cannot get status while event loop is running"}
        else:
            return loop.run_until_complete(orchestrator.get_ai_status())
    except RuntimeError:
        # No event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(orchestrator.get_ai_status())
        finally:
            loop.close()