/**
 * components/shots/ShotRow.jsx
 */

import { fmtTime, scoreBadgeClass } from '@/utils/format';
import { fmtSignedMm, shotOffsetMm } from '@/utils/units';

export default function ShotRow({ shot, isLatest }) {
  const offset = shotOffsetMm(shot);
  const badgeClass = scoreBadgeClass(shot.score);

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
        {fmtSignedMm(offset.x, 2)}
      </td>
      <td style={{ padding: '7px 12px', fontFamily: 'monospace', color: 'var(--c-text-2)' }}>
        {fmtSignedMm(offset.y, 2)}
      </td>
      <td style={{ padding: '7px 12px', color: 'var(--c-text-3)', fontSize: 11 }}>
        {shot.session_id?.slice(0, 8) ?? '-'}
      </td>
    </tr>
  );
}
