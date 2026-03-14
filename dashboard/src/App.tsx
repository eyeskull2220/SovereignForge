import React, { useCallback, useEffect, useRef, useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';

import Sidebar from './components/Layout/Sidebar';
import Header from './components/Header';
import AlertsPanel from './components/AlertsPanel';
import PnlChart from './components/PnlChart';
import PositionsTable from './components/PositionsTable';
import RiskGauges from './components/RiskGauges';
import RiskMetrics from './components/RiskMetrics';
import TrainingCards from './components/TrainingCards';
import TradesView from './components/Trades/TradesView';
import RiskView from './components/Risk/RiskView';
import StrategyView from './components/Strategy/StrategyView';
import SentimentView from './components/Sentiment/SentimentView';
import SettingsView from './components/Settings/SettingsView';
import SignalsView from './components/Signals/SignalsView';
import AuditView from './components/Audit/AuditView';
import ExchangeStatusGrid from './components/Exchanges/ExchangeStatusGrid';
import CapitalView from './components/Capital/CapitalView';
import ResearchView from './components/Research/ResearchView';
import CointegrationView from './components/Cointegration/CointegrationView';
import MarketRegimeWidget from './components/MarketRegime/MarketRegimeWidget';
import { ToastProvider, useToast } from './components/Toast';
import ErrorBoundary from './components/ErrorBoundary';
import { useWebSocket, type WebSocketMessage } from './useWebSocket';

import {
  useHealth,
  usePortfolio,
  useSignals,
  useModels,
  useTrainingStatus,
  useTrainingHistory,
  useTrades,
  useMetrics,
  useConfig,
} from './hooks/useApi';

import type { Portfolio, Signal, Trade, Metrics } from './types';

// ---------------------------------------------------------------------------
// Query client
// ---------------------------------------------------------------------------
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 3_000,
    },
  },
});

// ---------------------------------------------------------------------------
// Helper: map API portfolio positions to the shape PositionsTable expects
// ---------------------------------------------------------------------------
function mapPositions(portfolio?: Portfolio) {
  if (!portfolio?.positions) return [];
  const pos = Array.isArray(portfolio.positions)
    ? portfolio.positions
    : typeof portfolio.positions === 'object'
      ? Object.values(portfolio.positions)
      : [];
  return (pos as any[]).map(p => ({
    pair: p.pair,
    exchange: p.exchange,
    side: p.side,
    entryPrice: p.entry_price,
    currentPrice: p.current_price,
    quantity: p.quantity,
    pnl: p.pnl,
    pnlPct: p.pnl_pct,
    status: p.status,
  }));
}

// ---------------------------------------------------------------------------
// Helper: map signals to alert items for the AlertsPanel
// ---------------------------------------------------------------------------
function signalsToAlerts(signals?: Signal[]) {
  if (!signals) return [];
  return signals.map((s, i) => ({
    id: s.id ?? `sig-${i}`,
    type: (s.strength > 0.8 ? 'critical'
      : s.strength > 0.6 ? 'high'
      : s.strength > 0.3 ? 'medium'
      : 'low') as 'critical' | 'high' | 'medium' | 'low',
    title: `${s.direction.toUpperCase()} ${s.pair}`,
    message: `${s.strategy} on ${s.exchange} (strength ${(s.strength * 100).toFixed(0)}%)`,
    timestamp: s.timestamp ? new Date(s.timestamp).toLocaleTimeString() : '--',
  }));
}

