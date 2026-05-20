/**
 * components/stats/StatsPanel.jsx
 * Displays key ballistic metrics in A4 millimetres.
 */

import { useMemo } from 'react';
import { calcCEP, calcR50, calcGroupSize, calcMeanPOI, radialDeviation } from '@/utils/scoring';
import { fmtSignedMm, shotOffsetMm } from '@/utils/units';
import StatCard from './StatCard';

export default function StatsPanel({ shots = [] }) {
  const computed = useMemo(() => {
    if (!shots.length) return {};
    const mmShots = shots.map((shot) => ({ ...shot, ...shotOffsetMm(shot) }));
    const radii = mmShots.map((shot) => radialDeviation(shot.x, shot.y));
    const avgScore = shots.reduce((sum, shot) => sum + (shot.score ?? 0), 0) / shots.length;
    const hitRate = shots.filter((shot) => shot.score > 0).length / shots.length;

    return {
      cep: calcCEP(radii),
      r50: calcR50(mmShots),
      group: calcGroupSize(mmShots),
      poi: calcMeanPOI(mmShots),
      avgScore,
      hitRate,
    };
  }, [shots]);

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
        value={cep != null ? `${cep.toFixed(1)} mm` : '-'}
        sub="50% of shots inside"
        color="var(--c-accent-h)"
        icon="◎"
      />
      <StatCard
        label="R50"
        value={r50 != null ? `${r50.toFixed(1)} mm` : '-'}
        sub="Group centre radius"
        color="#a78bfa"
        icon="⊙"
      />
      <StatCard
        label="Group Size"
        value={group != null ? `${group.toFixed(1)} mm` : '-'}
        sub="Extreme spread"
        color="#34d399"
        icon="↔"
      />
      <StatCard
        label="Avg Score"
        value={avgScore != null ? avgScore.toFixed(1) : '-'}
        sub={`${shots.length} shots`}
        color="#fbbf24"
        icon="★"
      />
      <StatCard
        label="Mean POI"
        value={poi ? `${fmtSignedMm(poi.x)} / ${fmtSignedMm(poi.y)}` : '-'}
        sub="X / Y offset (mm)"
        color="#fb923c"
        icon="⊕"
      />
      <StatCard
        label="Hit Rate"
        value={hitRate != null ? `${(hitRate * 100).toFixed(0)} %` : '-'}
        sub="Scoring shots"
        color={hitRate > 0.9 ? 'var(--c-success)' : 'var(--c-warn)'}
        icon="✓"
      />
    </div>
  );
}
