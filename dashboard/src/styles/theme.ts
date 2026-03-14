import type { CSSProperties } from 'react';

// ---------------------------------------------------------------------------
// Color palette
// ---------------------------------------------------------------------------
export const colors = {
  bg: {
    primary: '#0d1117',
    card: '#161b22',
    hover: '#21262d',
    input: '#0d1117',
  },
  text: {
    primary: '#e2e8f0',
    secondary: '#a0aec0',
    muted: '#718096',
    dim: '#8b949e',
  },
  border: {
    primary: '#30363d',
    secondary: '#21262d',
    table: '#2d3748',
  },
  status: {
    green: '#3fb950',
    red: '#f85149',
    yellow: '#d29922',
    blue: '#58a6ff',
    greenText: '#68d391',
    redText: '#fc8181',
    orange: '#f6ad55',
  },
} as const;

// ---------------------------------------------------------------------------
// Shared component styles
// ---------------------------------------------------------------------------
export const cardStyle: CSSProperties = {
  background: colors.bg.card,
  border: `1px solid ${colors.border.primary}`,
  borderRadius: 8,
  padding: 16,
};

export const thStyle: CSSProperties = {
  color: colors.text.muted,
  padding: '4px 8px',
  textAlign: 'right',
  fontWeight: 500,
  whiteSpace: 'nowrap',
};

export const tdStyle: CSSProperties = {
  color: colors.text.primary,
  padding: '6px 8px',
  textAlign: 'right',
};

export const sectionTitleStyle: CSSProperties = {
  color: colors.text.primary,
  margin: 0,
  fontSize: 18,
  fontWeight: 700,
};
