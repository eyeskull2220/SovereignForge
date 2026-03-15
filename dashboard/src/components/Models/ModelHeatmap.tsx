import React, { useMemo, useState } from 'react';

interface ModelEntry {
  strategy: string;
  pair: string;
  exchange: string;
  val_loss: number;
  file_size: number;
  last_modified: string;
  epochs: number;
}

interface ModelHeatmapProps {
  models: ModelEntry[];
}

const STRATEGIES = ['arbitrage', 'fibonacci', 'grid', 'dca'];
const STRATEGY_LABELS: Record<string, string> = {
  arbitrage: 'ARB',
  fibonacci: 'FIB',
  grid: 'GRID',
  dca: 'DCA',
};

const lossToColor = (val: number): string => {
  if (val < 0.015) return '#3fb950';
  if (val < 0.03) return '#d29922';
  if (val < 0.04) return '#db6d28';
  return '#f85149';
};

const lossToBackground = (val: number): string => {
  if (val < 0.015) return 'rgba(63, 185, 80, 0.2)';
  if (val < 0.03) return 'rgba(210, 153, 34, 0.2)';
  if (val < 0.04) return 'rgba(219, 109, 40, 0.2)';
  return 'rgba(248, 81, 73, 0.2)';
};

const ModelHeatmap: React.FC<ModelHeatmapProps> = ({ models }) => {
  const [tooltip, setTooltip] = useState<{ x: number; y: number; content: string } | null>(null);

  const { coins, grid } = useMemo(() => {
    // Extract unique coins from pairs (take base currency)
    const coinSet = new Set<string>();
    models.forEach(m => {
      const base = m.pair.split('/')[0];
      if (base) coinSet.add(base);
    });
    const coins = Array.from(coinSet).sort();

    // Build lookup: coin -> strategy -> { best val_loss, entries }
    const grid: Record<string, Record<string, { best: number; entries: ModelEntry[] }>> = {};
    models.forEach(m => {
      const coin = m.pair.split('/')[0];
      const strat = m.strategy.toLowerCase();
      if (!grid[coin]) grid[coin] = {};
      if (!grid[coin][strat]) grid[coin][strat] = { best: m.val_loss, entries: [] };
      grid[coin][strat].entries.push(m);
      if (m.val_loss < grid[coin][strat].best) grid[coin][strat].best = m.val_loss;
    });
    return { coins, grid };
  }, [models]);

  if (models.length === 0) {
    return (
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 24, textAlign: 'center', color: '#484f58', fontSize: 13 }}>
        No model data for heatmap
      </div>
    );
  }

  const handleMouseEnter = (e: React.MouseEvent, coin: string, strat: string) => {
    const cell = grid[coin]?.[strat];
    if (!cell) return;
    const lines = cell.entries.map(
      en => `${en.exchange}: ${en.val_loss.toFixed(6)} (${en.epochs} ep)`,
    );
    setTooltip({ x: e.clientX, y: e.clientY, content: `${coin} / ${(strat ?? '').toUpperCase()}\n${lines.join('\n')}` });
  };

  const cellSize = 72;
  const headerH = 32;

  return (
    <div style={{ position: 'relative' }}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ padding: '6px 12px', fontSize: 11, color: '#8b949e', textAlign: 'left', height: headerH }}>Coin</th>
              {STRATEGIES.map(s => (
                <th key={s} style={{ padding: '6px 8px', fontSize: 11, color: '#58a6ff', textAlign: 'center', width: cellSize, height: headerH }}>
                  {STRATEGY_LABELS[s]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {coins.map(coin => (
              <tr key={coin}>
                <td style={{ padding: '6px 12px', fontSize: 12, fontWeight: 600, color: '#e2e8f0', borderBottom: '1px solid #21262d' }}>
                  {coin}
                </td>
                {STRATEGIES.map(strat => {
                  const cell = grid[coin]?.[strat];
                  return (
                    <td
                      key={strat}
                      style={{
                        width: cellSize,
                        height: cellSize,
                        textAlign: 'center',
                        borderBottom: '1px solid #21262d',
                        border: '1px solid #21262d',
                        background: cell ? lossToBackground(cell.best) : '#0d1117',
                        cursor: cell ? 'default' : 'default',
                        transition: 'background 0.2s',
                      }}
                      onMouseEnter={e => cell && handleMouseEnter(e, coin, strat)}
                      onMouseMove={e => tooltip && setTooltip(t => t ? { ...t, x: e.clientX, y: e.clientY } : null)}
                      onMouseLeave={() => setTooltip(null)}
                    >
                      {cell ? (
                        <span style={{ fontSize: 12, fontWeight: 600, color: lossToColor(cell.best) }}>
                          {cell.best.toFixed(4)}
                        </span>
                      ) : (
                        <span style={{ fontSize: 11, color: '#30363d' }}>--</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          style={{
            position: 'fixed',
            left: tooltip.x + 12,
            top: tooltip.y - 10,
            background: '#21262d',
            border: '1px solid #30363d',
            borderRadius: 6,
            padding: '8px 12px',
            fontSize: 12,
            color: '#e2e8f0',
            whiteSpace: 'pre-line',
            pointerEvents: 'none',
            zIndex: 1000,
            boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
            maxWidth: 280,
          }}
        >
          {tooltip.content}
        </div>
      )}

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, marginTop: 12, fontSize: 11, color: '#8b949e', alignItems: 'center' }}>
        <span>Val Loss:</span>
        <span style={{ color: '#3fb950' }}>&lt;0.015</span>
        <span style={{ color: '#d29922' }}>0.015-0.03</span>
        <span style={{ color: '#db6d28' }}>0.03-0.04</span>
        <span style={{ color: '#f85149' }}>&gt;0.04</span>
      </div>
    </div>
  );
};

export default ModelHeatmap;
