#!/usr/bin/env python3
"""
SovereignForge - Sentiment Analyzer

VADER-based sentiment scoring for crypto news headlines and text.
Lightweight, no API keys required, works offline.

Usage:
    from sentiment_analyzer import analyze_headline, analyze_batch

    score = analyze_headline("Bitcoin surges to new all-time high")
    # Returns: 0.6369 (positive)

    results = analyze_batch(["BTC crashes 20%", "ETH adoption grows"])
    # Returns: {"avg_sentiment": -0.05, "bullish_count": 1, "bearish_count": 1, ...}

CLI:
    python src/sentiment_analyzer.py "Bitcoin hits new high"
    python src/sentiment_analyzer.py  # runs demo headlines
"""

import sys
from typing import Dict, List, Optional

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Crypto-specific lexicon additions (VADER doesn't know these)
CRYPTO_LEXICON = {
    "bullish": 2.5,
    "bearish": -2.5,
    "moon": 2.0,
    "mooning": 2.5,
    "dump": -2.0,
    "dumping": -2.5,
    "pump": 1.5,
    "pumping": 2.0,
    "rekt": -3.0,
    "hodl": 1.5,
    "fud": -2.0,
    "rug": -3.5,
    "rugpull": -3.5,
    "ath": 2.5,
    "dip": -1.0,
    "crash": -3.0,
    "surge": 2.5,
    "rally": 2.0,
    "plunge": -2.5,
    "soar": 2.5,
    "tank": -2.5,
    "breakout": 2.0,
    "breakdown": -2.0,
    "whale": 1.0,
    "accumulation": 1.5,
    "distribution": -1.0,
    "adoption": 2.0,
    "ban": -2.5,
    "regulation": -0.5,
    "compliance": 0.5,
    "hack": -3.0,
    "exploit": -2.5,
    "liquidation": -2.0,
    "liquidated": -2.5,
    "delisting": -2.5,
    "listing": 2.0,
    "partnership": 1.5,
    "integration": 1.5,
    "upgrade": 1.5,
    "fork": -0.5,
    "stablecoin": 0.3,
    "defi": 0.5,
    "etf": 1.5,
    "approval": 2.0,
    "rejection": -2.0,
}

_analyzer: Optional[SentimentIntensityAnalyzer] = None


def _get_analyzer() -> SentimentIntensityAnalyzer:
    """Lazy-init analyzer with crypto lexicon."""
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
        _analyzer.lexicon.update(CRYPTO_LEXICON)
    return _analyzer


def analyze_headline(text: str) -> float:
    """Analyze sentiment of a single headline/text.

    Returns:
        float: Compound sentiment score in [-1, 1].
               > 0.05 = bullish, < -0.05 = bearish, else neutral.
    """
    analyzer = _get_analyzer()
    scores = analyzer.polarity_scores(text)
    return scores["compound"]


def analyze_detailed(text: str) -> Dict[str, float]:
    """Analyze sentiment with full breakdown.

    Returns:
        Dict with keys: compound, pos, neg, neu (all floats).
    """
    analyzer = _get_analyzer()
    return analyzer.polarity_scores(text)


def analyze_batch(headlines: List[str]) -> Dict:
    """Analyze a batch of headlines and return aggregate stats.

    Returns:
        Dict with:
            avg_sentiment: float — average compound score
            bullish_count: int — headlines with compound > 0.05
            bearish_count: int — headlines with compound < -0.05
            neutral_count: int — headlines with -0.05 <= compound <= 0.05
            strongest_bullish: str — most positive headline
            strongest_bearish: str — most negative headline
            scores: List[float] — individual scores
    """
    if not headlines:
        return {
            "avg_sentiment": 0.0,
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "strongest_bullish": "",
            "strongest_bearish": "",
            "scores": [],
        }

    scores = [analyze_headline(h) for h in headlines]

    bullish = sum(1 for s in scores if s > 0.05)
    bearish = sum(1 for s in scores if s < -0.05)
    neutral = len(scores) - bullish - bearish

    max_idx = scores.index(max(scores))
    min_idx = scores.index(min(scores))

    return {
        "avg_sentiment": sum(scores) / len(scores),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "strongest_bullish": headlines[max_idx],
        "strongest_bearish": headlines[min_idx],
        "scores": scores,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEMO_HEADLINES = [
    "Bitcoin surges past $100,000 as institutional adoption grows",
    "Ethereum ETF approval expected within weeks",
    "Major crypto exchange hacked, $200M stolen",
    "XRP wins SEC lawsuit, price rallies 30%",
    "Federal Reserve signals rate cuts, crypto markets respond",
    "Stablecoin regulation bill passes Senate committee",
    "Whale accumulates 10,000 BTC in 24 hours",
    "DeFi protocol exploited for $50M in flash loan attack",
    "Cardano announces major network upgrade for Q2",
    "Crypto market crashes as global recession fears mount",
    "HBAR partnership with Google Cloud expands",
    "Algorand achieves 10,000 TPS milestone",
]


def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        score = analyze_headline(text)
        details = analyze_detailed(text)
        label = "BULLISH" if score > 0.05 else "BEARISH" if score < -0.05 else "NEUTRAL"
        print(f"\n  Text: {text}")
        print(f"  Score: {score:+.4f} ({label})")
        print(f"  Pos: {details['pos']:.3f} | Neg: {details['neg']:.3f} | Neu: {details['neu']:.3f}")
        return

    print("\n  SovereignForge Sentiment Analyzer — Demo\n")
    print(f"  {'Score':>7}  {'Label':<8}  Headline")
    print(f"  {'='*7}  {'='*8}  {'='*50}")

    for headline in DEMO_HEADLINES:
        score = analyze_headline(headline)
        label = "BULL" if score > 0.05 else "BEAR" if score < -0.05 else "NEUT"
        print(f"  {score:+.4f}  {label:<8}  {headline[:60]}")

    print()
    results = analyze_batch(DEMO_HEADLINES)
    print(f"  Avg sentiment: {results['avg_sentiment']:+.4f}")
    print(f"  Bullish: {results['bullish_count']} | Bearish: {results['bearish_count']} | Neutral: {results['neutral_count']}")
    print(f"  Most bullish: {results['strongest_bullish'][:60]}")
    print(f"  Most bearish: {results['strongest_bearish'][:60]}")


if __name__ == "__main__":
    main()
