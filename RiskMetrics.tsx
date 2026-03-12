import React from 'react';

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, sub, color = '#e2e8f0' }) => (
  <div style={{ background: '#2d3748', borderRadius: 6, padding: '12px 16px', flex: 1, minWidth: 120 }}>
    <div style={{ color: '#718096', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>{label}</div>
    <div style={{ color, fontSize: 20, fontWeight: 700 }}>{value}</div>
    {sub && <div style={{ color: '#718096', fontSize: 11, marginTop: 2 }}>{sub}</div>}
  </div>
);

interface RiskMetricsProps {
  portfolioValue?: number;
  dailyPnl?: number;
  sharpeRatio?: number;
  winRate?: number;
  totalTrades?: number;
  maxDrawdown?: number;
}

const fmt = (n: number, d = 2) =>
  n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

const RiskMetrics: React.FC<RiskMetricsProps> = ({
  portfolioValue = 0,
  dailyPnl = 0,
  sharpeRatio = 0,
  winRate = 0,
  totalTrades = 0,
  maxDrawdown = 0,
}) => {
  const pnlColor = dailyPnl >= 0 ? '#68d391' : '#fc8181';
  return (
    <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 8, padding: 16 }}>
      <h3 style={{ color: '#e2e8f0', margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Portfolio Metrics</h3>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <MetricCard label="Portfolio" value={`$${fmt(portfolioValue)}`} sub="USDC" />
        <MetricCard
          label="Daily P&L"
          value={`${dailyPnl >= 0 ? '+' : ''}$${fmt(Math.abs(dailyPnl))}`}
          color={pnlColor}
        />
        <MetricCard label="Sharpe" value={fmt(sharpeRatio)} sub="ratio" />
        <MetricCard label="Win Rate" value={`${fmt(winRate * 100, 1)}%`} sub={`${totalTrades} trades`} />
        <MetricCard label="Max DD" value={`${fmt(maxDrawdown, 1)}%`} color={maxDrawdown > 10 ? '#fc8181' : '#e2e8f0'} />
      </div>
    </div>
  );
};

export default RiskMetrics;
