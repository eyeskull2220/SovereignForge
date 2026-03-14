import React, { useState, useEffect } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface TechnicalSignal {
  pair: string;
  rsi: number;
  bb_position: string;    // 'upper' | 'middle' | 'lower'
  macd: number;
  macd_signal: number;
  signal: 'buy' | 'sell' | 'hold';
}

interface StrategyWeight {
  name: string;
  current: number;
  recommended: number;
  reason: string;
}

interface ResearchData {
  fear_greed_index: number;
  fear_greed_label: string;
  market_sentiment: string;
  technical_signals: TechnicalSignal[];
  strategy_weights: StrategyWeight[];
  last_updated?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const SIGNAL_COLORS: Record<string, string> = {
  buy: '#3fb950',
  sell: '#f85149',
  hold: '#d29922',
};

const STRATEGY_COLORS: Record<string, string> = {
  arbitrage: '#58a6ff',
  fibonacci: '#3fb950',
  grid: '#d29922',
  dca: '#bc8cff',
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };
const metricCard: React.CSSProperties = { background: '#21262d', borderRadius: 6, padding: '14px 18px', flex: 1, minWidth: 140 };

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
const PAIRS = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC', 'LINK/USDC'];

function demoResearch(): ResearchData {
  const signals: TechnicalSignal[] = PAIRS.map(pair => {
    const rsi = Math.round(25 + Math.random() * 50);
    const macd = +((Math.random() - 0.5) * 2).toFixed(4);
    const macd_signal = +((Math.random() - 0.5) * 1.5).toFixed(4);
    const bbs = ['upper', 'middle', 'lower'] as const;
    const bb_position = bbs[Math.floor(Math.random() * 3)];
    let signal: 'buy' | 'sell' | 'hold' = 'hold';
    if (rsi < 35 && macd > macd_signal) signal = 'buy';
    else if (rsi > 65 && macd < macd_signal) signal = 'sell';
    return { pair, rsi, bb_position, macd, macd_signal, signal };
  });

  return {
    fear_greed_index: 42,
    fear_greed_label: 'Fear',
    market_sentiment: 'cautious',
    technical_signals: signals,
    strategy_weights: [
      { name: 'arbitrage', current: 0.4, recommended: 0.45, reason: 'Low correlation + high win rate' },
      { name: 'fibonacci', current: 0.2, recommended: 0.2, reason: 'Stable performance, maintain weight' },
      { name: 'grid', current: 0.2, recommended: 0.15, reason: 'Higher drawdown in volatile conditions' },
      { name: 'dca', current: 0.2, recommended: 0.2, reason: 'Consistent accumulation strategy' },
    ],
    last_updated: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Fear / Greed Gauge (semicircle)
// ---------------------------------------------------------------------------
const FearGreedGauge: React.FC<{ value: number; label: string }> = ({ value, label }) => {
  const radius = 70, cx = 90, cy = 85, strokeW = 14;
  const startAngle = Math.PI, endAngle = 0;
  const range = startAngle - endAngle;
  const pct = Math.min(Math.max(value, 0), 100) / 100;
  const angle = startAngle - pct * range;

  // Red (extreme fear) -> Yellow (neutral) -> Green (extreme greed)
  const color = value < 25 ? '#f85149' : value < 45 ? '#f0883e' : value < 55 ? '#d29922' : value < 75 ? '#3fb950' : '#238636';

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
      <text x={cx} y={cy - 5} textAnchor="middle" fill={color} fontSize={28} fontWeight={700}>{value}</text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#8b949e" fontSize={11}>{label}</text>
    </svg>
  );
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const ResearchView: React.FC = () => {
  const [data, setData] = useState<ResearchData | null>(null);
  const [sortField, setSortField] = useState<'pair' | 'rsi' | 'signal'>('pair');
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8420/api/agents/research')
      .then(r => r.json())
      .then(d => {
        setData({
          fear_greed_index: d.fear_greed_index ?? d.fear_greed ?? 50,
          fear_greed_label: d.fear_greed_label ?? d.label ?? 'Neutral',
          market_sentiment: d.market_sentiment ?? d.sentiment ?? 'neutral',
          technical_signals: d.technical_signals ?? d.signals ?? [],
          strategy_weights: d.strategy_weights ?? d.weights ?? [],
          last_updated: d.last_updated ?? d.timestamp ?? new Date().toISOString(),
        });
      })
      .catch(() => setData(demoResearch()));
  }, []);

  if (!data) {
    return <div style={{ ...card, textAlign: 'center', padding: 40, color: '#718096', fontSize: 14 }}>Loading research data...</div>;
  }

  // Sort signals
  const handleSort = (field: 'pair' | 'rsi' | 'signal') => {
    if (sortField === field) {
      setSortAsc(p => !p);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };
  const sortIndicator = (field: string) => sortField === field ? (sortAsc ? ' \u25B2' : ' \u25BC') : '';

  const SIGNAL_ORDER: Record<string, number> = { buy: 0, sell: 1, hold: 2 };
  const sortedSignals = [...data.technical_signals].sort((a, b) => {
    let cmp = 0;
    if (sortField === 'pair') cmp = a.pair.localeCompare(b.pair);
    else if (sortField === 'rsi') cmp = a.rsi - b.rsi;
    else cmp = (SIGNAL_ORDER[a.signal] ?? 9) - (SIGNAL_ORDER[b.signal] ?? 9);
    return sortAsc ? cmp : -cmp;
  });

  const buyCount = data.technical_signals.filter(s => s.signal === 'buy').length;
  const sellCount = data.technical_signals.filter(s => s.signal === 'sell').length;
  const holdCount = data.technical_signals.filter(s => s.signal === 'hold').length;

  const sentimentColor = data.market_sentiment === 'bullish' ? '#3fb950'
    : data.market_sentiment === 'bearish' ? '#f85149'
    : data.market_sentiment === 'cautious' ? '#d29922'
    : '#8b949e';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Research</h2>
        {data.last_updated && (
          <span style={{ fontSize: 12, color: '#8b949e' }}>
            Updated: {new Date(data.last_updated).toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Top row: Fear/Greed gauge + summary */}
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 16 }}>
        <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <FearGreedGauge value={data.fear_greed_index} label={data.fear_greed_label} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          <div style={metricCard}>
            <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>Sentiment</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: sentimentColor, textTransform: 'capitalize' }}>
              {data.market_sentiment}
            </div>
          </div>
          <div style={metricCard}>
            <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>Buy Signals</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#3fb950' }}>{buyCount}</div>
          </div>
          <div style={metricCard}>
            <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>Sell Signals</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#f85149' }}>{sellCount}</div>
          </div>
          <div style={metricCard}>
            <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>Hold Signals</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#d29922' }}>{holdCount}</div>
          </div>
        </div>
      </div>

