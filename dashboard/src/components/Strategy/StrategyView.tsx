import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------
interface StrategyStats {
  name: string;
  winRate: number;
  avgPnl: number;
  totalTrades: number;
  bestPair: string;
  valLossRange: string;
  color: string;
  sparkline: number[];
}

interface WeightEntry { name: string; weight: number; color: string }

const COLORS: Record<string, string> = {
  arbitrage: '#58a6ff',
  fibonacci: '#3fb950',
  grid: '#d29922',
  dca: '#bc8cff',
};

const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };
const PAIRS = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC'];

// ---------------------------------------------------------------------------
// Demo data generators
// ---------------------------------------------------------------------------
function demoStrategies(): StrategyStats[] {
  return [
    { name: 'arbitrage', winRate: 72.4, avgPnl: 12.80, totalTrades: 84, bestPair: 'BTC/USDC', valLossRange: '0.0021-0.0034', color: COLORS.arbitrage, sparkline: Array.from({ length: 20 }, () => (Math.random() - 0.35) * 20) },
    { name: 'fibonacci', winRate: 61.3, avgPnl: 8.42, totalTrades: 52, bestPair: 'ETH/USDC', valLossRange: '0.0045-0.0062', color: COLORS.fibonacci, sparkline: Array.from({ length: 20 }, () => (Math.random() - 0.4) * 15) },
    { name: 'grid', winRate: 58.9, avgPnl: 5.15, totalTrades: 67, bestPair: 'XRP/USDC', valLossRange: '0.0038-0.0055', color: COLORS.grid, sparkline: Array.from({ length: 20 }, () => (Math.random() - 0.42) * 12) },
    { name: 'dca', winRate: 66.7, avgPnl: 9.73, totalTrades: 42, bestPair: 'HBAR/USDC', valLossRange: '0.0029-0.0041', color: COLORS.dca, sparkline: Array.from({ length: 20 }, () => (Math.random() - 0.38) * 18) },
  ];
}

function demoWeights(): WeightEntry[] {
  return [
    { name: 'arbitrage', weight: 0.4, color: COLORS.arbitrage },
    { name: 'fibonacci', weight: 0.2, color: COLORS.fibonacci },
    { name: 'grid', weight: 0.2, color: COLORS.grid },
    { name: 'dca', weight: 0.2, color: COLORS.dca },
  ];
}

function demoEquityCurve(): Array<Record<string, number | string>> {
  const data: Array<Record<string, number | string>> = [];
  const cum: Record<string, number> = { arbitrage: 0, fibonacci: 0, grid: 0, dca: 0 };
  for (let i = 0; i < 30; i++) {
    const point: Record<string, number | string> = { day: `D${i + 1}` };
    for (const s of Object.keys(cum)) {
      cum[s] += (Math.random() - 0.42) * 25;
      point[s] = +cum[s].toFixed(2);
    }
    data.push(point);
  }
  return data;
}

function demoBestPairs(): Array<{ strategy: string; pair: string; trades: number; winRate: number; avgPnl: number }> {
  return ['arbitrage', 'fibonacci', 'grid', 'dca'].flatMap(strategy =>
    PAIRS.slice(0, 3).map(pair => ({
      strategy, pair,
      trades: 5 + Math.floor(Math.random() * 30),
      winRate: +(45 + Math.random() * 35).toFixed(1),
      avgPnl: +((Math.random() - 0.35) * 20).toFixed(2),
    }))
  );
}

function demoCorrelation(): { strategies: string[]; matrix: number[][] } {
  const strategies = ['arbitrage', 'fibonacci', 'grid', 'dca'];
  const matrix = strategies.map((_, i) =>
    strategies.map((_, j) => {
      if (i === j) return 1.0;
      return +((Math.random() - 0.3) * 0.8).toFixed(2);
    })
  );
  // symmetry
  for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) matrix[j][i] = matrix[i][j];
  return { strategies, matrix };
}

