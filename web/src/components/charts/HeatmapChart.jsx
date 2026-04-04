/**
 * components/charts/HeatmapChart.jsx
 * Renders a 2D hit-density heatmap on an HTML <canvas>.
 * Accepts either a pre-computed grid (number[][]) from the backend
 * or falls back to building one from raw shots.
 */

import { useEffect, useRef, useMemo } from 'react';
import { TARGET_RADIUS_MM } from '@/utils/scoring';

const RESOLUTION = 60; // grid cells per axis

/**
 * Build an NxN grid of hit counts from raw shot data.
 * Cell [row][col] covers a 2*R/N × 2*R/N region of the target.
 */
function buildGrid(shots, N = RESOLUTION) {
  const grid = Array.from({ length: N }, () => new Array(N).fill(0));
  const R    = TARGET_RADIUS_MM;
  const step = (2 * R) / N;

  shots.forEach(({ x_mm, y_mm }) => {
    const col = Math.floor((x_mm + R) / step);
    const row = Math.floor((R - y_mm) / step); // Y flipped
    if (col >= 0 && col < N && row >= 0 && row < N) grid[row][col]++;
  });
  return grid;
}

/**
 * Jet-like colour map: 0→transparent blue → cyan → yellow → red
 */
function heatColor(t) {
  // t in [0, 1]
  const r = Math.round(Math.min(1, t * 2)              * 255);
  const g = Math.round(Math.min(1, Math.max(0, t * 2 - 0.5)) * 255 * (t < 0.75 ? 1 : (1 - t) * 4));
  const b = Math.round(Math.max(0, 1 - t * 2)          * 200);
  const a = Math.round(Math.min(1, t * 3)              * 220);
  return [r, g, b, a];
}

export default function HeatmapChart({ shots = [], grid: backendGrid = null, showOverlay = true }) {
  const canvasRef = useRef(null);

  const grid = useMemo(
    () => backendGrid ?? buildGrid(shots, RESOLUTION),
    [shots, backendGrid]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const N   = grid.length;
    const ctx = canvas.getContext('2d');
    const W   = canvas.width;
    const H   = canvas.height;
    const cw  = W / N;
    const ch  = H / N;

    // Find max for normalisation
    let maxVal = 1;
    grid.forEach((row) => row.forEach((v) => { if (v > maxVal) maxVal = v; }));

    // Draw heat cells
    ctx.clearRect(0, 0, W, H);

    const imgData = ctx.createImageData(W, H);
    const data    = imgData.data;

    for (let row = 0; row < N; row++) {
      for (let col = 0; col < N; col++) {
        const t = grid[row][col] / maxVal;
        if (t === 0) continue;

        const [r, g, b, a] = heatColor(t);

        // Fill all pixels in this cell
        const x0 = Math.floor(col * cw);
        const y0 = Math.floor(row * ch);
        const x1 = Math.floor((col + 1) * cw);
        const y1 = Math.floor((row + 1) * ch);

        for (let py = y0; py < y1; py++) {
          for (let px = x0; px < x1; px++) {
            const idx = (py * W + px) * 4;
            // Alpha blend over any existing color
            const ea = data[idx + 3] / 255;
            const na = a / 255;
            const oa = na + ea * (1 - na);
            if (oa === 0) continue;
            data[idx]     = Math.round((r * na + data[idx]     * ea * (1 - na)) / oa);
            data[idx + 1] = Math.round((g * na + data[idx + 1] * ea * (1 - na)) / oa);
            data[idx + 2] = Math.round((b * na + data[idx + 2] * ea * (1 - na)) / oa);
            data[idx + 3] = Math.round(oa * 255);
          }
        }
      }
    }

    ctx.putImageData(imgData, 0, 0);

    // Optional: Gaussian blur pass for smoother look
    ctx.filter = 'blur(4px)';
    ctx.drawImage(canvas, 0, 0);
    ctx.filter = 'none';

    // Overlay: target rings
    if (showOverlay) {
      const R   = TARGET_RADIUS_MM;
      const CX  = W / 2;
      const CY  = H / 2;
      const scl = (W / 2) / R;

      ctx.strokeStyle = 'rgba(255,255,255,0.15)';
      ctx.lineWidth   = 0.8;

      [22.5, 45, 90, 135, 180, 225].forEach((r) => {
        ctx.beginPath();
        ctx.arc(CX, CY, r * scl, 0, Math.PI * 2);
        ctx.stroke();
      });

      // Crosshairs
      ctx.strokeStyle = 'rgba(255,255,255,0.1)';
      ctx.setLineDash([3, 4]);
      ctx.beginPath(); ctx.moveTo(CX, 0);   ctx.lineTo(CX, H); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, CY);   ctx.lineTo(W, CY); ctx.stroke();
      ctx.setLineDash([]);
    }
  }, [grid, showOverlay]);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Hit Density Heatmap</span>
        <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>
          {shots.length} shots · {RESOLUTION}×{RESOLUTION} grid
        </span>
      </div>
      <div style={{ padding: 16 }}>
        <canvas
          ref={canvasRef}
          width={400}
          height={400}
          style={{
            width: '100%',
            maxWidth: 400,
            display: 'block',
            margin: '0 auto',
            borderRadius: 8,
            background: '#0a0c10',
          }}
        />
        {/* Colour legend */}
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
    </div>
  );
}