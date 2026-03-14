import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import TrainingProgressBar from './TrainingProgressBar';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface CompletedModel {
  strategy: string;
  pair: string;
  exchange: string;
  val_loss: number;
}

interface InProgressModel {
  strategy: string;
  pair: string;
  exchange: string;
  epoch: number;
  total_epochs: number;
  val_loss: number;
}

interface SkippedModel {
  strategy: string;
  pair: string;
  exchange: string;
  reason: string;
}

interface TrainingStatus {
  completed: CompletedModel[];
  in_progress: InProgressModel | null;
  skipped: SkippedModel[];
  total_completed: number;
  total_skipped: number;
}

interface HistoryEntry {
  run_id: string;
  strategy: string;
  pair: string;
  exchange: string;
  val_loss: number;
  epochs: number;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: 16,
};

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 12px',
  fontSize: 12,
  color: '#8b949e',
  borderBottom: '1px solid #30363d',
  cursor: 'pointer',
  userSelect: 'none',
};

const tdStyle: React.CSSProperties = {
  padding: '8px 12px',
  fontSize: 13,
  color: '#e2e8f0',
  borderBottom: '1px solid #21262d',
};

const STRATEGY_COLORS: Record<string, string> = {
  momentum: '#58a6ff',
  mean_reversion: '#d29922',
  trend_following: '#3fb950',
  breakout: '#bc8cff',
  rsi_divergence: '#f85149',
  volatility: '#f0883e',
};

const colorFor = (s: string) => STRATEGY_COLORS[s] || '#8b949e';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const API_BASE = 'http://localhost:8420';

type SortKey = 'strategy' | 'pair' | 'exchange' | 'val_loss';
type SortDir = 'asc' | 'desc';

const TrainingView: React.FC = () => {
  const [status, setStatus] = useState<TrainingStatus | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('val_loss');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const fetchData = useCallback(async () => {
    try {
      const [sRes, hRes] = await Promise.all([
        fetch(`${API_BASE}/api/training/status`),
        fetch(`${API_BASE}/api/training/history`),
      ]);
      if (sRes.ok) setStatus(await sRes.json());
      if (hRes.ok) setHistory(await hRes.json());
      setError(null);
    } catch {
      setError('Cannot reach training API');
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 10_000);
    return () => clearInterval(id);
  }, [fetchData]);

  // Sort helpers
  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'val_loss' ? 'asc' : 'asc');
    }
  };

  const sortedCompleted = useMemo(() => {
    if (!status) return [];
    return [...status.completed].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp = typeof av === 'number' ? (av as number) - (bv as number) : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [status, sortKey, sortDir]);

  // Chart data
  const chartData = useMemo(() => {
    return history.map((h, i) => ({
      index: i + 1,
      val_loss: h.val_loss,
      strategy: h.strategy,
      label: `${h.strategy} ${h.pair}`,
    }));
  }, [history]);

  // Summary stats
  const totalTarget = status
    ? status.total_completed + status.total_skipped + (status.in_progress ? 1 : 0)
    : 0;
  const bestLoss = status && status.completed.length > 0
    ? Math.min(...status.completed.map(c => c.val_loss))
    : null;
  const avgLoss = status && status.completed.length > 0
    ? status.completed.reduce((s, c) => s + c.val_loss, 0) / status.completed.length
    : null;
  const pct = totalTarget > 0 ? (status!.total_completed / totalTarget) * 100 : 0;

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' \u25B2' : ' \u25BC') : '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Error banner */}
      {error && (
        <div style={{ ...card, borderColor: '#f8514966', color: '#f85149', fontSize: 13 }}>
          {error} &mdash; showing cached data
        </div>
      )}

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {[
          { label: 'Total Completed', value: status?.total_completed ?? '--' },
          { label: 'Total Skipped', value: status?.total_skipped ?? '--' },
          { label: 'Best Val Loss', value: bestLoss != null ? bestLoss.toFixed(6) : '--' },
          { label: 'Avg Val Loss', value: avgLoss != null ? avgLoss.toFixed(6) : '--' },
        ].map((c, i) => (
          <div key={i} style={{ ...card, textAlign: 'center' }}>
            <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {c.label}
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#e2e8f0' }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Overall progress bar */}
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#8b949e', marginBottom: 6 }}>
          <span>Overall Progress</span>
          <span>{status?.total_completed ?? 0} / {totalTarget} models</span>
        </div>
        <div style={{ height: 8, background: '#21262d', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${pct}%`,
            background: 'linear-gradient(90deg, #238636, #3fb950)',
            borderRadius: 4,
            transition: 'width 0.5s ease',
          }} />
        </div>
      </div>

      {/* Current training */}
      {status?.in_progress && (
        <TrainingProgressBar
          strategy={status.in_progress.strategy}
          pair={status.in_progress.pair}
          exchange={status.in_progress.exchange}
          currentEpoch={status.in_progress.epoch}
          totalEpochs={status.in_progress.total_epochs}
          isActive
        />
      )}

      {/* Val loss chart */}
      {chartData.length > 0 && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#e2e8f0' }}>Val Loss Over Training Runs</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData}>
              <XAxis dataKey="index" tick={{ fill: '#8b949e', fontSize: 11 }} />
              <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: '#8b949e' }}
                itemStyle={{ color: '#e2e8f0' }}
                formatter={(value: any) => [Number(value).toFixed(6), 'Val Loss']}
                labelFormatter={(l: any) => `Run #${l}`}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {Object.keys(STRATEGY_COLORS).map(strat => {
                const hasData = chartData.some(d => d.strategy === strat);
                if (!hasData) return null;
                return (
                  <Line
                    key={strat}
                    type="monotone"
                    dataKey="val_loss"
                    data={chartData.filter(d => d.strategy === strat)}
                    name={strat}
                    stroke={STRATEGY_COLORS[strat]}
                    dot={{ r: 3 }}
                    strokeWidth={2}
                    connectNulls={false}
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Completed models table */}
      {sortedCompleted.length > 0 && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#e2e8f0' }}>
            Completed Models ({sortedCompleted.length})
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#21262d' }}>
                  <th style={thStyle} onClick={() => handleSort('strategy')}>Strategy{arrow('strategy')}</th>
                  <th style={thStyle} onClick={() => handleSort('pair')}>Pair{arrow('pair')}</th>
                  <th style={thStyle} onClick={() => handleSort('exchange')}>Exchange{arrow('exchange')}</th>
                  <th style={{ ...thStyle, textAlign: 'right' }} onClick={() => handleSort('val_loss')}>Val Loss{arrow('val_loss')}</th>
                </tr>
              </thead>
              <tbody>
                {sortedCompleted.map((m, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? 'transparent' : '#0d111705' }}>
                    <td style={tdStyle}>
                      <span style={{ color: colorFor(m.strategy) }}>{m.strategy}</span>
                    </td>
                    <td style={tdStyle}>{m.pair}</td>
                    <td style={tdStyle}>{m.exchange}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>{m.val_loss.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Skipped models */}
      {status && status.skipped.length > 0 && (
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#d29922' }}>
            Skipped Models ({status.skipped.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {status.skipped.map((s, i) => (
              <div key={i} style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '6px 10px',
                background: '#21262d',
                borderRadius: 4,
                fontSize: 13,
              }}>
                <span style={{ color: '#e2e8f0' }}>
                  {s.strategy} &middot; {s.pair} &middot; {s.exchange}
                </span>
                <span style={{ color: '#8b949e', fontSize: 12 }}>{s.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default TrainingView;
