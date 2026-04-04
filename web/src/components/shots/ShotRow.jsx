/**
 * components/shots/ShotRow.jsx
 */

import { fmtTime, fmtMm, scoreBadgeClass } from '@/utils/format';
import { scoreShot } from '@/utils/scoring';

export default function ShotRow({ shot, isLatest }) {
  const { label, color } = scoreShot(shot.x_mm, shot.y_mm);
  const badgeClass       = scoreBadgeClass(shot.score);
  const radius           = shot.radius ?? Math.sqrt(shot.x_mm ** 2 + shot.y_mm ** 2);

  return (
    <tr
      style={{
        background: isLatest ? 'rgba(59,127,255,0.07)' : 'transparent',
        borderBottom: '1px solid var(--c-border)',
        transition: 'background 0.2s',
        animation: isLatest ? 'fadeIn 0.3s ease-out' : 'none',
      }}
    >
      <td style={{ padding: '7px 12px', color: 'var(--c-text-3)', fontFamily: 'monospace' }}>
        {shot.index}
      </td>
      <td style={{ padding: '7px 12px', color: 'var(--c-text-2)', whiteSpace: 'nowrap' }}>
        {fmtTime(shot.timestamp)}
      </td>
      <td style={{ padding: '7px 12px' }}>
        <span className={`badge ${badgeClass}`}>{shot.score}</span>
      </td>
      <td style={{ padding: '7px 12px', fontFamily: 'monospace', color: 'var(--c-text-2)' }}>
        {fmtMm(shot.x_mm)}
      </td>
      <td style={{ padding: '7px 12px', fontFamily: 'monospace', color: 'var(--c-text-2)' }}>
        {fmtMm(shot.y_mm)}
      </td>
      <td style={{ padding: '7px 12px', fontFamily: 'monospace', color: 'var(--c-text-2)' }}>
        {fmtMm(radius)}
      </td>
      <td style={{ padding: '7px 12px' }}>
        <span style={{ color, fontWeight: 600, fontSize: 13 }}>{label}</span>
      </td>
      <td style={{ padding: '7px 12px', color: 'var(--c-text-3)', fontSize: 11 }}>
        {shot.session_id?.slice(0, 8) ?? '—'}
      </td>
    </tr>
  );
}