// ---------------------------------------------------------------------------
// Sparkline
// ---------------------------------------------------------------------------
const Sparkline: React.FC<{ data: number[]; color: string; width?: number; height?: number }> = ({ data, color, width = 120, height = 32 }) => {
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`).join(' ');
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const StrategyView: React.FC = () => {
  const [strategies, setStrategies] = useState<StrategyStats[]>(demoStrategies);
  const [weights, setWeights] = useState(demoWeights);
  const [equity, setEquity] = useState(demoEquityCurve);
  const [bestPairs, setBestPairs] = useState(demoBestPairs);
  const [corr, setCorr] = useState(demoCorrelation);

  useEffect(() => {
    // Fetch strategy performance from API
    fetch('http://localhost:8420/api/strategy/performance')
      .then(r => r.json())
      .then(d => {
        if (d.strategies && Array.isArray(d.strategies)) {
          setStrategies(d.strategies.map((s: any) => ({
            name: s.name,
            winRate: s.win_rate ?? s.winRate ?? 0,
            avgPnl: s.avg_pnl ?? s.avgPnl ?? 0,
            totalTrades: s.total_trades ?? s.totalTrades ?? 0,
            bestPair: s.best_pair ?? s.bestPair ?? '--',
            valLossRange: s.val_loss_range ?? s.valLossRange ?? '--',
            color: COLORS[s.name] || '#8b949e',
            sparkline: s.sparkline ?? Array.from({ length: 20 }, () => 0),
          })));
        }
        if (d.equity_curve) setEquity(d.equity_curve);
        if (d.best_pairs) setBestPairs(d.best_pairs);
        if (d.correlation) setCorr(d.correlation);
      })
      .catch(() => {}); // keep demo data on failure

    // Fetch weights from config
    fetch('http://localhost:8420/api/config')
      .then(r => r.json())
      .then(cfg => {
        if (cfg.strategy_weights || cfg.strategies) {
          const sw = cfg.strategy_weights || cfg.strategies;
          const entries: WeightEntry[] = Object.entries(sw).map(([name, w]) => ({
            name, weight: w as number, color: COLORS[name] || '#8b949e',
          }));
          if (entries.length) setWeights(entries);
        }
      })
      .catch(() => {});
  }, []);

  const fmt = (n: number, d = 2) => n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Strategy Analytics</h2>

      {/* Strategy cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        {strategies.map(s => (
          <div key={s.name} style={{ ...card, borderLeft: `3px solid ${s.color}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <span style={{ fontSize: 15, fontWeight: 700, textTransform: 'capitalize' }}>{s.name}</span>
              <span style={{ fontSize: 11, color: '#8b949e' }}>{s.totalTrades} trades</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13, marginBottom: 10 }}>
              <div><span style={{ color: '#8b949e' }}>Win Rate </span><span style={{ color: s.winRate >= 60 ? '#3fb950' : '#d29922', fontWeight: 600 }}>{fmt(s.winRate, 1)}%</span></div>
              <div><span style={{ color: '#8b949e' }}>Avg P&L </span><span style={{ color: s.avgPnl >= 0 ? '#3fb950' : '#f85149', fontWeight: 600 }}>${fmt(s.avgPnl)}</span></div>
              <div><span style={{ color: '#8b949e' }}>Best </span><span style={{ color: '#58a6ff' }}>{s.bestPair}</span></div>
              <div><span style={{ color: '#8b949e' }}>Val Loss </span><span>{s.valLossRange}</span></div>
            </div>
            <Sparkline data={s.sparkline} color={s.color} />
          </div>
        ))}
      </div>

      {/* Weights bar + Equity curve */}
      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 16 }}>
        <div style={card}>
          <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 600 }}>Strategy Weights</h3>
          {weights.map(w => (
            <div key={w.name} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                <span style={{ textTransform: 'capitalize' }}>{w.name}</span>
                <span style={{ color: w.color, fontWeight: 600 }}>{(w.weight * 100).toFixed(0)}%</span>
              </div>
              <div style={{ background: '#21262d', borderRadius: 4, height: 8, overflow: 'hidden' }}>
                <div style={{ width: `${w.weight * 100}%`, height: '100%', background: w.color, borderRadius: 4 }} />
              </div>
            </div>
          ))}
        </div>

        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Equity Curve by Strategy</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={equity}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis dataKey="day" tick={{ fill: '#8b949e', fontSize: 10 }} interval={4} />
              <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} tickFormatter={v => `$${v}`} />
              <Tooltip contentStyle={{ background: '#21262d', border: '1px solid #30363d', borderRadius: 6, color: '#e2e8f0', fontSize: 12 }} formatter={(v: any) => `$${Number(v).toFixed(2)}`} />
              {Object.entries(COLORS).map(([key, color]) => (
                <Line key={key} type="monotone" dataKey={key} stroke={color} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Best pair per strategy + Correlation */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Best Performing Pair per Strategy</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {['Strategy', 'Pair', 'Trades', 'Win Rate', 'Avg P&L'].map(h => (
                    <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontSize: 11, color: '#8b949e', fontWeight: 600, borderBottom: '1px solid #30363d' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {['arbitrage', 'fibonacci', 'grid', 'dca'].map(strat => {
                  const rows = bestPairs.filter(r => r.strategy === strat).sort((a, b) => b.avgPnl - a.avgPnl);
                  const best = rows[0];
                  if (!best) return null;
                  return (
                    <tr key={strat} style={{ background: '#21262d' }}>
                      <td style={{ padding: '7px 10px', fontSize: 13, borderBottom: '1px solid #161b22', textTransform: 'capitalize', color: COLORS[strat] }}>{strat}</td>
                      <td style={{ padding: '7px 10px', fontSize: 13, borderBottom: '1px solid #161b22', fontWeight: 600 }}>{best.pair}</td>
                      <td style={{ padding: '7px 10px', fontSize: 13, borderBottom: '1px solid #161b22' }}>{best.trades}</td>
                      <td style={{ padding: '7px 10px', fontSize: 13, borderBottom: '1px solid #161b22', color: best.winRate >= 55 ? '#3fb950' : '#d29922' }}>{best.winRate}%</td>
                      <td style={{ padding: '7px 10px', fontSize: 13, borderBottom: '1px solid #161b22', color: best.avgPnl >= 0 ? '#3fb950' : '#f85149', fontWeight: 600 }}>${fmt(best.avgPnl)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Strategy Correlation Matrix</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ padding: 6, fontSize: 11, color: '#8b949e' }} />
                {corr.strategies.map(s => (
                  <th key={s} style={{ padding: 6, fontSize: 11, color: COLORS[s] || '#8b949e', textTransform: 'capitalize', fontWeight: 600 }}>{s.slice(0, 4)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {corr.strategies.map((rowS, i) => (
                <tr key={rowS}>
                  <td style={{ padding: 6, fontSize: 12, color: COLORS[rowS] || '#8b949e', textTransform: 'capitalize', fontWeight: 600 }}>{rowS.slice(0, 4)}</td>
                  {corr.matrix[i].map((val, j) => {
                    const abs = Math.abs(val);
                    const bg = i === j ? 'rgba(88,166,255,0.15)' : abs > 0.5 ? 'rgba(248,81,73,0.1)' : abs > 0.25 ? 'rgba(210,169,34,0.08)' : 'transparent';
                    return (
                      <td key={j} style={{ padding: 6, fontSize: 13, textAlign: 'center', fontWeight: i === j ? 700 : 400, color: i === j ? '#58a6ff' : val >= 0 ? '#3fb950' : '#f85149', background: bg, borderRadius: 4 }}>
                        {val.toFixed(2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11, color: '#8b949e', marginTop: 10, marginBottom: 0 }}>Lower correlation between strategies means better diversification.</p>
        </div>
      </div>
    </div>
  );
};

export default StrategyView;