      {/* Technical Signals Table */}
      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 600 }}>Technical Signals</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #30363d' }}>
                <th
                  style={{ padding: '6px 10px', textAlign: 'left', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                  onClick={() => handleSort('pair')}
                >
                  Pair{sortIndicator('pair')}
                </th>
                <th
                  style={{ padding: '6px 10px', textAlign: 'right', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                  onClick={() => handleSort('rsi')}
                >
                  RSI{sortIndicator('rsi')}
                </th>
                <th style={{ padding: '6px 10px', textAlign: 'center', fontSize: 11, color: '#8b949e', fontWeight: 600 }}>
                  BB Position
                </th>
                <th style={{ padding: '6px 10px', textAlign: 'right', fontSize: 11, color: '#8b949e', fontWeight: 600 }}>
                  MACD
                </th>
                <th style={{ padding: '6px 10px', textAlign: 'right', fontSize: 11, color: '#8b949e', fontWeight: 600 }}>
                  MACD Signal
                </th>
                <th
                  style={{ padding: '6px 10px', textAlign: 'center', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                  onClick={() => handleSort('signal')}
                >
                  Signal{sortIndicator('signal')}
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedSignals.map((sig, i) => {
                const rsiColor = sig.rsi < 30 ? '#3fb950' : sig.rsi > 70 ? '#f85149' : '#e2e8f0';
                const macdColor = sig.macd > sig.macd_signal ? '#3fb950' : '#f85149';
                const bbColor = sig.bb_position === 'lower' ? '#3fb950' : sig.bb_position === 'upper' ? '#f85149' : '#d29922';

                return (
                  <tr key={i} style={{ borderBottom: '1px solid #21262d' }}>
                    <td style={{ padding: '8px 10px', fontWeight: 600, color: '#e2e8f0' }}>{sig.pair}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right', color: rsiColor, fontWeight: 600 }}>{sig.rsi}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'center', textTransform: 'capitalize', color: bbColor }}>{sig.bb_position}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right', color: macdColor, fontFamily: 'monospace' }}>{sig.macd.toFixed(4)}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right', color: '#8b949e', fontFamily: 'monospace' }}>{sig.macd_signal.toFixed(4)}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                      <span style={{
                        display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 10px', borderRadius: 4,
                        background: `${SIGNAL_COLORS[sig.signal]}22`,
                        color: SIGNAL_COLORS[sig.signal],
                        textTransform: 'uppercase',
                      }}>
                        {sig.signal}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Strategy Weight Recommendations */}
      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 600 }}>Strategy Weight Recommendations</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {data.strategy_weights.map(sw => {
            const color = STRATEGY_COLORS[sw.name] || '#8b949e';
            const diff = sw.recommended - sw.current;
            const diffColor = diff > 0 ? '#3fb950' : diff < 0 ? '#f85149' : '#8b949e';
            const diffStr = diff > 0 ? `+${(diff * 100).toFixed(0)}%` : diff < 0 ? `${(diff * 100).toFixed(0)}%` : '0%';

            return (
              <div key={sw.name}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: 'inline-block' }} />
                    <span style={{ fontSize: 14, fontWeight: 600, textTransform: 'capitalize', color: '#e2e8f0' }}>{sw.name}</span>
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13 }}>
                    <span style={{ color: '#8b949e' }}>Current: <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{(sw.current * 100).toFixed(0)}%</span></span>
                    <span style={{ color: '#8b949e' }}>Recommended: <span style={{ color, fontWeight: 600 }}>{(sw.recommended * 100).toFixed(0)}%</span></span>
                    <span style={{
                      fontSize: 11, fontWeight: 600, padding: '2px 6px', borderRadius: 3,
                      background: `${diffColor}22`, color: diffColor,
                    }}>
                      {diffStr}
                    </span>
                  </span>
                </div>
                {/* Dual bar: current vs recommended */}
                <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ background: '#21262d', borderRadius: 4, height: 6, overflow: 'hidden' }}>
                      <div style={{ width: `${sw.current * 100}%`, height: '100%', background: '#8b949e', borderRadius: 4 }} />
                    </div>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ background: '#21262d', borderRadius: 4, height: 6, overflow: 'hidden' }}>
                      <div style={{ width: `${sw.recommended * 100}%`, height: '100%', background: color, borderRadius: 4 }} />
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <span style={{ flex: 1, fontSize: 10, color: '#8b949e' }}>Current</span>
                  <span style={{ flex: 1, fontSize: 10, color: '#8b949e' }}>Recommended</span>
                </div>
                <div style={{ fontSize: 12, color: '#8b949e', marginTop: 4, fontStyle: 'italic' }}>{sw.reason}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default ResearchView;
