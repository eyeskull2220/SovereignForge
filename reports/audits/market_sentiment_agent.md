# Market Sentiment Agent Audit Report
**Type:** research | **Score:** 100.0/100 | **Time:** 0.2s
**Files Scanned:** 0 | **Findings:** 0

## Summary
{
  "agent": "Market Sentiment Agent",
  "timestamp": "2026-03-15T22:58:41.395751",
  "market_mood": {
    "source": "default",
    "activity_level": "unknown",
    "pnl_direction": "neutral"
  },
  "per_asset": {
    "XRP": {
      "asset": "XRP",
      "sentiment_score": 1.0,
      "confidence": 0.761,
      "momentum_24h": 0.016,
      "momentum_7d": 0.0272,
      "volume_trend": 0.8444,
      "volatility_24h": 0.001954,
      "sources": [
        "local_ohlcv"
      ]
    },
    "XLM": {
      "asset": "XLM",
      "sentiment_score": 0.801,
      "confidence": 0.76,
      "momentum_24h": 0.0156,
      "momentum_7d": 0.0719,
      "volume_trend": 0.2539,
      "volatility_24h": 0.002002,
      "sources": [
        "local_ohlcv"
      ]
    },
    "HBAR": {
      "asset": "HBAR",
      "sentiment_score": 1.0,
      "confidence": 0.761,
      "momentum_24h": 0.0062,
      "momentum_7d": -0.0222,
      "volume_trend": 0.7045,
      "volatility_24h": 0.001956,
      "sources": [
        "local_ohlcv"
      ]
    },
    "ALGO": {
      "asset": "ALGO",
      "sentiment_score": 1.0,
      "confidence": 0.742,
      "momentum_24h": 0.0612,
      "momentum_7d": 0.1103,
      "volume_trend": 0.3655,
      "volatility_24h": 0.002899,
      "sources": [
        "local_ohlcv"
      ]
    },
    "ADA": {
      "asset": "ADA",
      "sentiment_score": 0.786,
      "confidence": 0.75,
      "momentum_24h": 0.0175,
      "momentum_7d": 0.0352,
      "volume_trend": 0.2964,
      "volatility_24h": 0.002498,
      "sources": [
        "local_ohlcv"
      ]
    },
    "LINK": {
      "asset": "LINK",
      "sentiment_score": 1.0,
      "confidence": 0.749,
      "momentum_24h": 0.0111,
      "momentum_7d": 0.0398,
      "volume_trend": 0.6916,
      "volatility_24h": 0.002564,
      "sources": [
        "local_ohlcv"
      ]
    },
    "IOTA": {
      "asset": "IOTA",
      "sentiment_score": 1.0,
      "confidence": 0.761,
      "momentum_24h": 0.0,
      "momentum_7d": -0.02,
      "volume_trend": 1.1564,
      "volatility_24h": 0.001974,
      "sources": [
        "local_ohlcv"
      ]
    },
    "VET": {
      "asset": "VET",
      "sentiment_score": 0.555,
      "confidence": 0.756,
      "momentum_24h": 0.0147,
      "momentum_7d": 0.0282,
      "volume_trend": 0.1983,
      "volatility_24h": 0.002208,
      "sources": [
        "local_ohlcv"
      ]
    },
    "XDC": {
      "asset": "XDC",
      "sentiment_score": -0.681,
      "confidence": 0.727,
      "momentum_24h": -0.0252,
      "momentum_7d": -0.0831,
      "volume_trend": -0.153,
      "volatility_24h": 0.003666,
      "sources": [
        "local_ohlcv"
      ]
    },
    "ONDO": {
      "asset": "ONDO",
      "sentiment_score": 1.0,
      "confidence": 0.746,
      "momentum_24h": 0.0247,
      "momentum_7d": 0.044,
      "volume_trend": 1.5625,
      "volatility_24h": 0.002724,
      "sources": [
        "local_ohlcv"
      ]
    },
    "BTC": {
      "asset": "BTC",
      "sentiment_score": 1.0,
      "confidence": 0.766,
      "momentum_24h": 0.0103,
      "momentum_7d": 0.0458,
      "volume_trend": 4.0805,
      "volatility_24h": 0.001681,
      "sources": [
        "local_ohlcv"
      ]
    },
    "ETH": {
      "asset": "ETH",
      "sentiment_score": 0.895,
      "confidence": 0.75,
      "momentum_24h": 0.0166,
      "momentum_7d": 0.0608,
      "volume_trend": 0.3148,
      "volatility_24h": 0.002483,
      "sources": [
        "local_ohlcv"
      ]
    }
  },
  "fear_greed_estimate": {
    "index": 50,
    "label": "neutral",
    "source": "paper_trading_proxy"
  },
  "actionable_signals": [
    {
      "signal": "Sentiment analysis requires API integration",
      "priority": "info",
      "action": "Configure CoinGecko API key for live sentiment data"
    }
  ],
  "execution_time": 0.25
}
