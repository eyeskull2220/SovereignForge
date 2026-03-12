import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders SovereignForge header', () => {
  render(<App />);
  expect(screen.getByText(/SovereignForge/i)).toBeInTheDocument();
});

test('renders MiCA compliance badge', () => {
  render(<App />);
  expect(screen.getByText(/MiCA Compliant/i)).toBeInTheDocument();
});

test('renders portfolio metrics section', () => {
  render(<App />);
  expect(screen.getByText(/Portfolio Metrics/i)).toBeInTheDocument();
});

test('renders risk gauges section', () => {
  render(<App />);
  expect(screen.getByText(/Risk Gauges/i)).toBeInTheDocument();
});

test('renders alerts panel', () => {
  render(<App />);
  expect(screen.getByText(/Alerts/i)).toBeInTheDocument();
});

test('renders open positions table', () => {
  render(<App />);
  const matches = screen.getAllByText(/Open Positions/i);
  expect(matches.length).toBeGreaterThanOrEqual(1);
});

test('renders cumulative PnL chart', () => {
  render(<App />);
  expect(screen.getByText(/Cumulative P&L/i)).toBeInTheDocument();
});

test('shows live connection status', () => {
  render(<App />);
  expect(screen.getByText(/Live/i)).toBeInTheDocument();
});
