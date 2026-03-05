#!/usr/bin/env python3
"""
SovereignForge Automated Agent Review System
Comprehensive automated testing, code analysis, and bug detection for personal trading system
"""

import os
import sys
import subprocess
import time
import json
import ast
import re
import argparse
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import logging
import traceback
import inspect
import importlib.util

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/agent_review.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BugReport:
    """Bug report data structure"""

    def __init__(self, severity: str, category: str, title: str, description: str,
                 file_path: str = "", line_number: int = 0, code_snippet: str = "",
                 suggestion: str = ""):
        self.severity = severity  # CRITICAL, HIGH, MEDIUM, LOW, INFO
        self.category = category  # SECURITY, PERFORMANCE, RELIABILITY, MAINTAINABILITY, etc.
        self.title = title
        self.description = description
        self.file_path = file_path
        self.line_number = line_number
        self.code_snippet = code_snippet
        self.suggestion = suggestion
        self.timestamp = datetime.now()
        self.agent_name = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'severity': self.severity,
            'category': self.category,
            'title': self.title,
            'description': self.description,
            'file_path': self.file_path,
            'line_number': self.line_number,
            'code_snippet': self.code_snippet,
            'suggestion': self.suggestion,
            'timestamp': self.timestamp.isoformat(),
            'agent_name': self.agent_name
        }

class BaseAgent:
    """Base class for all review agents"""

    def __init__(self, name: str):
        self.name = name
        self.bugs_found = []
        self.start_time = None
        self.end_time = None

    def run(self, codebase_path: str) -> List[BugReport]:
        """Run the agent review"""
        self.start_time = datetime.now()
        logger.info(f"🚀 Starting {self.name} agent review")

        try:
            self.bugs_found = self.analyze_codebase(codebase_path)
            self.end_time = datetime.now()

            duration = self.end_time - self.start_time
            logger.info(f"✅ {self.name} completed in {duration.total_seconds():.2f}s, found {len(self.bugs_found)} issues")

            # Mark bugs with agent name
            for bug in self.bugs_found:
                bug.agent_name = self.name

            return self.bugs_found

        except Exception as e:
            logger.error(f"❌ {self.name} failed: {e}")
            self.end_time = datetime.now()
            return [BugReport(
                severity="CRITICAL",
                category="RELIABILITY",
                title=f"{self.name} Agent Failure",
                description=f"Agent {self.name} crashed during execution: {str(e)}",
                suggestion="Check agent implementation and error handling"
            )]

    def analyze_codebase(self, codebase_path: str) -> List[BugReport]:
        """Override this method in subclasses"""
        raise NotImplementedError

    def add_bug(self, bug: BugReport):
        """Add a bug to the findings"""
        self.bugs_found.append(bug)

