/**
 * hooks/useStats.js
 * Polls /stats and /heatmap at a configurable interval.
 * Stats are re-fetched whenever `shotCount` changes (passed by caller)
 * so the stats always stay in sync without unnecessary polling.
 */

import { useState, useEffect, useCallback } from 'react';
import { getStats, getHeatmap } from '@/api/client';

const POLL_MS = 5000; // fallback polling interval

/**
 * @param {number} shotCount – dependency from useShots to trigger re-fetch
 * @returns {{ stats: object|null, heatmap: number[][]|null, statsLoading: boolean }}
 */
export function useStats(shotCount = 0) {
  const [stats,        setStats]        = useState(null);
  const [heatmap,      setHeatmap]      = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([getStats(), getHeatmap(50)]);
      setStats(s);
      setHeatmap(h?.grid ?? null);
    } catch (e) {
      console.warn('[useStats]', e.message);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  // Re-fetch whenever a new shot arrives
  useEffect(() => {
    fetchAll();
  }, [shotCount, fetchAll]);

  // Fallback polling in case WebSocket misses events
  useEffect(() => {
    const id = setInterval(fetchAll, POLL_MS);
    return () => clearInterval(id);
  }, [fetchAll]);

  return { stats, heatmap, statsLoading };
}