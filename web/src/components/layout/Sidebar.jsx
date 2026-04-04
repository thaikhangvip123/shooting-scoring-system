/**
 * components/layout/Sidebar.jsx
 * Left-side navigation with route links and live WS status indicator.
 */

import { NavLink } from 'react-router-dom';
import clsx from 'clsx';

const NAV_ITEMS = [
  { to: '/',          icon: '◎', label: 'Dashboard'  },
  { to: '/target',    icon: '⊕', label: 'Target'     },
  { to: '/shots',     icon: '≡', label: 'Shot Log'   },
  { to: '/analytics', icon: '∿', label: 'Analytics'  },
  { to: '/heatmap',   icon: '▦', label: 'Heatmap'    },
  { to: '/settings',  icon: '⚙', label: 'Settings'   },
];

export default function Sidebar({ wsStatus }) {
  const statusColor = {
    open:       'var(--c-success)',
    connecting: 'var(--c-warn)',
    closed:     'var(--c-danger)',
    error:      'var(--c-danger)',
  }[wsStatus] ?? 'var(--c-text-3)';

  return (
    <aside
      style={{
        width: 220,
        flexShrink: 0,
        background: 'var(--c-bg-1)',
        borderRight: '1px solid var(--c-border)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 0 16px',
      }}
    >
      {/* Logo */}
      <div style={{ padding: '0 20px 28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 22 }}>🎯</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--c-text-1)', lineHeight: 1 }}>
              ShootScore
            </div>
            <div style={{ fontSize: 11, color: 'var(--c-text-3)', marginTop: 2 }}>
              v1.0.0
            </div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1 }}>
        {NAV_ITEMS.map(({ to, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '9px 20px',
              textDecoration: 'none',
              fontSize: 13,
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--c-text-1)' : 'var(--c-text-2)',
              background: isActive ? 'var(--c-bg-2)' : 'transparent',
              borderRight: isActive ? '2px solid var(--c-accent)' : '2px solid transparent',
              transition: 'all 0.15s',
            })}
          >
            <span style={{ fontSize: 15, opacity: 0.85 }}>{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* WS Status */}
      <div
        style={{
          margin: '0 12px',
          padding: '10px 12px',
          background: 'var(--c-bg-2)',
          borderRadius: 8,
          border: '1px solid var(--c-border)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: statusColor,
            boxShadow: wsStatus === 'open' ? `0 0 6px ${statusColor}` : 'none',
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: 11, color: 'var(--c-text-2)', textTransform: 'capitalize' }}>
          {wsStatus === 'open' ? 'Live' : wsStatus}
        </span>
        <span style={{ fontSize: 11, color: 'var(--c-text-3)', marginLeft: 'auto' }}>
          WebSocket
        </span>
      </div>
    </aside>
  );
}