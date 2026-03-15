import { useState, useEffect, useRef, useCallback } from 'react';

const DEFAULT_WS_URL = 'ws://localhost:8001/ws';

/**
 * Hook that connects to the FreshFlow WebSocket endpoint, parses JSON messages,
 * and maintains a list of events plus connection status. Reconnects on close.
 * @param {string} [url] - WebSocket URL (default from env VITE_WS_URL or localhost:8001/ws)
 * @returns {{ events: object[], addEvent: (e: object) => void, clearEvents: () => void, connected: boolean }}
 */
export function useWebSocket(url = import.meta.env.VITE_WS_URL || DEFAULT_WS_URL) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);

  const addEvent = useCallback((payload) => {
    setEvents((prev) => [payload, ...prev].slice(0, 500));
  }, []);

  const clearEvents = useCallback(() => setEvents([]), []);

  useEffect(() => {
    let mounted = true;

    function connect() {
      if (!mounted) return;
      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          if (mounted) {
            setConnected(true);
            reconnectAttempts.current = 0;
          }
        };

        ws.onmessage = (event) => {
          if (!mounted) return;
          try {
            const payload = JSON.parse(event.data);
            addEvent(payload);
          } catch {
            // ignore non-JSON
          }
        };

        ws.onclose = () => {
          if (mounted) setConnected(false);
          if (!mounted) return;
          const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000);
          reconnectAttempts.current += 1;
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        };

        ws.onerror = () => {};
      } catch (err) {
        if (mounted) setConnected(false);
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      }
    }

    connect();
    return () => {
      mounted = false;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
      wsRef.current = null;
    };
  }, [url, addEvent]);

  return { events, addEvent, clearEvents, connected };
}
