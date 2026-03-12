import React from 'react';
import { render, screen } from '@testing-library/react';
import AlertsPanel, { AlertItem } from './AlertsPanel';

test('shows "No active alerts" when empty', () => {
  render(<AlertsPanel alerts={[]} />);
  expect(screen.getByText('No active alerts')).toBeInTheDocument();
});

test('renders alert count', () => {
  const alerts: AlertItem[] = [
    { id: '1', type: 'critical', title: 'Test Alert', message: 'msg', timestamp: '12:00' },
    { id: '2', type: 'low', title: 'Info', message: 'msg2', timestamp: '12:01' },
  ];
  render(<AlertsPanel alerts={alerts} />);
  expect(screen.getByText('(2)')).toBeInTheDocument();
});

test('renders alert title and message', () => {
  const alerts: AlertItem[] = [
    { id: '1', type: 'high', title: 'Spread Alert', message: 'XRP spread widening', timestamp: '12:00' },
  ];
  render(<AlertsPanel alerts={alerts} />);
  expect(screen.getByText('Spread Alert')).toBeInTheDocument();
  expect(screen.getByText('XRP spread widening')).toBeInTheDocument();
});

test('renders alert type label', () => {
  const alerts: AlertItem[] = [
    { id: '1', type: 'critical', title: 'T', message: 'M', timestamp: '12:00' },
  ];
  render(<AlertsPanel alerts={alerts} />);
  expect(screen.getByText('critical')).toBeInTheDocument();
});
