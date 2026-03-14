import React, { useRef, useEffect, useState, useCallback } from 'react';
import { createChart, CandlestickSeries, HistogramSeries, LineSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, CandlestickData, Time } from 'lightweight-charts';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const MICA_PAIRS = [
  'BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC',
  'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC', 'XDC/USDC', 'ONDO/USDC',
];
const EXCHANGES = ['binance', 'coinbase', 'kraken', 'okx'];
const TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d'];

const TIMEFRAME_SECONDS: Record<string, number> = {
  '5m': 300,
  '15m': 900,
  '1h': 3600,
  '4h': 14400,
  '1d': 86400,
};

// ---------------------------------------------------------------------------
// Demo data generator
// ---------------------------------------------------------------------------
interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface VolumeBar {
  time: number;
  value: number;
  color: string;
}

function generateDemoCandles(pair: string, tf: string, count = 200): { candles: Candle[]; volume: VolumeBar[] } {
  const basePrices: Record<string, number> = {
    'BTC/USDC': 67000, 'ETH/USDC': 3400, 'XRP/USDC': 0.52, 'XLM/USDC': 0.11,
    'HBAR/USDC': 0.08, 'ALGO/USDC': 0.18, 'ADA/USDC': 0.45, 'LINK/USDC': 14.5,
    'IOTA/USDC': 0.22, 'VET/USDC': 0.028, 'XDC/USDC': 0.045, 'ONDO/USDC': 0.78,
  };
  const base = basePrices[pair] ?? 100;
  const step = TIMEFRAME_SECONDS[tf] ?? 3600;
  const now = Math.floor(Date.now() / 1000);
  const startTime = now - count * step;

  let price = base * (0.9 + Math.random() * 0.2);
  const candles: Candle[] = [];
  const volume: VolumeBar[] = [];

  for (let i = 0; i < count; i++) {
    const time = startTime + i * step;
    const volatility = base * 0.008;
    const drift = (Math.random() - 0.48) * volatility;
    const open = price;
    const close = open + drift;
    const wick = volatility * (0.5 + Math.random());
    const high = Math.max(open, close) + Math.abs(wick * Math.random());
    const low = Math.min(open, close) - Math.abs(wick * Math.random());
    candles.push({
      time,
      open: +open.toPrecision(6),
      high: +high.toPrecision(6),
      low: +low.toPrecision(6),
      close: +close.toPrecision(6),
    });
    const vol = base * (500 + Math.random() * 2000);
    volume.push({
      time,
      value: +vol.toFixed(0),
      color: close >= open ? 'rgba(63,185,80,0.35)' : 'rgba(248,81,73,0.35)',
    });
    price = close;
  }
  return { candles, volume };
}

// ---------------------------------------------------------------------------
// RSI calculator (14-period)
// ---------------------------------------------------------------------------
function computeRSI(candles: Candle[], period = 14): { time: number; value: number }[] {
  if (candles.length < period + 1) return [];
  const closes = candles.map(c => c.close);
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    gains.push(diff > 0 ? diff : 0);
    losses.push(diff < 0 ? -diff : 0);
  }
  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
  const rsiData: { time: number; value: number }[] = [];
  for (let i = period; i < gains.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const rsi = 100 - 100 / (1 + rs);
    rsiData.push({ time: candles[i + 1].time, value: +rsi.toFixed(2) });
  }
  return rsiData;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const card: React.CSSProperties = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: 16,
};

