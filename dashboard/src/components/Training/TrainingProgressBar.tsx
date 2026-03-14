import React from 'react';

interface TrainingProgressBarProps {
  strategy: string;
  pair: string;
  exchange: string;
  currentEpoch: number;
  totalEpochs: number;
  isActive: boolean;
}

const TrainingProgressBar: React.FC<TrainingProgressBarProps> = ({
  strategy,
  pair,
  exchange,
  currentEpoch,
  totalEpochs,
  isActive,
}) => {
  const pct = totalEpochs > 0 ? (currentEpoch / totalEpochs) * 100 : 0;

  return (
    <div style={{
      background: '#161b22',
      border: '1px solid #30363d',
      borderRadius: 8,
      padding: '12px 16px',
    }}>
      <div style={{
        fontSize: 13,
        color: '#e2e8f0',
        marginBottom: 8,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>
          Training: <strong>{strategy}</strong>{' '}
          {pair}<span style={{ color: '#8b949e' }}>@{exchange}</span>
          {' '}&mdash; Epoch {currentEpoch}/{totalEpochs}
        </span>
        {isActive && (
          <span style={{ fontSize: 11, color: '#3fb950' }}>RUNNING</span>
        )}
      </div>
      <div style={{
        height: 10,
        background: '#21262d',
        borderRadius: 5,
        overflow: 'hidden',
        position: 'relative',
      }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: 'linear-gradient(90deg, #238636, #3fb950)',
          borderRadius: 5,
          transition: 'width 0.6s ease',
          ...(isActive ? {
            animation: 'pulse-bar 1.8s ease-in-out infinite',
          } : {}),
        }} />
      </div>
      <style>{`
        @keyframes pulse-bar {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.65; }
        }
      `}</style>
    </div>
  );
};

export default TrainingProgressBar;
