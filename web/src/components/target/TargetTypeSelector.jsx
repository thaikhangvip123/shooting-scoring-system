import { TARGET_TYPE_IDS, TARGET_TYPES } from '@/utils/targetGeometry';

export default function TargetTypeSelector({ value = 'TRON', onChange, disabled = false }) {
  return (
    <div className="target-type-selector" role="group" aria-label="Target type">
      {TARGET_TYPE_IDS.map((id) => (
        <button
          key={id}
          type="button"
          className={`target-type-button ${value === id ? 'is-active' : ''}`}
          disabled={disabled}
          onClick={() => onChange?.(id)}
        >
          {TARGET_TYPES[id].label}
        </button>
      ))}
    </div>
  );
}
