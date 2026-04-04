/**
 * pages/TargetPage.jsx
 * Full-screen target view with filter controls and mean POI toggle.
 */

import { useState } from 'react';
import TargetCanvas from '@/components/target/TargetCanvas';

export default function TargetPage({ shots, latestShot }) {
  const [showMeanPOI, setShowMeanPOI] = useState(true);
  const [maxShots,    setMaxShots]    = useState(50);

  const visible = shots.slice(0, maxShots);

  return (
    <div style={{ display: 'flex', gap: 20, height: '100%', minHeight: 0 }}>
      {/* Target canvas */}
      <div
        className="card"
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          minWidth: 0,
        }}
      >
        <TargetCanvas shots={visible} latestShot={latestShot} showMeanPOI={showMeanPOI} />
      </div>

      {/* Controls panel */}
      <div style={{ width: 220, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="card" style={{ padding: 18 }}>
          <div className="card-title" style={{ marginBottom: 14 }}>Display</div>

          {/* Shots to show */}
          <label style={{ fontSize: 12, color: 'var(--c-text-2)', display: 'block', marginBottom: 4 }}>
            Show last {maxShots} shots
          </label>
          <input
            type="range"
            min={5} max={200} step={5}
            value={maxShots}
            onChange={(e) => setMaxShots(Number(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--c-accent)' }}
          />

          {/* Mean POI toggle */}
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
              onChange={(e) => setShowMeanPOI(e.target.checked)}
              style={{ accentColor: 'var(--c-accent)' }}
            />
            Show Mean POI
          </label>
        </div>

        {/* Visible shot count */}
        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 11, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Shots on target
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--c-accent-h)', fontFamily: 'monospace' }}>
            {visible.length}
          </div>
          <div style={{ fontSize: 11, color: 'var(--c-text-3)', marginTop: 2 }}>
            of {shots.length} total
          </div>
        </div>

        {/* Latest shot details */}
        {latestShot && (
          <div className="card" style={{ padding: 18 }}>
            <div className="card-title" style={{ marginBottom: 10 }}>Latest</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
              {[
                ['Score',    latestShot.score],
                ['X',        `${latestShot.x_mm?.toFixed(2)} mm`],
                ['Y',        `${latestShot.y_mm?.toFixed(2)} mm`],
                ['Radius',   `${Math.sqrt(latestShot.x_mm**2+latestShot.y_mm**2).toFixed(2)} mm`],
              ].map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--c-text-3)' }}>{k}</span>
                  <span style={{ color: 'var(--c-text-1)', fontWeight: 500, fontFamily: 'monospace' }}>{v}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}