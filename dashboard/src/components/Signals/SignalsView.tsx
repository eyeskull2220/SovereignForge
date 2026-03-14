import React, { useState, useEffect, useCallback, useMemo } from 'react';

const API_BASE = 'http://localhost:8420';
const REFRESH_INTERVAL = 5000;

interface Signal {
  pair: string;
  exchange: string;
  strategy: string;
  signal: number;
  confidence: number;
  magnitude: number;
  timestamp: string;
}

interface MissedSignal {
  pair: string;
  exchange: string;
  signal: number;
  confidence: number;
  magnitude: number;
  reject_reason: string;
  timestamp: string;
  strategies?: Array<{ strategy: string; signal: number; confidence: number; magnitude: number }>;
}

type SortKey = 'signal' | 'confidence' | 'magnitude' | 'pair' | 'exchange';
type SortDir = 'asc' | 'desc';
type Tab = 'live' | 'missed';

const STRATEGIES = ['All', 'Arbitrage', 'Fibonacci', 'Grid', 'DCA'];

const REASON_LABELS: Record<string, { label: string; color: string }> = {
  weak_signal: { label: 'Weak Signal', color: '#8b949e' },
  low_confidence: { label: 'Low Confidence', color: '#d29922' },
  max_positions_reached: { label: 'Max Positions', color: '#f85149' },
  no_price_data: { label: 'No Price Data', color: '#f0883e' },
  position_too_small: { label: 'Too Small', color: '#8b949e' },
  daily_loss_limit: { label: 'Daily Loss Limit', color: '#f85149' },
};

const card: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: 16,
};

const signalColor = (val: number, confidence: number): string => {
  const base = val > 0 ? '63, 185, 80' : '248, 81, 73';
  const opacity = 0.3 + Math.abs(confidence) * 0.7;
  return `rgba(${base}, ${opacity})`;
};

