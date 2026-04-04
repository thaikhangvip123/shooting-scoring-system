/**
 * components/shots/ShotTable.jsx
 * Scrollable, sortable shot history table.
 */

import { useState, useMemo } from 'react';
import ShotRow from './ShotRow';

const COLUMNS = [
  { key: 'index',     label: '#',        width: 44  },
  { key: 'timestamp', label: 'Time',     width: 80  },
  { key: 'score',     label: 'Score',    width: 64  },
  { key: 'x_mm',      label: 'X (mm)',   width: 80  },
  { key: 'y_mm',      label: 'Y (mm)',   width: 80  },
  { key: 'radius',    label: 'R (mm)',   width: 80  },
  { key: 'ring',      label: 'Ring',     width: 56  },
  { key: 'session',   label: 'Session',  width: 90  },
];

export default function ShotTable({ shots = [], latestId = null }) {
  const [sortKey, setSortKey]   = useState('index');
  const [sortDir, setSortDir]   = useState('desc');
  const [filter,  setFilter]    = useState('');

  const handleSort = (key) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('asc'); }
  };

  const processed = useMemo(() => {
    let rows = shots.map((s, i) => ({
      ...s,
      index:  shots.length - i,
      radius: Math.sqrt(s.x_mm ** 2 + s.y_mm ** 2),
    }));

    if (filter.trim()) {
      const q = filter.trim().toLowerCase();
      rows = rows.filter(
        (r) =>
          String(r.score).includes(q) ||
          String(r.ring ?? '').toLowerCase().includes(q) ||
          String(r.session ?? '').toLowerCase().includes(q)
      );
    }

    rows.sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv;
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return rows;
  }, [shots, sortKey, sortDir, filter]);

  const SortIcon = ({ col }) => {
    if (sortKey !== col) return <span style={{ opacity: 0.3 }}>⇅</span>;
    return <span>{sortDir === 'asc' ? '↑' : '↓'}</span>;
  };

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Header */}
      <div className="card-header">
        <span className="card-title">Shot Log</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <input
            type="text"
            placeholder="Filter…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{
              background: 'var(--c-bg-2)',
              border: '1px solid var(--c-border-2)',
              borderRadius: 6,
              padding: '4px 10px',
              fontSize: 12,
              color: 'var(--c-text-1)',
              width: 140,
              outline: 'none',
            }}
          />
          <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>
            {processed.length} / {shots.length}
          </span>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowY: 'auto', flex: 1 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ position: 'sticky', top: 0, background: 'var(--c-bg-1)', zIndex: 1 }}>
              {COLUMNS.map(({ key, label, width }) => (
                <th
                  key={key}
                  onClick={() => handleSort(key)}
                  style={{
                    width,
                    padding: '8px 12px',
                    textAlign: 'left',
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: '0.05em',
                    textTransform: 'uppercase',
                    color: sortKey === key ? 'var(--c-text-1)' : 'var(--c-text-3)',
                    borderBottom: '1px solid var(--c-border)',
                    cursor: 'pointer',
                    userSelect: 'none',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {label} <SortIcon col={key} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {processed.length === 0 ? (
              <tr>
                <td
                  colSpan={COLUMNS.length}
                  style={{ textAlign: 'center', padding: 40, color: 'var(--c-text-3)', fontSize: 13 }}
                >
                  No shots recorded yet
                </td>
              </tr>
            ) : (
              processed.map((shot) => (
                <ShotRow
                  key={shot.id}
                  shot={shot}
                  isLatest={shot.id === latestId}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}