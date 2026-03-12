import React from 'react';
import { render, screen } from '@testing-library/react';
import PnlChart, { PnlDataPoint } from './PnlChart';

test('renders Cumulative P&L heading', () => {
  render(<PnlChart />);
  expect(screen.getByText('Cumulative P&L')).toBeInTheDocument();
});

test('shows waiting message when no data', () => {
  render(<PnlChart data={[]} />);
  expect(screen.getByText(/Waiting for trade data/i)).toBeInTheDocument();
});

test('renders total PnL value', () => {
  render(<PnlChart totalPnl={42.5} totalPnlPct={0.43} />);
  expect(screen.getByText('+42.50 USDC')).toBeInTheDocument();
  expect(screen.getByText('+0.43%')).toBeInTheDocument();
});

test('renders negative PnL', () => {
  render(<PnlChart totalPnl={-10.25} totalPnlPct={-0.1} />);
  expect(screen.getByText('-10.25 USDC')).toBeInTheDocument();
});

test('renders SVG sparkline when data provided', () => {
  const data: PnlDataPoint[] = [
    { timestamp: '10:00', pnl: 1, cumulative: 1 },
    { timestamp: '11:00', pnl: 2, cumulative: 3 },
    { timestamp: '12:00', pnl: -1, cumulative: 2 },
  ];
  const { container } = render(<PnlChart data={data} totalPnl={2} />);
  expect(container.querySelector('svg')).toBeTruthy();
});
