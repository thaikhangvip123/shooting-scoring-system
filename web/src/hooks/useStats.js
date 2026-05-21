/**
 * hooks/useStats.js
 * Compatibility hook kept for callers while stats/heatmap are computed client-side.
 */

export function useStats() {
  return {
    stats: null,
    heatmap: null,
    statsLoading: false,
  };
}

