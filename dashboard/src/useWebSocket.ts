import { useState, useEffect, useRef, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface WebSocketMessage {
  type: string;
  payload: unknown;
}

export type WSStatus = 'connecting' | 'open' | 'closed' | 'error';

export interface UseWebSocketOptions {
  /** Reconnect automatically on close/error (default: true) */
  autoReconnect?: boolean;
  /** Base delay in ms before first reconnect attempt (default: 1000) */
  reconnectDelay?: number;
  /** Maximum reconnect delay in ms with exponential backoff (default: 30000) */
  maxReconnectDelay?: number;
  /** Max reconnect attempts before giving up (default: Infinity) */
  maxAttempts?: number;
  /** Called with each parsed message */
  onMessage?: (msg: WebSocketMessage) => void;
  /** Called when connection opens */
  onOpen?: () => void;
  /** Called when connection closes */
  onClose?: (event: CloseEvent) => void;
  /** Called on error */
  onError?: (event: Event) => void;
}

export interface UseWebSocketReturn {
  status: WSStatus;
  lastMessage: WebSocketMessage | null;
  send: (msg: WebSocketMessage) => void;
  reconnectAttempts: number;
  disconnect: () => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export function useWebSocket(
  url: string | null,
  options: UseWebSocketOptions = {}
): UseWebSocketReturn {
  const {
    autoReconnect = true,
    reconnectDelay = 1000,
    maxReconnectDelay = 30_000,
    maxAttempts = Infinity,
    onMessage,
    onOpen,
    onClose,
    onError,
  } = options;

  const [status, setStatus] = useState<WSStatus>('closed');
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const isMounted = useRef(true);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptsRef = useRef(0);

  const clearReconnectTimer = () => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
  };

  const connect = useCallback(() => {
    if (!url || !isMounted.current) return;

    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
      wsRef.current.close();
    }

    setStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMounted.current) return;
      attemptsRef.current = 0;
      setReconnectAttempts(0);
      setStatus('open');
      onOpen?.();
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!isMounted.current) return;
      try {
        const msg: WebSocketMessage = JSON.parse(event.data as string);
        setLastMessage(msg);
        onMessage?.(msg);
      } catch {
        // Ignore non-JSON frames
      }
    };

    ws.onerror = (event: Event) => {
      if (!isMounted.current) return;
      setStatus('error');
      onError?.(event);
    };

    ws.onclose = (event: CloseEvent) => {
      if (!isMounted.current) return;
      setStatus('closed');
      onClose?.(event);

      if (autoReconnect && attemptsRef.current < maxAttempts) {
        const delay = Math.min(
          reconnectDelay * 2 ** attemptsRef.current,
          maxReconnectDelay
        );
        attemptsRef.current += 1;
        setReconnectAttempts(attemptsRef.current);

        reconnectTimer.current = setTimeout(() => {
          if (isMounted.current) connect();
        }, delay);
      }
    };
  }, [url, autoReconnect, reconnectDelay, maxReconnectDelay, maxAttempts, onMessage, onOpen, onClose, onError]);

  // Connect on mount / url change
  useEffect(() => {
    isMounted.current = true;
    if (url) connect();

    return () => {
      isMounted.current = false;
      clearReconnectTimer();
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on intentional unmount
        wsRef.current.close();
      }
    };
  }, [url]); // eslint-disable-line react-hooks/exhaustive-deps

  const send = useCallback((msg: WebSocketMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    } else {
      console.warn('[useWebSocket] Cannot send — socket not open');
    }
  }, []);

  const disconnect = useCallback(() => {
    clearReconnectTimer();
    attemptsRef.current = maxAttempts; // Prevent auto-reconnect
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      setStatus('closed');
    }
  }, [maxAttempts]);

  return { status, lastMessage, send, reconnectAttempts, disconnect };
}

export default useWebSocket;
