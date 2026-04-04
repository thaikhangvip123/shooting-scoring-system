/**
 * App.jsx
 * Root component: layout shell + React Router.
 * All pages receive shots/stats as props — single source of truth at the top.
 */

import { Routes, Route } from 'react-router-dom';
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
  const { shots, latestShot, loading, error, wsStatus, reset } = useShots();
  const { stats, heatmap }                                       = useStats(shots.length);

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
        <Header shots={shots} onReset={reset} />

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
                    <DashboardPage shots={shots} latestShot={latestShot} stats={stats} />
                  }
                />
                <Route
                  path="/target"
                  element={<TargetPage shots={shots} latestShot={latestShot} />}
                />
                <Route
                  path="/shots"
                  element={<ShotsPage shots={shots} latestShot={latestShot} />}
                />
                <Route
                  path="/analytics"
                  element={<AnalyticsPage shots={shots} stats={stats} />}
                />
                <Route
                  path="/heatmap"
                  element={<HeatmapPage shots={shots} heatmap={heatmap} />}
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