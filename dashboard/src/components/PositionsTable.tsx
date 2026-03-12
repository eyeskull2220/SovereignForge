import React from 'react';

export interface Position {
  pair: string;
  exchange: string;
  side: 'buy' | 'sell';
  entryPrice: number;
  currentPrice: number;
  quantity: number;
  pnl: number;
  pnlPct: number;
  status: 'open' | 'closed';
}

interface PositionsTableProps {
  positions?: Position[];
}

const fmt = (n: number, decimals = 2) =>
  n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const PositionsTable: React.FC<PositionsTableProps> = ({ positions = [] }) => (
  <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 8, padding: 16 }}>
    <h3 style={{ color: '#e2e8f0', margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>
      Open Positions <span style={{ color: '#718096', fontWeight: 400 }}>({positions.filter(p => p.status === 'open').length})</span>
    </h3>
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #2d3748' }}>
            {['Pair', 'Exchange', 'Side', 'Entry', 'Current', 'Qty', 'P&L', '%'].map(h => (
              <th key={h} style={{ color: '#718096', padding: '4px 8px', textAlign: 'right', fontWeight: 500, whiteSpace: 'nowrap' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.length === 0 ? (
            <tr>
              <td colSpan={8} style={{ color: '#718096', textAlign: 'center', padding: '16px 0' }}>
                No open positions
              </td>
            </tr>
          ) : (
            positions.map((p, i) => {
              const pnlColor = p.pnl >= 0 ? '#68d391' : '#fc8181';
              return (
                <tr key={i} style={{ borderBottom: '1px solid #2d3748' }}>
                  <td style={{ color: '#e2e8f0', padding: '6px 8px', fontWeight: 600 }}>{p.pair}</td>
                  <td style={{ color: '#a0aec0', padding: '6px 8px', textAlign: 'right' }}>{p.exchange}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', color: p.side === 'buy' ? '#68d391' : '#fc8181', textTransform: 'uppercase', fontSize: 11 }}>
                    {p.side}
                  </td>
                  <td style={{ color: '#a0aec0', padding: '6px 8px', textAlign: 'right' }}>{fmt(p.entryPrice)}</td>
                  <td style={{ color: '#e2e8f0', padding: '6px 8px', textAlign: 'right' }}>{fmt(p.currentPrice)}</td>
                  <td style={{ color: '#a0aec0', padding: '6px 8px', textAlign: 'right' }}>{fmt(p.quantity, 4)}</td>
                  <td style={{ color: pnlColor, padding: '6px 8px', textAlign: 'right', fontWeight: 600 }}>
                    {p.pnl >= 0 ? '+' : ''}{fmt(p.pnl)}
                  </td>
                  <td style={{ color: pnlColor, padding: '6px 8px', textAlign: 'right' }}>
                    {p.pnlPct >= 0 ? '+' : ''}{fmt(p.pnlPct)}%
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  </div>
);

export default PositionsTable;
