/**
 * pages/ShotsPage.jsx
 */
import ShotTable from '@/components/shots/ShotTable';

export default function ShotsPage({ shots, latestShot }) {
  return (
    <div style={{ height: '100%', minHeight: 0 }}>
      <ShotTable shots={shots} latestId={latestShot?.id} />
    </div>
  );
}