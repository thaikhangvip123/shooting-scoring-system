/**
 * components/layout/Header.jsx
 * Top bar: page title, shot counter, session reset, export actions.
 */

import { useLocation } from 'react-router-dom';
import ExportButtons from '@/components/shared/ExportButtons';
import { resetSession } from '@/api/client';

const PAGE_TITLES = {
  '/':          'Dashboard',
  '/target':    'Target View',
  '/shots':     'Shot Log',
  '/analytics': 'Analytics',
  '/heatmap':   'Heatmap',
  '/settings':  'Settings',
};

export default function Header({ shots, onReset }) {
  const location = useLocation();
  const title    = PAGE_TITLES[location.pathname] ?? 'Shooting Score';
  const total    = shots.length;
  const totalScore = shots.reduce((s, sh) => s + (sh.score ?? 0), 0);

  const handleReset = async () => {
    if (!window.confirm('Reset all shots in this session?')) return;
    try {
      await resetSession();
      onReset();
    } catch (e) {
      console.error('Reset failed', e);
    }
  };

  return (
    <header
      style={{
        height: 58,
        flexShrink: 0,
        background: 'var(--c-bg-1)',
        borderBottom: '1px solid var(--c-border)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        gap: 16,
      }}
    >
      {/* Title */}
      <h1 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: 'var(--c-text-1)' }}>
        {title}
      </h1>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Quick stats */}
      <div
        style={{
          display: 'flex',
          gap: 24,
          fontSize: 13,
          color: 'var(--c-text-2)',
        }}
      >
        <span>
          <span style={{ fontWeight: 600, color: 'var(--c-text-1)' }}>{total}</span> shots
        </span>
        <span>
          Total{' '}
          <span style={{ fontWeight: 600, color: 'var(--c-accent-h)' }}>{totalScore}</span>
        </span>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <ExportButtons shots={shots} />
        <button className="btn" onClick={handleReset} title="Reset session">
          ↺ Reset
        </button>
      </div>
    </header>
  );
}