import React from 'react';
import { render, screen } from '@testing-library/react';
import Header from './Header';

test('renders SovereignForge brand', () => {
  render(<Header />);
  expect(screen.getByText(/SovereignForge/i)).toBeInTheDocument();
});

test('shows MiCA compliance badge', () => {
  render(<Header />);
  expect(screen.getByText(/MiCA Compliant/i)).toBeInTheDocument();
  expect(screen.getByText(/USDC Only/i)).toBeInTheDocument();
});

test('shows disconnected status by default', () => {
  render(<Header />);
  expect(screen.getByText('Disconnected')).toBeInTheDocument();
});

test('shows live when connected', () => {
  render(<Header isConnected={true} lastUpdate="12:00:00" />);
  expect(screen.getByText('Live')).toBeInTheDocument();
  expect(screen.getByText(/12:00:00/)).toBeInTheDocument();
});
