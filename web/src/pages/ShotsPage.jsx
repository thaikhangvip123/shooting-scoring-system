/**
 * pages/ShotsPage.jsx
 */
import { useMemo, useState } from 'react';
import ShotTable from '@/components/shots/ShotTable';
import { compareSessionsDesc, sessionLabelFromShot, sessionNumberFromShot } from '@/utils/session';

export default function ShotsPage({ shots, latestShot }) {
  const [selectedSessionId, setSelectedSessionId] = useState('all');

  const sessions = useMemo(() => {
    const byId = new Map();
    for (const shot of shots) {
      const sessionId = shot.session_id || 'unknown';
      const existing = byId.get(sessionId) ?? {
        sessionId,
        sessionNumber: sessionNumberFromShot(shot),
        label: sessionLabelFromShot(shot),
        count: 0,
        totalScore: 0,
        latestTime: null,
      };
      existing.count += 1;
      existing.totalScore += shot.score ?? 0;
      if (!existing.latestTime || new Date(shot.timestamp) > new Date(existing.latestTime)) {
        existing.latestTime = shot.timestamp;
      }
      byId.set(sessionId, existing);
    }
    return Array.from(byId.values()).sort(compareSessionsDesc);
  }, [shots]);

  const selectedShots = useMemo(() => {
    if (selectedSessionId === 'all') return shots;
    return shots.filter((shot) => (shot.session_id || 'unknown') === selectedSessionId);
  }, [shots, selectedSessionId]);

  const selectedSession = sessions.find((item) => item.sessionId === selectedSessionId);
  const totalScore = selectedShots.reduce((sum, shot) => sum + (shot.score ?? 0), 0);
  const averageScore = selectedShots.length ? (totalScore / selectedShots.length).toFixed(2) : '0.00';
  const tableTitle = selectedSession ? `${selectedSession.label} Shot Log` : 'Shot Log';

  return (
    <div style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div
        className="card"
        style={{
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          flexShrink: 0,
        }}
      >
        <label style={{ fontSize: 12, color: 'var(--c-text-3)', fontWeight: 700 }}>
          View session
        </label>
        <select
          value={selectedSessionId}
          onChange={(event) => setSelectedSessionId(event.target.value)}
          style={{
            minWidth: 180,
            height: 32,
            background: 'var(--c-bg-2)',
            border: '1px solid var(--c-border-2)',
            borderRadius: 6,
            color: 'var(--c-text-1)',
            padding: '0 10px',
            fontSize: 12,
            outline: 'none',
          }}
        >
          <option value="all">All sessions</option>
          {sessions.map((session) => (
            <option key={session.sessionId} value={session.sessionId}>
              {session.label} - {session.count} shots
            </option>
          ))}
        </select>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: 'var(--c-text-2)' }}>
          Shots <b style={{ color: 'var(--c-text-1)' }}>{selectedShots.length}</b>
        </span>
        <span style={{ fontSize: 12, color: 'var(--c-text-2)' }}>
          Total <b style={{ color: 'var(--c-accent-h)' }}>{totalScore}</b>
        </span>
        <span style={{ fontSize: 12, color: 'var(--c-text-2)' }}>
          Avg <b style={{ color: 'var(--c-text-1)' }}>{averageScore}</b>
        </span>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <ShotTable
          shots={selectedShots}
          latestId={latestShot?.id}
          title={tableTitle}
          emptyMessage={selectedSessionId === 'all' ? 'No shots recorded yet' : 'No shots in this session'}
        />
      </div>
    </div>
  );
}
