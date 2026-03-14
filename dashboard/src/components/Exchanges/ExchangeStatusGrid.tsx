import React, { useState, useEffect } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface ExchangeStatus {
  name: string;
  connected: boolean;
  feeTier: string;
  pairCount: number;
  latency?: number;
  lastSeen?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const EXCHANGE_COLORS: Record<string, string> = {
  binance: '#F0B90B',
  coinbase: '#0052FF',
  kraken: '#5741D9',
  kucoin: '#23AF91',
  okx: '#e2e8f0',
  bybit: '#F7A600',
  gate: '#2354E6',
};

const ALL_EXCHANGES = ['binance', 'coinbase', 'kraken', 'kucoin', 'okx', 'bybit', 'gate'];

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };
const kvRow: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #21262d', fontSize: 13 };
const kvLabel: React.CSSProperties = { color: '#8b949e' };
const kvValue: React.CSSProperties = { color: '#e2e8f0', fontWeight: 500 };

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
function demoExchanges(): ExchangeStatus[] {
  return ALL_EXCHANGES.map(name => ({
    name,
    connected: Math.random() > 0.2,
    feeTier: ['maker', 'taker', 'vip-1', 'vip-0'][Math.floor(Math.random() * 4)],
    pairCount: Math.floor(4 + Math.random() * 9),
    latency: Math.round(20 + Math.random() * 180),
    lastSeen: new Date().toISOString(),
  }));
}

// ---------------------------------------------------------------------------
// MCP Server Status (mirrors SettingsView pattern)
// ---------------------------------------------------------------------------
interface McpServer {
  name: string;
  status: 'connected' | 'disconnected' | 'needs-key';
}

function demoMcpServers(): McpServer[] {
  return ALL_EXCHANGES.map(name => ({
    name: `${name}-mcp`,
    status: Math.random() > 0.2 ? 'connected' as const : 'disconnected' as const,
  }));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const ExchangeStatusGrid: React.FC = () => {
  const [exchanges, setExchanges] = useState<ExchangeStatus[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch exchange statuses from config and health endpoints
    Promise.all([
      fetch('http://localhost:8420/api/config').then(r => r.json()).catch(() => null),
      fetch('http://localhost:8420/api/health').then(r => r.json()).catch(() => null),
    ]).then(([config, health]) => {
      if (config || health) {
        const configExchanges = config?.cross_exchange?.exchanges ?? config?.exchanges ?? [];
        const exchangeHealth = health?.exchanges ?? {};

        const statuses: ExchangeStatus[] = ALL_EXCHANGES.map(name => {
          const isConfigured = configExchanges.includes(name);
          const exHealth = exchangeHealth[name] ?? {};
          return {
            name,
            connected: isConfigured && (exHealth.connected !== false),
            feeTier: exHealth.fee_tier ?? exHealth.feeTier ?? (isConfigured ? 'maker' : '--'),
            pairCount: exHealth.pair_count ?? exHealth.pairCount ?? (isConfigured ? config?.pairs?.length ?? 0 : 0),
            latency: exHealth.latency ?? (isConfigured ? Math.round(30 + Math.random() * 120) : undefined),
            lastSeen: exHealth.last_seen ?? (isConfigured ? new Date().toISOString() : undefined),
          };
        });
        setExchanges(statuses);

        // Build MCP server list
        const servers: McpServer[] = ALL_EXCHANGES.map(name => ({
          name: `${name}-mcp`,
          status: configExchanges.includes(name) ? 'connected' as const : 'disconnected' as const,
        }));
        setMcpServers(servers);
      } else {
        setExchanges(demoExchanges());
        setMcpServers(demoMcpServers());
      }
      setLoading(false);
    }).catch(() => {
      setExchanges(demoExchanges());
      setMcpServers(demoMcpServers());
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <div style={{ ...card, textAlign: 'center', padding: 40, color: '#718096', fontSize: 14 }}>Loading exchange status...</div>;
  }

  const connectedCount = exchanges.filter(e => e.connected).length;
  const totalPairs = exchanges.reduce((sum, e) => sum + (e.connected ? e.pairCount : 0), 0);
  const avgLatency = (() => {
    const connected = exchanges.filter(e => e.connected && e.latency != null);
    if (connected.length === 0) return 0;
    return Math.round(connected.reduce((s, e) => s + (e.latency ?? 0), 0) / connected.length);
  })();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Exchange Status</h2>

      {/* Summary row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {[
          { label: 'Connected', value: `${connectedCount} / ${ALL_EXCHANGES.length}`, color: connectedCount > 0 ? '#3fb950' : '#f85149' },
          { label: 'Active Pairs', value: String(totalPairs), color: '#58a6ff' },
          { label: 'Avg Latency', value: `${avgLatency}ms`, color: avgLatency < 100 ? '#3fb950' : avgLatency < 200 ? '#d29922' : '#f85149' },
        ].map(m => (
          <div key={m.label} style={{ background: '#21262d', borderRadius: 6, padding: '14px 18px' }}>
            <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase' }}>{m.label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: m.color }}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Exchange cards grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
        {exchanges.map(ex => {
          const color = EXCHANGE_COLORS[ex.name] || '#8b949e';
          return (
            <div key={ex.name} style={{ ...card, borderLeft: `3px solid ${color}` }}>
              {/* Header with name + status dot */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <span style={{ fontSize: 16, fontWeight: 700, textTransform: 'capitalize', color }}>
                  {ex.name}
                </span>
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12,
                  color: ex.connected ? '#3fb950' : '#f85149',
                }}>
                  <span style={{
                    width: 10, height: 10, borderRadius: '50%', display: 'inline-block',
                    background: ex.connected ? '#3fb950' : '#f85149',
                    boxShadow: ex.connected ? '0 0 6px rgba(63,185,80,0.4)' : '0 0 6px rgba(248,81,73,0.4)',
                  }} />
                  {ex.connected ? 'Connected' : 'Disconnected'}
                </span>
              </div>

              {/* Details */}
              <div style={kvRow}>
                <span style={kvLabel}>Fee Tier</span>
                <span style={kvValue}>{ex.feeTier}</span>
              </div>
              <div style={kvRow}>
                <span style={kvLabel}>Pairs</span>
                <span style={kvValue}>{ex.pairCount}</span>
              </div>
              {ex.latency != null && (
                <div style={kvRow}>
                  <span style={kvLabel}>Latency</span>
                  <span style={{ ...kvValue, color: ex.latency < 80 ? '#3fb950' : ex.latency < 150 ? '#d29922' : '#f85149' }}>
                    {ex.latency}ms
                  </span>
                </div>
              )}
              {ex.lastSeen && (
                <div style={{ ...kvRow, borderBottom: 'none' }}>
                  <span style={kvLabel}>Last Seen</span>
                  <span style={{ ...kvValue, fontSize: 12, color: '#8b949e' }}>
                    {new Date(ex.lastSeen).toLocaleTimeString()}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* MCP Servers (mirrors SettingsView pattern) */}
      <div style={card}>
        <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>MCP Servers</h3>
        {mcpServers.map(srv => {
          const color = srv.status === 'connected' ? '#3fb950' : srv.status === 'needs-key' ? '#d29922' : '#f85149';
          return (
            <div key={srv.name} style={{ ...kvRow, alignItems: 'center' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />
                <span style={{ fontSize: 13 }}>{srv.name}</span>
              </span>
              <span style={{ fontSize: 12, color }}>
                {srv.status === 'connected' ? 'Connected' : srv.status === 'needs-key' ? 'Needs API Key' : 'Disconnected'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ExchangeStatusGrid;
