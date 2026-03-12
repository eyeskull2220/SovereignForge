import React from 'react';
import { render, screen } from '@testing-library/react';
import PositionsTable, { Position } from './PositionsTable';

test('shows "No open positions" when empty', () => {
  render(<PositionsTable positions={[]} />);
  expect(screen.getByText('No open positions')).toBeInTheDocument();
});

test('renders position data', () => {
  const positions: Position[] = [{
    pair: 'XRP/USDC',
    exchange: 'binance',
    side: 'buy',
    entryPrice: 0.5,
    currentPrice: 0.52,
    quantity: 100,
    pnl: 2.0,
    pnlPct: 4.0,
    status: 'open',
  }];
  render(<PositionsTable positions={positions} />);
  expect(screen.getByText('XRP/USDC')).toBeInTheDocument();
  expect(screen.getByText('binance')).toBeInTheDocument();
});

test('renders table headers', () => {
  render(<PositionsTable positions={[]} />);
  expect(screen.getByText('Pair')).toBeInTheDocument();
  expect(screen.getByText('Exchange')).toBeInTheDocument();
  expect(screen.getByText('Side')).toBeInTheDocument();
  expect(screen.getByText('P&L')).toBeInTheDocument();
});

test('renders position count in header', () => {
  const positions: Position[] = [{
    pair: 'ADA/USDC',
    exchange: 'coinbase',
    side: 'sell',
    entryPrice: 0.4,
    currentPrice: 0.38,
    quantity: 50,
    pnl: -1.0,
    pnlPct: -5.0,
    status: 'open',
  }];
  render(<PositionsTable positions={positions} />);
  expect(screen.getByText('(1)')).toBeInTheDocument();
});
