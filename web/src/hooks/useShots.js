/**
 * hooks/useShots.js
 * Manages the shots list with:
 *  – initial REST load on mount
 *  – live append via WebSocket
 *  – automatic reconnect with exponential back-off
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { getShotHistory, openShotsSocket } from '@/api/client';

const MAX_SHOTS        = 500;   // cap in-memory history
const INITIAL_BACKOFF  = 1000;  // ms
const MAX_BACKOFF      = 30000; // ms

/**
 * @returns {{
 *   shots:      object[],
 *   latestShot: object | null,
 *   loading:    boolean,
 *   error:      string | null,
 *   wsStatus:   'connecting'|'open'|'closed'|'error',
 *   reset:      () => void,
 * }}
 */
export function useShots() {
  const [shots,      setShots]     = useState([]);
  const [loading,    setLoading]   = useState(true);
  const [error,      setError]     = useState(null);
  const [wsStatus,   setWsStatus]  = useState('connecting');

  const wsRef      = useRef(null);
  const backoffRef = useRef(INITIAL_BACKOFF);
  const retryTimer = useRef(null);
  const mounted    = useRef(true);

  // ── Initial load ────────────────────────────────────────────────────────────
  const fetchHistory = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getShotHistory(MAX_SHOTS);
      if (mounted.current) {
        setShots(Array.isArray(data) ? data : data.shots ?? []);
      }
    } catch (e) {
      if (mounted.current) setError(e.message);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  // ── WebSocket connect (with reconnect) ──────────────────────────────────────
  const connect = useCallback(() => {
    if (!mounted.current) return;
    setWsStatus('connecting');

    const ws = openShotsSocket(
      // onShot
      (shot) => {
        if (!mounted.current) return;
        backoffRef.current = INITIAL_BACKOFF; // reset on successful message
        setShots((prev) => {
          const next = [shot, ...prev];
          return next.length > MAX_SHOTS ? next.slice(0, MAX_SHOTS) : next;
        });
        setWsStatus('open');
      },
      // onError
      () => {
        if (mounted.current) setWsStatus('error');
      }
    );

    ws.addEventListener('open',  () => { if (mounted.current) setWsStatus('open'); });
    ws.addEventListener('close', () => {
      if (!mounted.current) return;
      setWsStatus('closed');
      // Exponential back-off reconnect
      retryTimer.current = setTimeout(() => {
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);
        connect();
      }, backoffRef.current);
    });

    wsRef.current = ws;
  }, []);

  // ── Reset helper ────────────────────────────────────────────────────────────
  const reset = useCallback(() => {
    setShots([]);
    fetchHistory();
  }, [fetchHistory]);

  // ── Effects ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    mounted.current = true;
    fetchHistory();
    connect();

    return () => {
      mounted.current = false;
      clearTimeout(retryTimer.current);
      wsRef.current?.close();
    };
  }, [fetchHistory, connect]);

  return {
    shots,
    latestShot: shots[0] ?? null,
    loading,
    error,
    wsStatus,
    reset,
  };
}