class CodeAnalysisAgent(BaseAgent):
    """Static code analysis agent"""

    def __init__(self):
        super().__init__("Code Analysis Agent")

    def analyze_codebase(self, codebase_path: str) -> List[BugReport]:
        bugs = []

        # Find all Python files
        python_files = self.find_python_files(codebase_path)

        for file_path in python_files:
            try:
                bugs.extend(self.analyze_file(file_path))
            except Exception as e:
                bugs.append(BugReport(
                    severity="MEDIUM",
                    category="MAINTAINABILITY",
                    title="File Analysis Error",
                    description=f"Could not analyze {file_path}: {str(e)}",
                    file_path=file_path,
                    suggestion="Check file syntax and encoding"
                ))

        return bugs

    def find_python_files(self, path: str) -> List[str]:
        """Find all Python files in the codebase"""
        python_files = []
        for root, dirs, files in os.walk(path):
            # Skip certain directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'venv', '.git']]

            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))

        return python_files

    def analyze_file(self, file_path: str) -> List[BugReport]:
        """Analyze a single Python file"""
        bugs = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')

            # Parse AST for structural analysis
            try:
                tree = ast.parse(content, filename=file_path)
                bugs.extend(self.analyze_ast(tree, file_path, lines))
            except SyntaxError as e:
                bugs.append(BugReport(
                    severity="HIGH",
                    category="RELIABILITY",
                    title="Syntax Error",
                    description=f"Syntax error in {file_path}: {str(e)}",
                    file_path=file_path,
                    line_number=e.lineno or 0,
                    suggestion="Fix the syntax error"
                ))

            # Pattern-based analysis
            bugs.extend(self.analyze_patterns(content, lines, file_path))

        except UnicodeDecodeError:
            bugs.append(BugReport(
                severity="LOW",
                category="MAINTAINABILITY",
                title="Encoding Issue",
                description=f"Could not read {file_path} with UTF-8 encoding",
                file_path=file_path,
                suggestion="Ensure file is UTF-8 encoded"
            ))

        return bugs

    def analyze_ast(self, tree: ast.AST, file_path: str, lines: List[str]) -> List[BugReport]:
        """Analyze AST for structural issues"""
        bugs = []

        class CodeVisitor(ast.NodeVisitor):
            def __init__(self, bugs_list, file_path, lines):
                self.bugs = bugs_list
                self.file_path = file_path
                self.lines = lines

            def visit_FunctionDef(self, node):
                # Check function complexity
                complexity = self.calculate_complexity(node)
                if complexity > 15:
                    self.bugs.append(BugReport(
                        severity="MEDIUM",
                        category="MAINTAINABILITY",
                        title="High Function Complexity",
                        description=f"Function '{node.name}' has high complexity ({complexity})",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        suggestion="Break down into smaller functions"
                    ))

                # Check function length
                if len(node.body) > 50:
                    self.bugs.append(BugReport(
                        severity="LOW",
                        category="MAINTAINABILITY",
                        title="Long Function",
                        description=f"Function '{node.name}' is very long ({len(node.body)} statements)",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        suggestion="Consider splitting into smaller functions"
                    ))

                self.generic_visit(node)

            def visit_ExceptHandler(self, node):
                # Check for bare except clauses
                if node.type is None:
                    self.bugs.append(BugReport(
                        severity="MEDIUM",
                        category="RELIABILITY",
                        title="Bare Except Clause",
                        description="Bare 'except:' clause catches all exceptions",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        suggestion="Specify exception types to catch"
                    ))

                self.generic_visit(node)

            def calculate_complexity(self, node):
                """Calculate cyclomatic complexity"""
                complexity = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.For, ast.While, ast.Assert,
                                       ast.With, ast.Try, ast.ExceptHandler)):
                        complexity += 1
                    elif isinstance(child, ast.BoolOp) and len(child.values) > 1:
                        complexity += len(child.values) - 1
                return complexity

        visitor = CodeVisitor(bugs, file_path, lines)
        visitor.visit(tree)

        return bugs

    def analyze_patterns(self, content: str, lines: List[str], file_path: str) -> List[BugReport]:
        """Analyze code patterns for potential issues"""
        bugs = []

        # Check for dangerous patterns
        dangerous_patterns = [
            (r'print\(', "DEBUG", "Print statements in production code"),
            (r'pdb\.set_trace\(\)', "CRITICAL", "Debugger breakpoint in code"),
            (r'input\(', "MEDIUM", "User input in automated code"),
            (r'eval\(', "HIGH", "Use of eval() function"),
            (r'exec\(', "HIGH", "Use of exec() function"),
            (r'assert\s+', "LOW", "Assertions in production code"),
            (r'pass\s*$', "INFO", "Empty code blocks"),
        ]

        for i, line in enumerate(lines, 1):
            for pattern, severity, description in dangerous_patterns:
                if re.search(pattern, line.strip()):
                    # Skip comments and docstrings
                    if not line.strip().startswith('#') and '"""' not in line and "'''" not in line:
                        bugs.append(BugReport(
                            severity=severity,
                            category="SECURITY" if severity in ["CRITICAL", "HIGH"] else "MAINTAINABILITY",
                            title=f"Potentially Dangerous Pattern: {description}",
                            description=f"Found '{pattern}' pattern in line {i}",
                            file_path=file_path,
                            line_number=i,
                            code_snippet=line.strip(),
                            suggestion="Review and remove if not needed for debugging"
                        ))

        # Check for TODO comments
        for i, line in enumerate(lines, 1):
            if 'TODO' in line.upper() or 'FIXME' in line.upper() or 'XXX' in line.upper():
                bugs.append(BugReport(
                    severity="INFO",
                    category="MAINTAINABILITY",
                    title="TODO Comment Found",
                    description="TODO/FIXME comment indicates incomplete work",
                    file_path=file_path,
                    line_number=i,
                    code_snippet=line.strip(),
                    suggestion="Address the TODO item or remove if completed"
                ))

        # Check for long lines
        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                bugs.append(BugReport(
                    severity="LOW",
                    category="MAINTAINABILITY",
                    title="Long Line",
                    description=f"Line {i} is {len(line)} characters long (recommended max: 120)",
                    file_path=file_path,
                    line_number=i,
                    code_snippet=line[:50] + "..." if len(line) > 50 else line,
                    suggestion="Break long lines for better readability"
                ))

        return bugs

