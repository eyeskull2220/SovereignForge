import React, { useState, useEffect, useCallback } from 'react';

const API = 'http://localhost:8420';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface ConfigData {
  trading?: { base_currency?: string; min_trade_size?: number; max_trade_size?: number; paper_trading?: boolean; enabled_pairs?: string[]; trading_enabled?: boolean; dry_run_mode?: boolean };
  cross_exchange?: { enabled?: boolean; exchanges?: string[] };
  strategies?: Record<string, { enabled?: boolean; weight?: number; [k: string]: any }>;
  strategy_weights?: Record<string, number>;
  risk?: Record<string, number>;
  risk_limits?: Record<string, number>;
  exchanges?: string[];
  pairs?: string[];
  alerts?: Record<string, any>;
  [key: string]: any;
}

const ALL_PAIRS = [
  'BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC',
  'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC', 'XDC/USDC', 'ONDO/USDC',
];
const ALL_EXCHANGES = ['binance', 'coinbase', 'kraken', 'okx'];

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };
const sectionTitle: React.CSSProperties = { fontSize: 14, fontWeight: 600, marginBottom: 12, marginTop: 0, color: '#e2e8f0' };
const kvRow: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #21262d', fontSize: 13 };
const kvLabel: React.CSSProperties = { color: '#8b949e' };
const kvValue: React.CSSProperties = { color: '#e2e8f0', fontWeight: 500 };
const badge: (color: string) => React.CSSProperties = (color) => ({
  display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 4,
  background: `${color}22`, color, marginLeft: 8,
});
const btnDisabled: React.CSSProperties = {
  background: '#21262d', color: '#8b949e', border: '1px solid #30363d', borderRadius: 6,
  padding: '10px 20px', fontSize: 14, cursor: 'not-allowed', opacity: 0.6,
};

const toggleTrack = (on: boolean): React.CSSProperties => ({
  width: 36, height: 20, borderRadius: 10, cursor: 'pointer',
  background: on ? '#238636' : '#30363d', position: 'relative',
  transition: 'background 0.2s', flexShrink: 0, border: 'none', padding: 0,
});
const toggleThumb = (on: boolean): React.CSSProperties => ({
  width: 16, height: 16, borderRadius: '50%', background: '#e2e8f0',
  position: 'absolute', top: 2, left: on ? 18 : 2,
  transition: 'left 0.2s', pointerEvents: 'none',
});

// ---------------------------------------------------------------------------
// Demo config
// ---------------------------------------------------------------------------
function demoConfig(): ConfigData {
  return {
    trading: { base_currency: 'USDC', min_trade_size: 10, max_trade_size: 500, paper_trading: true },
    strategy_weights: { arbitrage: 0.4, fibonacci: 0.2, grid: 0.2, dca: 0.2 },
    risk_limits: { max_drawdown_pct: 10, daily_loss_limit_pct: 5, max_positions: 12, stop_loss_pct: 3, max_exposure_pct: 80 },
    exchanges: ['binance', 'coinbase', 'kraken', 'okx'],
    pairs: ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC', 'XDC/USDC', 'ONDO/USDC'],
    alerts: { telegram: true, email: false, webhook: false },
  };
}

