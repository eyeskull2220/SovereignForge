import React from 'react';

interface HeaderProps {
  isConnected?: boolean;
  lastUpdate?: string;
  onMenuToggle?: () => void;
}

const hamburgerStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#e2e8f0',
  fontSize: 22,
  cursor: 'pointer',
  padding: '4px 8px',
  display: 'none', // hidden on desktop
};

const Header: React.FC<HeaderProps> = ({ isConnected = false, lastUpdate = '--', onMenuToggle }) => (
  <header style={{
    background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
    color: '#e2e8f0',
    padding: '12px 24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottom: '1px solid #2d3748',
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      {onMenuToggle && (
        <button
          onClick={onMenuToggle}
          style={hamburgerStyle}
          className="mobile-menu-btn"
          aria-label="Toggle menu"
        >
          {'\u2630'}
        </button>
      )}
      <span style={{ fontSize: 22, fontWeight: 700, letterSpacing: 1 }}>SovereignForge</span>
      <span style={{ fontSize: 11, background: '#2d3748', padding: '2px 8px', borderRadius: 4, color: '#90cdf4' }}>
        MiCA Compliant · USDC Only
      </span>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 13 }}>
      <span style={{ color: '#718096' }}>Last update: {lastUpdate}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: isConnected ? '#68d391' : '#fc8181' }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: isConnected ? '#68d391' : '#fc8181', display: 'inline-block' }} />
        {isConnected ? 'Live' : 'Disconnected'}
      </span>
    </div>
  </header>
);

export default Header;
