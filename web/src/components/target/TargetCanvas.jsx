/**
 * components/target/TargetCanvas.jsx
 * Fixed 500px SVG target renderer for TRON, IPSC, and NGUOI targets.
 */

import { useMemo, useState } from 'react';
import { fmtTime } from '@/utils/format';
import {
  TARGET_CANVAS_SIZE,
  TARGET_TYPES,
  cvPointToCanvas,
  scoreTargetShot,
  shotTargetType,
  shotToCanvas,
  targetGeometry,
} from '@/utils/targetGeometry';
import HitMarker from './HitMarker';
import '@/styles/target.css';

const SIZE = TARGET_CANVAS_SIZE;
const TRON_CENTER = cvPointToCanvas({ x: 1240, y: 1754 });
const IMAGE_SCALE = TARGET_CANVAS_SIZE / 3508;

function pointsToPath(points) {
  return points
    .map((point, index) => {
      const canvasPoint = cvPointToCanvas(point);
      return `${index === 0 ? 'M' : 'L'} ${canvasPoint.x.toFixed(2)} ${canvasPoint.y.toFixed(2)}`;
    })
    .join(' ');
}

function CircularTarget() {
  return (
    <>
      <circle cx={TRON_CENTER.x} cy={TRON_CENTER.y} r={248} fill="#090b0f" />
      {targetGeometry.TRON.zones.map((zone) => {
        const radius = zone.radiusPx * IMAGE_SCALE;
        return (
          <circle
            key={zone.id}
            cx={TRON_CENTER.x}
            cy={TRON_CENTER.y}
            r={radius}
            fill={zone.color}
            fillOpacity={0.07}
            stroke={zone.color}
            strokeOpacity={0.38}
            strokeWidth={1}
          />
        );
      })}
      <circle cx={TRON_CENTER.x} cy={TRON_CENTER.y} r={2.5} fill="rgba(255,255,255,0.48)" />
    </>
  );
}

function ZoneTarget({ targetType }) {
  const zones = targetGeometry[targetType]?.zones ?? [];

  return (
    <>
      <rect x={0} y={0} width={SIZE} height={SIZE} fill="#090b0f" />
      {zones.map((zone, index) => (
        <path
          key={zone.id}
          d={`${pointsToPath(zone.points)} Z`}
          fill={zone.color}
          fillOpacity={0.06 + index * 0.018}
          stroke={zone.color}
          strokeOpacity={0.55}
          strokeWidth={1.2}
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </>
  );
}

export default function TargetCanvas({
  shots = [],
  latestShot = null,
  showMeanPOI = true,
  targetType = 'TRON',
}) {
  const [tooltip, setTooltip] = useState(null);
  const normalizedTargetType = TARGET_TYPES[targetType] ? targetType : 'TRON';

  const plotted = useMemo(() => {
    const seen = new Set();
    return shots.filter((shot, index) => {
      if (shotTargetType(shot) !== normalizedTargetType) return false;
      const id = shot.id ?? shot.shot_id ?? `${shot.timestamp ?? 'shot'}-${index}`;
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  }, [normalizedTargetType, shots]);

  const meanPOI = useMemo(() => {
    if (!plotted.length) return null;
    const mx = plotted.reduce((a, s) => a + Number(s.x_px ?? s.x_mm ?? 0), 0) / plotted.length;
    const my = plotted.reduce((a, s) => a + Number(s.y_px ?? s.y_mm ?? 0), 0) / plotted.length;
    return shotToCanvas({ x_px: mx, y_px: my }, normalizedTargetType);
  }, [normalizedTargetType, plotted]);

  return (
    <div className="target-canvas-box">
      <svg
        className="target-svg"
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        width={SIZE}
        height={SIZE}
        aria-label={`${TARGET_TYPES[normalizedTargetType].title} target`}
      >
        {normalizedTargetType === 'TRON' ? (
          <CircularTarget />
        ) : (
          <ZoneTarget targetType={normalizedTargetType} />
        )}

        {showMeanPOI && meanPOI && plotted.length > 1 && (
          <g>
            <line
              x1={meanPOI.x - 8}
              y1={meanPOI.y}
              x2={meanPOI.x + 8}
              y2={meanPOI.y}
              stroke="#f59e0b"
              strokeWidth={1.5}
              strokeDasharray="3 2"
            />
            <line
              x1={meanPOI.x}
              y1={meanPOI.y - 8}
              x2={meanPOI.x}
              y2={meanPOI.y + 8}
              stroke="#f59e0b"
              strokeWidth={1.5}
              strokeDasharray="3 2"
            />
            <circle cx={meanPOI.x} cy={meanPOI.y} r={3} fill="#f59e0b" fillOpacity={0.72} />
          </g>
        )}

        {plotted.map((shot, index) => {
          const id = shot.id ?? shot.shot_id ?? `${shot.timestamp ?? 'shot'}-${index}`;
          const latestId = latestShot?.id ?? latestShot?.shot_id;
          const isLatest = latestId === id;
          const point = shotToCanvas(shot, normalizedTargetType);
          const score = scoreTargetShot(shot, normalizedTargetType);

          return (
            <HitMarker
              key={id}
              cx={point.x}
              cy={point.y}
              color={score.color}
              score={shot.score ?? score.score}
              isLatest={isLatest}
              onMouseEnter={() => setTooltip({ x: point.x, y: point.y, shot, score })}
              onMouseLeave={() => setTooltip(null)}
            />
          );
        })}

        {tooltip && (() => {
          const { x, y, shot, score } = tooltip;
          const tx = x > SIZE / 2 ? x - 110 : x + 10;
          const ty = y > SIZE / 2 ? y - 58 : y + 10;
          return (
            <g>
              <rect
                x={tx}
                y={ty}
                width={100}
                height={52}
                rx={5}
                fill="#0d0f14"
                stroke="rgba(255,255,255,0.15)"
                strokeWidth={0.5}
              />
              <text x={tx + 8} y={ty + 17} fontSize={11} fill="#e8eaf0" fontWeight={600}>
                Score: {shot.score ?? score.score} ({score.label})
              </text>
              <text x={tx + 8} y={ty + 31} fontSize={10} fill="#9499b0">
                X: {Number(shot.x_px ?? shot.x_mm ?? 0).toFixed(2)} px Y: {Number(shot.y_px ?? shot.y_mm ?? 0).toFixed(2)} px
              </text>
              <text x={tx + 8} y={ty + 45} fontSize={10} fill="#9499b0">
                {fmtTime(shot.timestamp)}
              </text>
            </g>
          );
        })()}
      </svg>
    </div>
  );
}
