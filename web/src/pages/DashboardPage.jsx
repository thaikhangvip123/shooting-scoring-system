/**
 * pages/DashboardPage.jsx
 * Main overview: target + latest shot + stats + score histogram.
 */

import TargetCanvas    from '@/components/target/TargetCanvas';
import TargetTypeSelector from '@/components/target/TargetTypeSelector';
import StatsPanel      from '@/components/stats/StatsPanel';
import ScoreHistogram  from '@/components/charts/ScoreHistogram';
import { fmtRelative } from '@/utils/format';
import { scoreTargetShot, shotTargetType } from '@/utils/targetGeometry';

export default function DashboardPage({ shots, latestShot, stats, targetType, onTargetTypeChange }) {
  const targetShots = shots.filter((shot) => shotTargetType(shot) === targetType);
  const latestTargetShot = targetShots[0] ?? null;
  const { color, label } = latestTargetShot
    ? scoreTargetShot(latestTargetShot, targetType)
    : {};

  return (
    <div style={{ display: 'flex', gap: 20, height: '100%', minHeight: 0 }}>
      {/* ── Left column: Target ──────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, width: 534, flexShrink: 0 }}>
        {/* Latest shot card */}
        <div className="card" style={{ padding: '16px 20px' }}>
          {latestTargetShot ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Latest Shot
                </span>
                <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>
                  {fmtRelative(latestTargetShot.timestamp)}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 8 }}>
                <span style={{ fontSize: 42, fontWeight: 800, color, lineHeight: 1, fontFamily: 'monospace' }}>
                  {latestTargetShot.score}
                </span>
                <span style={{ fontSize: 18, fontWeight: 600, color, opacity: 0.7 }}>
                  {label}
                </span>
                <div style={{ marginLeft: 'auto', textAlign: 'right', fontSize: 12, color: 'var(--c-text-2)' }}>
                  <div>X: <b>{Number(latestTargetShot.x_px ?? latestTargetShot.x_mm ?? 0).toFixed(1)} px</b></div>
                  <div>Y: <b>{Number(latestTargetShot.y_px ?? latestTargetShot.y_mm ?? 0).toFixed(1)} px</b></div>
                </div>
              </div>
            </>
          ) : (
            <div style={{ textAlign: 'center', color: 'var(--c-text-3)', padding: '8px 0' }}>
              Waiting for first shot…
            </div>
          )}
        </div>

        {/* Target */}
        <div className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
          <TargetTypeSelector value={targetType} onChange={onTargetTypeChange} />
          <TargetCanvas shots={shots} latestShot={latestTargetShot} targetType={targetType} />
        </div>
      </div>

      {/* ── Right column: Stats + histogram ─────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        <StatsPanel shots={shots} stats={stats} />
        <ScoreHistogram shots={shots} />

        {/* Recent shots mini-list */}
        <div className="card" style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <div className="card-header">
            <span className="card-title">Recent Shots</span>
            <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>last 10</span>
          </div>
          <div style={{ overflowY: 'auto', maxHeight: 220 }}>
            {targetShots.slice(0, 10).map((s, i) => {
              const { color: sc, label: sl } = scoreTargetShot(s, targetType);
              return (
                <div
                  key={s.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '7px 18px',
                    borderBottom: '1px solid var(--c-border)',
                    gap: 12,
                    background: i === 0 ? 'rgba(59,127,255,0.06)' : 'transparent',
                  }}
                >
                  <span style={{ color: 'var(--c-text-3)', fontSize: 11, width: 18, textAlign: 'right' }}>
                    {targetShots.length - i}
                  </span>
                  <span style={{ fontWeight: 700, color: sc, fontSize: 15, width: 24 }}>
                    {s.score}
                  </span>
                  <span style={{ fontSize: 11, color: sc, opacity: 0.7, width: 18 }}>{sl}</span>
                  <span style={{ fontSize: 11, color: 'var(--c-text-3)', fontFamily: 'monospace' }}>
                    ({Number(s.x_px ?? s.x_mm ?? 0).toFixed(1)}, {Number(s.y_px ?? s.y_mm ?? 0).toFixed(1)})
                  </span>
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--c-text-3)' }}>
                    {new Date(s.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              );
            })}
            {targetShots.length === 0 && (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--c-text-3)' }}>
                No shots yet
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
