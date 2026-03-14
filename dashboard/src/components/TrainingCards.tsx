import React, { useState, useEffect } from 'react';

interface ModelEntry {
  pair: string;
  exchange: string;
  val_loss?: number;
  sharpe?: number;
  win_rate?: number;
  net_pnl?: number;
  risk_score?: number;
  epochs_completed?: number;
}

interface DashboardData {
  strategies: Record<string, ModelEntry[]>;
  summary: {
    total_models: number;
    avg_val_loss?: number;
    best_val_loss?: number;
    total_net_pnl?: number;
  };
}

const cardStyle: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: 16,
};

const riskColor = (score: number): string => {
  if (score < 0.3) return '#3fb950';
  if (score < 0.5) return '#d29922';
  if (score < 0.65) return '#db6d28';
  return '#f85149';
};

const pnlColor = (pnl: number): string => pnl >= 0 ? '#3fb950' : '#f85149';

const TrainingCards: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    fetch('/reports/training_dashboard_data.json')
      .then(res => res.ok ? res.json() : null)
      .then(setData)
      .catch(() => setData(null));
  }, []);

  if (!data || !data.strategies || Object.keys(data.strategies).length === 0) {
    return (
      <div style={cardStyle}>
        <h3 style={{ margin: 0, fontSize: 14, color: '#8b949e' }}>Training Performance</h3>
        <p style={{ color: '#484f58', fontSize: 13, marginTop: 8 }}>No training data available yet.</p>
      </div>
    );
  }

  const { strategies, summary } = data;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Summary bar */}
      <div style={{ ...cardStyle, display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 14, color: '#e2e8f0' }}>Training Performance</h3>
        <span style={{ fontSize: 13, color: '#8b949e' }}>
          {summary.total_models} models
        </span>
        {summary.best_val_loss != null && (
          <span style={{ fontSize: 13, color: '#8b949e' }}>
            Best loss: {summary.best_val_loss.toFixed(6)}
          </span>
        )}
        {summary.total_net_pnl != null && (
          <span style={{ fontSize: 13, color: pnlColor(summary.total_net_pnl) }}>
            Net P&L: ${summary.total_net_pnl.toFixed(2)}
          </span>
        )}
      </div>

      {/* Per-strategy cards */}
      {Object.entries(strategies).map(([strategy, entries]) => (
        <div key={strategy} style={cardStyle}>
          <h4 style={{ margin: '0 0 10px', fontSize: 13, color: '#58a6ff', textTransform: 'uppercase' }}>
            {strategy}
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
            {entries.map((e, i) => (
              <div key={i} style={{
                background: '#0d1117',
                borderRadius: 6,
                padding: '10px 12px',
                border: '1px solid #21262d',
              }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>
                  {e.pair} <span style={{ color: '#484f58', fontWeight: 400 }}>@ {e.exchange}</span>
                </div>
                <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3, fontSize: 12 }}>
                  {e.val_loss != null && (
                    <div style={{ color: '#8b949e' }}>
                      Val Loss: <span style={{ color: '#e2e8f0' }}>{e.val_loss.toFixed(6)}</span>
                    </div>
                  )}
                  {e.sharpe != null && (
                    <div style={{ color: '#8b949e' }}>
                      Sharpe: <span style={{ color: e.sharpe > 0 ? '#3fb950' : '#f85149' }}>{e.sharpe.toFixed(3)}</span>
                    </div>
                  )}
                  {e.win_rate != null && (
                    <div style={{ color: '#8b949e' }}>
                      Win: <span style={{ color: '#e2e8f0' }}>{(e.win_rate * 100).toFixed(1)}%</span>
                    </div>
                  )}
                  {e.net_pnl != null && (
                    <div style={{ color: '#8b949e' }}>
                      P&L: <span style={{ color: pnlColor(e.net_pnl) }}>${e.net_pnl.toFixed(2)}</span>
                    </div>
                  )}
                  {e.risk_score != null && (
                    <div style={{ color: '#8b949e' }}>
                      Risk: <span style={{ color: riskColor(e.risk_score) }}>{e.risk_score.toFixed(2)}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default TrainingCards;