const selectStyle: React.CSSProperties = {
  background: '#21262d',
  color: '#e2e8f0',
  border: '1px solid #30363d',
  borderRadius: 4,
  padding: '6px 10px',
  fontSize: 13,
  cursor: 'pointer',
  outline: 'none',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const ChartView: React.FC = () => {
  const [pair, setPair] = useState(MICA_PAIRS[0]);
  const [exchange, setExchange] = useState(EXCHANGES[0]);
  const [timeframe, setTimeframe] = useState('1h');

  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  const buildChart = useCallback(() => {
    // Cleanup
    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
    if (rsiChartRef.current) { rsiChartRef.current.remove(); rsiChartRef.current = null; }

    if (!mainRef.current || !rsiRef.current) return;

    const { candles, volume } = generateDemoCandles(pair, timeframe);
    const rsiData = computeRSI(candles);

    // --- Main chart (candlesticks + volume) ---
    const chart = createChart(mainRef.current, {
      width: mainRef.current.clientWidth,
      height: 400,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e', fontSize: 11 },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      crosshair: { mode: 0 },
      timeScale: { borderColor: '#30363d', timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: '#30363d' },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#3fb950',
      downColor: '#f85149',
      borderUpColor: '#3fb950',
      borderDownColor: '#f85149',
      wickUpColor: '#3fb950',
      wickDownColor: '#f85149',
    });
    candleSeries.setData(candles as CandlestickData<Time>[]);
    candleSeriesRef.current = candleSeries as any;

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(volume as any);
    volumeSeriesRef.current = volumeSeries as any;

    chart.timeScale().fitContent();

    // --- RSI chart ---
    const rsiChart = createChart(rsiRef.current, {
      width: rsiRef.current.clientWidth,
      height: 120,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e', fontSize: 11 },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      crosshair: { mode: 0 },
      timeScale: { borderColor: '#30363d', timeVisible: true, secondsVisible: false, visible: false },
      rightPriceScale: { borderColor: '#30363d' },
    });
    rsiChartRef.current = rsiChart;

    const rsiSeries = rsiChart.addSeries(LineSeries, {
      color: '#bc8cff',
      lineWidth: 2,
      priceFormat: { type: 'custom', formatter: (v: number) => v.toFixed(1) },
    });
    rsiSeries.setData(rsiData as any);
    rsiSeriesRef.current = rsiSeries as any;

    // Add 30 / 70 lines via createPriceLine
    rsiSeries.createPriceLine({ price: 70, color: '#f8514966', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' });
    rsiSeries.createPriceLine({ price: 30, color: '#3fb95066', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' });

    rsiChart.timeScale().fitContent();

    // Sync crosshair
    chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (range) rsiChart.timeScale().setVisibleLogicalRange(range);
    });
    rsiChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (range) chart.timeScale().setVisibleLogicalRange(range);
    });
  }, [pair, timeframe]);

  // Build on mount & selector changes
  useEffect(() => {
    buildChart();
  }, [buildChart]);

  // Resize handler
  useEffect(() => {
    const onResize = () => {
      if (mainRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: mainRef.current.clientWidth });
      }
      if (rsiRef.current && rsiChartRef.current) {
        rsiChartRef.current.applyOptions({ width: rsiRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
      if (rsiChartRef.current) { rsiChartRef.current.remove(); rsiChartRef.current = null; }
    };
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Selectors */}
      <div style={{ ...card, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={{ fontSize: 13, color: '#8b949e' }}>
          Pair
          <select
            value={pair}
            onChange={e => setPair(e.target.value)}
            style={{ ...selectStyle, marginLeft: 6 }}
          >
            {MICA_PAIRS.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>

        <label style={{ fontSize: 13, color: '#8b949e' }}>
          Exchange
          <select
            value={exchange}
            onChange={e => setExchange(e.target.value)}
            style={{ ...selectStyle, marginLeft: 6 }}
          >
            {EXCHANGES.map(x => (
              <option key={x} value={x}>{x}</option>
            ))}
          </select>
        </label>

        <label style={{ fontSize: 13, color: '#8b949e' }}>
          Timeframe
          <select
            value={timeframe}
            onChange={e => setTimeframe(e.target.value)}
            style={{ ...selectStyle, marginLeft: 6 }}
          >
            {TIMEFRAMES.map(tf => (
              <option key={tf} value={tf}>{tf}</option>
            ))}
          </select>
        </label>

        <div style={{ marginLeft: 'auto', fontSize: 12, color: '#484f58' }}>
          Demo data &middot; {pair} @ {exchange}
        </div>
      </div>

      {/* Main candlestick + volume chart */}
      <div style={card}>
        <h3 style={{ margin: '0 0 8px', fontSize: 14, color: '#e2e8f0' }}>
          {pair} &middot; {exchange} &middot; {timeframe}
        </h3>
        <div ref={mainRef} style={{ width: '100%' }} />
      </div>

      {/* RSI chart */}
      <div style={card}>
        <h3 style={{ margin: '0 0 8px', fontSize: 14, color: '#bc8cff' }}>
          RSI (14)
        </h3>
        <div ref={rsiRef} style={{ width: '100%' }} />
      </div>
    </div>
  );
};

export default ChartView;
