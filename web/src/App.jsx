/**
 * App.jsx
 * Root component: layout shell + React Router.
 * All pages receive shots/stats as props — single source of truth at the top.
 */

import { Routes, Route } from 'react-router-dom';
import { useState } from 'react';
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
  const currentShots = currentSessionId
    ? shots.filter((shot) => shot.session_id === currentSessionId)
    : shots;
  const latestShot = currentShots[0] ?? null;
  const { stats, heatmap }                                       = useStats(currentShots.length, currentSessionId);
  const [targetType, setTargetType]                              = useState('TRON');

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
        <Header shots={currentShots} session={session} onReset={reset} />

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
                      shots={shots}
                      currentShots={currentShots}
                      stats={stats}
                      targetType={targetType}
                      onTargetTypeChange={setTargetType}
                      session={session}
                      onStartSession={start}
                      onShotsPerSessionChange={setShotsPerSession}
                    />
                  }
                />
                <Route
                  path="/target"
                  element={
                    <TargetPage
                      shots={currentShots}
                      latestShot={latestShot}
                      targetType={targetType}
                      onTargetTypeChange={setTargetType}
                    />
                  }
                />
                <Route
                  path="/shots"
                  element={<ShotsPage shots={shots} latestShot={latestShot} />}
                />
                <Route
                  path="/analytics"
                  element={<AnalyticsPage shots={currentShots} stats={stats} />}
                />
                <Route
                  path="/heatmap"
                  element={
                    <HeatmapPage
                      shots={currentShots}
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
