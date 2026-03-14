import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid, Cell } from 'recharts';

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
const COINS = ['BTC', 'ETH', 'XRP', 'XLM', 'HBAR', 'ALGO', 'ADA', 'LINK', 'IOTA', 'VET', 'XDC', 'ONDO'];

const coinSentiment = COINS.map(coin => ({
  coin,
  sentiment: +((Math.random() - 0.35) * 2).toFixed(2), // -1 to 1
})).sort((a, b) => b.sentiment - a.sentiment);

const overallScore = +(coinSentiment.reduce((s, c) => s + c.sentiment, 0) / coinSentiment.length).toFixed(2);

const demoHeadlines = [
  { headline: 'Bitcoin breaks through $72K resistance with strong volume', sentiment: 0.82, source: 'CoinDesk', time: '2h ago' },
  { headline: 'Ethereum ETF inflows reach record $1.2B in single day', sentiment: 0.91, source: 'Bloomberg', time: '3h ago' },
  { headline: 'SEC delays decision on XRP ETF application', sentiment: -0.34, source: 'Reuters', time: '4h ago' },
  { headline: 'Stellar partners with major European bank for CBDC pilot', sentiment: 0.65, source: 'The Block', time: '5h ago' },
  { headline: 'Hedera council adds two Fortune 500 members', sentiment: 0.58, source: 'CoinTelegraph', time: '6h ago' },
  { headline: 'Federal Reserve signals potential rate pause', sentiment: 0.42, source: 'CNBC', time: '7h ago' },
  { headline: 'Major DeFi protocol suffers $15M exploit', sentiment: -0.78, source: 'The Defiant', time: '8h ago' },
  { headline: 'Cardano Voltaire governance reaches milestone', sentiment: 0.51, source: 'CoinDesk', time: '10h ago' },
];

const sentimentTrend = Array.from({ length: 24 }, (_, i) => ({
  hour: `${String(i).padStart(2, '0')}:00`,
  score: +((Math.sin(i / 4) * 0.3 + (Math.random() - 0.4) * 0.4 + 0.1)).toFixed(2),
}));

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 20 };

// ---------------------------------------------------------------------------
// Sentiment Gauge (Bearish ← Neutral → Bullish)
// ---------------------------------------------------------------------------
const SentimentGauge: React.FC<{ score: number }> = ({ score }) => {
  // score: -1 (bearish) to +1 (bullish)
  const pct = ((score + 1) / 2) * 100; // 0-100
  const color = score > 0.2 ? '#3fb950' : score < -0.2 ? '#f85149' : '#d29922';
  const label = score > 0.2 ? 'Bullish' : score < -0.2 ? 'Bearish' : 'Neutral';

  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 13, color: '#8b949e', marginBottom: 8 }}>Market Sentiment</div>
      <div style={{ position: 'relative', height: 20, background: 'linear-gradient(90deg, #f85149 0%, #d29922 50%, #3fb950 100%)', borderRadius: 10, margin: '0 auto', maxWidth: 300 }}>
        <div style={{
          position: 'absolute', top: -4, left: `${pct}%`, transform: 'translateX(-50%)',
          width: 16, height: 28, borderRadius: 8, background: '#e2e8f0', border: '2px solid #0d1117',
        }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', maxWidth: 300, margin: '6px auto 0', fontSize: 11, color: '#8b949e' }}>
        <span>Bearish</span><span>Neutral</span><span>Bullish</span>
      </div>
      <div style={{ marginTop: 12, fontSize: 28, fontWeight: 700, color }}>{label}</div>
      <div style={{ fontSize: 14, color: '#8b949e' }}>Score: {score.toFixed(2)}</div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const SentimentView: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Market Sentiment</h2>
        <span style={{ fontSize: 12, color: '#8b949e', background: '#21262d', padding: '4px 10px', borderRadius: 4 }}>
          Demo Data — Connect NewsAPI key in .mcp.json for live sentiment
        </span>
      </div>

      {/* Gauge + Headlines */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={card}>
          <SentimentGauge score={overallScore} />
        </div>

        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Recent Headlines</h3>
          <div style={{ maxHeight: 260, overflowY: 'auto' }}>
            {demoHeadlines.map((h, i) => {
              const color = h.sentiment > 0.2 ? '#3fb950' : h.sentiment < -0.2 ? '#f85149' : '#d29922';
              return (
                <div key={i} style={{ padding: '8px 0', borderBottom: i < demoHeadlines.length - 1 ? '1px solid #21262d' : 'none', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color, minWidth: 42, textAlign: 'right' }}>{h.sentiment > 0 ? '+' : ''}{h.sentiment.toFixed(2)}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, lineHeight: 1.4 }}>{h.headline}</div>
                    <div style={{ fontSize: 11, color: '#8b949e', marginTop: 2 }}>{h.source} · {h.time}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Coin sentiment + Trend */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Sentiment by Coin</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={coinSentiment} layout="vertical" margin={{ left: 10 }}>
              <XAxis type="number" domain={[-1, 1]} tick={{ fill: '#8b949e', fontSize: 10 }} />
              <YAxis type="category" dataKey="coin" tick={{ fill: '#e2e8f0', fontSize: 12 }} width={45} />
              <Tooltip
                contentStyle={{ background: '#21262d', border: '1px solid #30363d', borderRadius: 6, color: '#e2e8f0', fontSize: 12 }}
                formatter={(v: any) => Number(v).toFixed(2)}
              />
              <Bar dataKey="sentiment" radius={[0, 4, 4, 0]}>
                {coinSentiment.map((entry, i) => (
                  <Cell key={i} fill={entry.sentiment > 0.2 ? '#3fb950' : entry.sentiment < -0.2 ? '#f85149' : '#d29922'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div style={card}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Sentiment Trend (24h)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={sentimentTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis dataKey="hour" tick={{ fill: '#8b949e', fontSize: 10 }} interval={3} />
              <YAxis domain={[-1, 1]} tick={{ fill: '#8b949e', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#21262d', border: '1px solid #30363d', borderRadius: 6, color: '#e2e8f0', fontSize: 12 }}
                formatter={(v: any) => Number(v).toFixed(2)}
              />
              <Line type="monotone" dataKey="score" stroke="#58a6ff" strokeWidth={2} dot={false} />
              {/* Reference lines */}
              <CartesianGrid horizontal={false} vertical={false} />
            </LineChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 20, marginTop: 8, fontSize: 11, color: '#8b949e' }}>
            <span>Below -0.2 = Bearish</span>
            <span>-0.2 to 0.2 = Neutral</span>
            <span>Above 0.2 = Bullish</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SentimentView;
