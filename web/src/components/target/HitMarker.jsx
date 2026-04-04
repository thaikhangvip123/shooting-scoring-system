/**
 * components/target/HitMarker.jsx
 * Individual hit dot on the target with pulse animation for new shots.
 */

import { useEffect, useRef } from 'react';

export default function HitMarker({
  cx, cy,
  color = '#5b9fff',
  score,
  isLatest = false,
  onMouseEnter,
  onMouseLeave,
}) {
  const pulseRef = useRef(null);

  // Trigger pulse animation when this becomes the latest shot
  useEffect(() => {
    if (!isLatest || !pulseRef.current) return;
    const el = pulseRef.current;
    el.setAttribute('r', '6');
    el.style.opacity = '1';

    let start = null;
    const DURATION = 700;

    const animate = (ts) => {
      if (!start) start = ts;
      const progress = Math.min((ts - start) / DURATION, 1);
      const r   = 6  + progress * 18;
      const opc = 1  - progress;
      el.setAttribute('r', r);
      el.style.opacity = opc;
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [isLatest]);

  return (
    <g
      className="hit-marker"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {/* Pulse ring for latest shot */}
      {isLatest && (
        <circle
          ref={pulseRef}
          cx={cx} cy={cy} r={6}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          opacity={0}
          pointerEvents="none"
        />
      )}

      {/* Outer halo */}
      <circle
        cx={cx} cy={cy} r={isLatest ? 8 : 6}
        fill={color}
        fillOpacity={isLatest ? 0.25 : 0.12}
        stroke="none"
      />

      {/* Hit dot */}
      <circle
        cx={cx} cy={cy} r={isLatest ? 5 : 4}
        fill={color}
        fillOpacity={isLatest ? 1 : 0.85}
        stroke="#0d0f14"
        strokeWidth={isLatest ? 1.5 : 1}
      />

      {/* Score badge on latest */}
      {isLatest && (
        <text
          x={cx + 9}
          y={cy - 9}
          fontSize={10}
          fontWeight={700}
          fill={color}
        >
          {score}
        </text>
      )}
    </g>
  );
}