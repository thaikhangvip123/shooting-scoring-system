/**
 * components/stats/StatCard.jsx
 */

export default function StatCard({ label, value, sub, color, icon }) {
  return (
    <div
      className="card"
      style={{ padding: '16px 18px' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--c-text-3)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            {label}
          </div>
          <div style={{ marginTop: 6, fontSize: 22, fontWeight: 700, color, lineHeight: 1, fontFamily: "'JetBrains Mono', monospace" }}>
            {value}
          </div>
          <div style={{ marginTop: 4, fontSize: 11, color: 'var(--c-text-3)' }}>
            {sub}
          </div>
        </div>
        <span style={{ fontSize: 18, opacity: 0.3 }}>{icon}</span>
      </div>
    </div>
  );
}