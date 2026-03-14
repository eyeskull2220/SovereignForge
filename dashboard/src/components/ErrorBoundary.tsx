import React, { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div style={{
          background: '#161b22',
          border: '1px solid #f85149',
          borderRadius: 8,
          padding: 24,
          margin: '20px 0',
          textAlign: 'center',
        }}>
          <h3 style={{ color: '#f85149', margin: '0 0 8px', fontSize: 16 }}>
            Something went wrong
          </h3>
          <p style={{ color: '#8b949e', fontSize: 13, margin: '0 0 16px' }}>
            {this.state.error?.message ?? 'An unexpected error occurred.'}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              background: '#21262d',
              color: '#58a6ff',
              border: '1px solid #30363d',
              borderRadius: 6,
              padding: '8px 20px',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
