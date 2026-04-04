/**
 * components/stats/StatsPanel.jsx
 * Displays key ballistic metrics: CEP, R50, Group Size, Mean POI.
 * Uses backend stats when available, falls back to client-side calc.
 */

import { useMemo } from 'react';
import { calcCEP, calcR50, calcGroupSize, calcMeanPOI, radialDeviation } from '@/utils/scoring';
import { fmtMm, fmtSigned } from '@/utils/format';
import StatCard from './StatCard';

export default function StatsPanel({ shots = [], stats = null }) {
  // Client-side fallback calculations
  const computed = useMemo(() => {
    if (!shots.length) return {};
    const radii    = shots.map((s) => radialDeviation(s.x_mm, s.y_mm));
    const cep      = stats?.cep       ?? calcCEP(radii);
    const r50      = stats?.r50       ?? calcR50(shots);
    const group    = stats?.group_size ?? calcGroupSize(shots);
    const poi      = calcMeanPOI(shots);
    const avgScore = shots.reduce((s, sh) => s + (sh.score ?? 0), 0) / shots.length;
    const hitRate  = shots.filter((s) => s.score > 0).length / shots.length;
    return { cep, r50, group, poi, avgScore, hitRate };
  }, [shots, stats]);

  const { cep, r50, group, poi, avgScore, hitRate } = computed;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
        gap: 12,
      }}
    >
      <StatCard
        label="CEP"
        value={fmtMm(cep)}
        sub="50% of shots inside"
        color="var(--c-accent-h)"
        icon="◎"
      />
      <StatCard
        label="R50"
        value={fmtMm(r50)}
        sub="Group centre radius"
        color="#a78bfa"
        icon="⊙"
      />
      <StatCard
        label="Group Size"
        value={fmtMm(group)}
        sub="Extreme spread"
        color="#34d399"
        icon="↔"
      />
      <StatCard
        label="Avg Score"
        value={avgScore != null ? avgScore.toFixed(1) : '—'}
        sub={`${shots.length} shots`}
        color="#fbbf24"
        icon="★"
      />
      <StatCard
        label="Mean POI"
        value={
          poi
            ? `${fmtSigned(poi.x)} / ${fmtSigned(poi.y)}`
            : '—'
        }
        sub="X / Y offset (mm)"
        color="#fb923c"
        icon="⊕"
      />
      <StatCard
        label="Hit Rate"
        value={hitRate != null ? `${(hitRate * 100).toFixed(0)} %` : '—'}
        sub="Scoring shots"
        color={hitRate > 0.9 ? 'var(--c-success)' : 'var(--c-warn)'}
        icon="✓"
      />
    </div>
  );
}