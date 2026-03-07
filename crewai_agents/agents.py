#!/usr/bin/env python3
"""
SovereignForge CrewAI Agents
Specialized agents for arbitrage operations
"""

import os
import sys
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from crewai import Agent, Task, Crew, Process
from crewai_tools import SerperDevTool, ScrapeWebsiteTool
from textwrap import dedent

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import SovereignForge components
try:
    from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
    from realtime_inference import RealTimeInferenceService
    from risk_management import RiskManager
except ImportError:
    # Mock classes for development
    class ArbitrageOpportunity:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class OpportunityFilter:
        def __init__(self, **kwargs):
            pass

    class RealTimeInferenceService:
        def __init__(self):
            pass

    class RiskManager:
        def __init__(self):
            pass

class ArbitrageDetectorAgent(Agent):
    """Agent specialized in detecting arbitrage opportunities"""

    def __init__(self):
        super().__init__(
            role="Arbitrage Opportunity Detector",
            goal="Analyze market data to identify profitable arbitrage opportunities across multiple exchanges",
            backstory=dedent("""
                You are an expert arbitrage detector with years of experience in cryptocurrency markets.
                Your specialty is identifying price discrepancies across exchanges and calculating
                optimal arbitrage spreads. You understand market microstructure, latency arbitrage,
                and statistical arbitrage techniques. You always prioritize opportunities with
                high probability and low risk.
            """),
            verbose=True,
            allow_delegation=False,
            tools=[SerperDevTool(), ScrapeWebsiteTool()]
        )

    def detect_opportunities(self, market_data: Dict[str, Any]) -> List[ArbitrageOpportunity]:
        """Detect arbitrage opportunities from market data"""
        # Initialize inference service
        inference_service = RealTimeInferenceService()

        # Process market data
        opportunities = inference_service.detect_opportunities(market_data)

        # Filter for high-quality opportunities
        filtered_opportunities = []
        for opp in opportunities:
            if (opp.probability > 0.75 and
                opp.spread_prediction > 0.002 and
                opp.risk_score < 0.3):
                filtered_opportunities.append(opp)

        return filtered_opportunities

class RiskManagerAgent(Agent):
    """Agent specialized in risk assessment and position sizing"""

    def __init__(self):
        super().__init__(
            role="Risk Manager & Position Sizer",
            goal="Assess risk for arbitrage opportunities and calculate optimal position sizes using Kelly Criterion",
            backstory=dedent("""
                You are a quantitative risk manager specializing in cryptocurrency arbitrage.
                You apply advanced risk management techniques including Kelly Criterion,
                Value at Risk (VaR), Expected Shortfall, and portfolio optimization.
                Your goal is to maximize returns while maintaining strict risk controls
                and ensuring capital preservation.
            """),
            verbose=True,
            allow_delegation=False
        )

    def assess_risk(self, opportunity: ArbitrageOpportunity) -> Dict[str, Any]:
        """Assess risk and calculate position sizing"""
        risk_manager = RiskManager()

        # Validate opportunity
        risk_valid = risk_manager.validate_opportunity(opportunity)

        # Calculate Kelly position size
        if hasattr(risk_manager, 'calculate_kelly_position'):
            kelly_fraction = risk_manager.calculate_kelly_position(opportunity)
        else:
            # Default Kelly calculation
            win_rate = opportunity.confidence
            win_loss_ratio = opportunity.profit_potential / 0.001  # Profit per unit risk
            kelly_fraction = win_rate - ((1 - win_rate) / win_loss_ratio)
            kelly_fraction = max(0.01, min(0.25, kelly_fraction))  # Bound between 1% and 25%

        # Calculate risk metrics
        risk_assessment = {
            "risk_valid": risk_valid,
            "kelly_fraction": kelly_fraction,
            "position_size": kelly_fraction,
            "max_drawdown_limit": 0.05,  # 5%
            "stop_loss_percentage": 0.02,  # 2%
            "risk_score": opportunity.risk_score,
            "volatility_adjustment": 1.0 - opportunity.risk_score,
            "recommendation": "execute" if risk_valid and kelly_fraction > 0.01 else "monitor"
        }

        return risk_assessment

class ComplianceOfficerAgent(Agent):
    """Agent specialized in regulatory compliance"""

    def __init__(self):
        super().__init__(
            role="MiCA Compliance Officer",
            goal="Ensure all arbitrage operations comply with MiCA regulations and whitelist requirements",
            backstory=dedent("""
                You are a regulatory compliance expert specializing in MiCA (Markets in Crypto-Assets)
                regulations. Your responsibility is to ensure all trading activities comply with
                EU financial regulations, particularly focusing on approved crypto assets,
                no custody operations, local execution only, and no public offerings.
                You maintain strict adherence to compliance requirements.
            """),
            verbose=True,
            allow_delegation=False
        )

    def check_compliance(self, pair: str, operation: str) -> Dict[str, Any]:
        """Check MiCA compliance for trading pair and operation"""

        # MiCA compliant pairs whitelist
        mica_whitelist = [
            'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT',
            'LINK/USDT', 'IOTA/USDT', 'XDC/USDT', 'ONDO/USDT', 'VET/USDT',
            'USDC/USDT', 'RLUSD/USDT'
        ]

        compliant = pair in mica_whitelist

        compliance_check = {
            "pair": pair,
            "operation": operation,
            "mica_compliant": compliant,
            "reason": "Pair in MiCA whitelist" if compliant else "Pair not in MiCA whitelist - operation blocked",
            "allowed_pairs": mica_whitelist,
            "regulatory_requirements": {
                "no_custody": True,
                "no_public_offering": True,
                "local_execution_only": True,
                "approved_assets_only": True,
                "transaction_reporting": True
            },
            "compliance_status": "approved" if compliant else "blocked",
            "timestamp": datetime.now().isoformat()
        }

        return compliance_check

