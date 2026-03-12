import React from 'react';

export interface PnlDataPoint {
  timestamp: string;
  pnl: number;
  cumulative: number;
}

interface PnlChartProps {
  data?: PnlDataPoint[];
  totalPnl?: number;
  totalPnlPct?: number;
}

const PnlChart: React.FC<PnlChartProps> = ({ data = [], totalPnl = 0, totalPnlPct = 0 }) => {
  const isPositive = totalPnl >= 0;
  const color = isPositive ? '#68d391' : '#fc8181';

  // Simple SVG sparkline
  const width = 400;
  const height = 80;
  const pts = data.length;
  const values = data.map(d => d.cumulative);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const range = max - min || 1;

  const toX = (i: number) => (i / Math.max(pts - 1, 1)) * width;
  const toY = (v: number) => height - ((v - min) / range) * height;

  const pathD = values.length > 1
    ? values.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ')
    : '';

  return (
    <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 8, padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <h3 style={{ color: '#e2e8f0', margin: 0, fontSize: 14, fontWeight: 600 }}>Cumulative P&L</h3>
        <div style={{ textAlign: 'right' }}>
          <div style={{ color, fontSize: 20, fontWeight: 700 }}>
            {isPositive ? '+' : ''}{totalPnl.toFixed(2)} USDC
          </div>
          <div style={{ color, fontSize: 12 }}>
            {isPositive ? '+' : ''}{totalPnlPct.toFixed(2)}%
          </div>
        </div>
      </div>
      {pts > 1 ? (
        <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
          <defs>
            <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <path d={`${pathD} L${toX(pts - 1).toFixed(1)},${height} L0,${height} Z`}
            fill="url(#pnlGrad)" />
          <path d={pathD} fill="none" stroke={color} strokeWidth={2} />
        </svg>
      ) : (
        <div style={{ color: '#718096', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
          Waiting for trade data…
        </div>
      )}
    </div>
  );
};

export default PnlChart;
