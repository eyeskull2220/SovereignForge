#!/usr/bin/env python3
"""
Grok Reasoning Integration for SovereignForge
Uses xAI's Grok model for advanced trading decision reasoning
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import xai_sdk
    _HAS_XAI = True
except ImportError:
    xai_sdk = None
    _HAS_XAI = False

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GrokReasoningEngine:
    """Advanced reasoning engine using Grok for trading decisions"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Grok reasoning engine

        Args:
            api_key: xAI API key (if not set in environment)
        """
        self.api_key = api_key
        self.client = None
        self.model = "grok-4.20-experimental-beta-0304-reasoning"
        self.max_tokens = 2000
        self.temperature = 0.3  # Lower temperature for more consistent reasoning

        # Initialize client
        self._initialize_client()

    def _initialize_client(self):
        """Initialize xAI client"""
        try:
            if self.api_key:
                self.client = xai_sdk.Client(api_key=self.api_key)
            else:
                # Try to get from environment or config
                import os
                api_key = os.getenv('XAI_API_KEY')
                if api_key:
                    self.client = xai_sdk.Client(api_key=api_key)
                else:
                    logger.warning("No xAI API key provided. Grok reasoning will be unavailable.")
                    self.client = None
        except Exception as e:
            logger.error(f"Failed to initialize xAI client: {e}")
            self.client = None

    async def analyze_arbitrage_opportunity(self, opportunity_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use Grok to analyze an arbitrage opportunity

        Args:
            opportunity_data: Dictionary containing opportunity details

        Returns:
            Analysis results with confidence and reasoning
        """
        if not self.client:
            return {"error": "Grok client not initialized", "confidence": 0.0}

        try:
            # Prepare context for Grok
            context = self._format_opportunity_context(opportunity_data)

            prompt = f"""
You are an expert cryptocurrency arbitrage analyst. Analyze this arbitrage opportunity and provide a detailed assessment.

Opportunity Details:
{context}

Please provide:
1. Risk assessment (Low/Medium/High)
2. Confidence score (0-100)
3. Key factors to consider
4. Recommended action (Execute/Hold/Monitor)
5. Potential profit estimate
6. Any warnings or concerns

Be precise and data-driven in your analysis.
"""

            # Call Grok
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            analysis = response.choices[0].message.content

            # Parse response (simplified parsing)
            parsed_analysis = self._parse_grok_response(analysis)

            return {
                "analysis": analysis,
                "parsed": parsed_analysis,
                "timestamp": datetime.now().isoformat(),
                "model": self.model
            }

        except Exception as e:
            logger.error(f"Grok analysis failed: {e}")
            return {"error": str(e), "confidence": 0.0}

    async def plan_trading_strategy(self, market_conditions: Dict[str, Any],
                                  portfolio_status: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use Grok to plan or adjust trading strategy

        Args:
            market_conditions: Current market data
            portfolio_status: Current portfolio state

        Returns:
            Strategy recommendations
        """
        if not self.client:
            return {"error": "Grok client not initialized"}

        try:
            context = f"""
Market Conditions:
{json.dumps(market_conditions, indent=2)}

Portfolio Status:
{json.dumps(portfolio_status, indent=2)}
"""

            prompt = f"""
You are a professional cryptocurrency trading strategist. Based on the current market conditions and portfolio status, provide strategic recommendations.

{context}

Please provide:
1. Overall market assessment
2. Risk level assessment
3. Recommended position adjustments
4. Suggested trading pairs to focus on
5. Risk management recommendations
6. Time horizon for recommendations

Focus on arbitrage opportunities and risk management.
"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            strategy_plan = response.choices[0].message.content

            return {
                "strategy_plan": strategy_plan,
                "timestamp": datetime.now().isoformat(),
                "model": self.model
            }

        except Exception as e:
            logger.error(f"Grok strategy planning failed: {e}")
            return {"error": str(e)}

    async def assess_risk_management(self, position_data: Dict[str, Any],
                                   market_volatility: float) -> Dict[str, Any]:
        """
        Use Grok for risk management assessment

        Args:
            position_data: Current positions
            market_volatility: Current volatility measure

        Returns:
            Risk management recommendations
        """
        if not self.client:
            return {"error": "Grok client not initialized"}

        try:
            context = f"""
Current Positions:
{json.dumps(position_data, indent=2)}

Market Volatility: {market_volatility}
"""

            prompt = f"""
You are a risk management expert for cryptocurrency trading. Assess the current risk exposure and provide recommendations.

{context}

Please provide:
1. Current risk exposure level
2. Recommended position size adjustments
3. Stop-loss recommendations
4. Diversification suggestions
5. Maximum drawdown limits
6. Emergency exit strategy

Be conservative and prioritize capital preservation.
"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            risk_assessment = response.choices[0].message.content

            return {
                "risk_assessment": risk_assessment,
                "timestamp": datetime.now().isoformat(),
                "model": self.model
            }

        except Exception as e:
            logger.error(f"Grok risk assessment failed: {e}")
            return {"error": str(e)}

    def _format_opportunity_context(self, opportunity_data: Dict[str, Any]) -> str:
        """Format opportunity data for Grok analysis"""
        context_parts = []

        if 'pair' in opportunity_data:
            context_parts.append(f"Trading Pair: {opportunity_data['pair']}")

        if 'exchanges' in opportunity_data:
            context_parts.append(f"Exchanges: {', '.join(opportunity_data['exchanges'])}")

        if 'spread' in opportunity_data:
            context_parts.append(f"Price Spread: {opportunity_data['spread']:.4f}")

        if 'probability' in opportunity_data:
            context_parts.append(f"Model Probability: {opportunity_data['probability']:.3f}")

        if 'volumes' in opportunity_data:
            context_parts.append(f"Exchange Volumes: {opportunity_data['volumes']}")

        if 'fees' in opportunity_data:
            context_parts.append(f"Trading Fees: {opportunity_data['fees']}")

        return "\n".join(context_parts)

    def _parse_grok_response(self, response: str) -> Dict[str, Any]:
        """Parse Grok's response into structured data"""
        parsed = {
            "risk_level": "Unknown",
            "confidence": 50,
            "action": "Monitor",
            "profit_estimate": 0.0,
            "warnings": []
        }

        # Simple keyword-based parsing (could be improved with better NLP)
        response_lower = response.lower()

        if "high risk" in response_lower or "risk: high" in response_lower:
            parsed["risk_level"] = "High"
        elif "medium risk" in response_lower or "risk: medium" in response_lower:
            parsed["risk_level"] = "Medium"
        elif "low risk" in response_lower or "risk: low" in response_lower:
            parsed["risk_level"] = "Low"

        # Extract confidence score
        import re
        confidence_match = re.search(r'confidence[:\s]+(\d+)', response_lower)
        if confidence_match:
            parsed["confidence"] = int(confidence_match.group(1))

        # Extract action
        if "execute" in response_lower:
            parsed["action"] = "Execute"
        elif "hold" in response_lower:
            parsed["action"] = "Hold"

        # Extract profit estimate
        profit_match = re.search(r'profit[:\s]+[\$]?(\d+\.?\d*)', response_lower)
        if profit_match:
            parsed["profit_estimate"] = float(profit_match.group(1))

        return parsed

    async def health_check(self) -> bool:
        """Check if Grok reasoning engine is operational"""
        if not self.client:
            return False

        try:
            # Simple test call
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello, are you operational?"}],
                max_tokens=50
            )
            return bool(response.choices)
        except Exception as e:
            logger.error(f"Grok health check failed: {e}")
            return False

