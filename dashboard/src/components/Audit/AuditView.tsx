import React, { useState, useEffect } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface AgentReport {
  agent: string;
  score: number;
  status: string;
  findings: Finding[];
  timestamp?: string;
}

interface Finding {
  agent: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  title: string;
  description: string;
  timestamp?: string;
}

interface Synthesis {
  overall_score: number;
  agent_scores: Record<string, number>;
  total_findings: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  timestamp?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const AGENT_COLORS: Record<string, string> = {
  risk: '#f85149',
  compliance: '#58a6ff',
  performance: '#3fb950',
  liquidity: '#d29922',
  security: '#bc8cff',
  infrastructure: '#f0883e',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#f85149',
  high: '#f0883e',
  medium: '#d29922',
  low: '#58a6ff',
  info: '#8b949e',
};

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };
const metricCard: React.CSSProperties = { background: '#21262d', borderRadius: 6, padding: '14px 18px', flex: 1, minWidth: 140 };

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
const AGENTS = ['risk', 'compliance', 'performance', 'liquidity', 'security', 'infrastructure'];

function demoSynthesis(): Synthesis {
  return {
    overall_score: 82,
    agent_scores: { risk: 78, compliance: 91, performance: 85, liquidity: 74, security: 88, infrastructure: 76 },
    total_findings: 14,
    critical_count: 1,
    high_count: 3,
    medium_count: 5,
    low_count: 5,
    timestamp: new Date().toISOString(),
  };
}

function demoReports(): AgentReport[] {
  return AGENTS.map(agent => ({
    agent,
    score: Math.round(65 + Math.random() * 30),
    status: Math.random() > 0.15 ? 'healthy' : 'warning',
    findings: [
      { agent, severity: 'medium' as const, title: `${agent} check passed with notes`, description: `Routine ${agent} audit found minor items to review.`, timestamp: new Date().toISOString() },
      ...(Math.random() > 0.5 ? [{ agent, severity: 'low' as const, title: `${agent} optimization suggestion`, description: `Consider adjusting ${agent} parameters for improved performance.`, timestamp: new Date().toISOString() }] : []),
    ],
  }));
}

