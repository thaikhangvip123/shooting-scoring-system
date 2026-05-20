/**
 * hooks/useShots.js
 * Manages shot history, live WebSocket updates, session status, and reset.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getShotHistory,
  getSessionStatus,
  openShotsSocket,
  resetSession,
  updateSessionSettings,
} from '@/api/client';

const MAX_SHOTS       = 500;
const INITIAL_BACKOFF = 1000;
const MAX_BACKOFF     = 30000;

function dedupeById(items = []) {
  const seen = new Set();
  const out = [];
  for (const item of items) {
    const id = item?.id;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(item);
  }
  return out;
}

export function useShots() {
  const [shots, setShots]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [session, setSession]   = useState(null);
  const [wsStatus, setWsStatus] = useState('connecting');

  const wsRef      = useRef(null);
  const backoffRef = useRef(INITIAL_BACKOFF);
  const retryTimer = useRef(null);
  const mounted    = useRef(true);

  const fetchHistory = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getShotHistory(MAX_SHOTS);
      if (mounted.current) {
        const history = Array.isArray(data) ? data : data.shots ?? [];
        setShots(dedupeById(history).slice(0, MAX_SHOTS));
      }
    } catch (e) {
      if (mounted.current) setError(e.message);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  const fetchSession = useCallback(async () => {
    try {
      const data = await getSessionStatus();
      if (mounted.current) setSession(data);
      return data;
    } catch (e) {
      if (mounted.current) setError(e.message);
      return null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!mounted.current) return;
    setWsStatus('connecting');

    const ws = openShotsSocket(
      (shot) => {
        if (!mounted.current) return;
        backoffRef.current = INITIAL_BACKOFF;
        setShots((prev) => {
          const next = dedupeById([shot, ...prev]);
          return next.length > MAX_SHOTS ? next.slice(0, MAX_SHOTS) : next;
        });
        fetchSession();
        setWsStatus('open');
      },
      () => {
        if (mounted.current) setWsStatus('error');
      },
      (message) => {
        if (!mounted.current) return;
        if (message.type === 'session_reset' && message.session_id) {
          setShots((prev) => prev.filter((shot) => shot.session_id !== message.session_id));
        }
        if (message.session) {
          setSession(message.session);
        } else {
          fetchSession();
        }
      }
    );

    ws.addEventListener('open', () => {
      if (mounted.current) setWsStatus('open');
    });
    ws.addEventListener('close', () => {
      if (!mounted.current) return;
      setWsStatus('closed');
      retryTimer.current = setTimeout(() => {
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);
        connect();
      }, backoffRef.current);
    });

    wsRef.current = ws;
  }, [fetchSession]);

  const reset = useCallback(async () => {
    try {
      setError(null);
      await resetSession();
      await Promise.all([fetchHistory(), fetchSession()]);
    } catch (e) {
      if (mounted.current) setError(e.message);
    }
  }, [fetchHistory, fetchSession]);

  const setShotsPerSession = useCallback(async (count) => {
    try {
      setError(null);
      const next = await updateSessionSettings(count);
      if (mounted.current) setSession(next);
    } catch (e) {
      if (mounted.current) setError(e.message);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    fetchHistory();
    fetchSession();
    connect();

    return () => {
      mounted.current = false;
      clearTimeout(retryTimer.current);
      wsRef.current?.close();
    };
  }, [fetchHistory, fetchSession, connect]);

  return {
    shots,
    latestShot: shots[0] ?? null,
    loading,
    error,
    session,
    wsStatus,
    reset,
    setShotsPerSession,
  };
}

