import React, { useState, useEffect, useMemo, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface TradeRecord {
  id: string;
  pair: string;
  exchange: string;
  strategy: string;
  side: 'buy' | 'sell';
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  pnl_pct: number;
  entry_time: string;
  exit_time: string;
  status: string;
  fee: number;
  slippage: number;
}

type SortKey = keyof TradeRecord;
type SortDir = 'asc' | 'desc';
type DateFilter = '24h' | '7d' | '30d' | 'all';
type PnlFilter = 'all' | 'winners' | 'losers';

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
const PAIRS = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC', 'XDC/USDC', 'ONDO/USDC'];
const EXCHANGES = ['binance', 'coinbase', 'kraken', 'okx'];
const STRATEGIES = ['arbitrage', 'fibonacci', 'grid', 'dca'];

function makeDemoTrades(): TradeRecord[] {
  return Array.from({ length: 60 }, (_, i) => {
    const entry = 0.3 + Math.random() * 49.7;
    const pnlPct = (Math.random() - 0.42) * 6;
    const exit = entry * (1 + pnlPct / 100);
    const qty = +(10 + Math.random() * 90).toFixed(2);
    const pnl = (exit - entry) * qty;
    const hoursAgo = Math.random() * 720;
    const entryDate = new Date(Date.now() - hoursAgo * 3600_000);
    const exitDate = new Date(entryDate.getTime() + (5 + Math.random() * 120) * 60_000);
    return {
      id: `t-${1000 + i}`,
      pair: PAIRS[i % PAIRS.length],
      exchange: EXCHANGES[i % EXCHANGES.length],
      strategy: STRATEGIES[i % STRATEGIES.length],
      side: Math.random() > 0.5 ? 'buy' : 'sell',
      entry_price: +entry.toFixed(4),
      exit_price: +exit.toFixed(4),
      quantity: qty,
      pnl: +pnl.toFixed(2),
      pnl_pct: +pnlPct.toFixed(2),
      entry_time: entryDate.toISOString(),
      exit_time: exitDate.toISOString(),
      status: 'closed',
      fee: +(qty * entry * 0.001).toFixed(4),
      slippage: +(Math.random() * 0.05).toFixed(4),
    };
  });
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };
const filterRow: React.CSSProperties = { display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16, alignItems: 'center' };
const selectStyle: React.CSSProperties = { background: '#21262d', color: '#e2e8f0', border: '1px solid #30363d', borderRadius: 4, padding: '6px 10px', fontSize: 13 };
const btnStyle: React.CSSProperties = { ...selectStyle, cursor: 'pointer' };
const thStyle: React.CSSProperties = { padding: '8px 10px', textAlign: 'left', fontSize: 12, color: '#8b949e', fontWeight: 600, cursor: 'pointer', userSelect: 'none', borderBottom: '1px solid #30363d', whiteSpace: 'nowrap' };
const tdStyle: React.CSSProperties = { padding: '7px 10px', fontSize: 13, borderBottom: '1px solid #21262d', whiteSpace: 'nowrap' };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const fmt = (n: number, d = 2) => n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

function duration(entry: string, exit: string): string {
  const ms = new Date(exit).getTime() - new Date(entry).getTime();
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  return `${h}h ${mins % 60}m`;
}

function exportCsv(trades: TradeRecord[]) {
  const header = 'Date,Pair,Exchange,Strategy,Side,Entry,Exit,P&L ($),P&L (%),Fee,Duration\n';
  const rows = trades.map(t =>
    `${new Date(t.entry_time).toLocaleDateString()},${t.pair},${t.exchange},${t.strategy},${t.side},${t.entry_price},${t.exit_price},${t.pnl},${t.pnl_pct},${t.fee},"${duration(t.entry_time, t.exit_time)}"`
  ).join('\n');
  const blob = new Blob([header + rows], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `trades_${Date.now()}.csv`; a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const TradesView: React.FC = () => {
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [dateFilter, setDateFilter] = useState<DateFilter>('all');
  const [strategyFilter, setStrategyFilter] = useState('all');
  const [pairFilter, setPairFilter] = useState('all');
  const [exchangeFilter, setExchangeFilter] = useState('all');
  const [pnlFilter, setPnlFilter] = useState<PnlFilter>('all');
  const [sortKey, setSortKey] = useState<SortKey>('entry_time');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  useEffect(() => {
    let cancelled = false;
    fetch('http://localhost:8420/api/trades')
      .then(r => r.json())
      .then(d => { if (!cancelled) { setTrades(Array.isArray(d) ? d : (d?.trades ?? [])); setLoading(false); } })
      .catch(() => { if (!cancelled) { setTrades([]); setLoading(false); } });
    return () => { cancelled = true; };
  }, []);

  const toggleSort = useCallback((key: SortKey) => {
    setSortKey(prev => { setSortDir(prev === key ? ((d: string) => d === 'asc' ? 'desc' : 'asc') as any : 'desc'); return key; });
    if (sortKey !== key) setSortDir('desc');
  }, [sortKey]);

  const filtered = useMemo(() => {
    let list = [...trades];
    // date
    if (dateFilter !== 'all') {
      const hours = dateFilter === '24h' ? 24 : dateFilter === '7d' ? 168 : 720;
      const cutoff = Date.now() - hours * 3600_000;
      list = list.filter(t => new Date(t.entry_time).getTime() >= cutoff);
    }
    if (strategyFilter !== 'all') list = list.filter(t => t.strategy === strategyFilter);
    if (pairFilter !== 'all') list = list.filter(t => t.pair === pairFilter);
    if (exchangeFilter !== 'all') list = list.filter(t => t.exchange === exchangeFilter);
    if (pnlFilter === 'winners') list = list.filter(t => t.pnl > 0);
    if (pnlFilter === 'losers') list = list.filter(t => t.pnl < 0);
    // sort
    list.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      const cmp = typeof av === 'number' ? (av as number) - (bv as number) : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [trades, dateFilter, strategyFilter, pairFilter, exchangeFilter, pnlFilter, sortKey, sortDir]);

  // summary
  const winners = filtered.filter(t => t.pnl > 0);
  const losers = filtered.filter(t => t.pnl < 0);
  const winRate = filtered.length ? (winners.length / filtered.length * 100) : 0;
  const avgWin = winners.length ? winners.reduce((s, t) => s + t.pnl, 0) / winners.length : 0;
  const avgLoss = losers.length ? losers.reduce((s, t) => s + t.pnl, 0) / losers.length : 0;
  const totalPnl = filtered.reduce((s, t) => s + t.pnl, 0);

  const uniqueStrategies = Array.from(new Set(trades.map(t => t.strategy)));
  const uniquePairs = Array.from(new Set(trades.map(t => t.pair)));
  const uniqueExchanges = Array.from(new Set(trades.map(t => t.exchange)));

  const arrow = (key: SortKey) => sortKey === key ? (sortDir === 'asc' ? ' \u25B2' : ' \u25BC') : '';

  if (loading) return <div style={{ ...card, textAlign: 'center', padding: 40 }}>Loading trades...</div>;

  return (
    <div style={card}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Trade History</h2>
        <button style={{ ...btnStyle, background: '#238636', color: '#fff', border: 'none', fontWeight: 600 }} onClick={() => exportCsv(filtered)}>Export CSV</button>
      </div>

      {/* Filters */}
      <div style={filterRow}>
        <select style={selectStyle} value={dateFilter} onChange={e => setDateFilter(e.target.value as DateFilter)}>
          <option value="all">All Time</option><option value="24h">Last 24h</option><option value="7d">Last 7d</option><option value="30d">Last 30d</option>
        </select>
        <select style={selectStyle} value={strategyFilter} onChange={e => setStrategyFilter(e.target.value)}>
          <option value="all">All Strategies</option>
          {uniqueStrategies.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select style={selectStyle} value={pairFilter} onChange={e => setPairFilter(e.target.value)}>
          <option value="all">All Pairs</option>
          {uniquePairs.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select style={selectStyle} value={exchangeFilter} onChange={e => setExchangeFilter(e.target.value)}>
          <option value="all">All Exchanges</option>
          {uniqueExchanges.map(x => <option key={x} value={x}>{x}</option>)}
        </select>
        <select style={selectStyle} value={pnlFilter} onChange={e => setPnlFilter(e.target.value as PnlFilter)}>
          <option value="all">All P&L</option><option value="winners">Winners</option><option value="losers">Losers</option>
        </select>
      </div>

      {/* Summary row */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 14, flexWrap: 'wrap' }}>
        {[
          { label: 'Total Trades', value: String(filtered.length), color: '#e2e8f0' },
          { label: 'Win Rate', value: `${fmt(winRate, 1)}%`, color: winRate >= 50 ? '#3fb950' : '#f85149' },
          { label: 'Avg Win', value: `$${fmt(avgWin)}`, color: '#3fb950' },
          { label: 'Avg Loss', value: `$${fmt(avgLoss)}`, color: '#f85149' },
          { label: 'Total P&L', value: `${totalPnl >= 0 ? '+' : ''}$${fmt(totalPnl)}`, color: totalPnl >= 0 ? '#3fb950' : '#f85149' },
        ].map(m => (
          <div key={m.label} style={{ background: '#21262d', borderRadius: 6, padding: '8px 14px', minWidth: 100 }}>
            <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 2 }}>{m.label}</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: m.color }}>{m.value}</div>
          </div>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#8b949e' }}>No trades to display. Adjust filters or wait for trading activity.</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {([
                  ['entry_time', 'Date'], ['pair', 'Pair'], ['exchange', 'Exchange'], ['strategy', 'Strategy'],
                  ['side', 'Side'], ['entry_price', 'Entry'], ['exit_price', 'Exit'], ['pnl', 'P&L ($)'],
                  ['pnl_pct', 'P&L (%)'], ['fee', 'Fee'], ['entry_time', 'Duration'],
                ] as [SortKey, string][]).map(([key, label]) => (
                  <th key={label} style={thStyle} onClick={() => toggleSort(key)}>{label}{arrow(key)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(t => {
                const rowBg = t.pnl > 0 ? 'rgba(63,185,80,0.06)' : t.pnl < 0 ? 'rgba(248,81,73,0.06)' : '#21262d';
                return (
                  <tr key={t.id} style={{ background: rowBg }}>
                    <td style={tdStyle}>{new Date(t.entry_time).toLocaleDateString()}</td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{t.pair}</td>
                    <td style={tdStyle}>{t.exchange}</td>
                    <td style={tdStyle}>{t.strategy}</td>
                    <td style={{ ...tdStyle, color: t.side === 'buy' ? '#3fb950' : '#f85149' }}>{t.side.toUpperCase()}</td>
                    <td style={tdStyle}>${fmt(t.entry_price, 4)}</td>
                    <td style={tdStyle}>${fmt(t.exit_price, 4)}</td>
                    <td style={{ ...tdStyle, color: t.pnl >= 0 ? '#3fb950' : '#f85149', fontWeight: 600 }}>{t.pnl >= 0 ? '+' : ''}${fmt(t.pnl)}</td>
                    <td style={{ ...tdStyle, color: t.pnl_pct >= 0 ? '#3fb950' : '#f85149' }}>{t.pnl_pct >= 0 ? '+' : ''}{fmt(t.pnl_pct)}%</td>
                    <td style={{ ...tdStyle, color: '#8b949e' }}>${fmt(t.fee, 4)}</td>
                    <td style={{ ...tdStyle, color: '#8b949e' }}>{duration(t.entry_time, t.exit_time)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default TradesView;
