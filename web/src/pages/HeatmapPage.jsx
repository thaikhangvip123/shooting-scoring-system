/**
 * pages/HeatmapPage.jsx
 */
import HeatmapChart   from '@/components/charts/HeatmapChart';
import ScoreHistogram from '@/components/charts/ScoreHistogram';

export default function HeatmapPage({ shots, heatmap }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>
      <HeatmapChart shots={shots} grid={heatmap} />
      <ScoreHistogram shots={shots} />
    </div>
  );
}