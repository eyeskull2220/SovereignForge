import React, { useState, useRef, useCallback, useEffect } from 'react';

export interface PnlDataPoint {
  timestamp: string;
  pnl: number;
  cumulative: number;
}

type TimeRange = '1h' | '4h' | '24h' | '7d';

const RANGE_MS: Record<TimeRange, number> = {
  '1h': 3_600_000,
  '4h': 14_400_000,
  '24h': 86_400_000,
  '7d': 604_800_000,
};

const MAX_POINTS = 500;

interface PnlChartProps {
  data?: PnlDataPoint[];
  totalPnl?: number;
  totalPnlPct?: number;
}

const rangeBtn = (active: boolean): React.CSSProperties => ({
  background: active ? '#21262d' : 'transparent',
  color: active ? '#58a6ff' : '#8b949e',
  border: active ? '1px solid #30363d' : '1px solid transparent',
  borderRadius: 4,
  padding: '4px 10px',
  fontSize: 11,
  fontWeight: 600,
  cursor: 'pointer',
});

const PnlChart: React.FC<PnlChartProps> = ({ data = [], totalPnl = 0, totalPnlPct = 0 }) => {
  const [range, setRange] = useState<TimeRange>('24h');
  const bufferRef = useRef<PnlDataPoint[]>([]);

  // Append incoming data points to the buffer
  useEffect(() => {
    if (data.length === 0) return;
    const buf = bufferRef.current;
    for (const pt of data) {
      // Avoid duplicates by timestamp
      if (buf.length === 0 || buf[buf.length - 1].timestamp !== pt.timestamp) {
        buf.push(pt);
      }
    }
    // Cap buffer size
    if (buf.length > MAX_POINTS) {
      bufferRef.current = buf.slice(buf.length - MAX_POINTS);
    }
  }, [data]);

  // Filter by time range
  const getFilteredData = useCallback((): PnlDataPoint[] => {
    const cutoff = Date.now() - RANGE_MS[range];
    return bufferRef.current.filter(pt => {
      const t = new Date(pt.timestamp).getTime();
      return !isNaN(t) ? t >= cutoff : true;
    });
  }, [range]);

  const filtered = getFilteredData();
  const displayData = filtered.length > 0 ? filtered : data;

  const isPositive = totalPnl >= 0;
  const color = isPositive ? '#68d391' : '#fc8181';

  // SVG sparkline
  const width = 400;
  const height = 80;
  const pts = displayData.length;
  const values = displayData.map(d => d.cumulative);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const rangeVal = max - min || 1;

  const toX = (i: number) => (i / Math.max(pts - 1, 1)) * width;
  const toY = (v: number) => height - ((v - min) / rangeVal) * height;

  const pathD = values.length > 1
    ? values.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ')
    : '';

  return (
    <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 8, padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <h3 style={{ color: '#e2e8f0', margin: '0 0 8px', fontSize: 14, fontWeight: 600 }}>Cumulative P&L</h3>
          <div style={{ display: 'flex', gap: 4 }}>
            {(['1h', '4h', '24h', '7d'] as TimeRange[]).map(r => (
              <button key={r} style={rangeBtn(range === r)} onClick={() => setRange(r)}>{r}</button>
            ))}
          </div>
        </div>
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
          Waiting for trade data...
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 10, color: '#8b949e' }}>
        <span>{displayData.length > 0 ? displayData[0].timestamp : ''}</span>
        <span>{displayData.length > 0 ? displayData[displayData.length - 1].timestamp : ''}</span>
      </div>
    </div>
  );
};

export default PnlChart;
