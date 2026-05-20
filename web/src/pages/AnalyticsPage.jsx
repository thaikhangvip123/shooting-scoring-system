/**
 * pages/AnalyticsPage.jsx
 * Per-target analytics: CEP trend, running average score, and scatter plot.
 */

import { useMemo, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, CartesianGrid, ReferenceLine,
} from 'recharts';
import StatsPanel from '@/components/stats/StatsPanel';
import TargetTypeSelector from '@/components/target/TargetTypeSelector';
import { radialDeviation, calcCEP } from '@/utils/scoring';
import { fmtTime } from '@/utils/format';
import { shotTargetType } from '@/utils/targetGeometry';
import { shotOffsetMm } from '@/utils/units';

const shotX = (shot) => shotOffsetMm(shot).x;
const shotY = (shot) => shotOffsetMm(shot).y;

const ChartTooltip = ({ active, payload }) => {
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

export default function AnalyticsPage({ shots }) {
  const [targetType, setTargetType] = useState('TRON');
  const targetShots = useMemo(
    () => shots.filter((shot) => shotTargetType(shot) === targetType),
    [shots, targetType]
  );

  const cepTrend = useMemo(() => {
    const chronological = targetShots.slice().reverse();
    return chronological.map((shot, index) => {
      const subset = chronological.slice(0, index + 1);
      const radii = subset.map((item) => radialDeviation(shotX(item), shotY(item)));
      return {
        shot: index + 1,
        cep: Number(calcCEP(radii).toFixed(2)),
        score: shot.score,
        time: fmtTime(shot.timestamp),
      };
    });
  }, [targetShots]);

  const scoreTrend = useMemo(() => {
    let sum = 0;
    return targetShots
      .slice()
      .reverse()
      .map((shot, index) => {
        sum += shot.score ?? 0;
        return { shot: index + 1, avg: Number((sum / (index + 1)).toFixed(3)), score: shot.score };
      });
  }, [targetShots]);

  const scatter = useMemo(
    () => targetShots.map((shot) => ({
      x: Number(shotX(shot).toFixed(2)),
      y: Number(shotY(shot).toFixed(2)),
      score: shot.score,
    })),
    [targetShots]
  );

  const chartStyle = {
    background: 'transparent',
    fontSize: 11,
    color: 'var(--c-text-3)',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, height: '100%', overflowY: 'auto' }}>
      <div className="card" style={{ padding: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
        <span className="card-title">Analytics by Target</span>
        <TargetTypeSelector value={targetType} onChange={setTargetType} />
      </div>

      <StatsPanel shots={targetShots} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
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

        <div className="card">
          <div className="card-header">
            <span className="card-title">Running Avg Score</span>
            <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>selected target only</span>
          </div>
          <div style={{ padding: '12px 8px' }}>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={scoreTrend} style={chartStyle}>
                <XAxis dataKey="shot" tick={{ fontSize: 10, fill: 'var(--c-text-3)' }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 10]} tick={{ fontSize: 10, fill: 'var(--c-text-3)' }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <ReferenceLine y={8} stroke="#22c55e" strokeDasharray="3 3" strokeWidth={1} />
                <Line type="monotone" dataKey="score" stroke="#f59e0b" strokeWidth={1} dot={{ r: 2, fill: '#f59e0b' }} name="Score" opacity={0.4} />
                <Line type="monotone" dataKey="avg" stroke="#fbbf24" strokeWidth={2} dot={false} name="Avg" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Shot Scatter (mm)</span>
          <span style={{ fontSize: 11, color: 'var(--c-text-3)' }}>X / Y offset from A4 centre</span>
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

