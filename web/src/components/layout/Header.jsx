/**
 * components/layout/Header.jsx
 * Top bar: page title, session status, export actions, reset, and counters.
 */

import { useLocation } from 'react-router-dom';
import ExportButtons from '@/components/shared/ExportButtons';

const PAGE_TITLES = {
  '/':          'Dashboard',
  '/target':    'Target View',
  '/shots':     'Shot Log',
  '/analytics': 'Analytics',
  '/heatmap':   'Heatmap',
  '/settings':  'Settings',
};

const LIVE_SESSION = '__live__';

function formatSessionOption(summary) {
  const name = summary.number != null ? `Session ${summary.number}` : summary.id;
  const status = summary.status ? ` ${summary.status}` : '';
  const target = summary.targetType ? ` - ${summary.targetType}` : '';
  return `${name}${target} (${summary.shotCount} shots)${status}`;
}

export default function Header({
  shots,
  session,
  sessionSummaries = [],
  selectedSessionId = LIVE_SESSION,
  onSessionSelect,
  onReset,
}) {
  const location = useLocation();
  const title    = PAGE_TITLES[location.pathname] ?? 'Shooting Score';
  const total    = shots.length;
  const totalScore = shots.reduce((s, sh) => s + (sh.score ?? 0), 0);
  const previousSessions = sessionSummaries.filter((summary) => summary.id !== session?.session_id);
  const currentSessionLabel = session
    ? `Session ${session.session_number} (${session.shot_count}/${session.shots_per_session}) ${session.status ?? ''}`.trim()
    : 'Session -';

  const handleReset = async () => {
    if (!window.confirm('Reset current session?')) return;
    try {
      await onReset();
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
      <h1 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: 'var(--c-text-1)' }}>
        {title}
      </h1>

      <div style={{ flex: 1 }} />

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: 'var(--c-text-1)',
            padding: '7px 10px',
            border: '1px solid var(--c-border)',
            borderRadius: 6,
            background: 'var(--c-bg-0)',
            whiteSpace: 'nowrap',
          }}
        >
          {currentSessionLabel}
        </span>
        {session?.status === 'running' && (
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: 'var(--c-accent)',
              whiteSpace: 'nowrap',
            }}
          >
            {session.target_type}
          </span>
        )}
        {session?.completed && (
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: 'var(--c-success)',
              whiteSpace: 'nowrap',
            }}
          >
            Session complete
          </span>
        )}
        <select
          value={selectedSessionId}
          onChange={(event) => onSessionSelect?.(event.target.value)}
          title="View session"
          style={{
            height: 32,
            width: 190,
            border: '1px solid var(--c-border)',
            borderRadius: 6,
            background: 'var(--c-bg-0)',
            color: 'var(--c-text-1)',
            padding: '0 8px',
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          <option value={LIVE_SESSION}>Live session</option>
          {previousSessions.map((summary) => (
            <option key={summary.id} value={summary.id}>
              {formatSessionOption(summary)}
            </option>
          ))}
        </select>
        <ExportButtons shots={shots} />
        <button className="btn" onClick={handleReset} title="Reset current session">
          Reset
        </button>
      </div>

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
    </header>
  );
}