class UnitTestAgent(BaseAgent):
    """Automated unit test generation and execution agent"""

    def __init__(self):
        super().__init__("Unit Test Agent")

    def analyze_codebase(self, codebase_path: str) -> List[BugReport]:
        bugs = []

        # Find Python files to test
        python_files = self.find_testable_files(codebase_path)

        for file_path in python_files:
            try:
                bugs.extend(self.analyze_and_test_file(file_path))
            except Exception as e:
                bugs.append(BugReport(
                    severity="MEDIUM",
                    category="RELIABILITY",
                    title="Test Analysis Error",
                    description=f"Could not analyze tests for {file_path}: {str(e)}",
                    file_path=file_path,
                    suggestion="Check file structure and imports"
                ))

        return bugs

    def find_testable_files(self, path: str) -> List[str]:
        """Find Python files that should have tests"""
        testable_files = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'venv', '.git', 'tests']]

            for file in files:
                if file.endswith('.py') and not file.startswith('test_'):
                    file_path = os.path.join(root, file)
                    testable_files.append(file_path)

        return testable_files

    def analyze_and_test_file(self, file_path: str) -> List[BugReport]:
        """Analyze file and check for test coverage"""
        bugs = []

        # Check if test file exists
        test_file = self.get_test_file_path(file_path)
        if not os.path.exists(test_file):
            bugs.append(BugReport(
                severity="MEDIUM",
                category="RELIABILITY",
                title="Missing Unit Tests",
                description=f"No test file found for {os.path.basename(file_path)}",
                file_path=file_path,
                suggestion=f"Create test file: {test_file}"
            ))
            return bugs

        # Try to run the tests
        try:
            result = subprocess.run([
                sys.executable, '-m', 'pytest', test_file, '-v', '--tb=short'
            ], capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                bugs.append(BugReport(
                    severity="HIGH",
                    category="RELIABILITY",
                    title="Failing Unit Tests",
                    description=f"Tests failed for {os.path.basename(file_path)}",
                    file_path=test_file,
                    suggestion=f"Fix test failures: {result.stdout[-500:]}"
                ))

        except subprocess.TimeoutExpired:
            bugs.append(BugReport(
                severity="MEDIUM",
                category="PERFORMANCE",
                title="Slow Unit Tests",
                description=f"Tests for {os.path.basename(file_path)} timed out",
                file_path=test_file,
                suggestion="Optimize test execution time"
            ))
        except Exception as e:
            bugs.append(BugReport(
                severity="MEDIUM",
                category="RELIABILITY",
                title="Test Execution Error",
                description=f"Could not run tests for {os.path.basename(file_path)}: {str(e)}",
                file_path=test_file,
                suggestion="Check test setup and dependencies"
            ))

        return bugs

    def get_test_file_path(self, source_file: str) -> str:
        """Get the corresponding test file path"""
        dirname = os.path.dirname(source_file)
        basename = os.path.basename(source_file)
        test_name = f"test_{basename}"
        return os.path.join(dirname, "tests", test_name)

class IntegrationTestAgent(BaseAgent):
    """Integration testing agent"""

    def __init__(self):
        super().__init__("Integration Test Agent")

    def analyze_codebase(self, codebase_path: str) -> List[BugReport]:
        bugs = []

        # Test key integration points
        bugs.extend(self.test_database_integration(codebase_path))
        bugs.extend(self.test_config_integration(codebase_path))
        bugs.extend(self.test_trading_integration(codebase_path))

        return bugs

    def test_database_integration(self, codebase_path: str) -> List[BugReport]:
        """Test database integration"""
        bugs = []

        try:
            # Try to import database module
            spec = importlib.util.spec_from_file_location(
                "database", os.path.join(codebase_path, "src", "database.py")
            )
            if spec and spec.loader:
                db_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(db_module)

                # Test basic database operations
                if hasattr(db_module, 'DatabaseManager'):
                    # This would require actual database setup
                    bugs.append(BugReport(
                        severity="INFO",
                        category="INTEGRATION",
                        title="Database Integration Check",
                        description="Database module found and importable",
                        suggestion="Consider adding integration tests for database operations"
                    ))

        except Exception as e:
            bugs.append(BugReport(
                severity="HIGH",
                category="INTEGRATION",
                title="Database Integration Failure",
                description=f"Could not test database integration: {str(e)}",
                suggestion="Check database configuration and dependencies"
            ))

        return bugs

    def test_config_integration(self, codebase_path: str) -> List[BugReport]:
        """Test configuration integration"""
        bugs = []

        config_file = os.path.join(codebase_path, "config", "personal_config.json")
        if not os.path.exists(config_file):
            bugs.append(BugReport(
                severity="MEDIUM",
                category="CONFIGURATION",
                title="Missing Configuration File",
                description="Personal configuration file not found",
                file_path=config_file,
                suggestion="Run configuration setup or create config file"
            ))

        return bugs

    def test_trading_integration(self, codebase_path: str) -> List[BugReport]:
        """Test trading system integration"""
        bugs = []

        # Check for required trading components
        required_files = [
            "src/arbitrage_detector.py",
            "src/exchange_connector.py",
            "src/risk_manager.py",
            "src/order_executor.py"
        ]

        for file_path in required_files:
            full_path = os.path.join(codebase_path, file_path)
            if not os.path.exists(full_path):
                bugs.append(BugReport(
                    severity="HIGH",
                    category="INTEGRATION",
                    title="Missing Trading Component",
                    description=f"Required trading file not found: {file_path}",
                    file_path=full_path,
                    suggestion="Ensure all trading components are present"
                ))

        return bugs

class PerformanceAgent(BaseAgent):
    """Performance analysis agent"""

    def __init__(self):
        super().__init__("Performance Agent")

    def analyze_codebase(self, codebase_path: str) -> List[BugReport]:
        bugs = []

        # Analyze import efficiency
        bugs.extend(self.analyze_imports(codebase_path))

        # Analyze memory usage patterns
        bugs.extend(self.analyze_memory_usage(codebase_path))

        # Analyze algorithmic complexity
        bugs.extend(self.analyze_complexity(codebase_path))

        return bugs

    def analyze_imports(self, codebase_path: str) -> List[BugReport]:
        """Analyze import efficiency"""
        bugs = []

        python_files = []
        for root, dirs, files in os.walk(codebase_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'venv', '.git']]
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))

        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Check for wildcard imports
                if 'from ' in content and ' import *' in content:
                    bugs.append(BugReport(
                        severity="LOW",
                        category="PERFORMANCE",
                        title="Wildcard Import",
                        description="Wildcard imports can slow down startup",
                        file_path=file_path,
                        suggestion="Use explicit imports instead of 'import *'"
                    ))

                # Check for unused imports (basic check)
                lines = content.split('\n')
                imports = []
                for line in lines:
                    line = line.strip()
                    if line.startswith('import ') or line.startswith('from '):
                        imports.append(line)

                if len(imports) > 20:
                    bugs.append(BugReport(
                        severity="LOW",
                        category="PERFORMANCE",
                        title="Many Imports",
                        description=f"File has {len(imports)} imports, consider consolidating",
                        file_path=file_path,
                        suggestion="Review and consolidate imports"
                    ))

            except Exception as e:
                continue

        return bugs

    def analyze_memory_usage(self, codebase_path: str) -> List[BugReport]:
        """Analyze potential memory issues"""
        bugs = []

        # This is a simplified analysis - in a real system you'd run the code
        # and profile memory usage

        python_files = []
        for root, dirs, files in os.walk(codebase_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'venv', '.git']]
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))

        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Check for large data structures
                if 'list(' in content and len(content) > 10000:
                    bugs.append(BugReport(
                        severity="INFO",
                        category="PERFORMANCE",
                        title="Potential Memory Usage",
                        description="Large file with list operations may use significant memory",
                        file_path=file_path,
                        suggestion="Consider streaming or chunked processing for large data"
                    ))

            except Exception as e:
                continue

        return bugs

    def analyze_complexity(self, codebase_path: str) -> List[BugReport]:
        """Analyze algorithmic complexity"""
        bugs = []

        # This would require more sophisticated analysis
        # For now, just check file sizes as a proxy

        python_files = []
        for root, dirs, files in os.walk(codebase_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'venv', '.git']]
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))

        for file_path in python_files:
            try:
                size = os.path.getsize(file_path)
                if size > 100000:  # 100KB
                    bugs.append(BugReport(
                        severity="INFO",
                        category="MAINTAINABILITY",
                        title="Large Source File",
                        description=f"File is {size/1024:.1f}KB, consider splitting",
                        file_path=file_path,
                        suggestion="Break large files into smaller modules"
                    ))

            except Exception as e:
                continue

        return bugs

