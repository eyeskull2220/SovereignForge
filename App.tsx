import React, { useState, useEffect } from 'react';
import Header from './Header';
import AlertsPanel, { AlertItem } from './AlertsPanel';
import PnlChart, { PnlDataPoint } from './PnlChart';
import PositionsTable, { Position } from './PositionsTable';
import RiskGauges from './RiskGauges';
import RiskMetrics from './RiskMetrics';

// ---------------------------------------------------------------------------
// Demo data helpers (replace with WebSocket feed in production)
// ---------------------------------------------------------------------------
const PAIRS = ['XRP/USDC', 'ADA/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC'];
const EXCHANGES = ['binance', 'coinbase', 'kraken'];

function makeAlert(i: number): AlertItem {
  const types: AlertItem['type'][] = ['critical', 'high', 'medium', 'low'];
  return {
    id: `${Date.now()}-${i}`,
    type: types[i % types.length],
    title: `Arbitrage Opportunity: ${PAIRS[i % PAIRS.length]}`,
    message: `Spread +${(0.2 + Math.random() * 0.5).toFixed(3)}% on ${EXCHANGES[i % EXCHANGES.length]}`,
    timestamp: new Date().toLocaleTimeString(),
  };
}

function makePosition(i: number): Position {
  const entry = 0.3 + Math.random() * 49.7;
  const current = entry * (1 + (Math.random() - 0.48) * 0.02);
  const qty = +(10 + Math.random() * 90).toFixed(2);
  const pnl = (current - entry) * qty;
  return {
    pair: PAIRS[i % PAIRS.length],
    exchange: EXCHANGES[i % EXCHANGES.length],
    side: Math.random() > 0.5 ? 'buy' : 'sell',
    entryPrice: +entry.toFixed(4),
    currentPrice: +current.toFixed(4),
    quantity: qty,
    pnl: +pnl.toFixed(2),
    pnlPct: +((pnl / (entry * qty)) * 100).toFixed(2),
    status: 'open',
  };
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------
const App: React.FC = () => {
  const [alerts, setAlerts] = useState<AlertItem[]>(() => [0, 1, 2].map(makeAlert));
  const [positions, setPositions] = useState<Position[]>(() => [0, 1, 2].map(makePosition));
  const [pnlHistory, setPnlHistory] = useState<PnlDataPoint[]>([]);
  const [totalPnl, setTotalPnl] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState('--');

  // Simulate live data feed
  useEffect(() => {
    setIsConnected(true);

    // Seed P&L history
    let cumulative = 0;
    const history: PnlDataPoint[] = Array.from({ length: 30 }, (_, i) => {
      const pnl = (Math.random() - 0.45) * 8;
      cumulative += pnl;
      return {
        timestamp: new Date(Date.now() - (29 - i) * 3600_000).toLocaleTimeString(),
        pnl: +pnl.toFixed(2),
        cumulative: +cumulative.toFixed(2),
      };
    });
    setPnlHistory(history);
    setTotalPnl(cumulative);

    const tick = setInterval(() => {
      setLastUpdate(new Date().toLocaleTimeString());
      setPositions([0, 1, 2].map(makePosition));

      const newPnl = (Math.random() - 0.45) * 6;
      setTotalPnl(prev => {
        const next = +(prev + newPnl).toFixed(2);
        setPnlHistory(h => {
          const point: PnlDataPoint = {
            timestamp: new Date().toLocaleTimeString(),
            pnl: +newPnl.toFixed(2),
            cumulative: next,
          };
          return [...h.slice(-59), point];
        });
        return next;
      });

      // Occasionally add alert
      if (Math.random() > 0.7) {
        setAlerts(prev => [makeAlert(Date.now()), ...prev].slice(0, 20));
      }
    }, 3000);

    return () => { clearInterval(tick); setIsConnected(false); };
  }, []);

  const openPositions = positions.filter(p => p.status === 'open');
  const totalPnlPct = totalPnl / 10000 * 100;

  return (
    <div style={{ minHeight: '100vh', background: '#0d1117', color: '#e2e8f0', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <Header isConnected={isConnected} lastUpdate={lastUpdate} />
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* Top row */}
        <RiskMetrics
          portfolioValue={10000 + totalPnl}
          dailyPnl={totalPnl}
          sharpeRatio={1.42 + Math.random() * 0.2}
          winRate={0.63}
          totalTrades={positions.length * 4}
          maxDrawdown={3.2}
        />

        {/* Middle row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <PnlChart data={pnlHistory} totalPnl={totalPnl} totalPnlPct={+totalPnlPct.toFixed(2)} />
          <RiskGauges
            portfolioExposure={openPositions.length * 8}
            dailyLoss={totalPnl < 0 ? Math.abs(totalPnlPct) : 0}
            drawdown={3.2}
            openPositions={openPositions.length}
            maxPositions={5}
          />
        </div>

        {/* Bottom row */}
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
          <PositionsTable positions={openPositions} />
          <AlertsPanel alerts={alerts} />
        </div>
      </div>
    </div>
  );
};

export default App;
