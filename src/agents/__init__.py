"""SovereignForge Multi-Personality Agent System.

Registry of all audit and research agents. Each agent has a distinct personality,
target files, checklist, and prompt template for use as a Claude Code subagent.
"""

# --- Research Agents ---

try:
    from agents.research_sentiment import MarketSentimentAgent
except ImportError:
    MarketSentimentAgent = None

try:
    from agents.research_technical import TechnicalAnalysisAgent
except ImportError:
    TechnicalAnalysisAgent = None

try:
    from agents.research_performance import StrategyPerformanceAgent
except ImportError:
    StrategyPerformanceAgent = None

# --- Audit Agents ---

try:
    from agents.audit_security import SecurityAuditor
except ImportError:
    SecurityAuditor = None

try:
    from agents.audit_performance import PerformanceAnalyst
except ImportError:
    PerformanceAnalyst = None

try:
    from agents.audit_trading import TradingLogicReviewer
except ImportError:
    TradingLogicReviewer = None

try:
    from agents.audit_risk import RiskAuditor
except ImportError:
    RiskAuditor = None

try:
    from agents.audit_compliance import MiCAComplianceChecker
except ImportError:
    MiCAComplianceChecker = None

try:
    from agents.audit_quality import CodeQualityGuardian
except ImportError:
    CodeQualityGuardian = None

# --- Agent Registries ---

RESEARCH_AGENTS = {
    'sentiment': MarketSentimentAgent,
    'technical': TechnicalAnalysisAgent,
    'performance': StrategyPerformanceAgent,
}

AUDIT_AGENTS = {
    'security': SecurityAuditor,
    'performance': PerformanceAnalyst,
    'trading': TradingLogicReviewer,
    'risk': RiskAuditor,
    'compliance': MiCAComplianceChecker,
    'quality': CodeQualityGuardian,
}

ALL_AGENTS = {**RESEARCH_AGENTS, **AUDIT_AGENTS}
