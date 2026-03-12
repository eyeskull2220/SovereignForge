#!/usr/bin/env python3
"""
SovereignForge - GPU-Accelerated Analysis Module
High-performance market analysis and arbitrage detection using GPU acceleration

This module provides:
- GPU-accelerated statistical analysis
- Real-time market data processing
- Arbitrage opportunity detection
- Performance metrics calculation
- Risk analysis and position sizing
"""

import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

@dataclass
class MarketAnalysisResult:
    """Result of GPU-accelerated market analysis"""
    timestamp: datetime
    arbitrage_opportunities: List[Dict[str, Any]]
    market_efficiency_score: float
    volatility_metrics: Dict[str, float]
    correlation_matrix: np.ndarray
    processing_time_ms: float
    gpu_memory_used_mb: float

@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity"""
    pair1: str
    pair2: str
    exchange1: str
    exchange2: str
    price_diff_pct: float
    volume_available: float
    estimated_profit: float
    risk_score: float
    confidence: float
    timestamp: datetime

class GPUAcceleratedAnalyzer:
    """
    GPU-accelerated market analysis engine
    """

    def __init__(self,
                 device: Optional[str] = None,
                 analysis_batch_size: int = 1000,
                 max_concurrent_analyses: int = 4):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.analysis_batch_size = analysis_batch_size
        self.max_concurrent_analyses = max_concurrent_analyses

        # GPU optimization
        if self.device == "cuda":
            torch.backends.cudnn.benchmark = True
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

        # Thread pool for concurrent analysis
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_analyses)
        self.analysis_lock = threading.RLock()

        # Performance tracking
        self.performance_stats = {
            "total_analyses": 0,
            "successful_analyses": 0,
            "average_processing_time_ms": 0.0,
            "peak_gpu_memory_mb": 0.0
        }

        logger.info(f"GPUAcceleratedAnalyzer initialized on device: {self.device}")

    def analyze_market_data(self,
                           market_data: Dict[str, pd.DataFrame],
                           analysis_types: List[str] = None) -> MarketAnalysisResult:
        """
        Perform comprehensive GPU-accelerated market analysis
        """
        start_time = time.time()

        if analysis_types is None:
            analysis_types = ["arbitrage", "volatility", "correlation", "efficiency"]

        try:
            with self.analysis_lock:
                results = {}

                # Convert data to tensors for GPU processing
                tensor_data = self._prepare_market_data_tensors(market_data)

                # Perform analyses based on requested types
                if "arbitrage" in analysis_types:
                    results["arbitrage"] = self._detect_arbitrage_opportunities(tensor_data)

                if "volatility" in analysis_types:
                    results["volatility"] = self._calculate_volatility_metrics(tensor_data)

                if "correlation" in analysis_types:
                    results["correlation"] = self._compute_correlation_matrix(tensor_data)

                if "efficiency" in analysis_types:
                    results["efficiency"] = self._assess_market_efficiency(tensor_data)

                # Calculate overall market efficiency score
                market_efficiency_score = self._calculate_market_efficiency_score(results)

                # GPU memory monitoring
                gpu_memory_used = 0.0
                if torch.cuda.is_available():
                    gpu_memory_used = torch.cuda.memory_allocated() / 1024 / 1024

                processing_time_ms = (time.time() - start_time) * 1000

                # Update performance stats
                self._update_performance_stats(processing_time_ms, gpu_memory_used, success=True)

                return MarketAnalysisResult(
                    timestamp=datetime.now(),
                    arbitrage_opportunities=results.get("arbitrage", []),
                    market_efficiency_score=market_efficiency_score,
                    volatility_metrics=results.get("volatility", {}),
                    correlation_matrix=results.get("correlation", np.array([])),
                    processing_time_ms=processing_time_ms,
                    gpu_memory_used_mb=gpu_memory_used
                )

        except Exception as e:
            processing_time_ms = (time.time() - start_time) * 1000
            self._update_performance_stats(processing_time_ms, 0.0, success=False)
            logger.error(f"Market analysis failed: {e}")

            # Return minimal result on failure
            return MarketAnalysisResult(
                timestamp=datetime.now(),
                arbitrage_opportunities=[],
                market_efficiency_score=0.0,
                volatility_metrics={},
                correlation_matrix=np.array([]),
                processing_time_ms=processing_time_ms,
                gpu_memory_used_mb=0.0
            )

    def _prepare_market_data_tensors(self, market_data: Dict[str, pd.DataFrame]) -> Dict[str, torch.Tensor]:
        """Convert market data to GPU tensors for processing"""
        tensor_data = {}

        for symbol, df in market_data.items():
            # Extract relevant columns (price, volume, etc.)
            if 'close' in df.columns:
                prices = torch.tensor(df['close'].values, dtype=torch.float32, device=self.device)
                tensor_data[f"{symbol}_prices"] = prices

            if 'volume' in df.columns:
                volumes = torch.tensor(df['volume'].values, dtype=torch.float32, device=self.device)
                tensor_data[f"{symbol}_volumes"] = volumes

        return tensor_data

    def _detect_arbitrage_opportunities(self, tensor_data: Dict[str, torch.Tensor]) -> List[Dict[str, Any]]:
        """Detect arbitrage opportunities using GPU-accelerated analysis"""
        opportunities = []

        # Get all price tensors
        price_tensors = {k: v for k, v in tensor_data.items() if k.endswith('_prices')}

        if len(price_tensors) < 2:
            return opportunities

        # Compare prices across different symbols/exchanges
        symbols = list(price_tensors.keys())

        for i, symbol1 in enumerate(symbols):
            for symbol2 in symbols[i+1:]:
                prices1 = price_tensors[symbol1]
                prices2 = price_tensors[symbol2]

                # Calculate price differences
                if len(prices1) == len(prices2):
                    price_ratio = prices1 / prices2
                    avg_ratio = torch.mean(price_ratio)

                    # Detect significant deviations
                    std_ratio = torch.std(price_ratio)
                    threshold = avg_ratio * 0.02  # 2% threshold

                    # Find arbitrage opportunities
                    arbitrage_mask = torch.abs(price_ratio - avg_ratio) > threshold

                    if torch.any(arbitrage_mask):
                        # Extract opportunity details
                        max_diff_idx = torch.argmax(torch.abs(price_ratio - avg_ratio))
                        max_diff = price_ratio[max_diff_idx].item() - avg_ratio.item()

                        opportunity = {
                            "symbol1": symbol1.replace('_prices', ''),
                            "symbol2": symbol2.replace('_prices', ''),
                            "price_difference_pct": (max_diff / avg_ratio.item()) * 100,
                            "direction": "buy_low_sell_high" if max_diff > 0 else "buy_high_sell_low",
                            "confidence": min(abs(max_diff) / std_ratio.item(), 1.0),
                            "timestamp": datetime.now()
                        }
                        opportunities.append(opportunity)

        return opportunities

    def _calculate_volatility_metrics(self, tensor_data: Dict[str, torch.Tensor]) -> Dict[str, float]:
        """Calculate volatility metrics for all symbols"""
        metrics = {}

        price_tensors = {k: v for k, v in tensor_data.items() if k.endswith('_prices')}

        for symbol, prices in price_tensors.items():
            if len(prices) > 1:
                # Calculate returns
                returns = torch.diff(prices) / prices[:-1]

                # Calculate volatility (standard deviation of returns)
                volatility = torch.std(returns).item()

                # Calculate Sharpe-like ratio (assuming risk-free rate of 0)
                avg_return = torch.mean(returns).item()
                sharpe_ratio = avg_return / volatility if volatility > 0 else 0

                clean_symbol = symbol.replace('_prices', '')
                metrics[f"{clean_symbol}_volatility"] = volatility
                metrics[f"{clean_symbol}_sharpe_ratio"] = sharpe_ratio

        return metrics

    def _compute_correlation_matrix(self, tensor_data: Dict[str, torch.Tensor]) -> np.ndarray:
        """Compute correlation matrix for all price series"""
        price_tensors = {k: v for k, v in tensor_data.items() if k.endswith('_prices')}

        if len(price_tensors) < 2:
            return np.array([])

        # Extract price data
        symbols = []
        price_matrix = []

        for symbol, prices in price_tensors.items():
            symbols.append(symbol.replace('_prices', ''))
            price_matrix.append(prices.cpu().numpy())

        # Create price matrix
        price_matrix = np.array(price_matrix)

        # Calculate correlation matrix
        correlation_matrix = np.corrcoef(price_matrix)

        return correlation_matrix

    def _assess_market_efficiency(self, tensor_data: Dict[str, torch.Tensor]) -> Dict[str, float]:
        """Assess market efficiency metrics"""
        efficiency_metrics = {}

        price_tensors = {k: v for k, v in tensor_data.items() if k.endswith('_prices')}

        for symbol, prices in price_tensors.items():
            if len(prices) > 10:
                # Calculate autocorrelation (market efficiency indicator)
                autocorr = torch.corrcoef(torch.stack([prices[:-1], prices[1:]]))[0, 1].item()

                # Calculate Hurst exponent approximation
                # (values closer to 0.5 indicate more efficient markets)
                returns = torch.diff(torch.log(prices))
                hurst_exponent = self._calculate_hurst_exponent(returns)

                clean_symbol = symbol.replace('_prices', '')
                efficiency_metrics[f"{clean_symbol}_autocorr"] = autocorr
                efficiency_metrics[f"{clean_symbol}_hurst"] = hurst_exponent

        return efficiency_metrics

    def _calculate_hurst_exponent(self, returns: torch.Tensor) -> float:
        """Calculate Hurst exponent for market efficiency assessment"""
        if len(returns) < 10:
            return 0.5  # Default random walk

        # Simplified Hurst exponent calculation
        # In practice, this would use more sophisticated methods
        cumsum = torch.cumsum(returns, dim=0)
        r = cumsum.max() - cumsum.min()

        if r == 0:
            return 0.5

        s = torch.std(returns)
        if s == 0:
            return 0.5

        # R/S analysis approximation
        rs = r / s
        hurst = torch.log(rs) / torch.log(torch.tensor(len(returns), dtype=torch.float32))

        return max(0.0, min(1.0, hurst.item()))

    def _calculate_market_efficiency_score(self, analysis_results: Dict[str, Any]) -> float:
        """Calculate overall market efficiency score"""
        score = 0.5  # Default neutral score
        weight_sum = 0

        # Factor in arbitrage opportunities (fewer = more efficient)
        arbitrage_count = len(analysis_results.get("arbitrage", []))
        if arbitrage_count < 5:
            score += 0.2
            weight_sum += 1
        elif arbitrage_count > 20:
            score -= 0.2
            weight_sum += 1

        # Factor in correlation patterns
        correlation_matrix = analysis_results.get("correlation", np.array([]))
        if correlation_matrix.size > 0:
            # Lower average correlation = more efficient market
            avg_correlation = np.mean(np.abs(correlation_matrix))
            efficiency_factor = 1.0 - avg_correlation
            score += (efficiency_factor - 0.5) * 0.3
            weight_sum += 1

        # Factor in volatility metrics
        volatility_metrics = analysis_results.get("volatility", {})
        avg_volatility = np.mean([v for k, v in volatility_metrics.items() if k.endswith('_volatility')])
        if not np.isnan(avg_volatility):
            # Moderate volatility = more efficient
            volatility_score = 1.0 - abs(avg_volatility - 0.02) / 0.02  # Optimal around 2%
            score += (volatility_score - 0.5) * 0.2
            weight_sum += 1

        if weight_sum > 0:
            score = score / weight_sum

        return max(0.0, min(1.0, score))

    def _update_performance_stats(self, processing_time: float, gpu_memory: float, success: bool):
        """Update performance monitoring statistics"""
        self.performance_stats["total_analyses"] += 1

        if success:
            self.performance_stats["successful_analyses"] += 1
        else:
            self.performance_stats["failed_analyses"] = self.performance_stats.get("failed_analyses", 0) + 1

        # Update average processing time
        total_time = self.performance_stats["average_processing_time_ms"] * (self.performance_stats["total_analyses"] - 1)
        self.performance_stats["average_processing_time_ms"] = (total_time + processing_time) / self.performance_stats["total_analyses"]

        # Update peak GPU memory
        self.performance_stats["peak_gpu_memory_mb"] = max(
            self.performance_stats.get("peak_gpu_memory_mb", 0),
            gpu_memory
        )

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        stats = self.performance_stats.copy()
        stats["success_rate"] = (
            stats["successful_analyses"] / stats["total_analyses"]
            if stats["total_analyses"] > 0 else 0.0
        )
        return stats

    def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "gpu_available": torch.cuda.is_available(),
            "device": self.device,
            "performance": self.get_performance_stats()
        }

        # GPU health check
        if torch.cuda.is_available():
            health["gpu_device_count"] = torch.cuda.device_count()
            health["current_gpu_device"] = torch.cuda.current_device()
            health["gpu_memory_allocated_mb"] = torch.cuda.memory_allocated() / 1024 / 1024
            health["gpu_memory_reserved_mb"] = torch.cuda.memory_reserved() / 1024 / 1024
        else:
            health["status"] = "degraded"
            health["issues"] = ["GPU not available - analysis will be slower"]

        return health

    def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down GPUAcceleratedAnalyzer")
        self.executor.shutdown(wait=True)

        # Clean up GPU memory
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        logger.info("GPUAcceleratedAnalyzer shutdown complete")

# Global analyzer instance
_analyzer = None

def get_gpu_analyzer() -> GPUAcceleratedAnalyzer:
    """Get or create global GPU analyzer instance"""
    global _analyzer

    if _analyzer is None:
        _analyzer = GPUAcceleratedAnalyzer()

    return _analyzer

def analyze_market_data_gpu(market_data: Dict[str, pd.DataFrame],
                           analysis_types: List[str] = None) -> MarketAnalysisResult:
    """Convenience function for GPU market analysis"""
    analyzer = get_gpu_analyzer()
    return analyzer.analyze_market_data(market_data, analysis_types)

def get_analyzer_health() -> Dict[str, Any]:
    """Get analyzer health status"""
    analyzer = get_gpu_analyzer()
    return analyzer.health_check()

if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.INFO)

    # Initialize analyzer
    analyzer = GPUAcceleratedAnalyzer()

    # Health check
    health = analyzer.health_check()
    logger.info(f"Analyzer health: {health['status']}")

    # Example analysis (would need real market data)
    # sample_data = {"BTCUSDT": pd.DataFrame({"close": [50000, 51000, 52000], "volume": [100, 110, 120]})}
    # result = analyzer.analyze_market_data(sample_data)
    # print(f"Analysis completed in {result.processing_time_ms:.2f}ms")