class AgentReviewOrchestrator:
    """Orchestrates all agent reviews"""

    def __init__(self):
        self.agents = [
            CodeAnalysisAgent(),
            UnitTestAgent(),
            IntegrationTestAgent(),
            PerformanceAgent()
        ]
        self.all_bugs = []

    def run_full_review(self, codebase_path: str) -> Dict[str, Any]:
        """Run all agents and generate comprehensive report"""

        print("🤖 SovereignForge Agent Review System")
        print("=" * 50)
        print(f"📊 Running {len(self.agents)} agents on codebase: {codebase_path}")
        print()

        start_time = datetime.now()
        total_bugs = 0

        for agent in self.agents:
            print(f"🚀 Running {agent.name}...")
            agent_bugs = agent.run(codebase_path)
            self.all_bugs.extend(agent_bugs)
            total_bugs += len(agent_bugs)
            print(f"   Found {len(agent_bugs)} issues")
            print()

        end_time = datetime.now()
        duration = end_time - start_time

        # Generate summary
        summary = self.generate_summary(duration)

        # Save detailed report
        self.save_report(summary)

        return summary

    def generate_summary(self, duration) -> Dict[str, Any]:
        """Generate comprehensive review summary"""

        # Categorize bugs by severity
        severity_counts = {
            'CRITICAL': 0,
            'HIGH': 0,
            'MEDIUM': 0,
            'LOW': 0,
            'INFO': 0
        }

        # Categorize bugs by category
        category_counts = {}

        # Group bugs by agent
        agent_counts = {}

        for bug in self.all_bugs:
            severity_counts[bug.severity] = severity_counts.get(bug.severity, 0) + 1
            category_counts[bug.category] = category_counts.get(bug.category, 0) + 1
            agent_counts[bug.agent_name] = agent_counts.get(bug.agent_name, 0) + 1

        summary = {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': duration.total_seconds(),
            'total_bugs': len(self.all_bugs),
            'severity_breakdown': severity_counts,
            'category_breakdown': category_counts,
            'agent_breakdown': agent_counts,
            'bugs': [bug.to_dict() for bug in self.all_bugs],
            'recommendations': self.generate_recommendations(severity_counts)
        }

        return summary

    def generate_recommendations(self, severity_counts: Dict[str, int]) -> List[str]:
        """Generate recommendations based on findings"""

        recommendations = []

        if severity_counts.get('CRITICAL', 0) > 0:
            recommendations.append("🚨 CRITICAL ISSUES FOUND: Address immediately before deployment")

        if severity_counts.get('HIGH', 0) > 0:
            recommendations.append("⚠️ HIGH PRIORITY: Fix security and reliability issues promptly")

        if severity_counts.get('MEDIUM', 0) > 5:
            recommendations.append("📋 MULTIPLE MEDIUM ISSUES: Consider refactoring for better maintainability")

        if severity_counts.get('LOW', 0) > 10:
            recommendations.append("🧹 CODE CLEANUP: Address low-priority issues for better code quality")

        if not recommendations:
            recommendations.append("✅ CODE QUALITY GOOD: No critical issues found")

        recommendations.extend([
            "🔧 TESTING: Ensure all critical paths have unit tests",
            "📚 DOCUMENTATION: Add docstrings to complex functions",
            "🚀 PERFORMANCE: Profile and optimize slow functions",
            "🔒 SECURITY: Review and fix security-related findings"
        ])

        return recommendations

    def save_report(self, summary: Dict[str, Any]):
        """Save detailed review report"""

        # Create reports directory
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        # Save JSON report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = reports_dir / f"agent_review_{timestamp}.json"

        with open(json_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        # Save CEO summary report
        ceo_file = reports_dir / f"ceo_report_{timestamp}.md"
        self.generate_ceo_report(summary, ceo_file)

        print(f"📄 Detailed report saved: {json_file}")
        print(f"👔 CEO summary saved: {ceo_file}")

    def generate_ceo_report(self, summary: Dict[str, Any], file_path: Path):
        """Generate executive summary for CEO"""

        with open(file_path, 'w') as f:
            f.write("# SovereignForge Agent Review - CEO Summary\n\n")
            f.write(f"**Report Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Review Duration:** {summary['duration_seconds']:.1f} seconds\n\n")

            f.write("## 📊 Executive Summary\n\n")
            f.write(f"- **Total Issues Found:** {summary['total_bugs']}\n")
            f.write(f"- **Critical Issues:** {summary['severity_breakdown'].get('CRITICAL', 0)}\n")
            f.write(f"- **High Priority:** {summary['severity_breakdown'].get('HIGH', 0)}\n")
            f.write(f"- **Code Quality:** {'Excellent' if summary['total_bugs'] < 10 else 'Good' if summary['total_bugs'] < 50 else 'Needs Attention'}\n\n")

            f.write("## 🚨 Critical Issues\n\n")
            critical_bugs = [b for b in summary['bugs'] if b['severity'] == 'CRITICAL']
            if critical_bugs:
                for bug in critical_bugs[:5]:  # Show top 5
                    f.write(f"- **{bug['title']}**: {bug['description']}\n")
                if len(critical_bugs) > 5:
                    f.write(f"- ... and {len(critical_bugs) - 5} more critical issues\n")
            else:
                f.write("✅ No critical issues found\n")
            f.write("\n")

            f.write("## 📈 Key Metrics\n\n")
            f.write("| Category | Count |\n")
            f.write("|----------|-------|\n")
            for category, count in summary['category_breakdown'].items():
                f.write(f"| {category} | {count} |\n")
            f.write("\n")

            f.write("## 🎯 Recommendations\n\n")
            for rec in summary['recommendations']:
                f.write(f"- {rec}\n")
            f.write("\n")

            f.write("## 📋 Next Steps\n\n")
            f.write("1. **Review Critical Issues** - Address immediately\n")
            f.write("2. **Fix High Priority Items** - Security and reliability\n")
            f.write("3. **Code Quality Improvements** - Refactoring and cleanup\n")
            f.write("4. **Testing Enhancement** - Add missing unit tests\n")
            f.write("5. **Performance Optimization** - Profile and improve slow code\n")
            f.write("\n")

            f.write("---\n")
            f.write("*Generated by SovereignForge Automated Agent Review System*\n")

def main():
    """Main entry point for agent review"""

    parser = argparse.ArgumentParser(
        description='SovereignForge Automated Agent Review System'
    )
    parser.add_argument('--path', default='.',
                       help='Path to codebase to review (default: current directory)')
    parser.add_argument('--agents', nargs='+',
                       help='Specific agents to run (default: all)')
    parser.add_argument('--output-dir', default='reports',
                       help='Output directory for reports')

    args = parser.parse_args()

    # Run the review
    orchestrator = AgentReviewOrchestrator()

    if args.agents:
        # Run specific agents
        agent_map = {agent.name: agent for agent in orchestrator.agents}
        selected_agents = []
        for agent_name in args.agents:
            if agent_name in agent_map:
                selected_agents.append(agent_map[agent_name])
            else:
                print(f"⚠️  Agent '{agent_name}' not found")
        orchestrator.agents = selected_agents

    summary = orchestrator.run_full_review(args.path)

    # Print summary
    print("\n" + "=" * 60)
    print("🎯 REVIEW COMPLETE")
    print("=" * 60)
    print(f"📊 Total Issues: {summary['total_bugs']}")
    print(f"🚨 Critical: {summary['severity_breakdown'].get('CRITICAL', 0)}")
    print(f"⚠️  High: {summary['severity_breakdown'].get('HIGH', 0)}")
    print(f"📋 Medium: {summary['severity_breakdown'].get('MEDIUM', 0)}")
    print(f"🧹 Low: {summary['severity_breakdown'].get('LOW', 0)}")
    print(f"ℹ️  Info: {summary['severity_breakdown'].get('INFO', 0)}")
    print()
    print("📄 Reports saved in reports/ directory")
    print("👔 CEO summary available for executive review")

if __name__ == "__main__":
    main()