#!/usr/bin/env python3
"""
SovereignForge Warm Start Hook
Injects full project state in 1.4 seconds for session persistence
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import platform
import psutil

class WarmStart:
    """Project state injection for session persistence"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root or self._find_project_root())
        self.start_time = time.time()
        self.state = {}

    def _find_project_root(self) -> str:
        """Find project root by looking for key files"""
        current = Path.cwd()
        for parent in [current] + list(current.parents):
            if (parent / "WORKING.md").exists() and (parent / "AGENTS.md").exists():
                return str(parent)
        return str(Path.cwd())

    def _run_command(self, cmd: List[str], cwd: Optional[str] = None) -> Optional[str]:
        """Run command and return output, None on failure"""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.project_root,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            return None

    def get_git_state(self) -> Dict[str, Any]:
        """Get git repository state"""
        git_state = {
            "branch": "unknown",
            "commit_hash": "unknown",
            "uncommitted_changes": [],
            "upstream_sync": "unknown",
            "stash_count": 0,
            "last_commit": "unknown",
            "recent_commits": []
        }

        # Current branch
        branch = self._run_command(["git", "branch", "--show-current"])
        if branch:
            git_state["branch"] = branch

        # Current commit hash
        commit_hash = self._run_command(["git", "rev-parse", "HEAD"])
        if commit_hash:
            git_state["commit_hash"] = commit_hash[:8]

        # Uncommitted changes
        status = self._run_command(["git", "status", "--porcelain"])
        if status:
            git_state["uncommitted_changes"] = status.split('\n') if status else []

        # Upstream sync status
        upstream = self._run_command(["git", "status", "-b", "--ahead-behind"])
        if upstream:
            git_state["upstream_sync"] = upstream

        # Stash count
        stash_count = self._run_command(["git", "stash", "list"])
        if stash_count:
            git_state["stash_count"] = len(stash_count.split('\n')) if stash_count else 0

        # Last commit info
        last_commit = self._run_command(["git", "log", "-1", "--oneline"])
        if last_commit:
            git_state["last_commit"] = last_commit

        # Recent commits (last 5)
        recent = self._run_command(["git", "log", "-5", "--oneline"])
        if recent:
            git_state["recent_commits"] = recent.split('\n') if recent else []

        return git_state

    def get_stack_info(self) -> Dict[str, Any]:
        """Detect technology stack and versions"""
        stack = {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": platform.system(),
            "architecture": platform.machine(),
            "cpu_count": os.cpu_count(),
            "memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "frameworks": {},
            "languages": []
        }

        # Check for Python frameworks
        try:
            import torch
            stack["frameworks"]["pytorch"] = torch.__version__
            stack["cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                stack["cuda_version"] = torch.version.cuda
                stack["gpu_count"] = torch.cuda.device_count()
                stack["gpu_name"] = torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else "unknown"
        except ImportError:
            stack["frameworks"]["pytorch"] = None

        try:
            import fastapi
            stack["frameworks"]["fastapi"] = fastapi.__version__
        except ImportError:
            pass

        try:
            import flask
            stack["frameworks"]["flask"] = flask.__version__
        except ImportError:
            pass

        # Check for Node.js
        node_version = self._run_command(["node", "--version"])
        if node_version:
            stack["languages"].append("node")
            stack["node_version"] = node_version

        # Check for Docker
        docker_version = self._run_command(["docker", "--version"])
        if docker_version:
            stack["docker_available"] = True
            stack["docker_version"] = docker_version.split()[2].rstrip(',') if len(docker_version.split()) > 2 else "unknown"

        # Check for kubectl
        kubectl_version = self._run_command(["kubectl", "version", "--client", "--short"])
        if kubectl_version:
            stack["kubectl_available"] = True

        return stack

    def get_key_commands(self) -> Dict[str, str]:
        """Extract key development commands from project files"""
        commands = {
            "test": "python -m pytest tests/ -v",
            "build": "docker build -t sovereignforge .",
            "dev": "docker-compose up -d",
            "lint": "python -m pylint src/",
            "format": "python -m black src/",
            "deploy": "./deploy.sh"
        }

        # Try to extract from package.json if it exists
        package_json = self.project_root / "package.json"
        if package_json.exists():
            try:
                with open(package_json) as f:
                    pkg = json.load(f)
                    scripts = pkg.get("scripts", {})
                    if "test" in scripts:
                        commands["test"] = f"npm run {scripts['test']}"
                    if "build" in scripts:
                        commands["build"] = f"npm run {scripts['build']}"
                    if "dev" in scripts:
                        commands["dev"] = f"npm run {scripts['dev']}"
            except:
                pass

        # Check for deploy.sh
        deploy_script = self.project_root / "deploy.sh"
        if deploy_script.exists():
            commands["deploy"] = "./deploy.sh"

        return commands

    def get_project_structure(self) -> Dict[str, Any]:
        """Get key project structure and load-bearing files"""
        structure: Dict[str, Any] = {
            "load_bearing_configs": [],
            "model_dirs": [],
            "test_dirs": [],
            "deployment_files": [],
            "documentation": [],
            "monitoring_components": [],
            "production_ready": False
        }

        # Load-bearing config files
        config_files = [
            "core/config.py", "config.py", "personal_config.json",
            "pyrightconfig.json", ".vscode/settings.json",
            "docker-compose.yml", "Dockerfile", "requirements.txt",
            "production_docker_compose.yml", "live_testing_validator.py"
        ]

        for config in config_files:
            if (self.project_root / config).exists():
                structure["load_bearing_configs"].append(config)

        # Model directories
        model_dirs = ["models/", "src/models/", "model_checkpoints/", "training_logs/"]
        for model_dir in model_dirs:
            if (self.project_root / model_dir).exists():
                structure["model_dirs"].append(model_dir)

        # Test directories
        test_dirs = ["tests/", "test/", "src/tests/", "integration_test_suite.py"]
        for test_dir in test_dirs:
            if (self.project_root / test_dir).exists():
                structure["test_dirs"].append(test_dir)

        # Deployment files
        deploy_files = ["deploy.sh", "k8s/", "docker/", "production_docker_compose.yml"]
        for deploy_file in deploy_files:
            if (self.project_root / deploy_file).exists():
                structure["deployment_files"].append(deploy_file)

        # Documentation
        docs = ["WORKING.md", "AGENTS.md", "README.md", "PRODUCTION_README.md",
                "user_manual.md", "troubleshooting_guide.md", "compliance_documentation.md"]
        for doc in docs:
            if (self.project_root / doc).exists():
                structure["documentation"].append(doc)

        # Monitoring components
        monitoring_files = ["monitoring/dashboard/", "monitoring/backend/",
                           "PnlChart.tsx", "RiskGauges.tsx", "PositionsTable.tsx"]
        for monitor_file in monitoring_files:
            if (self.project_root / monitor_file).exists():
                structure["monitoring_components"].append(monitor_file)

        # Production readiness check
        required_files = ["production_docker_compose.yml", "integration_test_suite.py",
                         "user_manual.md", "system_readiness_report.json"]
        structure["production_ready"] = all((self.project_root / f).exists() for f in required_files)

        return structure

    def get_recent_changes(self) -> Dict[str, Any]:
        """Get recent project changes and issues"""
        changes = {
            "last_modified_files": [],
            "open_issues": [],
            "recent_activity": []
        }

        # Last modified files (last 7 days)
        try:
            import datetime
            week_ago = datetime.datetime.now() - datetime.timedelta(days=7)
            for file_path in Path(self.project_root).rglob("*"):
                if file_path.is_file():
                    mtime = datetime.datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime > week_ago:
                        changes["last_modified_files"].append({
                            "path": str(file_path.relative_to(self.project_root)),
                            "modified": mtime.isoformat()
                        })
        except:
            pass

        # Recent git activity
        recent_activity = self._run_command(["git", "log", "--since=1.week", "--oneline"])
        if recent_activity:
            changes["recent_activity"] = recent_activity.split('\n')[:10]  # Last 10 commits

        return changes

    def inject_context(self) -> str:
        """Inject full project state for session context"""
        self.state = {
            "git_state": self.get_git_state(),
            "stack_info": self.get_stack_info(),
            "key_commands": self.get_key_commands(),
            "project_structure": self.get_project_structure(),
            "recent_changes": self.get_recent_changes(),
            "injection_time": time.time() - self.start_time,
            "project_root": str(self.project_root)
        }

        # Format for context injection
        context_lines = [
            f"## SovereignForge Project State (Injected in {self.state['injection_time']:.2f}s)",
            "",
            "### Git State",
            f"- Branch: {self.state['git_state']['branch']}",
            f"- Commit: {self.state['git_state']['commit_hash']}",
            f"- Uncommitted: {len(self.state['git_state']['uncommitted_changes'])} files",
            f"- Upstream: {self.state['git_state']['upstream_sync']}",
            f"- Stash: {self.state['git_state']['stash_count']} items",
            "",
            "### Technology Stack",
            f"- Python: {self.state['stack_info']['python_version']}",
            f"- PyTorch: {self.state['stack_info']['frameworks'].get('pytorch', 'not found')}",
            f"- CUDA: {'available' if self.state['stack_info'].get('cuda_available') else 'not available'}",
            f"- Platform: {self.state['stack_info']['platform']} {self.state['stack_info']['architecture']}",
            f"- CPU: {self.state['stack_info']['cpu_count']} cores, {self.state['stack_info']['memory_gb']}GB RAM",
            "",
            "### Key Commands",
            f"- Test: {self.state['key_commands']['test']}",
            f"- Build: {self.state['key_commands']['build']}",
            f"- Dev: {self.state['key_commands']['dev']}",
            f"- Deploy: {self.state['key_commands']['deploy']}",
            "",
            "### Load-Bearing Files",
            f"- Configs: {', '.join(self.state['project_structure']['load_bearing_configs'])}",
            f"- Models: {', '.join(self.state['project_structure']['model_dirs'])}",
            f"- Tests: {', '.join(self.state['project_structure']['test_dirs'])}",
            f"- Deployment: {', '.join(self.state['project_structure']['deployment_files'])}",
            "",
            "### Recent Activity",
            f"- Modified files (7d): {len(self.state['recent_changes']['last_modified_files'])}",
            f"- Recent commits: {len(self.state['recent_changes']['recent_activity'])}",
            "",
            "---",
            "Context injected. Ready for session."
        ]

        return "\n".join(context_lines)

def main():
    """Main warm start execution"""
    warm_start = WarmStart()
    context = warm_start.inject_context()
    print(context)

    # Save state to file for reference
    with open("warm_start_state.json", "w") as f:
        json.dump(warm_start.state, f, indent=2, default=str)

if __name__ == "__main__":
    main()