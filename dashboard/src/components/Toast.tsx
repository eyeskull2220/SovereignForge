import React, { createContext, useCallback, useContext, useState } from 'react';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  addToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({ addToast: () => {} });

export const useToast = () => useContext(ToastContext);

let nextId = 0;

const typeColors: Record<ToastType, { bg: string; border: string; text: string }> = {
  success: { bg: '#0d2818', border: '#3fb950', text: '#3fb950' },
  error:   { bg: '#2d1117', border: '#f85149', text: '#f85149' },
  warning: { bg: '#2d2200', border: '#d29922', text: '#d29922' },
  info:    { bg: '#0d1d31', border: '#58a6ff', text: '#58a6ff' },
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++nextId;
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      {/* Toast container */}
      <div style={{
        position: 'fixed',
        top: 16,
        right: 16,
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        pointerEvents: 'none',
      }}>
        {toasts.map(toast => {
          const colors = typeColors[toast.type];
          return (
            <div
              key={toast.id}
              onClick={() => removeToast(toast.id)}
              style={{
                pointerEvents: 'auto',
                background: colors.bg,
                border: `1px solid ${colors.border}`,
                borderRadius: 8,
                padding: '10px 16px',
                color: colors.text,
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
                maxWidth: 360,
                boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
                animation: 'slideIn 0.2s ease-out',
              }}
            >
              {toast.message}
            </div>
          );
        })}
      </div>
      <style>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(20px); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </ToastContext.Provider>
  );
};
