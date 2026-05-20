/**
 * pages/HeatmapPage.jsx
 */
import HeatmapChart   from '@/components/charts/HeatmapChart';
import ScoreHistogram from '@/components/charts/ScoreHistogram';
import TargetTypeSelector from '@/components/target/TargetTypeSelector';
import { shotTargetType } from '@/utils/targetGeometry';

export default function HeatmapPage({ shots, heatmap, targetType, onTargetTypeChange }) {
  const targetShots = shots.filter((shot) => shotTargetType(shot) === targetType);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(540px, 1fr) 1fr', gap: 20, alignItems: 'start' }}>
      <div className="card">
        <div className="card-header">
          <span className="card-title">Target Heatmap</span>
          <TargetTypeSelector value={targetType} onChange={onTargetTypeChange} />
        </div>
        <HeatmapChart shots={targetShots} grid={heatmap} targetType={targetType} />
      </div>
      <ScoreHistogram shots={targetShots} />
    </div>
  );
}
