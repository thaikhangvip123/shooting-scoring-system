/**
 * pages/SettingsPage.jsx
 * Runtime configuration: API endpoint, target dimensions, display prefs.
 * All values are persisted to localStorage.
 */

import { useState } from 'react';

const DEFAULTS = {
  apiUrl:          'http://localhost:8000',
  targetRadiusMm:  225,
  refreshMs:       5000,
  maxShotsDisplay: 200,
};

function loadSettings() {
  try {
    const raw = localStorage.getItem('shoot_settings');
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
  } catch {
    return { ...DEFAULTS };
  }
}

function saveSettings(s) {
  localStorage.setItem('shoot_settings', JSON.stringify(s));
}

export default function SettingsPage() {
  const [settings, setSettings] = useState(loadSettings);
  const [saved,    setSaved]    = useState(false);

  const set = (key) => (e) =>
    setSettings((prev) => ({ ...prev, [key]: e.target.value }));

  const handleSave = () => {
    saveSettings(settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleReset = () => {
    setSettings({ ...DEFAULTS });
    saveSettings(DEFAULTS);
  };

  const Field = ({ label, hint, children }) => (
    <div style={{ marginBottom: 20 }}>
      <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--c-text-2)', marginBottom: 6 }}>
        {label}
      </label>
      {children}
      {hint && (
        <div style={{ fontSize: 11, color: 'var(--c-text-3)', marginTop: 4 }}>{hint}</div>
      )}
    </div>
  );

  const inputStyle = {
    width: '100%',
    background: 'var(--c-bg-2)',
    border: '1px solid var(--c-border-2)',
    borderRadius: 7,
    padding: '8px 12px',
    fontSize: 13,
    color: 'var(--c-text-1)',
    outline: 'none',
    fontFamily: "'JetBrains Mono', monospace",
  };

  return (
    <div style={{ maxWidth: 560 }}>
      <div className="card" style={{ padding: 28 }}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 24, color: 'var(--c-text-1)' }}>
          Configuration
        </div>

        <Field label="Backend API URL" hint="Base URL of the FastAPI server (no trailing slash)">
          <input style={inputStyle} value={settings.apiUrl} onChange={set('apiUrl')} />
        </Field>

        <Field label="Target radius (mm)" hint="Outermost scoring ring radius in millimetres">
          <input style={inputStyle} type="number" min={50} max={1000}
            value={settings.targetRadiusMm} onChange={set('targetRadiusMm')} />
        </Field>

        <Field label="Stats refresh interval (ms)" hint="How often to poll /stats endpoint (minimum 1000)">
          <input style={inputStyle} type="number" min={1000} step={500}
            value={settings.refreshMs} onChange={set('refreshMs')} />
        </Field>

        <Field label="Max shots in memory" hint="Older shots are evicted from the live view (not from the DB)">
          <input style={inputStyle} type="number" min={10} max={2000}
            value={settings.maxShotsDisplay} onChange={set('maxShotsDisplay')} />
        </Field>

        <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
          <button className="btn btn-accent" onClick={handleSave}>
            {saved ? '✓ Saved' : 'Save Settings'}
          </button>
          <button className="btn" onClick={handleReset}>
            Reset Defaults
          </button>
        </div>
      </div>

      {/* Build info */}
      <div style={{ marginTop: 12, fontSize: 11, color: 'var(--c-text-3)', padding: '0 4px' }}>
        ShootScore Dashboard v1.0.0 · Built with React + Vite · FastAPI backend
      </div>
    </div>
  );
}