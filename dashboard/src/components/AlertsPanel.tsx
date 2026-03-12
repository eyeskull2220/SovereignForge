import React from 'react';

export interface AlertItem {
  id: string;
  type: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  message: string;
  timestamp: string;
}

interface AlertsPanelProps {
  alerts?: AlertItem[];
}

const PRIORITY_COLOR: Record<string, string> = {
  critical: '#fc8181',
  high: '#f6ad55',
  medium: '#63b3ed',
  low: '#68d391',
};

const AlertsPanel: React.FC<AlertsPanelProps> = ({ alerts = [] }) => (
  <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 8, padding: 16 }}>
    <h3 style={{ color: '#e2e8f0', margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>
      Alerts <span style={{ color: '#718096', fontWeight: 400 }}>({alerts.length})</span>
    </h3>
    {alerts.length === 0 ? (
      <p style={{ color: '#718096', fontSize: 13, margin: 0 }}>No active alerts</p>
    ) : (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 300, overflowY: 'auto' }}>
        {alerts.map(alert => (
          <div key={alert.id} style={{
            background: '#2d3748',
            borderLeft: `3px solid ${PRIORITY_COLOR[alert.type] ?? '#718096'}`,
            borderRadius: 4,
            padding: '8px 12px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
              <span style={{ color: PRIORITY_COLOR[alert.type], fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
                {alert.type}
              </span>
              <span style={{ color: '#718096', fontSize: 11 }}>{alert.timestamp}</span>
            </div>
            <div style={{ color: '#e2e8f0', fontSize: 13, fontWeight: 600 }}>{alert.title}</div>
            <div style={{ color: '#a0aec0', fontSize: 12, marginTop: 2 }}>{alert.message}</div>
          </div>
        ))}
      </div>
    )}
  </div>
);

export default AlertsPanel;
