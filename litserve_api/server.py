#!/usr/bin/env python3
"""
SovereignForge LitServe API Server
Private, secure API for arbitrage operations using LitServe
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio
from contextlib import asynccontextmanager

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import LitServe components
try:
    import litserve as ls
    from litserve import LitAPI, LitServer
except ImportError:
    logging.warning("LitServe not available, using mock implementation")
    # Mock LitServe classes for development
    class LitAPI:
        def setup(self, *args, **kwargs): pass
        def predict(self, *args, **kwargs): pass
        def encode_response(self, *args, **kwargs): pass

    class LitServer:
        def __init__(self, *args, **kwargs): pass
        def run(self, *args, **kwargs): pass

# Import SovereignForge components
try:
    from live_arbitrage_pipeline import ArbitrageOpportunity, OpportunityFilter
    from realtime_inference import RealTimeInferenceService
    from risk_management import RiskManager
    from crewai_agents.agents import get_arbitrage_crew
except ImportError as e:
    logging.warning(f"Could not import SovereignForge components: {e}")
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

    def get_arbitrage_crew():
        return None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ArbitrageAPI(LitAPI):
    """LitServe API for SovereignForge arbitrage operations"""

    def setup(self, device: str = "cpu"):
        """Setup the API with required components"""
        logger.info(f"Setting up ArbitrageAPI on device: {device}")

        # Initialize SovereignForge components
        self.inference_service = RealTimeInferenceService()
        self.risk_manager = RiskManager()
        self.opportunity_filter = OpportunityFilter(
            min_probability=0.7,
            min_spread=0.001,
            max_risk_score=0.5
        )
        self.arbitrage_crew = get_arbitrage_crew()

        # API statistics
        self.stats = {
            "requests_processed": 0,
            "opportunities_found": 0,
            "start_time": datetime.now().isoformat()
        }

        logger.info("ArbitrageAPI setup complete")

    def predict(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process arbitrage prediction request"""
        try:
            self.stats["requests_processed"] += 1

            request_type = request.get("type", "detect_opportunities")

            if request_type == "detect_opportunities":
                return self._detect_opportunities(request)
            elif request_type == "assess_risk":
                return self._assess_risk(request)
            elif request_type == "check_compliance":
                return self._check_compliance(request)
            elif request_type == "crew_analysis":
                return self._crew_analysis(request)
            elif request_type == "pipeline_status":
                return self._get_pipeline_status()
            else:
                return {
                    "status": "error",
                    "error": f"Unknown request type: {request_type}",
                    "timestamp": datetime.now().isoformat()
                }

        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _detect_opportunities(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Detect arbitrage opportunities"""
        market_data = request.get("market_data", {})
        pairs = request.get("pairs", ["BTC/USDC", "ETH/USDC"])

        try:
            # Process market data through inference service
            opportunities = self.inference_service.detect_opportunities(market_data)

            # Filter opportunities
            filtered_opportunities = []
            for opp in opportunities:
                filtered = self.opportunity_filter.filter_opportunity(opp)
                if filtered:
                    filtered_opportunities.append({
                        "pair": filtered.opportunity.pair,
                        "probability": filtered.opportunity.probability,
                        "spread": filtered.opportunity.spread_prediction,
                        "risk_assessment": filtered.risk_assessment,
                        "recommended_action": filtered.recommended_action,
                        "alerts": filtered.alerts
                    })

            self.stats["opportunities_found"] += len(filtered_opportunities)

            return {
                "status": "success",
                "opportunities_found": len(filtered_opportunities),
                "opportunities": filtered_opportunities,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _assess_risk(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Assess risk for opportunity"""
        opportunity_data = request.get("opportunity", {})

        try:
            # Create opportunity object
            opp = ArbitrageOpportunity(**opportunity_data)

            # Get risk assessment
            risk_valid = self.risk_manager.validate_opportunity(opp)

            # Calculate position sizing using Kelly Criterion
            if hasattr(self.risk_manager, 'calculate_kelly_position'):
                position_size = self.risk_manager.calculate_kelly_position(opp)
            else:
                position_size = 0.1  # Default 10%

            return {
                "status": "success",
                "risk_valid": risk_valid,
                "position_size": position_size,
                "kelly_fraction": position_size,
                "max_drawdown_limit": 0.05,  # 5% max drawdown
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _check_compliance(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Check MiCA compliance"""
        pair = request.get("pair", "")
        operation = request.get("operation", "arbitrage")

        # MiCA compliant pairs whitelist
        mica_whitelist = [
            'BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC',
            'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC',
            'XRP/RLUSD', 'XLM/RLUSD', 'ADA/RLUSD'
        ]

        compliant = pair in mica_whitelist

        return {
            "status": "success",
            "pair": pair,
            "operation": operation,
            "mica_compliant": compliant,
            "reason": "Pair in MiCA whitelist" if compliant else "Pair not in MiCA whitelist - operation blocked",
            "allowed_pairs": mica_whitelist,
            "local_execution_only": True,
            "no_custody": True,
            "no_public_offering": True,
            "timestamp": datetime.now().isoformat()
        }

    def _crew_analysis(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute CrewAI arbitrage analysis"""
        market_data = request.get("market_data", {})

        try:
            if self.arbitrage_crew:
                result = self.arbitrage_crew.execute_arbitrage_analysis(market_data)
                return result
            else:
                return {
                    "status": "error",
                    "error": "CrewAI agents not available",
                    "timestamp": datetime.now().isoformat()
                }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _get_pipeline_status(self) -> Dict[str, Any]:
        """Get pipeline status"""
        try:
            status = {
                "status": "operational",
                "components": {
                    "inference_service": "active",
                    "risk_manager": "active",
                    "opportunity_filter": "active",
                    "crew_agents": "active" if self.arbitrage_crew else "inactive"
                },
                "security": {
                    "local_execution": True,
                    "mica_compliance": True,
                    "network_isolation": True
                },
                "statistics": self.stats,
                "timestamp": datetime.now().isoformat()
            }

            return status

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def encode_response(self, output: Dict[str, Any]) -> str:
        """Encode response as JSON string"""
        return json.dumps(output, indent=2, default=str)

@asynccontextmanager
async def lifespan(app):
    """Application lifespan context manager"""
    logger.info("Starting SovereignForge LitServe API")
    yield
    logger.info("Shutting down SovereignForge LitServe API")

def create_server() -> LitServer:
    """Create LitServe server instance"""
    api = ArbitrageAPI()
    server = LitServer(
        api,
        accelerator="auto",  # Auto-detect GPU/CPU
        devices="auto",
        workers=1,  # Single worker for security
        timeout=30.0,
        max_batch_size=1,  # No batching for arbitrage operations
        batch_timeout=0.1,
        stream=False  # Synchronous responses for arbitrage
    )
    return server

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="SovereignForge LitServe API")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers")

    args = parser.parse_args()

    server = create_server()

    logger.info(f"Starting SovereignForge API server on {args.host}:{args.port}")

    # Run the server
    server.run(
        host=args.host,
        port=args.port,
        num_api_servers=args.workers,
        log_level="info"
    )

if __name__ == "__main__":
    main()