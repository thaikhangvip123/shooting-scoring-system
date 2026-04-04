/**
 * components/charts/ScoreHistogram.jsx
 * Bar chart of score-ring distribution using Recharts.
 */

import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts';
import { scoreDistribution, scoreColor } from '@/utils/scoring';

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const { score, count, pct } = payload[0].payload;
  return (
    <div
      style={{
        background: 'var(--c-bg-2)',
        border: '1px solid var(--c-border-2)',
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 12,
        color: 'var(--c-text-1)',
      }}
    >
      <div style={{ fontWeight: 600 }}>Score {score === 0 ? 'Miss' : score}</div>
      <div style={{ color: 'var(--c-text-2)', marginTop: 2 }}>{count} shots ({pct}%)</div>
    </div>
  );
};

export default function ScoreHistogram({ shots = [] }) {
  const data = useMemo(() => {
    const dist  = scoreDistribution(shots);
    const total = shots.length || 1;
    return Object.entries(dist).map(([score, count]) => ({
      score:  Number(score),
      label:  Number(score) === 0 ? 'M' : String(score),
      count,
      pct:    ((count / total) * 100).toFixed(1),
      color:  scoreColor(Number(score)),
    }));
  }, [shots]);

  const avg = shots.length
    ? (shots.reduce((s, sh) => s + (sh.score ?? 0), 0) / shots.length).toFixed(2)
    : null;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Score Distribution</span>
        {avg && (
          <span style={{ fontSize: 12, color: 'var(--c-text-2)' }}>
            avg <span style={{ fontWeight: 700, color: '#fbbf24' }}>{avg}</span>
          </span>
        )}
      </div>
      <div style={{ padding: '12px 8px 8px' }}>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: 'var(--c-text-3)' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--c-text-3)' }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
            {avg && (
              <ReferenceLine
                x={String(Math.round(avg))}
                stroke="var(--c-accent)"
                strokeDasharray="4 3"
                strokeWidth={1}
                label={{
                  value: 'avg',
                  position: 'top',
                  fontSize: 10,
                  fill: 'var(--c-accent-h)',
                }}
              />
            )}
            <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={28}>
              {data.map((entry) => (
                <Cell key={entry.score} fill={entry.color} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}