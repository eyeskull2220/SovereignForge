import React from 'react';
import { render, screen } from '@testing-library/react';
import RiskGauges from './RiskGauges';

test('renders Risk Gauges heading', () => {
  render(<RiskGauges />);
  expect(screen.getByText('Risk Gauges')).toBeInTheDocument();
});

test('renders gauge labels', () => {
  render(<RiskGauges />);
  expect(screen.getByText('Portfolio Exposure')).toBeInTheDocument();
  expect(screen.getByText('Daily Loss')).toBeInTheDocument();
  expect(screen.getByText('Max Drawdown')).toBeInTheDocument();
  expect(screen.getByText('Open Positions')).toBeInTheDocument();
});

test('renders with custom values', () => {
  render(<RiskGauges portfolioExposure={45} dailyLoss={1.2} drawdown={5.5} openPositions={3} maxPositions={5} />);
  expect(screen.getByText('45.0%')).toBeInTheDocument();
  expect(screen.getByText('1.2%')).toBeInTheDocument();
  expect(screen.getByText('5.5%')).toBeInTheDocument();
  expect(screen.getByText('3.0/5')).toBeInTheDocument();
});
