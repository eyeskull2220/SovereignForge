import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ModelHeatmap from './ModelHeatmap';

const API_BASE = 'http://localhost:8420';

interface ModelEntry {
  strategy: string;
  pair: string;
  exchange: string;
  val_loss: number;
  file_size: number;
  last_modified: string;
  epochs: number;
}

interface Metrics {
  total_models: number;
  avg_val_loss: number;
  best_model: { strategy: string; pair: string; exchange: string; val_loss: number } | null;
  worst_model: { strategy: string; pair: string; exchange: string; val_loss: number } | null;
  avg_val_loss_per_strategy: Record<string, number>;
}

type SortKey = 'strategy' | 'pair' | 'exchange' | 'val_loss' | 'epochs' | 'file_size' | 'last_modified';
type SortDir = 'asc' | 'desc';

const STRATEGIES = ['All', 'Arbitrage', 'Fibonacci', 'Grid', 'DCA'];

const card: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: 16,
};

const lossColor = (val: number): string => {
  if (val < 0.015) return '#3fb950';
  if (val < 0.03) return '#d29922';
  if (val < 0.04) return '#db6d28';
  return '#f85149';
};

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const ModelsView: React.FC = () => {
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategyFilter, setStrategyFilter] = useState('All');
  const [sortKey, setSortKey] = useState<SortKey>('val_loss');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [viewMode, setViewMode] = useState<'table' | 'heatmap'>('table');

  const fetchData = useCallback(async () => {
    try {
      const [modelsRes, metricsRes] = await Promise.all([
        fetch(`${API_BASE}/api/models`),
        fetch(`${API_BASE}/api/metrics`),
      ]);
      if (!modelsRes.ok) throw new Error(`Models: HTTP ${modelsRes.status}`);
      const modelsData: ModelEntry[] = await modelsRes.json();
      setModels(modelsData);

      if (metricsRes.ok) {
        const metricsData: Metrics = await metricsRes.json();
        setMetrics(metricsData);
      }
      setError(null);
    } catch (e: any) {
      setError(e.message ?? 'Failed to fetch models');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filtered = useMemo(() => {
    let list = models;
    if (strategyFilter !== 'All') {
      list = list.filter(m => m.strategy.toLowerCase() === strategyFilter.toLowerCase());
    }
    list = [...list].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
    return list;
  }, [models, strategyFilter, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'val_loss' ? 'asc' : 'desc');
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

  const statCard = (label: string, value: string, color?: string): React.ReactNode => (
    <div style={{ ...card, flex: 1, minWidth: 140, textAlign: 'center' }}>
      <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: color ?? '#e2e8f0' }}>{value}</div>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Summary cards */}
      {metrics && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {statCard('Total Models', String(metrics.total_models))}
          {statCard('Avg Val Loss', metrics.avg_val_loss.toFixed(6), lossColor(metrics.avg_val_loss))}
          {statCard(
            'Best Model',
            metrics.best_model
              ? `${metrics.best_model.pair} (${metrics.best_model.val_loss.toFixed(6)})`
              : '--',
            '#3fb950',
          )}
          {statCard(
            'Worst Model',
            metrics.worst_model
              ? `${metrics.worst_model.pair} (${metrics.worst_model.val_loss.toFixed(6)})`
              : '--',
            '#f85149',
          )}
        </div>
      )}

      {/* Controls */}
      <div style={{ ...card, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 16, color: '#e2e8f0' }}>Model Leaderboard</h3>
          <span style={{ fontSize: 12, color: '#8b949e' }}>({filtered.length} models)</span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Strategy filter tabs */}
          {STRATEGIES.map(s => (
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
          {/* View toggle */}
          <div style={{ display: 'flex', border: '1px solid #30363d', borderRadius: 6, overflow: 'hidden', marginLeft: 8 }}>
            <button
              onClick={() => setViewMode('table')}
              style={{
                background: viewMode === 'table' ? '#58a6ff' : '#21262d',
                color: viewMode === 'table' ? '#0d1117' : '#8b949e',
                border: 'none',
                padding: '5px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Table
            </button>
            <button
              onClick={() => setViewMode('heatmap')}
              style={{
                background: viewMode === 'heatmap' ? '#58a6ff' : '#21262d',
                color: viewMode === 'heatmap' ? '#0d1117' : '#8b949e',
                border: 'none',
                padding: '5px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Heatmap
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div style={{ ...card, textAlign: 'center', color: '#8b949e' }}>Loading models...</div>
      ) : error ? (
        <div style={{ ...card, textAlign: 'center', color: '#f85149' }}>Error: {error}</div>
      ) : filtered.length === 0 ? (
        <div style={{ ...card, textAlign: 'center', color: '#484f58', fontSize: 13 }}>
          No trained models found for the selected filter.
        </div>
      ) : viewMode === 'heatmap' ? (
        <div style={card}>
          <ModelHeatmap models={filtered} />
        </div>
      ) : (
        <div style={{ ...card, padding: 0, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ ...thStyle, width: 30 }}>#</th>
                <th style={thStyle} onClick={() => handleSort('strategy')}>Strategy{arrow('strategy')}</th>
                <th style={thStyle} onClick={() => handleSort('pair')}>Pair{arrow('pair')}</th>
                <th style={thStyle} onClick={() => handleSort('exchange')}>Exchange{arrow('exchange')}</th>
                <th style={thStyle} onClick={() => handleSort('val_loss')}>Val Loss{arrow('val_loss')}</th>
                <th style={thStyle} onClick={() => handleSort('epochs')}>Epochs{arrow('epochs')}</th>
                <th style={thStyle} onClick={() => handleSort('file_size')}>Size{arrow('file_size')}</th>
                <th style={thStyle} onClick={() => handleSort('last_modified')}>Modified{arrow('last_modified')}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((m, i) => (
                <tr key={`${m.strategy}-${m.pair}-${m.exchange}-${i}`} style={{ background: i % 2 === 0 ? '#0d1117' : '#161b22' }}>
                  <td style={{ ...tdStyle, color: '#484f58', fontSize: 11, textAlign: 'center' }}>{i + 1}</td>
                  <td style={{ ...tdStyle, color: '#58a6ff', textTransform: 'capitalize', fontWeight: 600 }}>{m.strategy}</td>
                  <td style={{ ...tdStyle, fontWeight: 600, color: '#e2e8f0' }}>{m.pair}</td>
                  <td style={tdStyle}>{m.exchange}</td>
                  <td style={tdStyle}>
                    <span style={{
                      color: lossColor(m.val_loss),
                      fontWeight: 600,
                      fontFamily: 'monospace',
                    }}>
                      {m.val_loss.toFixed(6)}
                    </span>
                  </td>
                  <td style={tdStyle}>{m.epochs}</td>
                  <td style={{ ...tdStyle, color: '#8b949e' }}>{formatBytes(m.file_size)}</td>
                  <td style={{ ...tdStyle, color: '#8b949e', fontSize: 12 }}>
                    {new Date(m.last_modified).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ModelsView;
