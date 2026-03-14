"""Base infrastructure for audit and research agents."""

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Finding:
    severity: str       # critical / high / medium / low / info
    file: str
    line: Optional[int]
    category: str
    description: str
    recommendation: str


@dataclass
class AgentReport:
    agent_name: str
    agent_type: str     # "audit" or "research"
    timestamp: str
    health_score: float  # 0-100
    findings: List[Finding]
    summary: str
    files_scanned: int
    execution_time_seconds: float = 0.0
    recommendations: List[str] = field(default_factory=list)

    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == 'critical')

    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == 'high')

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        lines = [
            f"# {self.agent_name} Audit Report",
            f"**Type:** {self.agent_type} | **Score:** {self.health_score}/100 | **Time:** {self.execution_time_seconds:.1f}s",
            f"**Files Scanned:** {self.files_scanned} | **Findings:** {len(self.findings)}",
            "",
            f"## Summary",
            self.summary,
            "",
        ]

        # Group by severity
        for sev in ['critical', 'high', 'medium', 'low', 'info']:
            sev_findings = [f for f in self.findings if f.severity == sev]
            if sev_findings:
                lines.append(f"## {sev.upper()} ({len(sev_findings)})")
                for f in sev_findings:
                    loc = f"{f.file}"
                    if f.line:
                        loc += f":{f.line}"
                    lines.append(f"- **[{f.category}]** `{loc}` — {f.description}")
                    lines.append(f"  - Fix: {f.recommendation}")
                lines.append("")

        if self.recommendations:
            lines.append("## Top Recommendations")
            for r in self.recommendations:
                lines.append(f"- {r}")

        return "\n".join(lines)


def save_report(report: AgentReport, output_dir: Path):
    """Save report as both JSON and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    name = report.agent_name.lower().replace(" ", "_")

    json_path = output_dir / f"{name}.json"
    json_path.write_text(report.to_json(), encoding="utf-8")

    md_path = output_dir / f"{name}.md"
    md_path.write_text(report.to_markdown(), encoding="utf-8")

    return json_path, md_path


def load_all_reports(output_dir: Path) -> List[AgentReport]:
    """Load all JSON reports from directory."""
    reports = []
    for json_file in sorted(output_dir.glob("*.json")):
        if json_file.name == "synthesis.json":
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            findings = [Finding(**f) for f in data.pop("findings", [])]
            reports.append(AgentReport(**data, findings=findings))
        except Exception:
            pass
    return reports
