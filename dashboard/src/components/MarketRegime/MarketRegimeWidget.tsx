import React from 'react';

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------
const REGIME_COLORS: Record<string, string> = {
  trending_up: '#3fb950',
  trending_down: '#f85149',
  ranging: '#d29922',
  high_vol: '#f0883e',
  low_vol: '#58a6ff',
};

const REGIME_LABELS: Record<string, string> = {
  trending_up: 'Trending Up',
  trending_down: 'Trending Down',
  ranging: 'Ranging',
  high_vol: 'High Volatility',
  low_vol: 'Low Volatility',
};

const STRATEGY_ABBREVS: Record<string, string> = {
  arbitrage: 'ARB',
  fibonacci: 'FIB',
  grid: 'GRID',
  dca: 'DCA',
  mean_reversion: 'MR',
  momentum: 'MOM',
  breakout: 'BRK',
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: '14px 20px',
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface MarketRegimeWidgetProps {
  regime: string | null;
  multipliers: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const MarketRegimeWidget: React.FC<MarketRegimeWidgetProps> = ({ regime, multipliers }) => {
  const activeRegime = regime || 'ranging';
  const color = REGIME_COLORS[activeRegime] || '#8b949e';
  const label = REGIME_LABELS[activeRegime] || activeRegime.replace(/_/g, ' ');

  const entries = Object.entries(multipliers);
  const maxMult = entries.length > 0 ? Math.max(...entries.map(([, v]) => v), 1) : 1;

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        {/* Regime indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 160 }}>
          <span style={{
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: color,
            display: 'inline-block',
            boxShadow: `0 0 6px ${color}66`,
            flexShrink: 0,
          }} />
          <div>
            <div style={{ fontSize: 11, color: '#8b949e', textTransform: 'uppercase', marginBottom: 2 }}>Market Regime</div>
            <div style={{ fontSize: 15, fontWeight: 700, color, textTransform: 'capitalize' }}>{label}</div>
          </div>
        </div>

        {/* Strategy multiplier bars */}
        {entries.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, flex: 1, minWidth: 200 }}>
            {entries.map(([strategy, mult]) => {
              const abbrev = STRATEGY_ABBREVS[strategy] || (strategy ?? '').slice(0, 3).toUpperCase();
              const barWidth = Math.max((mult / maxMult) * 60, 4);
              const barColor = mult >= 1.0 ? '#3fb950' : mult >= 0.5 ? '#d29922' : '#f85149';

              return (
                <div key={strategy} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                  <span style={{ fontSize: 10, color: '#8b949e', fontWeight: 600 }}>{mult.toFixed(1)}x</span>
                  <div style={{
                    width: 14,
                    height: barWidth,
                    background: barColor,
                    borderRadius: 2,
                    transition: 'height 0.3s',
                  }} />
                  <span style={{ fontSize: 9, color: '#8b949e', fontWeight: 600 }}>{abbrev}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default MarketRegimeWidget;
