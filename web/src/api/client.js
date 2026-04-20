/**
 * api/client.js
 * Centralised HTTP client for the Shooting Scoring backend.
 * Base URL is picked from the VITE_API_URL env-var (falls back to /api for
 * the Vite proxy when running in dev mode).
 */

import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api';
const WS_URL   = import.meta.env.VITE_WS_URL  ?? `ws://${window.location.host}/ws`;

// ─── Axios instance ──────────────────────────────────────────────────────────

const http = axios.create({
  baseURL: BASE_URL,
  timeout: 10_000,
  headers: { 'Content-Type': 'application/json' },
});

// Global response interceptor for unified error handling
http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg = err.response?.data?.detail ?? err.message ?? 'Unknown error';
    console.error('[API]', msg);
    return Promise.reject(new Error(msg));
  }
);

// ─── Endpoints ───────────────────────────────────────────────────────────────

/** POST a new shot from the CV pipeline */
export const postShot = (shot) => http.post('/shot', shot);

/** GET the most recent shot */
export const getLatestShot = () => http.get('/latest');

/**
 * GET shot history with optional pagination.
 * @param {number} limit  – max records to return (default 200)
 * @param {number} offset – pagination offset
 */
export const getShotHistory = (limit = 200, offset = 0) =>
  http.get('/history', { params: { limit, offset } });

/**
 * GET aggregated stats: CEP, R50, grouping, ring distribution.
 * @param {string} sessionId – optional session filter
 */
export const getStats = (sessionId = null) =>
  http.get('/stats', { params: sessionId ? { session_id: sessionId } : {} });

/** GET heatmap bin data (NxN grid of hit counts) */
export const getHeatmap = (resolution = 50) =>
  http.get('/heatmap', { params: { resolution } });

/** DELETE all shots (reset session) */
export const resetSession = () => http.delete('/shots');

// ─── WebSocket factory ────────────────────────────────────────────────────────

/**
 * Opens a WebSocket connection to /ws/shots.
 * Returns the WebSocket instance so the caller controls lifecycle.
 *
 * @param {(shot: object) => void} onShot   – called for each new shot event
 * @param {(err:  Event)  => void} onError  – called on connection error
 * @returns {WebSocket}
 */
export const openShotsSocket = (onShot, onError) => {
  const ws = new WebSocket(`${WS_URL}/shots`);

  ws.onopen = () => console.info('[WS] Connected to /ws/shots');

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      // Backend sends control messages too; don't treat them as shots.
      if (data?.type === 'connected' || data?.type === 'ping') return;
      onShot(data);
    } catch (e) {
      console.warn('[WS] Unparseable message', event.data);
    }
  };

  ws.onerror = (err) => {
    console.error('[WS] Error', err);
    onError?.(err);
  };

  ws.onclose = (e) => console.info('[WS] Closed', e.code, e.reason);

  return ws;
};

export default http;