// ---------------------------------------------------------------------------
// Health Gauge (inverted: green = high score, red = low)
// ---------------------------------------------------------------------------
const HealthGauge: React.FC<{ score: number }> = ({ score }) => {
  const radius = 70, cx = 90, cy = 85, strokeW = 14;
  const startAngle = Math.PI, endAngle = 0;
  const range = startAngle - endAngle;
  const pct = Math.min(Math.max(score, 0), 100) / 100;
  const angle = startAngle - pct * range;
  // Inverted: green when high, red when low
  const color = score >= 80 ? '#3fb950' : score >= 60 ? '#d29922' : '#f85149';

  const arcPath = (start: number, end: number) => {
    const x1 = cx + radius * Math.cos(start), y1 = cy - radius * Math.sin(start);
    const x2 = cx + radius * Math.cos(end), y2 = cy - radius * Math.sin(end);
    const large = start - end > Math.PI ? 1 : 0;
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${large} 0 ${x2} ${y2}`;
  };

  return (
    <svg width={180} height={110} viewBox="0 0 180 110">
      <path d={arcPath(startAngle, endAngle)} fill="none" stroke="#21262d" strokeWidth={strokeW} strokeLinecap="round" />
      <path d={arcPath(startAngle, angle)} fill="none" stroke={color} strokeWidth={strokeW} strokeLinecap="round" />
      <text x={cx} y={cy - 5} textAnchor="middle" fill={color} fontSize={28} fontWeight={700}>{score}</text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#8b949e" fontSize={11}>Health Score</text>
    </svg>
  );
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const AuditView: React.FC = () => {
  const [synthesis, setSynthesis] = useState<Synthesis | null>(null);
  const [reports, setReports] = useState<AgentReport[]>([]);
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [sortField, setSortField] = useState<'severity' | 'agent' | 'title'>('severity');
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8420/api/agents/synthesis')
      .then(r => r.json())
      .then(d => setSynthesis(d))
      .catch(() => setSynthesis(demoSynthesis()));

    fetch('http://localhost:8420/api/agents/reports')
      .then(r => r.json())
      .then(d => setReports(d.reports || d || []))
      .catch(() => setReports(demoReports()));
  }, []);

  if (!synthesis) {
    return <div style={{ ...card, textAlign: 'center', padding: 40, color: '#718096', fontSize: 14 }}>Loading audit data...</div>;
  }

  // Collect all findings from reports
  const allFindings: Finding[] = reports.flatMap(r =>
    (r.findings || []).map(f => ({ ...f, agent: f.agent || r.agent }))
  );

  // Filter + sort
  const filtered = severityFilter === 'all'
    ? allFindings
    : allFindings.filter(f => f.severity === severityFilter);

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    if (sortField === 'severity') {
      cmp = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9);
    } else if (sortField === 'agent') {
      cmp = a.agent.localeCompare(b.agent);
    } else {
      cmp = a.title.localeCompare(b.title);
    }
    return sortAsc ? cmp : -cmp;
  });

  const handleSort = (field: 'severity' | 'agent' | 'title') => {
    if (sortField === field) {
      setSortAsc(p => !p);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const sortIndicator = (field: string) => sortField === field ? (sortAsc ? ' \u25B2' : ' \u25BC') : '';

  const agentScores = synthesis.agent_scores || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Audit Overview</h2>

      {/* Top row: Health Gauge + Summary metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 16 }}>
        <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <HealthGauge score={synthesis.overall_score} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {[
            { label: 'Total Findings', value: String(synthesis.total_findings), color: '#e2e8f0' },
            { label: 'Critical', value: String(synthesis.critical_count), color: synthesis.critical_count > 0 ? '#f85149' : '#3fb950' },
            { label: 'High', value: String(synthesis.high_count), color: synthesis.high_count > 0 ? '#f0883e' : '#3fb950' },
            { label: 'Medium / Low', value: `${synthesis.medium_count} / ${synthesis.low_count}`, color: '#d29922' },
          ].map(m => (
            <div key={m.label} style={metricCard}>
              <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>{m.label}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: m.color }}>{m.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Agent score cards (3x2 grid) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {AGENTS.map(agent => {
          const score = agentScores[agent] ?? 0;
          const color = AGENT_COLORS[agent] || '#8b949e';
          const report = reports.find(r => r.agent === agent);
          const status = report?.status || 'unknown';
          const findingCount = (report?.findings || []).length;
          const scoreColor = score >= 80 ? '#3fb950' : score >= 60 ? '#d29922' : '#f85149';

          return (
            <div key={agent} style={{ ...card, borderLeft: `3px solid ${color}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <span style={{ fontSize: 15, fontWeight: 700, textTransform: 'capitalize' }}>{agent}</span>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11,
                  color: status === 'healthy' ? '#3fb950' : status === 'warning' ? '#d29922' : '#8b949e',
                }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
                    background: status === 'healthy' ? '#3fb950' : status === 'warning' ? '#d29922' : '#484f58',
                  }} />
                  {status}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
                <span style={{ fontSize: 28, fontWeight: 700, color: scoreColor }}>{score}</span>
                <span style={{ fontSize: 12, color: '#8b949e' }}>{findingCount} finding{findingCount !== 1 ? 's' : ''}</span>
              </div>
              {/* Score bar */}
              <div style={{ background: '#21262d', borderRadius: 4, height: 6, overflow: 'hidden' }}>
                <div style={{ width: `${Math.min(score, 100)}%`, height: '100%', background: scoreColor, borderRadius: 4, transition: 'width 0.4s' }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Findings table */}
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Findings</h3>
          {/* Severity filter pills */}
          <div style={{ display: 'flex', gap: 6 }}>
            {['all', 'critical', 'high', 'medium', 'low', 'info'].map(sev => (
              <button
                key={sev}
                onClick={() => setSeverityFilter(sev)}
                style={{
                  background: severityFilter === sev ? (sev === 'all' ? '#21262d' : `${SEVERITY_COLORS[sev]}22`) : 'transparent',
                  color: sev === 'all' ? '#e2e8f0' : SEVERITY_COLORS[sev],
                  border: `1px solid ${severityFilter === sev ? (sev === 'all' ? '#30363d' : SEVERITY_COLORS[sev]) : '#30363d'}`,
                  borderRadius: 4, padding: '3px 10px', fontSize: 11, fontWeight: 600,
                  cursor: 'pointer', textTransform: 'capitalize',
                }}
              >
                {sev}
              </button>
            ))}
          </div>
        </div>

        {sorted.length === 0 ? (
          <p style={{ color: '#718096', fontSize: 13 }}>No findings match the current filter.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #30363d' }}>
                  <th
                    style={{ padding: '6px 10px', textAlign: 'left', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('severity')}
                  >
                    Severity{sortIndicator('severity')}
                  </th>
                  <th
                    style={{ padding: '6px 10px', textAlign: 'left', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('agent')}
                  >
                    Agent{sortIndicator('agent')}
                  </th>
                  <th
                    style={{ padding: '6px 10px', textAlign: 'left', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('title')}
                  >
                    Title{sortIndicator('title')}
                  </th>
                  <th style={{ padding: '6px 10px', textAlign: 'left', fontSize: 11, color: '#8b949e', fontWeight: 600 }}>
                    Description
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((f, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #21262d' }}>
                    <td style={{ padding: '8px 10px' }}>
                      <span style={{
                        display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 4,
                        background: `${SEVERITY_COLORS[f.severity] || '#8b949e'}22`,
                        color: SEVERITY_COLORS[f.severity] || '#8b949e',
                        textTransform: 'uppercase',
                      }}>
                        {f.severity}
                      </span>
                    </td>
                    <td style={{ padding: '8px 10px', color: AGENT_COLORS[f.agent] || '#e2e8f0', textTransform: 'capitalize', fontWeight: 600 }}>
                      {f.agent}
                    </td>
                    <td style={{ padding: '8px 10px', color: '#e2e8f0', fontWeight: 500 }}>
                      {f.title}
                    </td>
                    <td style={{ padding: '8px 10px', color: '#8b949e', fontSize: 12 }}>
                      {f.description}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AuditView;