const mcpServers = [
  { name: 'binance-mcp', status: 'connected', needsKey: false },
  { name: 'coinbase-mcp', status: 'connected', needsKey: false },
  { name: 'kraken-mcp', status: 'connected', needsKey: false },
  { name: 'okx-mcp', status: 'connected', needsKey: false },
  { name: 'newsapi-mcp', status: 'needs-key', needsKey: true },
  { name: 'telegram-mcp', status: 'connected', needsKey: false },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const btnActive: React.CSSProperties = {
  background: '#238636', color: '#fff', border: '1px solid #2ea043', borderRadius: 6,
  padding: '10px 20px', fontSize: 14, cursor: 'pointer', fontWeight: 600,
};
const btnDanger: React.CSSProperties = {
  background: '#da3633', color: '#fff', border: '1px solid #f85149', borderRadius: 6,
  padding: '10px 20px', fontSize: 14, cursor: 'pointer', fontWeight: 600,
};

const SettingsView: React.FC = () => {
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [ptRunning, setPtRunning] = useState(false);
  const [ptLoading, setPtLoading] = useState(false);
  const [ptError, setPtError] = useState<string | null>(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineInfo, setPipelineInfo] = useState<{ uptime?: number; pid?: number } | null>(null);
  const [modelCount, setModelCount] = useState(0);
  const [enabledPairs, setEnabledPairs] = useState<Set<string>>(new Set(ALL_PAIRS));
  const [enabledStrategies, setEnabledStrategies] = useState<Record<string, boolean>>({});
  const [enabledExchanges, setEnabledExchanges] = useState<Set<string>>(new Set(ALL_EXCHANGES));

  const togglePair = useCallback(async (pair: string, enabled: boolean) => {
    try {
      await fetch(`${API}/api/config/toggle-pair`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pair, enabled }),
      });
      setEnabledPairs(prev => {
        const next = new Set(prev);
        enabled ? next.add(pair) : next.delete(pair);
        return next;
      });
    } catch {}
  }, []);

  const toggleStrategy = useCallback(async (strategy: string, enabled: boolean) => {
    try {
      await fetch(`${API}/api/config/toggle-strategy`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy, enabled }),
      });
      setEnabledStrategies(prev => ({ ...prev, [strategy]: enabled }));
    } catch {}
  }, []);

  const toggleExchange = useCallback(async (exchange: string, enabled: boolean) => {
    try {
      await fetch(`${API}/api/config/toggle-exchange`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exchange, enabled }),
      });
      setEnabledExchanges(prev => {
        const next = new Set(prev);
        enabled ? next.add(exchange) : next.delete(exchange);
        return next;
      });
    } catch {}
  }, []);

  useEffect(() => {
    fetch(`${API}/api/config`)
      .then(r => r.json())
      .then(d => {
        setConfig(d);
        setLoading(false);
        // Populate toggle states from config
        const ep = d?.trading?.enabled_pairs ?? d?.pairs ?? ALL_PAIRS;
        setEnabledPairs(new Set(ep));
        const strats = d?.strategies ?? {};
        const stratEnabled: Record<string, boolean> = {};
        for (const [k, v] of Object.entries(strats)) {
          stratEnabled[k] = (v as any)?.enabled !== false;
        }
        if (Object.keys(stratEnabled).length === 0) {
          for (const s of ['arbitrage', 'fibonacci', 'grid', 'dca']) stratEnabled[s] = true;
        }
        setEnabledStrategies(stratEnabled);
        const exs = d?.cross_exchange?.exchanges ?? d?.exchanges ?? ALL_EXCHANGES;
        setEnabledExchanges(new Set(exs));
      })
      .catch(() => { setConfig(demoConfig()); setLoading(false); });
    fetch(`${API}/api/health`)
      .then(r => r.json())
      .then(d => setModelCount(d.models_loaded ?? 0))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const check = () => {
      fetch(`${API}/api/paper-trading/status`)
        .then(r => r.json())
        .then(d => setPtRunning(!!d.running))
        .catch(() => {});
      fetch(`${API}/api/pipeline/status`)
        .then(r => r.json())
        .then(d => {
          setPipelineRunning(!!d.running);
          setPipelineInfo({ uptime: d.uptime, pid: d.pid });
        })
        .catch(() => {});
    };
    check();
    const id = setInterval(check, 5000);
    return () => clearInterval(id);
  }, []);

  const togglePipeline = async () => {
    setPipelineLoading(true);
    setPipelineError(null);
    try {
      const endpoint = pipelineRunning ? '/api/pipeline/stop' : '/api/pipeline/start';
      const res = await fetch(`${API}${endpoint}`, { method: 'POST' });
      const d = await res.json();
      if (d.status === 'error') {
        setPipelineError(d.detail || 'Failed to toggle pipeline');
      } else {
        setPipelineRunning(d.status === 'started' || d.status === 'already_running');
      }
    } catch (e: any) {
      setPipelineError(e.message || 'Connection failed');
    }
    setPipelineLoading(false);
  };

  const togglePaperTrading = async () => {
    setPtLoading(true);
    setPtError(null);
    try {
      const endpoint = ptRunning ? '/api/paper-trading/stop' : '/api/paper-trading/start';
      const res = await fetch(`${API}${endpoint}`, { method: 'POST' });
      const d = await res.json();
      if (d.status === 'error') {
        setPtError(d.detail || 'Failed to toggle paper trading');
      } else {
        setPtRunning(d.status === 'started' || d.status === 'already_running');
      }
    } catch (e: any) {
      setPtError(e.message || 'Connection failed — is the API running?');
    }
    setPtLoading(false);
  };

  if (loading || !config) return <div style={{ ...card, textAlign: 'center', padding: 40 }}>Loading configuration...</div>;

  const trading = config.trading || {};
  const weights = config.strategy_weights || {};
  const riskLimits = config.risk_limits || {};
  const exchanges = config.cross_exchange?.exchanges ?? config.exchanges ?? [];
  const pairs = config.trading?.enabled_pairs ?? config.pairs ?? [];
  const alerts = config.alerts || {};

  const KV: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
    <div style={kvRow}><span style={kvLabel}>{label}</span><span style={kvValue}>{value}</span></div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Settings</h2>
        <span style={{ fontSize: 12, color: '#8b949e' }}>Read-only view — edit config files directly</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Trading Config */}
        <div style={card}>
          <h3 style={sectionTitle}>Trading Configuration</h3>
          <KV label="Base Currency" value={trading.base_currency || 'USDC'} />
          <KV label="Min Trade Size" value={`$${trading.min_trade_size || 10}`} />
          <KV label="Max Trade Size" value={`$${trading.max_trade_size || 500}`} />
          <KV label="Paper Trading" value={
            <span>{trading.paper_trading ? 'Enabled' : 'Disabled'}
              <span style={badge(trading.paper_trading ? '#3fb950' : '#f85149')}>{trading.paper_trading ? 'SAFE' : 'LIVE'}</span>
            </span>
          } />
          <KV label="Active Pairs" value={`${enabledPairs.size} / ${ALL_PAIRS.length} pairs`} />
          <KV label="Active Exchanges" value={`${enabledExchanges.size} / ${ALL_EXCHANGES.length}`} />
        </div>

        {/* Pair Toggles */}
        <div style={card}>
          <h3 style={sectionTitle}>Trading Pairs</h3>
          {ALL_PAIRS.map(pair => {
            const on = enabledPairs.has(pair);
            return (
              <div key={pair} style={{ ...kvRow, alignItems: 'center' }}>
                <span style={{ fontSize: 13, color: on ? '#e2e8f0' : '#484f58' }}>{pair}</span>
                <button style={toggleTrack(on)} onClick={() => togglePair(pair, !on)}>
                  <span style={toggleThumb(on)} />
                </button>
              </div>
            );
          })}
        </div>

        {/* Exchange Toggles */}
        <div style={card}>
          <h3 style={sectionTitle}>Exchanges</h3>
          {ALL_EXCHANGES.map(ex => {
            const on = enabledExchanges.has(ex);
            return (
              <div key={ex} style={{ ...kvRow, alignItems: 'center' }}>
                <span style={{ fontSize: 13, color: on ? '#e2e8f0' : '#484f58', textTransform: 'capitalize' }}>{ex}</span>
                <button style={toggleTrack(on)} onClick={() => toggleExchange(ex, !on)}>
                  <span style={toggleThumb(on)} />
                </button>
              </div>
            );
          })}
        </div>

        {/* Strategy Weights */}
        <div style={card}>
          <h3 style={sectionTitle}>Strategies</h3>
          {Object.entries(weights).map(([name, weight]) => {
            const pct = (weight as number) * 100;
            const colors: Record<string, string> = { arbitrage: '#58a6ff', fibonacci: '#3fb950', grid: '#d29922', dca: '#bc8cff' };
            const c = colors[name] || '#8b949e';
            const on = enabledStrategies[name] !== false;
            return (
              <div key={name} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 13, marginBottom: 4 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button style={toggleTrack(on)} onClick={() => toggleStrategy(name, !on)}>
                      <span style={toggleThumb(on)} />
                    </button>
                    <span style={{ textTransform: 'capitalize', color: on ? '#e2e8f0' : '#484f58' }}>{name}</span>
                  </span>
                  <span style={{ color: on ? c : '#484f58', fontWeight: 600 }}>{pct.toFixed(0)}%</span>
                </div>
                <div style={{ background: '#21262d', borderRadius: 4, height: 6, overflow: 'hidden' }}>
                  <div style={{ width: on ? `${pct}%` : '0%', height: '100%', background: c, borderRadius: 4, transition: 'width 0.3s' }} />
                </div>
              </div>
            );
          })}
        </div>

        {/* Risk Limits */}
        <div style={card}>
          <h3 style={sectionTitle}>Risk Limits</h3>
          {Object.entries(riskLimits).map(([key, val]) => {
            const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).replace('Pct', '(%)');
            return <KV key={key} label={label} value={typeof val === 'number' ? (key.includes('pct') ? `${val}%` : String(val)) : String(val)} />;
          })}
        </div>

        {/* Alert Config */}
        <div style={card}>
          <h3 style={sectionTitle}>Alert Configuration</h3>
          {Object.entries(alerts).map(([channel, enabled]) => (
            <KV key={channel} label={channel.charAt(0).toUpperCase() + channel.slice(1)} value={
              <span style={{ color: enabled ? '#3fb950' : '#8b949e' }}>{enabled ? 'Enabled' : 'Disabled'}</span>
            } />
          ))}
        </div>

        {/* MCP Servers */}
        <div style={card}>
          <h3 style={sectionTitle}>MCP Servers</h3>
          {mcpServers.map(srv => {
            const color = srv.status === 'connected' ? '#3fb950' : '#d29922';
            return (
              <div key={srv.name} style={{ ...kvRow, alignItems: 'center' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />
                  <span style={{ fontSize: 13 }}>{srv.name}</span>
                </span>
                <span style={{ fontSize: 12, color }}>
                  {srv.status === 'connected' ? 'Connected' : 'Needs API Key'}
                </span>
              </div>
            );
          })}
        </div>

        {/* System Info */}
        <div style={card}>
          <h3 style={sectionTitle}>System Info</h3>
          <KV label="Model Count" value={`${modelCount || 92} (${pairs.length} pairs x 4 strategies x ${exchanges.length} exchanges)`} />
          <KV label="Training Log Size" value="~2.4 GB" />
          <KV label="Dashboard Version" value="0.1.0" />
          <KV label="Backend" value="FastAPI @ :8420" />
          <KV label="MiCA Compliance" value={<span style={{ color: '#3fb950' }}>USDC Only - Compliant</span>} />

        </div>

        {/* Trading Controls */}
        <div style={{ ...card, gridColumn: '1 / -1' }}>
          <h3 style={sectionTitle}>Trading Controls</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {/* Pipeline */}
            <div>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, marginTop: 0, color: '#e2e8f0' }}>Live Pipeline</h4>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <button
                  style={pipelineLoading ? btnDisabled : pipelineRunning ? btnDanger : btnActive}
                  disabled={pipelineLoading}
                  onClick={togglePipeline}
                >
                  {pipelineLoading ? 'Working...' : pipelineRunning ? 'Stop Pipeline' : 'Start Pipeline'}
                </button>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  fontSize: 12, color: pipelineRunning ? '#3fb950' : '#8b949e',
                }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: pipelineRunning ? '#3fb950' : '#484f58',
                    display: 'inline-block',
                  }} />
                  {pipelineRunning ? 'Running' : 'Stopped'}
                </span>
              </div>
              {pipelineInfo?.uptime != null && pipelineRunning && (
                <div style={{ fontSize: 11, color: '#8b949e' }}>
                  Uptime: {Math.floor(pipelineInfo.uptime / 60)}m {Math.round(pipelineInfo.uptime % 60)}s
                  {pipelineInfo.pid && ` (PID ${pipelineInfo.pid})`}
                </div>
              )}
              {pipelineError && (
                <div style={{ marginTop: 8, fontSize: 12, color: '#f85149', background: '#f8514922', padding: '6px 10px', borderRadius: 4 }}>
                  {pipelineError}
                </div>
              )}
            </div>

            {/* Paper Trading */}
            <div>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, marginTop: 0, color: '#e2e8f0' }}>Paper Trading</h4>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <button
                  style={ptLoading ? btnDisabled : ptRunning ? btnDanger : btnActive}
                  disabled={ptLoading}
                  onClick={togglePaperTrading}
                >
                  {ptLoading ? 'Working...' : ptRunning ? 'Stop Paper Trading' : 'Start Paper Trading'}
                </button>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  fontSize: 12, color: ptRunning ? '#3fb950' : '#8b949e',
                }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: ptRunning ? '#3fb950' : '#484f58',
                    display: 'inline-block',
                  }} />
                  {ptRunning ? 'Running' : 'Stopped'}
                </span>
              </div>
              {ptError && (
                <div style={{ marginTop: 8, fontSize: 12, color: '#f85149', background: '#f8514922', padding: '6px 10px', borderRadius: 4 }}>
                  {ptError}
                </div>
              )}
            </div>
          </div>

          {/* Mode toggles */}
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #21262d' }}>
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 13, color: '#8b949e' }}>Trading Enabled</span>
                <button style={toggleTrack(!!trading.trading_enabled)} onClick={() => {
                  fetch(`${API}/api/config/update`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: 'trading.trading_enabled', value: !trading.trading_enabled }),
                  }).then(() => setConfig(c => c ? { ...c, trading: { ...c.trading, trading_enabled: !trading.trading_enabled } } : c)).catch(() => {});
                }}>
                  <span style={toggleThumb(!!trading.trading_enabled)} />
                </button>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 13, color: '#8b949e' }}>Dry Run Mode</span>
                <button style={toggleTrack(trading.dry_run_mode !== false)} onClick={() => {
                  const newVal = trading.dry_run_mode === false;
                  fetch(`${API}/api/config/update`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: 'trading.dry_run_mode', value: newVal }),
                  }).then(() => setConfig(c => c ? { ...c, trading: { ...c.trading, dry_run_mode: newVal } } : c)).catch(() => {});
                }}>
                  <span style={toggleThumb(trading.dry_run_mode !== false)} />
                </button>
                <span style={badge(trading.dry_run_mode !== false ? '#3fb950' : '#f85149')}>
                  {trading.dry_run_mode !== false ? 'SAFE' : 'LIVE'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsView;