class ArbitrageCrew:
    """CrewAI orchestration for arbitrage operations"""

    def __init__(self):
        self.detector = ArbitrageDetectorAgent()
        self.risk_manager = RiskManagerAgent()
        self.compliance_officer = ComplianceOfficerAgent()

    def create_arbitrage_workflow(self, market_data: Dict[str, Any]) -> Crew:
        """Create the arbitrage analysis workflow"""

        # Task 1: Detect opportunities
        detection_task = Task(
            description=dedent(f"""
                Analyze the following market data for arbitrage opportunities:
                {json.dumps(market_data, indent=2)}

                Focus on:
                - Price discrepancies across exchanges
                - Statistical arbitrage opportunities
                - Triangular arbitrage possibilities
                - High-probability, low-risk opportunities

                Return a list of potential arbitrage opportunities with detailed analysis.
            """),
            agent=self.detector,
            expected_output="List of arbitrage opportunities with probability, spread, and risk assessments"
        )

        # Task 2: Risk assessment (depends on detection)
        risk_task = Task(
            description=dedent("""
                For each detected arbitrage opportunity, perform comprehensive risk assessment:

                - Apply Kelly Criterion for position sizing
                - Calculate Value at Risk (VaR)
                - Assess liquidity risk
                - Evaluate execution risk
                - Determine optimal position sizes

                Provide detailed risk analysis and position sizing recommendations.
            """),
            agent=self.risk_manager,
            context=[detection_task],
            expected_output="Risk assessment and position sizing recommendations for each opportunity"
        )

        # Task 3: Compliance check (depends on risk assessment)
        compliance_task = Task(
            description=dedent("""
                Verify MiCA compliance for all arbitrage opportunities:

                - Check if trading pairs are in approved whitelist
                - Confirm no custody operations
                - Verify local execution only
                - Ensure no public offering elements
                - Validate regulatory compliance

                Only approve opportunities that meet all MiCA requirements.
            """),
            agent=self.compliance_officer,
            context=[risk_task],
            expected_output="Compliance verification and final approval/rejection for each opportunity"
        )

        # Create crew with sequential process
        crew = Crew(
            agents=[self.detector, self.risk_manager, self.compliance_officer],
            tasks=[detection_task, risk_task, compliance_task],
            process=Process.sequential,
            verbose=True
        )

        return crew

    def execute_arbitrage_analysis(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the complete arbitrage analysis workflow"""

        try:
            # Create and run the crew
            crew = self.create_arbitrage_workflow(market_data)
            result = crew.kickoff()

            # Process results
            analysis_result = {
                "status": "success",
                "workflow_completed": True,
                "crew_result": str(result),
                "timestamp": datetime.now().isoformat(),
                "market_data_summary": {
                    "pairs_analyzed": len(market_data.get("pairs", [])),
                    "exchanges_covered": len(market_data.get("exchanges", [])),
                    "data_points": len(market_data)
                }
            }

            return analysis_result

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "workflow_completed": False,
                "timestamp": datetime.now().isoformat()
            }

def get_arbitrage_crew() -> ArbitrageCrew:
    """Factory function for ArbitrageCrew singleton"""
    return ArbitrageCrew()

# Example usage
if __name__ == "__main__":
    # Sample market data
    sample_market_data = {
        "pairs": ["BTC/USDT", "ETH/USDT", "XRP/USDT"],
        "exchanges": ["binance", "coinbase", "kraken"],
        "prices": {
            "BTC/USDT": {"binance": 45000, "coinbase": 44900, "kraken": 45050},
            "ETH/USDT": {"binance": 2800, "coinbase": 2790, "kraken": 2810},
            "XRP/USDT": {"binance": 0.50, "coinbase": 0.49, "kraken": 0.51}
        },
        "volumes": {
            "BTC/USDT": {"binance": 100, "coinbase": 80, "kraken": 120},
            "ETH/USDT": {"binance": 500, "coinbase": 400, "kraken": 600},
            "XRP/USDT": {"binance": 10000, "coinbase": 8000, "kraken": 12000}
        }
    }

    # Initialize crew
    arbitrage_crew = get_arbitrage_crew()

    # Execute analysis
    result = arbitrage_crew.execute_arbitrage_analysis(sample_market_data)

    print("Arbitrage Analysis Result:")
    print(json.dumps(result, indent=2))