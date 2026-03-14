import React, { useState, useEffect } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface CointegrationPair {
  pair_a: string;
  pair_b: string;
  correlation: number;
  p_value: number;
  half_life: number;
  z_score: number;
  signal: 'LONG A / SHORT B' | 'SHORT A / LONG B' | 'NEUTRAL';
}

interface CointegrationData {
  pairs: CointegrationPair[];
  total_pairs: number;
  active_signals: number;
  avg_half_life: number;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };
const metricCard: React.CSSProperties = { background: '#21262d', borderRadius: 6, padding: '14px 18px', flex: 1, minWidth: 140 };

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
function demoData(): CointegrationData {
  const pairs: CointegrationPair[] = [
    { pair_a: 'BTC/USDC', pair_b: 'ETH/USDC', correlation: 0.91, p_value: 0.003, half_life: 14.2, z_score: 2.34, signal: 'LONG A / SHORT B' },
    { pair_a: 'XRP/USDC', pair_b: 'XLM/USDC', correlation: 0.87, p_value: 0.012, half_life: 8.7, z_score: -1.72, signal: 'SHORT A / LONG B' },
    { pair_a: 'HBAR/USDC', pair_b: 'ALGO/USDC', correlation: 0.78, p_value: 0.028, half_life: 22.1, z_score: 0.45, signal: 'NEUTRAL' },
    { pair_a: 'ADA/USDC', pair_b: 'LINK/USDC', correlation: 0.83, p_value: 0.008, half_life: 11.5, z_score: -2.18, signal: 'SHORT A / LONG B' },
  ];

  const activeSignals = pairs.filter(p => p.signal !== 'NEUTRAL').length;
  const avgHalfLife = pairs.reduce((sum, p) => sum + p.half_life, 0) / pairs.length;

  return {
    pairs,
    total_pairs: pairs.length,
    active_signals: activeSignals,
    avg_half_life: +avgHalfLife.toFixed(1),
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function zScoreBg(z: number): string {
  const abs = Math.abs(z);
  if (abs > 2.0) return 'rgba(63,185,80,0.15)';
  if (abs >= 1.5) return 'rgba(210,169,34,0.15)';
  return 'transparent';
}

function zScoreColor(z: number): string {
  const abs = Math.abs(z);
  if (abs > 2.0) return '#3fb950';
  if (abs >= 1.5) return '#d29922';
  return '#e2e8f0';
}

function signalBadge(signal: string): { bg: string; color: string } {
  if (signal === 'LONG A / SHORT B') return { bg: 'rgba(63,185,80,0.15)', color: '#3fb950' };
  if (signal === 'SHORT A / LONG B') return { bg: 'rgba(248,81,73,0.15)', color: '#f85149' };
  return { bg: 'rgba(139,148,158,0.15)', color: '#8b949e' };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const CointegrationView: React.FC = () => {
  const [data, setData] = useState<CointegrationData | null>(null);
  const [sortField, setSortField] = useState<'pair_a' | 'correlation' | 'p_value' | 'half_life' | 'z_score'>('z_score');
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    fetch('http://localhost:8420/api/pipeline/cointegration')
      .then(r => r.json())
      .then(d => {
        const pairs: CointegrationPair[] = (d.pairs || d || []).map((p: any) => ({
          pair_a: p.pair_a ?? p.pairA ?? '--',
          pair_b: p.pair_b ?? p.pairB ?? '--',
          correlation: p.correlation ?? 0,
          p_value: p.p_value ?? p.pValue ?? 1,
          half_life: p.half_life ?? p.halfLife ?? 0,
          z_score: p.z_score ?? p.zScore ?? 0,
          signal: p.signal ?? 'NEUTRAL',
        }));
        const activeSignals = pairs.filter(p => p.signal !== 'NEUTRAL').length;
        const avgHalfLife = pairs.length > 0
          ? pairs.reduce((sum, p) => sum + p.half_life, 0) / pairs.length
          : 0;
        setData({
          pairs,
          total_pairs: d.total_pairs ?? pairs.length,
          active_signals: d.active_signals ?? activeSignals,
          avg_half_life: d.avg_half_life ?? +avgHalfLife.toFixed(1),
        });
      })
      .catch(() => setData(demoData()));
  }, []);

  if (!data) {
    return <div style={{ ...card, textAlign: 'center', padding: 40, color: '#718096', fontSize: 14 }}>Loading cointegration data...</div>;
  }

  // Sort pairs
  const sorted = [...data.pairs].sort((a, b) => {
    let cmp = 0;
    if (sortField === 'pair_a') {
      cmp = a.pair_a.localeCompare(b.pair_a);
    } else if (sortField === 'correlation') {
      cmp = a.correlation - b.correlation;
    } else if (sortField === 'p_value') {
      cmp = a.p_value - b.p_value;
    } else if (sortField === 'half_life') {
      cmp = a.half_life - b.half_life;
    } else {
      cmp = Math.abs(a.z_score) - Math.abs(b.z_score);
    }
    return sortAsc ? cmp : -cmp;
  });

  const handleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortAsc(p => !p);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const sortIndicator = (field: string) => sortField === field ? (sortAsc ? ' \u25B2' : ' \u25BC') : '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Cointegrated Pairs Monitor</h2>

      {/* Summary strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {[
          { label: 'Total Pairs', value: String(data.total_pairs), color: '#e2e8f0' },
          { label: 'Active Signals', value: String(data.active_signals), color: data.active_signals > 0 ? '#3fb950' : '#8b949e' },
          { label: 'Avg Half-Life', value: `${data.avg_half_life} bars`, color: '#58a6ff' },
        ].map(m => (
          <div key={m.label} style={metricCard}>
            <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>{m.label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: m.color }}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Main table */}
      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 600 }}>Pair Analysis</h3>

        {sorted.length === 0 ? (
          <p style={{ color: '#718096', fontSize: 13 }}>No cointegrated pairs found.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #30363d' }}>
                  <th
                    style={{ padding: '6px 10px', textAlign: 'left', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('pair_a')}
                  >
                    Pair A{sortIndicator('pair_a')}
                  </th>
                  <th style={{ padding: '6px 10px', textAlign: 'left', fontSize: 11, color: '#8b949e', fontWeight: 600 }}>
                    Pair B
                  </th>
                  <th
                    style={{ padding: '6px 10px', textAlign: 'right', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('correlation')}
                  >
                    Correlation{sortIndicator('correlation')}
                  </th>
                  <th
                    style={{ padding: '6px 10px', textAlign: 'right', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('p_value')}
                  >
                    P-Value{sortIndicator('p_value')}
                  </th>
                  <th
                    style={{ padding: '6px 10px', textAlign: 'right', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('half_life')}
                  >
                    Half-Life{sortIndicator('half_life')}
                  </th>
                  <th
                    style={{ padding: '6px 10px', textAlign: 'right', fontSize: 11, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none' }}
                    onClick={() => handleSort('z_score')}
                  >
                    Z-Score{sortIndicator('z_score')}
                  </th>
                  <th style={{ padding: '6px 10px', textAlign: 'center', fontSize: 11, color: '#8b949e', fontWeight: 600 }}>
                    Signal
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((p, i) => {
                  const badge = signalBadge(p.signal);
                  return (
                    <tr key={i} style={{ borderBottom: '1px solid #21262d' }}>
                      <td style={{ padding: '8px 10px', color: '#58a6ff', fontWeight: 600 }}>
                        {p.pair_a}
                      </td>
                      <td style={{ padding: '8px 10px', color: '#58a6ff', fontWeight: 600 }}>
                        {p.pair_b}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', color: '#e2e8f0' }}>
                        {p.correlation.toFixed(3)}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', color: p.p_value < 0.05 ? '#3fb950' : '#d29922' }}>
                        {p.p_value.toFixed(4)}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', color: '#e2e8f0' }}>
                        {p.half_life.toFixed(1)}
                      </td>
                      <td style={{
                        padding: '8px 10px',
                        textAlign: 'right',
                        fontWeight: 600,
                        color: zScoreColor(p.z_score),
                        background: zScoreBg(p.z_score),
                        borderRadius: 4,
                      }}>
                        {p.z_score.toFixed(2)}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                        <span style={{
                          display: 'inline-block',
                          fontSize: 11,
                          fontWeight: 600,
                          padding: '2px 8px',
                          borderRadius: 4,
                          background: badge.bg,
                          color: badge.color,
                          whiteSpace: 'nowrap',
                        }}>
                          {p.signal}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default CointegrationView;
