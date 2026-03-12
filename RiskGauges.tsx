import React from 'react';

interface GaugeProps {
  label: string;
  value: number;      // 0–100
  max?: number;
  unit?: string;
  warnAt?: number;
  dangerAt?: number;
}

const Gauge: React.FC<GaugeProps> = ({ label, value, max = 100, unit = '%', warnAt = 60, dangerAt = 80 }) => {
  const pct = Math.min((value / max) * 100, 100);
  const color = pct >= dangerAt ? '#fc8181' : pct >= warnAt ? '#f6ad55' : '#68d391';
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ color: '#a0aec0', fontSize: 12 }}>{label}</span>
        <span style={{ color, fontSize: 13, fontWeight: 600 }}>{value.toFixed(1)}{unit}</span>
      </div>
      <div style={{ background: '#2d3748', borderRadius: 4, height: 6, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.4s ease' }} />
      </div>
    </div>
  );
};

interface RiskGaugesProps {
  portfolioExposure?: number;   // %
  dailyLoss?: number;           // %
  drawdown?: number;            // %
  openPositions?: number;
  maxPositions?: number;
}

const RiskGauges: React.FC<RiskGaugesProps> = ({
  portfolioExposure = 0,
  dailyLoss = 0,
  drawdown = 0,
  openPositions = 0,
  maxPositions = 5,
}) => (
  <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 8, padding: 16 }}>
    <h3 style={{ color: '#e2e8f0', margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Risk Gauges</h3>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Gauge label="Portfolio Exposure" value={portfolioExposure} warnAt={60} dangerAt={80} />
      <Gauge label="Daily Loss" value={Math.abs(dailyLoss)} warnAt={2} dangerAt={3} />
      <Gauge label="Max Drawdown" value={drawdown} warnAt={10} dangerAt={20} />
      <Gauge label="Open Positions" value={openPositions} max={maxPositions} unit={`/${maxPositions}`} warnAt={70} dangerAt={90} />
    </div>
  </div>
);

export default RiskGauges;
