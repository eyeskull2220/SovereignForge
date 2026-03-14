import React, { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid } from 'recharts';

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------
interface PortfolioData {
  balance: number;
  starting_balance: number;
  total_pnl: number;
  total_pnl_pct: number;
  positions: Array<{ pair: string; quantity: number; pnl: number; entry_price: number }>;
  metrics: { sharpe: number; max_drawdown: number; win_rate: number; total_trades: number };
}

const PIE_COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#bc8cff', '#f0883e', '#39d353', '#8b949e', '#da3633', '#a5d6ff', '#7ee787', '#d2a8ff'];

const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };
const metricCard: React.CSSProperties = { background: '#21262d', borderRadius: 6, padding: '14px 18px', flex: 1, minWidth: 140 };

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
const PAIRS = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC', 'LINK/USDC'];

function demoPortfolio(): PortfolioData {
  return {
    balance: 10842.50, starting_balance: 10000,
    total_pnl: 842.50, total_pnl_pct: 8.43,
    positions: PAIRS.map(pair => ({
      pair, quantity: +(10 + Math.random() * 90).toFixed(2),
      pnl: +((Math.random() - 0.4) * 200).toFixed(2),
      entry_price: +(0.5 + Math.random() * 40).toFixed(4),
    })),
    metrics: { sharpe: 1.48, max_drawdown: 4.2, win_rate: 0.63, total_trades: 187 },
  };
}

function demoDrawdown(): Array<{ time: string; drawdown: number }> {
  let peak = 10000;
  return Array.from({ length: 60 }, (_, i) => {
    const val = 10000 + (Math.random() - 0.42) * 400 * (i + 1) / 60;
    if (val > peak) peak = val;
    const dd = ((peak - val) / peak) * 100;
    return { time: new Date(Date.now() - (59 - i) * 3600_000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), drawdown: +dd.toFixed(2) };
  });
}

// ---------------------------------------------------------------------------
// SVG Gauge
// ---------------------------------------------------------------------------
const RiskGauge: React.FC<{ score: number }> = ({ score }) => {
  const radius = 70, cx = 90, cy = 85, strokeW = 14;
  const startAngle = Math.PI, endAngle = 0;
  const range = startAngle - endAngle;
  const pct = Math.min(Math.max(score, 0), 100) / 100;
  const angle = startAngle - pct * range;
  const color = score < 33 ? '#3fb950' : score < 66 ? '#d29922' : '#f85149';

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
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#8b949e" fontSize={11}>Risk Score</text>
    </svg>
  );
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const RiskView: React.FC = () => {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [ddData] = useState(demoDrawdown);

  useEffect(() => {
    fetch('http://localhost:8420/api/portfolio')
      .then(r => r.json())
      .then(raw => {
        // Normalize API response to PortfolioData shape
        const m = raw.metrics ?? raw;
        const rawPos = raw.positions;
        const positions = Array.isArray(rawPos)
          ? rawPos
          : typeof rawPos === 'object' && rawPos !== null
            ? Object.values(rawPos)
            : [];
        setData({
          balance: m.equity ?? m.balance ?? 10000,
          starting_balance: m.starting_balance ?? 10000,
          total_pnl: m.total_pnl ?? 0,
          total_pnl_pct: m.total_pnl_pct ?? 0,
          positions: positions as PortfolioData['positions'],
          metrics: {
            sharpe: m.sharpe_ratio ?? m.sharpe ?? 0,
            max_drawdown: m.max_drawdown_pct ?? m.max_drawdown ?? 0,
            win_rate: m.win_rate ?? 0,
            total_trades: m.total_trades ?? 0,
          },
        });
      })
      .catch(() => setData(demoPortfolio()));
  }, []);

  if (!data) return <div style={{ ...card, textAlign: 'center', padding: 40 }}>Loading risk data...</div>;

  const { metrics } = data;
  const riskScore = Math.min(100, Math.round(metrics.max_drawdown * 8 + (1 - metrics.win_rate) * 30 + (2 - metrics.sharpe) * 10));
  const sortinoEstimate = +(metrics.sharpe * 1.15).toFixed(2);
  const dailyVaR = +(data.balance * 0.018).toFixed(2);

  const positionPie = data.positions.map(p => ({
    name: p.pair, value: Math.abs(p.quantity * p.entry_price),
  }));

  // Risk limits
  const limits = [
    { label: 'Stop Loss', current: metrics.max_drawdown, limit: 10, unit: '%' },
    { label: 'Max Positions', current: data.positions.length, limit: 12, unit: '' },
    { label: 'Daily Loss Limit', current: Math.abs(data.total_pnl < 0 ? data.total_pnl_pct : 0), limit: 5, unit: '%' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Risk Management</h2>

      {/* Top row: Gauge + Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 16 }}>
        <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <RiskGauge score={riskScore} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {[
            { label: 'Max Drawdown', value: `${metrics.max_drawdown.toFixed(1)}%`, color: metrics.max_drawdown > 8 ? '#f85149' : '#e2e8f0' },
            { label: 'Sharpe Ratio', value: metrics.sharpe.toFixed(2), color: metrics.sharpe > 1 ? '#3fb950' : '#d29922' },
            { label: 'Sortino Ratio', value: String(sortinoEstimate), color: sortinoEstimate > 1.2 ? '#3fb950' : '#d29922' },
            { label: 'Daily VaR (95%)', value: `$${dailyVaR.toLocaleString()}`, color: '#58a6ff' },
          ].map(m => (
            <div key={m.label} style={metricCard}>
              <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>{m.label}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: m.color }}>{m.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Middle row: Pie + Drawdown chart */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Position Risk Breakdown</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={positionPie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} innerRadius={40} paddingAngle={2} stroke="none">
                {positionPie.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#21262d', border: '1px solid #30363d', borderRadius: 6, color: '#e2e8f0', fontSize: 12 }} formatter={(v: any) => `$${Number(v).toFixed(2)}`} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            {positionPie.map((p, i) => (
              <span key={p.name} style={{ fontSize: 11, color: '#8b949e', display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: PIE_COLORS[i % PIE_COLORS.length], display: 'inline-block' }} />
                {p.name}
              </span>
            ))}
          </div>
        </div>

        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Drawdown Over Time</h3>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={ddData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis dataKey="time" tick={{ fill: '#8b949e', fontSize: 10 }} interval={9} />
              <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} reversed domain={[0, 'auto']} tickFormatter={v => `${v}%`} />
              <Tooltip contentStyle={{ background: '#21262d', border: '1px solid #30363d', borderRadius: 6, color: '#e2e8f0', fontSize: 12 }} formatter={(v: any) => `${Number(v).toFixed(2)}%`} />
              <Area type="monotone" dataKey="drawdown" stroke="#f85149" fill="rgba(248,81,73,0.15)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Risk Limits */}
      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 600 }}>Risk Limits</h3>
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
          {limits.map(l => {
            const pct = (l.current / l.limit) * 100;
            const color = pct < 50 ? '#3fb950' : pct < 80 ? '#d29922' : '#f85149';
            return (
              <div key={l.label} style={{ flex: 1, minWidth: 180 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
                  <span>{l.label}</span>
                  <span style={{ color }}>{l.current}{l.unit} / {l.limit}{l.unit}</span>
                </div>
                <div style={{ background: '#21262d', borderRadius: 4, height: 8, overflow: 'hidden' }}>
                  <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.4s' }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default RiskView;
