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
import { fmtSignedMm, shotOffsetMm } from '@/utils/units';
import { useEffect, useState } from 'react';

export default function DashboardPage({
  shots,
  currentShots,
  stats,
  targetType,
  onTargetTypeChange,
  session,
  onStartSession,
  onShotsPerSessionChange,
}) {
  const visibleShots = currentShots ?? shots;
  const targetShots = visibleShots.filter((shot) => shotTargetType(shot) === targetType);
  const latestTargetShot = targetShots[0] ?? null;
  const [draftShotsPerSession, setDraftShotsPerSession] = useState(session?.shots_per_session ?? 10);
  const [savingSession, setSavingSession] = useState(false);
  const [startingSession, setStartingSession] = useState(false);
  const sessionRunning = session?.status === 'running';
  const { color, label } = latestTargetShot
    ? scoreTargetShot(latestTargetShot, targetType)
    : {};
  const latestOffsetMm = latestTargetShot ? shotOffsetMm(latestTargetShot) : null;

  useEffect(() => {
    if (session?.shots_per_session) {
      setDraftShotsPerSession(session.shots_per_session);
    }
  }, [session?.shots_per_session]);

  const handleSessionSave = async () => {
    const next = Math.min(15, Math.max(5, Number(draftShotsPerSession) || 10));
    setDraftShotsPerSession(next);
    setSavingSession(true);
    try {
      await onShotsPerSessionChange?.(next);
    } finally {
      setSavingSession(false);
    }
  };

  const handleStartSession = async () => {
    setStartingSession(true);
    try {
      await onStartSession?.(targetType);
    } finally {
      setStartingSession(false);
    }
  };

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
                  <div>X: <b>{fmtSignedMm(latestOffsetMm.x, 1)}</b></div>
                  <div>Y: <b>{fmtSignedMm(latestOffsetMm.y, 1)}</b></div>
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
          <TargetTypeSelector value={targetType} onChange={onTargetTypeChange} disabled={sessionRunning} />
          <TargetCanvas shots={visibleShots} latestShot={latestTargetShot} targetType={targetType} />
          <div
            style={{
              width: '100%',
              borderTop: '1px solid var(--c-border)',
              paddingTop: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              fontSize: 12,
              color: 'var(--c-text-2)',
            }}
          >
            <span style={{ fontWeight: 600, color: 'var(--c-text-1)' }}>Session shots</span>
            <input
              type="number"
              min="5"
              max="15"
              value={draftShotsPerSession}
              onChange={(event) => setDraftShotsPerSession(event.target.value)}
              style={{
                width: 64,
                height: 32,
                border: '1px solid var(--c-border)',
                borderRadius: 6,
                background: 'var(--c-bg-0)',
                color: 'var(--c-text-1)',
                padding: '0 8px',
                fontSize: 13,
              }}
            />
            <span>5-15</span>
            {session?.completed && (
              <span
                style={{
                  color: 'var(--c-success)',
                  fontWeight: 700,
                  marginLeft: 4,
                  whiteSpace: 'nowrap',
                }}
              >
                Session complete
              </span>
            )}
            {sessionRunning && (
              <span
                style={{
                  color: 'var(--c-accent)',
                  fontWeight: 700,
                  marginLeft: 4,
                  whiteSpace: 'nowrap',
                }}
              >
                Running
              </span>
            )}
            <button
              className="btn primary"
              onClick={handleStartSession}
              disabled={startingSession || sessionRunning}
              style={{ marginLeft: 'auto' }}
            >
              {startingSession ? 'Starting...' : 'Start Session'}
            </button>
            <button
              className="btn"
              onClick={handleSessionSave}
              disabled={
                savingSession ||
                sessionRunning ||
                (!session?.completed && Number(draftShotsPerSession) === session?.shots_per_session)
              }
            >
              {savingSession ? 'Saving...' : session?.completed ? 'Apply New Session' : 'Apply'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Right column: Stats + histogram ─────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        <StatsPanel shots={targetShots} stats={stats} />
        <ScoreHistogram shots={targetShots} />

        {/* Recent shots mini-list */}
        <div className="card" style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <div className="card-header">
            <span className="card-title">Recent Shots</span>
            <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>last 10</span>
          </div>
          <div style={{ overflowY: 'auto', maxHeight: 220 }}>
            {shots.slice(0, 10).map((s, i) => {
              const { color: sc, label: sl } = scoreTargetShot(s, shotTargetType(s));
              const offset = shotOffsetMm(s);
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
                    ({fmtSignedMm(offset.x, 1)}, {fmtSignedMm(offset.y, 1)})
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
