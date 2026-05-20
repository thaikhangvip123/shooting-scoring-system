/**
 * pages/TargetPage.jsx
 * Full-screen target view with filter controls and mean POI toggle.
 */

import { useState } from 'react';
import TargetCanvas from '@/components/target/TargetCanvas';
import TargetTypeSelector from '@/components/target/TargetTypeSelector';
import { shotTargetType } from '@/utils/targetGeometry';
import { distancePxToMm, fmtSignedMm, shotOffsetMm } from '@/utils/units';

export default function TargetPage({ shots, targetType, onTargetTypeChange }) {
  const [showMeanPOI, setShowMeanPOI] = useState(true);
  const [maxShots, setMaxShots] = useState(50);

  const targetShots = shots.filter((shot) => shotTargetType(shot) === targetType);
  const visible = targetShots.slice(0, maxShots);
  const latestTargetShot = targetShots[0] ?? null;

  return (
    <div style={{ display: 'flex', gap: 20, height: '100%', minHeight: 0 }}>
      <div
        className="card"
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          minWidth: 0,
          overflow: 'auto',
        }}
      >
        <TargetCanvas
          shots={visible}
          latestShot={latestTargetShot}
          showMeanPOI={showMeanPOI}
          targetType={targetType}
        />
      </div>

      <div style={{ width: 220, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="card" style={{ padding: 18 }}>
          <div className="card-title" style={{ marginBottom: 14 }}>Display</div>

          <TargetTypeSelector value={targetType} onChange={onTargetTypeChange} />

          <label style={{ fontSize: 12, color: 'var(--c-text-2)', display: 'block', marginTop: 16, marginBottom: 4 }}>
            Show last {maxShots} shots
          </label>
          <input
            type="range"
            min={5}
            max={200}
            step={5}
            value={maxShots}
            onChange={(event) => setMaxShots(Number(event.target.value))}
            style={{ width: '100%', accentColor: 'var(--c-accent)' }}
          />

          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginTop: 16,
              fontSize: 12,
              color: 'var(--c-text-2)',
              cursor: 'pointer',
            }}
          >
            <input
              type="checkbox"
              checked={showMeanPOI}
              onChange={(event) => setShowMeanPOI(event.target.checked)}
              style={{ accentColor: 'var(--c-accent)' }}
            />
            Show Mean POI
          </label>
        </div>

        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 11, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Shots on target
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--c-accent-h)', fontFamily: 'monospace' }}>
            {visible.length}
          </div>
          <div style={{ fontSize: 11, color: 'var(--c-text-3)', marginTop: 2 }}>
            of {targetShots.length} target shots
          </div>
        </div>

        {latestTargetShot && (() => {
          const offset = shotOffsetMm(latestTargetShot);
          const radius = latestTargetShot.radius_px != null
            ? `${distancePxToMm(latestTargetShot.radius_px).toFixed(2)} mm`
            : '-';

          return (
            <div className="card" style={{ padding: 18 }}>
              <div className="card-title" style={{ marginBottom: 10 }}>Latest</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
                {[
                  ['Score', latestTargetShot.score],
                  ['X', fmtSignedMm(offset.x, 2)],
                  ['Y', fmtSignedMm(offset.y, 2)],
                  ['Radius', radius],
                ].map(([key, value]) => (
                  <div key={key} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--c-text-3)' }}>{key}</span>
                    <span style={{ color: 'var(--c-text-1)', fontWeight: 500, fontFamily: 'monospace' }}>{value}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

