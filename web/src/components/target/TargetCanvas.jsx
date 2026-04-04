/**
 * components/target/TargetCanvas.jsx
 * Renders a full scoring target as SVG.
 * Shots are plotted in real-world mm coordinates normalised to the SVG viewport.
 * Includes: scoring rings, X/Y crosshairs, hit markers, latest-shot highlight.
 */

import { useMemo, useState } from 'react';
import { RINGS, TARGET_RADIUS_MM, scoreShot } from '@/utils/scoring';
import { fmtMm, fmtTime } from '@/utils/format';
import HitMarker from './HitMarker';
import '@/styles/target.css';

const SVG_RADIUS = 240; // px – SVG coordinate radius
const SVG_SIZE   = SVG_RADIUS * 2 + 20; // full canvas size (500px)
const CX         = SVG_SIZE / 2;        // centre x
const CY         = SVG_SIZE / 2;        // centre y

/** Scale mm → SVG pixels */
const mmToPx = (mm) => (mm / TARGET_RADIUS_MM) * SVG_RADIUS;

export default function TargetCanvas({ shots = [], latestShot = null, showMeanPOI = true }) {
  const [tooltip, setTooltip] = useState(null);

  // Build ring props once
  const rings = useMemo(
    () =>
      [...RINGS].reverse().map(([maxR, score, label, color]) => ({
        r:     mmToPx(maxR),
        score,
        label,
        color,
      })),
    []
  );

  // Deduplicate by shot id
  const plotted = useMemo(() => {
    const seen = new Set();
    return shots.filter((s) => {
      if (seen.has(s.id)) return false;
      seen.add(s.id);
      return true;
    });
  }, [shots]);

  // Mean POI
  const meanPOI = useMemo(() => {
    if (!plotted.length) return null;
    const mx = plotted.reduce((a, s) => a + s.x_mm, 0) / plotted.length;
    const my = plotted.reduce((a, s) => a + s.y_mm, 0) / plotted.length;
    return { cx: CX + mmToPx(mx), cy: CY - mmToPx(my) };
  }, [plotted]);

  return (
    <div style={{ position: 'relative', width: '100%', maxWidth: SVG_SIZE }}>
      <svg
        className="target-svg"
        viewBox={`0 0 ${SVG_SIZE} ${SVG_SIZE}`}
        width="100%"
        style={{ display: 'block' }}
        aria-label="Shooting target"
      >
        {/* ── Background ── */}
        <circle cx={CX} cy={CY} r={SVG_RADIUS + 8} fill="#111318" />

        {/* ── Scoring rings (outside-in) ── */}
        {rings.map(({ r, score, label, color }) => (
          <g key={label}>
            <circle
              cx={CX} cy={CY} r={r}
              fill={color}
              fillOpacity={0.07}
              stroke={color}
              strokeOpacity={0.3}
              strokeWidth={0.5}
            />
            {/* Score label at 3 o'clock */}
            <text
              className="target-ring-label"
              x={CX + r - 4}
              y={CY + 4}
              textAnchor="end"
              fontSize={9}
              fill={color}
              fillOpacity={0.7}
            >
              {score}
            </text>
          </g>
        ))}

        {/* ── X-ring highlight ── */}
        <circle
          cx={CX} cy={CY}
          r={mmToPx(RINGS[0][0])}
          fill="none"
          stroke="#e8f4ff"
          strokeWidth={1}
          strokeOpacity={0.5}
        />

        {/* ── Crosshairs ── */}
        <line className="target-crosshair" x1={CX} y1={CY - SVG_RADIUS} x2={CX} y2={CY + SVG_RADIUS} />
        <line className="target-crosshair" x1={CX - SVG_RADIUS} y1={CY} x2={CX + SVG_RADIUS} y2={CY} />

        {/* ── Outer ring border ── */}
        <circle
          cx={CX} cy={CY} r={SVG_RADIUS}
          fill="none"
          stroke="rgba(255,255,255,0.18)"
          strokeWidth={1.5}
        />

        {/* ── Centre dot ── */}
        <circle cx={CX} cy={CY} r={2} fill="rgba(255,255,255,0.4)" />

        {/* ── Mean POI marker ── */}
        {showMeanPOI && meanPOI && plotted.length > 1 && (
          <g>
            <line
              x1={meanPOI.cx - 8} y1={meanPOI.cy}
              x2={meanPOI.cx + 8} y2={meanPOI.cy}
              stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="3 2"
            />
            <line
              x1={meanPOI.cx} y1={meanPOI.cy - 8}
              x2={meanPOI.cx} y2={meanPOI.cy + 8}
              stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="3 2"
            />
            <circle cx={meanPOI.cx} cy={meanPOI.cy} r={3} fill="#f59e0b" fillOpacity={0.6} />
          </g>
        )}

        {/* ── Hit markers ── */}
        {plotted.map((shot) => {
          const isLatest = latestShot?.id === shot.id;
          const sx = CX + mmToPx(shot.x_mm);
          const sy = CY - mmToPx(shot.y_mm); // Y flipped (SVG top-down)
          const { color } = scoreShot(shot.x_mm, shot.y_mm);

          return (
            <HitMarker
              key={shot.id}
              cx={sx}
              cy={sy}
              color={color}
              score={shot.score}
              isLatest={isLatest}
              onMouseEnter={() =>
                setTooltip({
                  x: sx, y: sy,
                  shot,
                })
              }
              onMouseLeave={() => setTooltip(null)}
            />
          );
        })}

        {/* ── Tooltip ── */}
        {tooltip && (() => {
          const { x, y, shot } = tooltip;
          const { label } = scoreShot(shot.x_mm, shot.y_mm);
          const tx = x > SVG_SIZE / 2 ? x - 100 : x + 10;
          const ty = y > SVG_SIZE / 2 ? y - 56  : y + 10;
          return (
            <g>
              <rect
                x={tx} y={ty} width={90} height={50}
                rx={5}
                fill="#0d0f14"
                stroke="rgba(255,255,255,0.15)"
                strokeWidth={0.5}
              />
              <text x={tx + 8} y={ty + 16} fontSize={11} fill="#e8eaf0" fontWeight={600}>
                Score: {shot.score} ({label})
              </text>
              <text x={tx + 8} y={ty + 30} fontSize={10} fill="#9499b0">
                X: {fmtMm(shot.x_mm)}  Y: {fmtMm(shot.y_mm)}
              </text>
              <text x={tx + 8} y={ty + 44} fontSize={10} fill="#9499b0">
                {fmtTime(shot.timestamp)}
              </text>
            </g>
          );
        })()}
      </svg>

      {/* Axis labels */}
      <div style={{
        position: 'absolute',
        top: '50%',
        left: 4,
        transform: 'translateY(-50%)',
        fontSize: 10,
        color: 'var(--c-text-3)',
      }}>
        Y
      </div>
      <div style={{
        position: 'absolute',
        bottom: 4,
        right: '50%',
        transform: 'translateX(50%)',
        fontSize: 10,
        color: 'var(--c-text-3)',
      }}>
        X
      </div>
    </div>
  );
}