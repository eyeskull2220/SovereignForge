import React, { useState, useEffect } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface CapitalTier {
  name: string;
  min: number;
  max: number;
  color: string;
}

interface StrategyAllocation {
  name: string;
  allocated: number;
  weight: number;
  color: string;
}

interface CapitalData {
  balance: number;
  target: number;
  tier: string;
  allocations: StrategyAllocation[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TIERS: CapitalTier[] = [
  { name: 'micro', min: 0, max: 500, color: '#8b949e' },
  { name: 'small', min: 500, max: 2000, color: '#58a6ff' },
  { name: 'medium', min: 2000, max: 5000, color: '#d29922' },
  { name: 'standard', min: 5000, max: Infinity, color: '#3fb950' },
];

const STRATEGY_COLORS: Record<string, string> = {
  arbitrage: '#58a6ff',
  fibonacci: '#3fb950',
  grid: '#d29922',
  dca: '#bc8cff',
};

const TARGET_AMOUNT = 5000;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };
const metricCard: React.CSSProperties = { background: '#21262d', borderRadius: 6, padding: '14px 18px', flex: 1, minWidth: 140 };

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
function demoCapital(): CapitalData {
  const balance = 1842.50;
  return {
    balance,
    target: TARGET_AMOUNT,
    tier: 'small',
    allocations: [
      { name: 'arbitrage', allocated: balance * 0.4, weight: 0.4, color: STRATEGY_COLORS.arbitrage },
      { name: 'fibonacci', allocated: balance * 0.2, weight: 0.2, color: STRATEGY_COLORS.fibonacci },
      { name: 'grid', allocated: balance * 0.2, weight: 0.2, color: STRATEGY_COLORS.grid },
      { name: 'dca', allocated: balance * 0.2, weight: 0.2, color: STRATEGY_COLORS.dca },
    ],
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const CapitalView: React.FC = () => {
  const [data, setData] = useState<CapitalData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('http://localhost:8420/api/config').then(r => r.json()).catch(() => null),
      fetch('http://localhost:8420/api/portfolio').then(r => r.json()).catch(() => null),
    ]).then(([config, portfolio]) => {
      const balance = portfolio?.total_value ?? portfolio?.balance ?? portfolio?.equity ?? portfolio?.metrics?.equity ?? 0;
      const weights = config?.strategy_weights ?? {};

      // Determine tier
      let tierName = 'micro';
      for (const t of TIERS) {
        if (balance >= t.min && balance < t.max) {
          tierName = t.name;
          break;
        }
      }

      // Build allocations from config weights
      const weightEntries = Object.entries(weights);
      const allocations: StrategyAllocation[] = weightEntries.length > 0
        ? weightEntries.map(([name, weight]) => ({
            name,
            allocated: balance * (weight as number),
            weight: weight as number,
            color: STRATEGY_COLORS[name] || '#8b949e',
          }))
        : [
            { name: 'arbitrage', allocated: balance * 0.4, weight: 0.4, color: STRATEGY_COLORS.arbitrage },
            { name: 'fibonacci', allocated: balance * 0.2, weight: 0.2, color: STRATEGY_COLORS.fibonacci },
            { name: 'grid', allocated: balance * 0.2, weight: 0.2, color: STRATEGY_COLORS.grid },
            { name: 'dca', allocated: balance * 0.2, weight: 0.2, color: STRATEGY_COLORS.dca },
          ];

      if (balance > 0 || config || portfolio) {
        setData({
          balance: balance || demoCapital().balance,
          target: TARGET_AMOUNT,
          tier: tierName,
          allocations,
        });
      } else {
        setData(demoCapital());
      }
      setLoading(false);
    }).catch(() => {
      setData(demoCapital());
      setLoading(false);
    });
  }, []);

  if (loading || !data) {
    return <div style={{ ...card, textAlign: 'center', padding: 40, color: '#718096', fontSize: 14 }}>Loading capital data...</div>;
  }

  const currentTier = TIERS.find(t => t.name === data.tier) || TIERS[0];
  const progressPct = Math.min((data.balance / data.target) * 100, 100);
  const remaining = Math.max(data.target - data.balance, 0);
  const maxAllocation = Math.max(...data.allocations.map(a => a.allocated), 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Capital Allocation</h2>

      {/* Summary metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <div style={metricCard}>
          <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>Balance</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#e2e8f0' }}>${data.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
        </div>
        <div style={metricCard}>
          <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>Target</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#58a6ff' }}>${data.target.toLocaleString()}</div>
        </div>
        <div style={metricCard}>
          <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>Remaining</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: remaining > 0 ? '#d29922' : '#3fb950' }}>
            ${remaining.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
        <div style={metricCard}>
          <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>Current Tier</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: currentTier.color, textTransform: 'capitalize' }}>{data.tier}</div>
        </div>
      </div>

      {/* Tier badge + progress */}
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Progress to $5,000 Target</h3>
          <span style={{ fontSize: 14, fontWeight: 700, color: currentTier.color }}>
            {progressPct.toFixed(1)}%
          </span>
        </div>

        {/* Progress bar */}
        <div style={{ background: '#21262d', borderRadius: 6, height: 16, overflow: 'hidden', position: 'relative', marginBottom: 16 }}>
          <div style={{
            width: `${progressPct}%`, height: '100%',
            background: `linear-gradient(90deg, ${currentTier.color}cc, ${currentTier.color})`,
            borderRadius: 6, transition: 'width 0.6s ease',
          }} />
        </div>

        {/* Tier markers */}
        <div style={{ display: 'flex', gap: 0, marginBottom: 4 }}>
          {TIERS.map((tier, i) => {
            const isActive = tier.name === data.tier;
            const widthPct = tier.max === Infinity
              ? `${((data.target - tier.min) / data.target) * 100}%`
              : `${((Math.min(tier.max, data.target) - tier.min) / data.target) * 100}%`;
            return (
              <div key={tier.name} style={{ width: widthPct, position: 'relative' }}>
                <div style={{
                  fontSize: 11, fontWeight: isActive ? 700 : 400,
                  color: isActive ? tier.color : '#8b949e',
                  textTransform: 'capitalize',
                  textAlign: 'center',
                  padding: '4px 0',
                }}>
                  {tier.name}
                  {isActive && (
                    <span style={{
                      display: 'inline-block', fontSize: 9, fontWeight: 600, padding: '1px 6px', borderRadius: 3,
                      background: `${tier.color}22`, color: tier.color, marginLeft: 4,
                    }}>
                      CURRENT
                    </span>
                  )}
                </div>
                {i < TIERS.length - 1 && (
                  <div style={{
                    position: 'absolute', right: 0, top: 0, bottom: 0,
                    width: 1, background: '#30363d',
                  }} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Per-strategy allocation bars */}
      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 600 }}>Per-Strategy Allocation</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {data.allocations.map(alloc => {
            const barPct = (alloc.allocated / maxAllocation) * 100;
            return (
              <div key={alloc.name}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 2, background: alloc.color, display: 'inline-block' }} />
                    <span style={{ fontSize: 14, fontWeight: 600, textTransform: 'capitalize', color: '#e2e8f0' }}>{alloc.name}</span>
                    <span style={{ fontSize: 12, color: '#8b949e' }}>({(alloc.weight * 100).toFixed(0)}%)</span>
                  </span>
                  <span style={{ fontSize: 14, fontWeight: 700, color: alloc.color }}>
                    ${alloc.allocated.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
                <div style={{ background: '#21262d', borderRadius: 4, height: 10, overflow: 'hidden' }}>
                  <div style={{
                    width: `${barPct}%`, height: '100%', background: alloc.color,
                    borderRadius: 4, transition: 'width 0.4s ease',
                  }} />
                </div>
              </div>
            );
          })}
        </div>

        {/* Stacked total bar */}
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #21262d' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 8 }}>
            <span style={{ color: '#8b949e' }}>Total Allocated</span>
            <span style={{ color: '#e2e8f0', fontWeight: 600 }}>
              ${data.allocations.reduce((s, a) => s + a.allocated, 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <div style={{ display: 'flex', borderRadius: 4, height: 10, overflow: 'hidden', background: '#21262d' }}>
            {data.allocations.map(alloc => (
              <div key={alloc.name} style={{
                width: `${alloc.weight * 100}%`, height: '100%',
                background: alloc.color,
              }} />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
            {data.allocations.map(alloc => (
              <span key={alloc.name} style={{ fontSize: 11, color: '#8b949e', display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: alloc.color, display: 'inline-block' }} />
                <span style={{ textTransform: 'capitalize' }}>{alloc.name}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CapitalView;
