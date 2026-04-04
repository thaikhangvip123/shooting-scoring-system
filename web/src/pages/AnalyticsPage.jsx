/**
 * pages/AnalyticsPage.jsx
 * Deeper analytics: CEP trend, running average score, scatter plot.
 */

import { useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, CartesianGrid, ReferenceLine,
} from 'recharts';
import StatsPanel from '@/components/stats/StatsPanel';
import { radialDeviation, calcCEP } from '@/utils/scoring';
import { fmtTime } from '@/utils/format';

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--c-bg-2)', border: '1px solid var(--c-border-2)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color }}>
          {p.name}: <b>{typeof p.value === 'number' ? p.value.toFixed(2) : p.value}</b>
        </div>
      ))}
    </div>
  );
};

export default function AnalyticsPage({ shots, stats }) {
  // Running CEP after each shot
  const cepTrend = useMemo(() => {
    return shots
      .slice()
      .reverse()
      .map((s, i) => {
        const subset = shots.slice(shots.length - 1 - i);
        const radii  = subset.map((sh) => radialDeviation(sh.x_mm, sh.y_mm));
        return {
          shot:  i + 1,
          cep:   Number(calcCEP(radii).toFixed(2)),
          score: s.score,
          time:  fmtTime(s.timestamp),
        };
      });
  }, [shots]);

  // Running average score
  const scoreTrend = useMemo(() => {
    let sum = 0;
    return shots
      .slice()
      .reverse()
      .map((s, i) => {
        sum += s.score ?? 0;
        return { shot: i + 1, avg: Number((sum / (i + 1)).toFixed(3)), score: s.score };
      });
  }, [shots]);

  // Scatter data for x_mm vs y_mm
  const scatter = useMemo(
    () => shots.map((s) => ({ x: Number(s.x_mm?.toFixed(2)), y: Number(s.y_mm?.toFixed(2)), score: s.score })),
    [shots]
  );

  const chartStyle = {
    background: 'transparent',
    fontSize: 11,
    color: 'var(--c-text-3)',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, height: '100%', overflowY: 'auto' }}>
      <StatsPanel shots={shots} stats={stats} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* CEP trend */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">CEP Trend</span>
            <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>mm vs shot #</span>
          </div>
          <div style={{ padding: '12px 8px' }}>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={cepTrend} style={chartStyle}>
                <XAxis dataKey="shot" tick={{ fontSize: 10, fill: 'var(--c-text-3)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--c-text-3)' }} axisLine={false} tickLine={false} unit=" mm" />
                <Tooltip content={<ChartTooltip />} />
                <Line type="monotone" dataKey="cep" stroke="var(--c-accent)" strokeWidth={2} dot={false} name="CEP" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Score trend */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Running Avg Score</span>
            <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>converging mean</span>
          </div>
          <div style={{ padding: '12px 8px' }}>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={scoreTrend} style={chartStyle}>
                <XAxis dataKey="shot" tick={{ fontSize: 10, fill: 'var(--c-text-3)' }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 10]} tick={{ fontSize: 10, fill: 'var(--c-text-3)' }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <ReferenceLine y={8} stroke="#22c55e" strokeDasharray="3 3" strokeWidth={1} />
                <Line type="monotone" dataKey="score" stroke="#f59e0b" strokeWidth={1} dot={{ r: 2, fill: '#f59e0b' }} name="Score" opacity={0.4} />
                <Line type="monotone" dataKey="avg"   stroke="#fbbf24" strokeWidth={2} dot={false} name="Avg" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Scatter plot */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Shot Scatter (mm)</span>
          <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>X / Y deviation from centre</span>
        </div>
        <div style={{ padding: '12px 8px' }}>
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart style={chartStyle}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--c-border)" />
              <XAxis
                dataKey="x" type="number" name="X"
                unit=" mm" domain={['auto', 'auto']}
                tick={{ fontSize: 10, fill: 'var(--c-text-3)' }} axisLine={false} tickLine={false}
              />
              <YAxis
                dataKey="y" type="number" name="Y"
                unit=" mm" domain={['auto', 'auto']}
                tick={{ fontSize: 10, fill: 'var(--c-text-3)' }} axisLine={false} tickLine={false}
              />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} content={<ChartTooltip />} />
              <ReferenceLine x={0} stroke="rgba(255,255,255,0.1)" />
              <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" />
              <Scatter data={scatter} fill="var(--c-accent)" fillOpacity={0.7} r={4} name="Shot" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}