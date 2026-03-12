import React from 'react';
import { render, screen } from '@testing-library/react';
import RiskMetrics from './RiskMetrics';

test('renders Portfolio Metrics heading', () => {
  render(<RiskMetrics />);
  expect(screen.getByText('Portfolio Metrics')).toBeInTheDocument();
});

test('renders portfolio value', () => {
  render(<RiskMetrics portfolioValue={10500} />);
  expect(screen.getByText('$10,500.00')).toBeInTheDocument();
});

test('renders metric labels', () => {
  render(<RiskMetrics />);
  expect(screen.getByText('Portfolio')).toBeInTheDocument();
  expect(screen.getByText('Daily P&L')).toBeInTheDocument();
  expect(screen.getByText('Sharpe')).toBeInTheDocument();
  expect(screen.getByText('Win Rate')).toBeInTheDocument();
  expect(screen.getByText('Max DD')).toBeInTheDocument();
});

test('renders USDC sub-label', () => {
  render(<RiskMetrics />);
  expect(screen.getByText('USDC')).toBeInTheDocument();
});