// ---------------------------------------------------------------------------
// Page: Dashboard (main overview)
// ---------------------------------------------------------------------------
const DashboardPage: React.FC = () => {
  const { data: portfolio } = usePortfolio();
  const { data: signals } = useSignals();
  const { data: metrics } = useMetrics();

  const [regime, setRegime] = useState<string | null>(null);
  const [multipliers, setMultipliers] = useState<Record<string, number>>({
    arbitrage: 1.0, fibonacci: 0.8, grid: 1.2, dca: 0.6, mean_reversion: 1.1, momentum: 0.4, breakout: 0.9,
  });

  useEffect(() => {
    fetch('http://localhost:8420/api/pipeline/status')
      .then(r => r.json())
      .then(d => {
        if (d.regime) setRegime(d.regime);
        if (d.multipliers && typeof d.multipliers === 'object') setMultipliers(d.multipliers);
        else if (d.strategy_multipliers && typeof d.strategy_multipliers === 'object') setMultipliers(d.strategy_multipliers);
      })
      .catch(() => {}); // keep defaults on failure
  }, []);

  const positions = mapPositions(portfolio);
  const openPositions = positions.filter(p => p.status === 'open');
  const alerts = signalsToAlerts(signals);

  const totalPnl = portfolio?.daily_pnl ?? metrics?.daily_pnl ?? 0;
  const portfolioValue = portfolio?.total_value ?? metrics?.portfolio_value ?? 10000;
  const totalPnlPct = portfolioValue > 0 ? (totalPnl / portfolioValue) * 100 : 0;

  // Build a simple cumulative PnL point from the current snapshot
  const pnlData = totalPnl !== 0
    ? [{ timestamp: new Date().toLocaleTimeString(), pnl: totalPnl, cumulative: totalPnl }]
    : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Metric cards */}
      <RiskMetrics
        portfolioValue={portfolioValue}
        dailyPnl={totalPnl}
        sharpeRatio={portfolio?.sharpe_ratio ?? metrics?.sharpe_ratio ?? 0}
        winRate={portfolio?.win_rate ?? metrics?.win_rate ?? 0}
        totalTrades={portfolio?.total_trades ?? metrics?.total_trades ?? 0}
        maxDrawdown={portfolio?.max_drawdown ?? metrics?.max_drawdown ?? 0}
      />

      {/* Market Regime Widget */}
      <MarketRegimeWidget regime={regime} multipliers={multipliers} />

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <PnlChart data={pnlData} totalPnl={totalPnl} totalPnlPct={+totalPnlPct.toFixed(2)} />
        <RiskGauges
          portfolioExposure={portfolio?.exposure_pct ?? metrics?.exposure_pct ?? 0}
          dailyLoss={totalPnl < 0 ? Math.abs(totalPnlPct) : 0}
          drawdown={portfolio?.max_drawdown ?? metrics?.drawdown_pct ?? 0}
          openPositions={openPositions.length}
          maxPositions={metrics?.max_positions ?? 5}
        />
      </div>

      {/* Training cards */}
      <TrainingCards />

      {/* Positions + Alerts */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <PositionsTable positions={openPositions} />
        <AlertsPanel alerts={alerts} />
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page: Models
// ---------------------------------------------------------------------------
const ModelsPage: React.FC = () => {
  const { data: models, isLoading } = useModels();

  if (isLoading) return <PageLoading label="models" />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionTitle>Trained Models</SectionTitle>
      <div style={cardStyle}>
        {!models || models.length === 0 ? (
          <p style={{ color: '#718096', fontSize: 13 }}>No models loaded.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #2d3748' }}>
                {['Strategy', 'Pair', 'Exchange', 'Val Loss', 'Sharpe', 'Win Rate', 'P&L', 'Status'].map(h => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {models.map((m, i) => (
                <tr key={m.id ?? i} style={{ borderBottom: '1px solid #2d3748' }}>
                  <td style={{ ...tdStyle, color: '#58a6ff', fontWeight: 600 }}>{m.strategy}</td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{m.pair}</td>
                  <td style={tdStyle}>{m.exchange}</td>
                  <td style={tdStyle}>{m.val_loss?.toFixed(6) ?? '--'}</td>
                  <td style={{ ...tdStyle, color: (m.sharpe ?? 0) > 0 ? '#68d391' : '#fc8181' }}>
                    {m.sharpe?.toFixed(3) ?? '--'}
                  </td>
                  <td style={tdStyle}>{m.win_rate != null ? `${(m.win_rate * 100).toFixed(1)}%` : '--'}</td>
                  <td style={{ ...tdStyle, color: (m.net_pnl ?? 0) >= 0 ? '#68d391' : '#fc8181' }}>
                    {m.net_pnl != null ? `$${m.net_pnl.toFixed(2)}` : '--'}
                  </td>
                  <td style={tdStyle}>{m.status ?? '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page: Training
// ---------------------------------------------------------------------------
const TrainingPage: React.FC = () => {
  const { data: status, isLoading: loadingStatus } = useTrainingStatus();
  const { data: history, isLoading: loadingHistory } = useTrainingHistory();

  if (loadingStatus && loadingHistory) return <PageLoading label="training data" />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionTitle>Training Status</SectionTitle>

      {/* Active runs */}
      <div style={cardStyle}>
        <h4 style={{ margin: '0 0 12px', fontSize: 13, color: '#58a6ff' }}>Active Runs</h4>
        {!status || status.length === 0 ? (
          <p style={{ color: '#718096', fontSize: 13 }}>No active training runs.</p>
        ) : (
          status.map((run, i) => (
            <div key={run.id ?? i} style={{
              background: '#0d1117',
              borderRadius: 6,
              padding: '10px 12px',
              border: '1px solid #21262d',
              marginBottom: 8,
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>
                {run.strategy} -- {run.pair} @ {run.exchange}
              </div>
              <div style={{ fontSize: 12, color: '#8b949e', marginTop: 4 }}>
                Epoch {run.epoch ?? '?'}/{run.total_epochs ?? '?'}
                {run.val_loss != null && ` | Val Loss: ${run.val_loss.toFixed(6)}`}
                {run.gpu && ` | GPU: ${run.gpu}`}
              </div>
              {run.epoch != null && run.total_epochs != null && (
                <div style={{ background: '#21262d', borderRadius: 4, height: 4, marginTop: 6, overflow: 'hidden' }}>
                  <div style={{
                    width: `${(run.epoch / run.total_epochs) * 100}%`,
                    height: '100%',
                    background: '#58a6ff',
                    borderRadius: 4,
                  }} />
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* History */}
      <div style={cardStyle}>
        <h4 style={{ margin: '0 0 12px', fontSize: 13, color: '#58a6ff' }}>Training History</h4>
        {!history || history.length === 0 ? (
          <p style={{ color: '#718096', fontSize: 13 }}>No training history.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #2d3748' }}>
                {['Strategy', 'Pair', 'Exchange', 'Status', 'Epochs', 'Val Loss', 'Sharpe'].map(h => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map((run, i) => (
                <tr key={run.id ?? i} style={{ borderBottom: '1px solid #2d3748' }}>
                  <td style={{ ...tdStyle, color: '#58a6ff' }}>{run.strategy}</td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{run.pair}</td>
                  <td style={tdStyle}>{run.exchange}</td>
                  <td style={{
                    ...tdStyle,
                    color: run.status === 'completed' ? '#68d391' : run.status === 'failed' ? '#fc8181' : '#f6ad55',
                  }}>{run.status}</td>
                  <td style={tdStyle}>{run.epochs_completed ?? run.epoch ?? '--'}</td>
                  <td style={tdStyle}>{run.val_loss?.toFixed(6) ?? '--'}</td>
                  <td style={{ ...tdStyle, color: (run.sharpe ?? 0) > 0 ? '#68d391' : '#fc8181' }}>
                    {run.sharpe?.toFixed(3) ?? '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Existing training cards component */}
      <TrainingCards />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page: Charts (placeholder -- PnL chart view)
// ---------------------------------------------------------------------------
const ChartsPage: React.FC = () => {
  const { data: portfolio } = usePortfolio();
  const { data: metrics } = useMetrics();

  const totalPnl = portfolio?.daily_pnl ?? metrics?.daily_pnl ?? 0;
  const portfolioValue = portfolio?.total_value ?? metrics?.portfolio_value ?? 10000;
  const totalPnlPct = portfolioValue > 0 ? (totalPnl / portfolioValue) * 100 : 0;

  const pnlData = totalPnl !== 0
    ? [{ timestamp: new Date().toLocaleTimeString(), pnl: totalPnl, cumulative: totalPnl }]
    : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionTitle>Charts</SectionTitle>
      <PnlChart data={pnlData} totalPnl={totalPnl} totalPnlPct={+totalPnlPct.toFixed(2)} />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page: Risk
// ---------------------------------------------------------------------------
const RiskPage: React.FC = () => {
  const { data: portfolio } = usePortfolio();
  const { data: metrics } = useMetrics();

  const positions = mapPositions(portfolio);
  const openPositions = positions.filter(p => p.status === 'open');
  const totalPnl = portfolio?.daily_pnl ?? metrics?.daily_pnl ?? 0;
  const portfolioValue = portfolio?.total_value ?? metrics?.portfolio_value ?? 10000;
  const totalPnlPct = portfolioValue > 0 ? (totalPnl / portfolioValue) * 100 : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionTitle>Risk Management</SectionTitle>
      <RiskMetrics
        portfolioValue={portfolioValue}
        dailyPnl={totalPnl}
        sharpeRatio={portfolio?.sharpe_ratio ?? metrics?.sharpe_ratio ?? 0}
        winRate={portfolio?.win_rate ?? metrics?.win_rate ?? 0}
        totalTrades={portfolio?.total_trades ?? metrics?.total_trades ?? 0}
        maxDrawdown={portfolio?.max_drawdown ?? metrics?.max_drawdown ?? 0}
      />
      <RiskGauges
        portfolioExposure={portfolio?.exposure_pct ?? metrics?.exposure_pct ?? 0}
        dailyLoss={totalPnl < 0 ? Math.abs(totalPnlPct) : 0}
        drawdown={portfolio?.max_drawdown ?? metrics?.drawdown_pct ?? 0}
        openPositions={openPositions.length}
        maxPositions={metrics?.max_positions ?? 5}
      />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page: Trades
// ---------------------------------------------------------------------------
const TradesPage: React.FC = () => {
  const { data: trades, isLoading } = useTrades();
  const { data: portfolio } = usePortfolio();

  if (isLoading) return <PageLoading label="trades" />;

  // Also show open positions from portfolio
  const positions = mapPositions(portfolio);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionTitle>Trades</SectionTitle>

      <PositionsTable positions={positions} />

      <div style={cardStyle}>
        <h4 style={{ margin: '0 0 12px', fontSize: 13, color: '#58a6ff' }}>Trade History</h4>
        {!trades || trades.length === 0 ? (
          <p style={{ color: '#718096', fontSize: 13 }}>No trade history.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #2d3748' }}>
                {['Pair', 'Exchange', 'Side', 'Price', 'Qty', 'P&L', 'Strategy', 'Time'].map(h => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => (
                <tr key={t.id ?? i} style={{ borderBottom: '1px solid #2d3748' }}>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{t.pair}</td>
                  <td style={tdStyle}>{t.exchange}</td>
                  <td style={{
                    ...tdStyle,
                    color: t.side === 'buy' ? '#68d391' : '#fc8181',
                    textTransform: 'uppercase',
                    fontSize: 11,
                    fontWeight: 600,
                  }}>{t.side}</td>
                  <td style={tdStyle}>{t.price.toFixed(4)}</td>
                  <td style={tdStyle}>{t.quantity.toFixed(4)}</td>
                  <td style={{ ...tdStyle, color: (t.pnl ?? 0) >= 0 ? '#68d391' : '#fc8181' }}>
                    {t.pnl != null ? `$${t.pnl.toFixed(2)}` : '--'}
                  </td>
                  <td style={tdStyle}>{t.strategy ?? '--'}</td>
                  <td style={{ ...tdStyle, color: '#718096' }}>
                    {t.timestamp ? new Date(t.timestamp).toLocaleTimeString() : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page: Settings
// ---------------------------------------------------------------------------
const SettingsPage: React.FC = () => {
  const { data: config, isLoading } = useConfig();

  if (isLoading) return <PageLoading label="configuration" />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionTitle>Settings</SectionTitle>
      <div style={cardStyle}>
        {config ? (
          <pre style={{ color: '#e2e8f0', fontSize: 13, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {JSON.stringify(config, null, 2)}
          </pre>
        ) : (
          <p style={{ color: '#718096', fontSize: 13 }}>No configuration data available.</p>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Shared small components
// ---------------------------------------------------------------------------
const cardStyle: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: 16,
};

const thStyle: React.CSSProperties = {
  color: '#718096',
  padding: '4px 8px',
  textAlign: 'right',
  fontWeight: 500,
  whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
  color: '#e2e8f0',
  padding: '6px 8px',
  textAlign: 'right',
};

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h2 style={{ color: '#e2e8f0', margin: 0, fontSize: 18, fontWeight: 700 }}>{String(children)}</h2>
);

const PageLoading: React.FC<{ label: string }> = ({ label }) => (
  <div style={{ color: '#718096', fontSize: 14, padding: '40px 0', textAlign: 'center' }}>
    Loading {label}...
  </div>
);

// ---------------------------------------------------------------------------
// App shell: Header content area showing connection status from health hook
// ---------------------------------------------------------------------------
const AppContent: React.FC = () => {
  const { data: health, dataUpdatedAt } = useHealth();
  const qc = useQueryClient();
  const { addToast } = useToast();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // WebSocket for real-time updates
  const onWsMessage = useCallback((msg: WebSocketMessage) => {
    const { type } = msg;
    if (type === 'trade_executed') {
      qc.invalidateQueries({ queryKey: ['trades'] });
      qc.invalidateQueries({ queryKey: ['portfolio'] });
      addToast('Trade executed', 'success');
    } else if (type === 'opportunity') {
      qc.invalidateQueries({ queryKey: ['signals'] });
    } else if (type === 'alert') {
      addToast(String((msg.payload as any)?.message ?? 'New alert'), 'warning');
    }
    // pipeline_status updates are handled by polling already
  }, [qc, addToast]);

  const { status: wsStatus } = useWebSocket('ws://localhost:8420/ws', {
    onMessage: onWsMessage,
  });

  const isConnected = wsStatus === 'open' || health?.status === 'ok' || health?.status === 'healthy';
  const lastUpdate = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '--';

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0d1117', color: '#e2e8f0', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <Sidebar mobileOpen={mobileMenuOpen} onMobileClose={() => setMobileMenuOpen(false)} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Header isConnected={isConnected} lastUpdate={lastUpdate} onMenuToggle={() => setMobileMenuOpen(o => !o)} />
        <main style={{ maxWidth: 1400, width: '100%', margin: '0 auto', padding: 20 }}>
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/signals" element={<SignalsView />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/training" element={<TrainingPage />} />
              <Route path="/charts" element={<ChartsPage />} />
              <Route path="/risk" element={<RiskView />} />
              <Route path="/trades" element={<TradesView />} />
              <Route path="/strategy" element={<StrategyView />} />
              <Route path="/sentiment" element={<SentimentView />} />
              <Route path="/settings" element={<SettingsView />} />
              <Route path="/audit" element={<AuditView />} />
              <Route path="/exchanges" element={<ExchangeStatusGrid />} />
              <Route path="/capital" element={<CapitalView />} />
              <Route path="/research" element={<ResearchView />} />
              <Route path="/cointegration" element={<CointegrationView />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Root App with providers
// ---------------------------------------------------------------------------
const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <ToastProvider>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </ToastProvider>
  </QueryClientProvider>
);

export default App;