const SignalsView: React.FC = () => {
  const [tab, setTab] = useState<Tab>('live');
  const [signals, setSignals] = useState<Signal[]>([]);
  const [missed, setMissed] = useState<MissedSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategyFilter, setStrategyFilter] = useState('All');
  const [exchangeFilter, setExchangeFilter] = useState('All');
  const [sortKey, setSortKey] = useState<SortKey>('signal');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const fetchSignals = useCallback(async () => {
    try {
      const [sigRes, missedRes] = await Promise.all([
        fetch(`${API_BASE}/api/signals`),
        fetch(`${API_BASE}/api/signals/missed`),
      ]);
      if (sigRes.ok) {
        const raw = await sigRes.json();
        setSignals(Array.isArray(raw) ? raw : (raw?.signals ?? []));
      }
      if (missedRes.ok) {
        const raw = await missedRes.json();
        setMissed(Array.isArray(raw) ? raw : (raw?.missed ?? []));
      }
      setError(null);
    } catch (e: any) {
      setError(e.message ?? 'Failed to fetch signals');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSignals();
    const id = setInterval(fetchSignals, REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, [fetchSignals]);

  const exchanges = useMemo(
    () => ['All', ...Array.from(new Set(signals.map(s => s.exchange))).sort()],
    [signals],
  );

  const filtered = useMemo(() => {
    let list = signals;
    if (strategyFilter !== 'All') {
      list = list.filter(s => s.strategy.toLowerCase() === strategyFilter.toLowerCase());
    }
    if (exchangeFilter !== 'All') {
      list = list.filter(s => s.exchange === exchangeFilter);
    }
    list = [...list].sort((a, b) => {
      const av = a[sortKey] as number | string;
      const bv = b[sortKey] as number | string;
      if (sortKey === 'signal') {
        return sortDir === 'desc'
          ? Math.abs(b.signal) - Math.abs(a.signal)
          : Math.abs(a.signal) - Math.abs(b.signal);
      }
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'desc' ? bv - av : av - bv;
      }
      return sortDir === 'desc'
        ? String(bv).localeCompare(String(av))
        : String(av).localeCompare(String(bv));
    });
    return list;
  }, [signals, strategyFilter, exchangeFilter, sortKey, sortDir]);

  const filteredMissed = useMemo(() => {
    let list = [...missed];
    if (exchangeFilter !== 'All') {
      list = list.filter(m => m.exchange === exchangeFilter);
    }
    list.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    return list;
  }, [missed, exchangeFilter]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => (d === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortDir === 'desc' ? ' \u25BC' : ' \u25B2') : '';

  const thStyle: React.CSSProperties = {
    padding: '10px 12px',
    textAlign: 'left',
    fontSize: 12,
    color: '#8b949e',
    fontWeight: 600,
    cursor: 'pointer',
    userSelect: 'none',
    borderBottom: '1px solid #30363d',
    whiteSpace: 'nowrap',
  };

  const tdStyle: React.CSSProperties = {
    padding: '10px 12px',
    fontSize: 13,
    borderBottom: '1px solid #21262d',
  };

  const tabBtn = (t: Tab, label: string, count: number) => (
    <button
      onClick={() => setTab(t)}
      style={{
        background: tab === t ? '#58a6ff' : '#21262d',
        color: tab === t ? '#0d1117' : '#8b949e',
        border: 'none',
        borderRadius: 6,
        padding: '6px 16px',
        fontSize: 13,
        fontWeight: 600,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}
    >
      {label}
      <span style={{
        background: tab === t ? 'rgba(0,0,0,0.2)' : '#30363d',
        borderRadius: 10,
        padding: '1px 7px',
        fontSize: 11,
      }}>{count}</span>
    </button>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Header with tabs */}
      <div style={{ ...card, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          {tabBtn('live', 'Live Signals', signals.length)}
          {tabBtn('missed', 'Missed Trades', missed.length)}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {tab === 'live' && STRATEGIES.map(s => (
            <button
              key={s}
              onClick={() => setStrategyFilter(s)}
              style={{
                background: strategyFilter === s ? '#58a6ff' : '#21262d',
                color: strategyFilter === s ? '#0d1117' : '#8b949e',
                border: 'none',
                borderRadius: 6,
                padding: '5px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {s}
            </button>
          ))}
          <select
            value={exchangeFilter}
            onChange={e => setExchangeFilter(e.target.value)}
            style={{
              background: '#21262d',
              color: '#e2e8f0',
              border: '1px solid #30363d',
              borderRadius: 6,
              padding: '5px 10px',
              fontSize: 12,
            }}
          >
            {exchanges.map(ex => (
              <option key={ex} value={ex}>{ex}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Content */}
      <div style={{ ...card, padding: 0, overflow: 'auto' }}>
        {loading ? (
          <p style={{ padding: 24, color: '#8b949e', textAlign: 'center' }}>Loading signals...</p>
        ) : error ? (
          <p style={{ padding: 24, color: '#f85149', textAlign: 'center' }}>Error: {error}</p>
        ) : tab === 'live' ? (
          /* Live Signals Table */
          filtered.length === 0 ? (
            <p style={{ padding: 24, color: '#484f58', textAlign: 'center', fontSize: 13 }}>
              No active signals — paper trading may not be running
            </p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle} onClick={() => handleSort('pair')}>Pair{arrow('pair')}</th>
                  <th style={thStyle} onClick={() => handleSort('exchange')}>Exchange{arrow('exchange')}</th>
                  <th style={thStyle}>Strategy</th>
                  <th style={thStyle} onClick={() => handleSort('signal')}>Signal{arrow('signal')}</th>
                  <th style={thStyle} onClick={() => handleSort('confidence')}>Confidence{arrow('confidence')}</th>
                  <th style={thStyle} onClick={() => handleSort('magnitude')}>Magnitude{arrow('magnitude')}</th>
                  <th style={{ ...thStyle, cursor: 'default' }}>Time</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s, i) => (
                  <tr key={`${s.pair}-${s.exchange}-${s.strategy}-${i}`} style={{ background: i % 2 === 0 ? '#0d1117' : '#161b22' }}>
                    <td style={{ ...tdStyle, fontWeight: 600, color: '#e2e8f0' }}>{s.pair}</td>
                    <td style={tdStyle}>{s.exchange}</td>
                    <td style={{ ...tdStyle, color: '#58a6ff', textTransform: 'capitalize' }}>{s.strategy}</td>
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{
                          width: 60, height: 8, background: '#21262d', borderRadius: 4,
                          overflow: 'hidden', position: 'relative',
                        }}>
                          <div style={{
                            position: 'absolute', top: 0,
                            left: s.signal >= 0 ? '50%' : `${50 + s.signal * 50}%`,
                            width: `${Math.abs(s.signal) * 50}%`, height: '100%',
                            background: signalColor(s.signal, s.confidence), borderRadius: 4,
                          }} />
                        </div>
                        <span style={{ color: s.signal > 0 ? '#3fb950' : s.signal < 0 ? '#f85149' : '#8b949e', fontWeight: 600, fontSize: 12, minWidth: 44 }}>
                          {s.signal > 0 ? '+' : ''}{s.signal.toFixed(3)}
                        </span>
                      </div>
                    </td>
                    <td style={tdStyle}>
                      <span style={{ color: '#e2e8f0' }}>{(s.confidence * 100).toFixed(1)}%</span>
                    </td>
                    <td style={tdStyle}>{s.magnitude.toFixed(4)}</td>
                    <td style={{ ...tdStyle, color: '#8b949e', fontSize: 12 }}>
                      {new Date(s.timestamp).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : (
          /* Missed Trades Table */
          filteredMissed.length === 0 ? (
            <p style={{ padding: 24, color: '#484f58', textAlign: 'center', fontSize: 13 }}>
              No missed trades recorded yet — signals below threshold or blocked by risk limits will appear here
            </p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ ...thStyle, cursor: 'default' }}>Pair</th>
                  <th style={{ ...thStyle, cursor: 'default' }}>Exchange</th>
                  <th style={{ ...thStyle, cursor: 'default' }}>Signal</th>
                  <th style={{ ...thStyle, cursor: 'default' }}>Confidence</th>
                  <th style={{ ...thStyle, cursor: 'default' }}>Magnitude</th>
                  <th style={{ ...thStyle, cursor: 'default' }}>Reject Reason</th>
                  <th style={{ ...thStyle, cursor: 'default' }}>Time</th>
                </tr>
              </thead>
              <tbody>
                {filteredMissed.map((m, i) => {
                  const reason = REASON_LABELS[m.reject_reason] ?? { label: m.reject_reason, color: '#8b949e' };
                  return (
                    <tr key={`missed-${i}`} style={{ background: i % 2 === 0 ? '#0d1117' : '#161b22' }}>
                      <td style={{ ...tdStyle, fontWeight: 600, color: '#e2e8f0' }}>{m.pair}</td>
                      <td style={tdStyle}>{m.exchange}</td>
                      <td style={tdStyle}>
                        <span style={{ color: m.signal > 0 ? '#3fb950' : m.signal < 0 ? '#f85149' : '#8b949e', fontWeight: 600, fontSize: 12 }}>
                          {m.signal > 0 ? '+' : ''}{m.signal.toFixed(3)}
                        </span>
                      </td>
                      <td style={tdStyle}>{(m.confidence * 100).toFixed(1)}%</td>
                      <td style={tdStyle}>{m.magnitude.toFixed(4)}</td>
                      <td style={tdStyle}>
                        <span style={{
                          background: `${reason.color}22`,
                          color: reason.color,
                          padding: '2px 8px',
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                        }}>
                          {reason.label}
                        </span>
                      </td>
                      <td style={{ ...tdStyle, color: '#8b949e', fontSize: 12 }}>
                        {new Date(m.timestamp).toLocaleTimeString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  );
};

export default SignalsView;
