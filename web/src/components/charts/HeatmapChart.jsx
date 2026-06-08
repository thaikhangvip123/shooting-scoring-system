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
  const radiusCells = Math.max(2, Math.round(N / 18));
  const sigma = Math.max(1, radiusCells / 2);

  shots.filter((shot) => shotTargetType(shot) === targetType).forEach((shot) => {
    const point = shotToCanvas(shot, targetType);
    const centerCol = Math.floor(point.x / step);
    const centerRow = Math.floor(point.y / step);

    for (let row = centerRow - radiusCells; row <= centerRow + radiusCells; row += 1) {
      if (row < 0 || row >= N) continue;
      for (let col = centerCol - radiusCells; col <= centerCol + radiusCells; col += 1) {
        if (col < 0 || col >= N) continue;
        const dx = col - centerCol;
        const dy = row - centerRow;
        const distSq = dx * dx + dy * dy;
        if (distSq > radiusCells * radiusCells) continue;
        grid[row][col] += Math.exp(-distSq / (2 * sigma * sigma));
      }
    }
  });

  return grid;
}

function heatColor(t) {
  const v = Math.max(0, Math.min(1, t));
  let r;
  let g;
  let b;

  if (v < 0.33) {
    const p = v / 0.33;
    r = 0;
    g = Math.round(90 + p * 165);
    b = 255;
  } else if (v < 0.66) {
    const p = (v - 0.33) / 0.33;
    r = Math.round(p * 255);
    g = 255;
    b = Math.round(255 - p * 220);
  } else {
    const p = (v - 0.66) / 0.34;
    r = 255;
    g = Math.round(255 - p * 230);
    b = 0;
  }

  const a = Math.round(45 + v * 175);
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

    drawTarget(ctx, targetType);

    let maxVal = 1;
    grid.forEach((row) => row.forEach((value) => { if (value > maxVal) maxVal = value; }));
    const filtered = shots.filter((shot) => shotTargetType(shot) === targetType);
    const saturation = Math.max(2, Math.min(maxVal, Math.min(4, Math.max(2, Math.ceil(filtered.length / 3)))));

    const densityCanvas = document.createElement('canvas');
    densityCanvas.width = N;
    densityCanvas.height = N;
    const densityCtx = densityCanvas.getContext('2d');
    const image = densityCtx.createImageData(N, N);

    grid.forEach((row, y) => {
      row.forEach((value, x) => {
        if (value <= 0) return;
        const density = Math.min(1, value / saturation);
        const [r, g, b, a] = heatColor(density);
        const index = (y * N + x) * 4;
        image.data[index] = r;
        image.data[index + 1] = g;
        image.data[index + 2] = b;
        image.data[index + 3] = a;
      });
    });
    densityCtx.putImageData(image, 0, 0);

    ctx.save();
    ctx.filter = 'blur(8px)';
    ctx.globalCompositeOperation = 'source-over';
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(densityCanvas, 0, 0, W, H);
    ctx.restore();
    ctx.filter = 'none';

    filtered.forEach((shot) => {
      const point = shotToCanvas(shot, targetType);
      ctx.beginPath();
      ctx.arc(point.x, point.y, 1.8, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,255,255,0.45)';
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