# Synchronous wrapper for easier integration
class GrokReasoningWrapper:
    """Synchronous wrapper for Grok reasoning engine"""

    def __init__(self, api_key: Optional[str] = None):
        self.engine = GrokReasoningEngine(api_key)

    def analyze_opportunity(self, opportunity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for opportunity analysis"""
        try:
            # Run in new event loop if needed
            import nest_asyncio
            nest_asyncio.apply()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.engine.analyze_arbitrage_opportunity(opportunity_data)
            )
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Synchronous analysis failed: {e}")
            return {"error": str(e), "confidence": 0.0}

    def plan_strategy(self, market_conditions: Dict[str, Any],
                     portfolio_status: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for strategy planning"""
        try:
            import nest_asyncio
            nest_asyncio.apply()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.engine.plan_trading_strategy(market_conditions, portfolio_status)
            )
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Synchronous planning failed: {e}")
            return {"error": str(e)}

    def assess_risk(self, position_data: Dict[str, Any],
                   market_volatility: float) -> Dict[str, Any]:
        """Synchronous wrapper for risk assessment"""
        try:
            import nest_asyncio
            nest_asyncio.apply()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.engine.assess_risk_management(position_data, market_volatility)
            )
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Synchronous risk assessment failed: {e}")
            return {"error": str(e)}

    def is_operational(self) -> bool:
        """Check if reasoning engine is operational"""
        try:
            import nest_asyncio
            nest_asyncio.apply()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.engine.health_check())
            loop.close()
            return result
        except Exception:
            return False

# Example usage and testing
async def test_grok_integration():
    """Test Grok integration"""
    print("🧠 Testing Grok Reasoning Integration...")

    # Initialize engine (requires API key)
    reasoner = GrokReasoningWrapper()

    if not reasoner.is_operational():
        print("❌ Grok reasoning not operational (API key required)")
        return

    # Test opportunity analysis
    test_opportunity = {
        "pair": "BTC/USDC",
        "exchanges": ["binance", "coinbase"],
        "spread": 0.005,
        "probability": 0.85,
        "volumes": {"binance": 1000000, "coinbase": 500000},
        "fees": {"binance": 0.001, "coinbase": 0.002}
    }

    print("\\n📊 Analyzing test arbitrage opportunity...")
    analysis = reasoner.analyze_opportunity(test_opportunity)
    print(f"Analysis: {analysis}")

    # Test strategy planning
    market_conditions = {
        "volatility": 0.02,
        "trend": "bullish",
        "liquidity": "high"
    }

    portfolio = {
        "balance": 10000,
        "positions": {"BTC/USDC": 0.5}
    }

    print("\\n🎯 Planning trading strategy...")
    strategy = reasoner.plan_strategy(market_conditions, portfolio)
    print(f"Strategy: {strategy}")

if __name__ == "__main__":
    # Run test
    asyncio.run(test_grok_integration())
