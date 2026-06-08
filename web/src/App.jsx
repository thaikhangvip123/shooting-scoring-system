/**
 * App.jsx
 * Root component: layout shell + React Router.
 * All pages receive shots/stats as props — single source of truth at the top.
 */

import { Routes, Route } from 'react-router-dom';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Sidebar       from '@/components/layout/Sidebar';
import Header        from '@/components/layout/Header';
import { useShots }  from '@/hooks/useShots';
import { useStats }  from '@/hooks/useStats';

import DashboardPage from '@/pages/DashboardPage';
import TargetPage    from '@/pages/TargetPage';
import ShotsPage     from '@/pages/ShotsPage';
import AnalyticsPage from '@/pages/AnalyticsPage';
import HeatmapPage   from '@/pages/HeatmapPage';
import SettingsPage  from '@/pages/SettingsPage';

const LIVE_SESSION = '__live__';

function sessionNumberFromId(sessionId) {
  const match = String(sessionId ?? '').match(/^session-(\d+)$/);
  return match ? Number(match[1]) : null;
}

function buildSessionSummaries(shots, session) {
  const summaries = new Map();

  shots.forEach((shot) => {
    if (!shot.session_id) return;
    const current = summaries.get(shot.session_id) ?? {
      id: shot.session_id,
      number: sessionNumberFromId(shot.session_id),
      shotCount: 0,
      totalScore: 0,
      latestTimestamp: null,
      targetType: shot.metadata?.target_type ?? null,
      status: null,
      isCurrent: false,
    };

    current.shotCount += 1;
    current.totalScore += shot.score ?? 0;
    if (!current.latestTimestamp || new Date(shot.timestamp) > new Date(current.latestTimestamp)) {
      current.latestTimestamp = shot.timestamp;
    }
    if (!current.targetType && shot.metadata?.target_type) current.targetType = shot.metadata.target_type;
    summaries.set(shot.session_id, current);
  });

  if (session?.session_id) {
    const current = summaries.get(session.session_id) ?? {
      id: session.session_id,
      number: session.session_number ?? sessionNumberFromId(session.session_id),
      shotCount: 0,
      totalScore: 0,
      latestTimestamp: session.started_at ?? session.completed_at ?? null,
      targetType: session.target_type ?? null,
      status: session.status ?? null,
      isCurrent: true,
    };
    current.number = session.session_number ?? current.number;
    current.shotCount = Math.max(current.shotCount, session.shot_count ?? 0);
    current.targetType = session.target_type ?? current.targetType;
    current.status = session.status ?? current.status;
    current.isCurrent = true;
    summaries.set(session.session_id, current);
  }

  return Array.from(summaries.values()).sort((a, b) => {
    if (a.number != null && b.number != null && a.number !== b.number) return b.number - a.number;
    return new Date(b.latestTimestamp ?? 0) - new Date(a.latestTimestamp ?? 0);
  });
}

export default function App() {
  const {
    shots,
    loading,
    error,
    session,
    wsStatus,
    start,
    reset,
    setShotsPerSession,
  } = useShots();
  const currentSessionId = session?.session_id ?? null;
  const [selectedSessionId, setSelectedSessionId] = useState(LIVE_SESSION);
  const sessionSummaries = useMemo(() => buildSessionSummaries(shots, session), [shots, session]);
  const activeSessionId = selectedSessionId === LIVE_SESSION ? currentSessionId : selectedSessionId;
  const selectedShots = activeSessionId
    ? shots.filter((shot) => shot.session_id === activeSessionId)
    : shots;
  const latestShot = selectedShots[0] ?? null;
  const { stats, heatmap }                                       = useStats(selectedShots.length, activeSessionId);
  const [targetType, setTargetType]                              = useState('TRON');
  const activeSessionSummary = sessionSummaries.find((summary) => summary.id === activeSessionId);
  const activeSessionTargetType = activeSessionId === currentSessionId
    ? session?.target_type ?? activeSessionSummary?.targetType
    : activeSessionSummary?.targetType;

  useEffect(() => {
    if (selectedSessionId === LIVE_SESSION) return;
    if (!sessionSummaries.some((summary) => summary.id === selectedSessionId)) {
      setSelectedSessionId(LIVE_SESSION);
    }
  }, [selectedSessionId, sessionSummaries]);

  useEffect(() => {
    if (!activeSessionTargetType) return;
    setTargetType((current) => (
      current === activeSessionTargetType ? current : activeSessionTargetType
    ));
  }, [activeSessionId, activeSessionTargetType]);

  const handleStartSession = useCallback(async (nextTargetType) => {
    const next = await start(nextTargetType);
    setSelectedSessionId(LIVE_SESSION);
    return next;
  }, [start]);

  const handleReset = useCallback(async () => {
    await reset();
    setSelectedSessionId(LIVE_SESSION);
  }, [reset]);

  return (
    <div
      style={{
        display: 'flex',
        height: '100vh',
        overflow: 'hidden',
        background: 'var(--c-bg-0)',
      }}
    >
      <Sidebar wsStatus={wsStatus} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Header
          shots={selectedShots}
          session={session}
          sessionSummaries={sessionSummaries}
          selectedSessionId={selectedSessionId}
          onSessionSelect={setSelectedSessionId}
          onReset={handleReset}
        />

        {/* Global error banner */}
        {error && (
          <div
            style={{
              background: 'rgba(239,68,68,0.12)',
              borderBottom: '1px solid rgba(239,68,68,0.25)',
              padding: '8px 24px',
              fontSize: 12,
              color: 'var(--c-danger)',
            }}
          >
            ⚠ {error}
          </div>
        )}

        {/* Loading overlay */}
        {loading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center', color: 'var(--c-text-3)' }}>
              <div style={{ fontSize: 24, marginBottom: 12, opacity: 0.4 }}>⊙</div>
              <div>Loading shot history…</div>
            </div>
          </div>
        ) : (
          <main
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: 20,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
            }}
          >
            <div style={{ flex: 1, minHeight: 0 }}>
              <Routes>
                <Route
                  path="/"
                  element={
                    <DashboardPage
                      shots={selectedShots}
                      currentShots={selectedShots}
                      stats={stats}
                      targetType={targetType}
                      onTargetTypeChange={setTargetType}
                      session={session}
                      onStartSession={handleStartSession}
                      onShotsPerSessionChange={setShotsPerSession}
                    />
                  }
                />
                <Route
                  path="/target"
                  element={
                    <TargetPage
                      shots={selectedShots}
                      latestShot={latestShot}
                      targetType={targetType}
                      onTargetTypeChange={setTargetType}
                    />
                  }
                />
                <Route
                  path="/shots"
                  element={<ShotsPage shots={selectedShots} latestShot={latestShot} />}
                />
                <Route
                  path="/analytics"
                  element={<AnalyticsPage shots={selectedShots} stats={stats} />}
                />
                <Route
                  path="/heatmap"
                  element={
                    <HeatmapPage
                      shots={selectedShots}
                      heatmap={heatmap}
                      targetType={targetType}
                      onTargetTypeChange={setTargetType}
                    />
                  }
                />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </div>
          </main>
        )}
      </div>
    </div>
  );
}
