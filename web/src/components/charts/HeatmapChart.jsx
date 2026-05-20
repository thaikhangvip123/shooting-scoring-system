/**
 * components/charts/HeatmapChart.jsx
 * Renders hit density over the selected fixed 500px target surface.
 */

import { useEffect, useMemo, useRef } from 'react';
import {
  TARGET_CANVAS_SIZE,
  cvPointToCanvas,
  shotTargetType,
  shotToCanvas,
  targetGeometry,
} from '@/utils/targetGeometry';

const RESOLUTION = 60;
const IMAGE_SCALE = TARGET_CANVAS_SIZE / 3508;

function buildGrid(shots, targetType, N = RESOLUTION) {
  const grid = Array.from({ length: N }, () => new Array(N).fill(0));
  const step = TARGET_CANVAS_SIZE / N;

  shots.filter((shot) => shotTargetType(shot) === targetType).forEach((shot) => {
    const point = shotToCanvas(shot, targetType);
    const col = Math.floor(point.x / step);
    const row = Math.floor(point.y / step);
    if (col >= 0 && col < N && row >= 0 && row < N) grid[row][col]++;
  });

  return grid;
}

function heatColor(t) {
  const r = Math.round(Math.min(1, t * 2) * 255);
  const g = Math.round(Math.min(1, Math.max(0, t * 2 - 0.5)) * 255 * (t < 0.75 ? 1 : (1 - t) * 4));
  const b = Math.round(Math.max(0, 1 - t * 2) * 200);
  const a = Math.round(Math.min(1, t * 3) * 220);
  return [r, g, b, a];
}

function drawTarget(ctx, targetType) {
  ctx.fillStyle = '#090b0f';
  ctx.fillRect(0, 0, TARGET_CANVAS_SIZE, TARGET_CANVAS_SIZE);

  if (targetType === 'TRON') {
    const center = cvPointToCanvas({ x: 1240, y: 1754 });
    targetGeometry.TRON.zones.forEach((zone) => {
      const radius = zone.radiusPx * IMAGE_SCALE;
      ctx.beginPath();
      ctx.arc(center.x, center.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = `${zone.color}12`;
      ctx.strokeStyle = `${zone.color}55`;
      ctx.lineWidth = 1;
      ctx.fill();
      ctx.stroke();
    });
    return;
  }

  const zones = targetGeometry[targetType]?.zones ?? [];
  zones.forEach((zone, index) => {
    ctx.beginPath();
    zone.points.forEach((sourcePoint, pointIndex) => {
      const point = cvPointToCanvas(sourcePoint);
      if (pointIndex === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.closePath();
    ctx.fillStyle = `${zone.color}${Math.min(30 + index * 7, 80).toString(16).padStart(2, '0')}`;
    ctx.strokeStyle = `${zone.color}88`;
    ctx.lineWidth = 1.2;
    ctx.fill();
    ctx.stroke();
  });
}

export default function HeatmapChart({ shots = [], grid: backendGrid = null, targetType = 'TRON' }) {
  const canvasRef = useRef(null);

  const grid = useMemo(
    () => buildGrid(shots, targetType, backendGrid?.length || RESOLUTION),
    [shots, backendGrid, targetType]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const N = grid.length;
    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    const cw = W / N;
    const ch = H / N;

    drawTarget(ctx, targetType);

    let maxVal = 1;
    grid.forEach((row) => row.forEach((value) => { if (value > maxVal) maxVal = value; }));

    const heatCanvas = document.createElement('canvas');
    heatCanvas.width = W;
    heatCanvas.height = H;
    const heatCtx = heatCanvas.getContext('2d');
    heatCtx.globalCompositeOperation = 'lighter';

    const filtered = shots.filter((shot) => shotTargetType(shot) === targetType);
    filtered.forEach((shot) => {
      const point = shotToCanvas(shot, targetType);
      const col = Math.floor(point.x / cw);
      const row = Math.floor(point.y / ch);
      const density = row >= 0 && row < N && col >= 0 && col < N ? grid[row][col] / maxVal : 1;
      const [r, g, b] = heatColor(Math.max(0.35, density));
      const radius = 32 + Math.min(22, density * 18);
      const gradient = heatCtx.createRadialGradient(point.x, point.y, 0, point.x, point.y, radius);
      gradient.addColorStop(0, `rgba(255,255,210,${0.55 + density * 0.25})`);
      gradient.addColorStop(0.25, `rgba(${r},${g},${b},${0.32 + density * 0.22})`);
      gradient.addColorStop(0.62, `rgba(${r},${g},${b},${0.12 + density * 0.12})`);
      gradient.addColorStop(1, `rgba(${r},${g},${b},0)`);

      heatCtx.fillStyle = gradient;
      heatCtx.beginPath();
      heatCtx.arc(point.x, point.y, radius, 0, Math.PI * 2);
      heatCtx.fill();
    });

    ctx.filter = 'blur(7px)';
    ctx.drawImage(heatCanvas, 0, 0);
    ctx.filter = 'none';

    filtered.forEach((shot) => {
      const point = shotToCanvas(shot, targetType);
      ctx.beginPath();
      ctx.arc(point.x, point.y, 2.4, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,255,255,0.75)';
      ctx.fill();
    });
  }, [grid, shots, targetType]);

  return (
    <div style={{ padding: 16 }}>
      <canvas
        ref={canvasRef}
        width={TARGET_CANVAS_SIZE}
        height={TARGET_CANVAS_SIZE}
        className="target-heatmap-canvas"
      />
      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>Low</span>
        <div
          style={{
            flex: 1,
            height: 8,
            borderRadius: 4,
            background: 'linear-gradient(to right, #00008820, #00ffff88, #ffff0088, #ff000088)',
          }}
        />
        <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>High</span>
      </div>
    </div>
  );
}
