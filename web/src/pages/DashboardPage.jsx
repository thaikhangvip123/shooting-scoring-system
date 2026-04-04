/**
 * pages/DashboardPage.jsx
 * Main overview: target + latest shot + stats + score histogram.
 */

import TargetCanvas    from '@/components/target/TargetCanvas';
import StatsPanel      from '@/components/stats/StatsPanel';
import ScoreHistogram  from '@/components/charts/ScoreHistogram';
import { fmtRelative } from '@/utils/format';
import { scoreShot }   from '@/utils/scoring';

export default function DashboardPage({ shots, latestShot, stats }) {
  const { color, label } = latestShot
    ? scoreShot(latestShot.x_mm, latestShot.y_mm)
    : {};

  return (
    <div style={{ display: 'flex', gap: 20, height: '100%', minHeight: 0 }}>
      {/* ── Left column: Target ──────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, width: 340, flexShrink: 0 }}>
        {/* Latest shot card */}
        <div className="card" style={{ padding: '16px 20px' }}>
          {latestShot ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Latest Shot
                </span>
                <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>
                  {fmtRelative(latestShot.timestamp)}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 8 }}>
                <span style={{ fontSize: 42, fontWeight: 800, color, lineHeight: 1, fontFamily: 'monospace' }}>
                  {latestShot.score}
                </span>
                <span style={{ fontSize: 18, fontWeight: 600, color, opacity: 0.7 }}>
                  {label}
                </span>
                <div style={{ marginLeft: 'auto', textAlign: 'right', fontSize: 12, color: 'var(--c-text-2)' }}>
                  <div>X: <b>{latestShot.x_mm?.toFixed(1)} mm</b></div>
                  <div>Y: <b>{latestShot.y_mm?.toFixed(1)} mm</b></div>
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
        <div className="card" style={{ padding: 16, display: 'flex', justifyContent: 'center' }}>
          <TargetCanvas shots={shots} latestShot={latestShot} />
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
            {shots.slice(0, 10).map((s, i) => {
              const { color: sc, label: sl } = scoreShot(s.x_mm, s.y_mm);
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
                    {shots.length - i}
                  </span>
                  <span style={{ fontWeight: 700, color: sc, fontSize: 15, width: 24 }}>
                    {s.score}
                  </span>
                  <span style={{ fontSize: 11, color: sc, opacity: 0.7, width: 18 }}>{sl}</span>
                  <span style={{ fontSize: 11, color: 'var(--c-text-3)', fontFamily: 'monospace' }}>
                    ({s.x_mm?.toFixed(1)}, {s.y_mm?.toFixed(1)})
                  </span>
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--c-text-3)' }}>
                    {new Date(s.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              );
            })}
            {shots.length === 0 && (
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