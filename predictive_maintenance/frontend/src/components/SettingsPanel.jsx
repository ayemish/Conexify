import { useState, useEffect, useCallback } from 'react'
import {
  Settings, Database, Wifi, Shield, Bell, Sliders,
  Save, RefreshCw, CheckCircle, AlertTriangle, Server,
  Activity, Clock, Zap
} from 'lucide-react'
import { safeRequest } from '../services/apiClient'

// ── Styles ───────────────────────────────────────────────────────────

const S = {
  card: {
    background: '#fff', borderRadius: 12, padding: '1.25rem',
    border: '1px solid #e2e8f0', marginBottom: '1rem',
  },
  sectionTitle: {
    display: 'flex', alignItems: 'center', gap: 8,
    fontSize: '0.95rem', fontWeight: 700, color: '#1e293b',
    margin: '0 0 1rem',
  },
  label: {
    display: 'block', fontSize: '0.8rem', fontWeight: 600,
    color: '#475569', marginBottom: 4,
  },
  help: { fontSize: '0.7rem', color: '#94a3b8', marginTop: 2 },
  input: {
    width: '100%', padding: '0.45rem 0.65rem', borderRadius: 8,
    border: '1px solid #e2e8f0', fontSize: '0.85rem', boxSizing: 'border-box',
    background: '#f8fafc',
  },
  row: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '0.75rem' },
  toggle: (active) => ({
    position: 'relative', width: 40, height: 22, borderRadius: 11,
    background: active ? '#3b82f6' : '#cbd5e1', cursor: 'pointer',
    transition: 'background 0.2s', border: 'none',
  }),
  toggleDot: (active) => ({
    position: 'absolute', top: 2, left: active ? 20 : 2,
    width: 18, height: 18, borderRadius: '50%', background: '#fff',
    transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
  }),
}

function Toggle({ value, onChange, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.35rem 0' }}>
      <span style={{ fontSize: '0.8rem', color: '#334155' }}>{label}</span>
      <button style={S.toggle(value)} onClick={() => onChange(!value)}>
        <div style={S.toggleDot(value)} />
      </button>
    </div>
  )
}

function StatusDot({ ok, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0.25rem 0' }}>
      <div style={{
        width: 8, height: 8, borderRadius: '50%',
        background: ok ? '#22c55e' : '#ef4444',
      }} />
      <span style={{ fontSize: '0.8rem', color: '#475569' }}>{label}</span>
      <span style={{ fontSize: '0.7rem', color: ok ? '#22c55e' : '#ef4444', marginLeft: 'auto' }}>
        {ok ? 'Connected' : 'Unavailable'}
      </span>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────────

export default function SettingsPanel() {
  const [saved, setSaved] = useState(false)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(false)

  // Settings state
  const [settings, setSettings] = useState({
    // Site
    siteId: 'default',
    siteName: 'Demo Site',
    // Alert thresholds
    alertConfidenceThreshold: 0.70,
    dispatchConfidenceThreshold: 0.85,
    maxAlertsPerDay: 10,
    maxDispatchesPerWeek: 3,
    consensusThreshold: 0.60,
    // Notifications
    enableDesktopNotifications: true,
    enableSoundAlerts: false,
    enableEmailAlerts: false,
    emailRecipients: '',
    // Data
    autoRefreshInterval: 30,
    telemetryRetentionDays: 90,
    // Ingest
    mqttEnabled: false,
    mqttBroker: 'localhost',
    mqttPort: 1883,
    mqttTopics: 'bms/+/telemetry',
    bacnetEnabled: false,
    bacnetPort: 47808,
    // ETL
    etlEnabled: false,
    etlWatchDir: '',
    etlPollInterval: 300,
    // Display
    darkMode: false,
    compactView: false,
    showDebugInfo: false,
  })

  const set = useCallback((key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }))
    setSaved(false)
  }, [])

  // Check system health
  const checkHealth = useCallback(async () => {
    setLoading(true)
    try {
      const [healthResult, readyResult, orchestResult] = await Promise.all([
        safeRequest('/api/v1/health'),
        safeRequest('/api/v1/ready'),
        safeRequest('/api/v1/orchestration/status'),
      ])
      setHealth({
        api: healthResult.ok,
        database: readyResult.data?.database || false,
        redis: readyResult.data?.redis || false,
        orchestrator: orchestResult.data?.available || false,
        version: healthResult.data?.version || 'unknown',
      })
    } catch {
      setHealth({ api: false, database: false, redis: false, orchestrator: false, version: 'unknown' })
    }
    setLoading(false)
  }, [])

  useEffect(() => { checkHealth() }, [checkHealth])

  const handleSave = useCallback(() => {
    // In production this would POST to /api/v1/settings
    localStorage.setItem('pdm_settings', JSON.stringify(settings))
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }, [settings])

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '1.5rem', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0, color: '#1e293b' }}>
          <Settings size={24} /> Settings
        </h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={checkHealth}
            disabled={loading}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '0.4rem 0.8rem', borderRadius: 8, border: '1px solid #e2e8f0',
              background: '#f8fafc', color: '#475569', fontSize: '0.8rem', cursor: 'pointer',
            }}
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} /> Check Health
          </button>
          <button
            onClick={handleSave}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '0.4rem 1rem', borderRadius: 8, border: 'none',
              background: saved ? '#22c55e' : '#2563eb', color: '#fff',
              fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
            }}
          >
            {saved ? <><CheckCircle size={14} /> Saved</> : <><Save size={14} /> Save Settings</>}
          </button>
        </div>
      </div>

      {/* System Health */}
      <div style={S.card}>
        <h3 style={S.sectionTitle}><Server size={18} style={{ color: '#3b82f6' }} /> System Health</h3>
        {health ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem 2rem' }}>
            <StatusDot ok={health.api} label="API Server" />
            <StatusDot ok={health.database} label="PostgreSQL" />
            <StatusDot ok={health.redis} label="Redis Event Bus" />
            <StatusDot ok={health.orchestrator} label="Agent Orchestrator" />
            <div style={{ gridColumn: '1/3', fontSize: '0.7rem', color: '#94a3b8', marginTop: 4 }}>
              API Version: {health.version}
            </div>
          </div>
        ) : (
          <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Checking system health...</div>
        )}
      </div>

      {/* Site Configuration */}
      <div style={S.card}>
        <h3 style={S.sectionTitle}><Database size={18} style={{ color: '#8b5cf6' }} /> Site Configuration</h3>
        <div style={S.row}>
          <div>
            <label style={S.label}>Site ID</label>
            <input style={S.input} value={settings.siteId} onChange={e => set('siteId', e.target.value)} />
            <div style={S.help}>Unique identifier for this deployment site</div>
          </div>
          <div>
            <label style={S.label}>Site Name</label>
            <input style={S.input} value={settings.siteName} onChange={e => set('siteName', e.target.value)} />
          </div>
        </div>
        <div style={S.row}>
          <div>
            <label style={S.label}>Telemetry Retention (days)</label>
            <input type="number" style={S.input} value={settings.telemetryRetentionDays} min={7} max={365}
              onChange={e => set('telemetryRetentionDays', parseInt(e.target.value) || 90)} />
          </div>
          <div>
            <label style={S.label}>Dashboard Auto-Refresh (seconds)</label>
            <input type="number" style={S.input} value={settings.autoRefreshInterval} min={5} max={300}
              onChange={e => set('autoRefreshInterval', parseInt(e.target.value) || 30)} />
          </div>
        </div>
      </div>

      {/* Alert Thresholds */}
      <div style={S.card}>
        <h3 style={S.sectionTitle}><Shield size={18} style={{ color: '#f59e0b' }} /> Alert & Decision Thresholds</h3>
        <div style={S.row}>
          <div>
            <label style={S.label}>Alert Confidence Threshold</label>
            <input type="number" style={S.input} value={settings.alertConfidenceThreshold} min={0} max={1} step={0.05}
              onChange={e => set('alertConfidenceThreshold', parseFloat(e.target.value) || 0.7)} />
            <div style={S.help}>Min confidence to generate an actionable alert</div>
          </div>
          <div>
            <label style={S.label}>Dispatch Confidence Threshold</label>
            <input type="number" style={S.input} value={settings.dispatchConfidenceThreshold} min={0} max={1} step={0.05}
              onChange={e => set('dispatchConfidenceThreshold', parseFloat(e.target.value) || 0.85)} />
            <div style={S.help}>Min confidence for dispatch recommendation</div>
          </div>
        </div>
        <div style={S.row}>
          <div>
            <label style={S.label}>Max Alerts Per Day</label>
            <input type="number" style={S.input} value={settings.maxAlertsPerDay} min={1} max={100}
              onChange={e => set('maxAlertsPerDay', parseInt(e.target.value) || 10)} />
          </div>
          <div>
            <label style={S.label}>Max Dispatches Per Week</label>
            <input type="number" style={S.input} value={settings.maxDispatchesPerWeek} min={0} max={20}
              onChange={e => set('maxDispatchesPerWeek', parseInt(e.target.value) || 3)} />
          </div>
        </div>
        <div style={{ ...S.row, gridTemplateColumns: '1fr' }}>
          <div>
            <label style={S.label}>Consensus Threshold</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="range" min={0.3} max={0.95} step={0.05} value={settings.consensusThreshold}
                onChange={e => set('consensusThreshold', parseFloat(e.target.value))}
                style={{ flex: 1 }}
              />
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#1e293b', minWidth: 40, textAlign: 'right' }}>
                {(settings.consensusThreshold * 100).toFixed(0)}%
              </span>
            </div>
            <div style={S.help}>Weighted vote threshold for collaborative agent consensus</div>
          </div>
        </div>
      </div>

      {/* Streaming Ingest */}
      <div style={S.card}>
        <h3 style={S.sectionTitle}><Wifi size={18} style={{ color: '#06b6d4' }} /> Streaming Ingest</h3>

        <Toggle label="Enable MQTT Ingest" value={settings.mqttEnabled} onChange={v => set('mqttEnabled', v)} />
        {settings.mqttEnabled && (
          <div style={{ ...S.row, marginTop: '0.5rem' }}>
            <div>
              <label style={S.label}>MQTT Broker</label>
              <input style={S.input} value={settings.mqttBroker} onChange={e => set('mqttBroker', e.target.value)} />
            </div>
            <div>
              <label style={S.label}>MQTT Port</label>
              <input type="number" style={S.input} value={settings.mqttPort} onChange={e => set('mqttPort', parseInt(e.target.value) || 1883)} />
            </div>
            <div style={{ gridColumn: '1/3' }}>
              <label style={S.label}>MQTT Topics (comma-separated)</label>
              <input style={S.input} value={settings.mqttTopics} onChange={e => set('mqttTopics', e.target.value)} />
              <div style={S.help}>Use + for single-level wildcard, # for multi-level. E.g. bms/+/telemetry</div>
            </div>
          </div>
        )}

        <div style={{ marginTop: '0.5rem' }} />
        <Toggle label="Enable BACnet/IP Polling" value={settings.bacnetEnabled} onChange={v => set('bacnetEnabled', v)} />
        {settings.bacnetEnabled && (
          <div style={{ ...S.row, marginTop: '0.5rem' }}>
            <div>
              <label style={S.label}>BACnet Port</label>
              <input type="number" style={S.input} value={settings.bacnetPort} onChange={e => set('bacnetPort', parseInt(e.target.value) || 47808)} />
            </div>
          </div>
        )}
      </div>

      {/* ETL Pipeline */}
      <div style={S.card}>
        <h3 style={S.sectionTitle}><Clock size={18} style={{ color: '#f97316' }} /> ETL / Scheduled Import</h3>
        <Toggle label="Enable Scheduled ETL" value={settings.etlEnabled} onChange={v => set('etlEnabled', v)} />
        {settings.etlEnabled && (
          <div style={{ ...S.row, marginTop: '0.5rem' }}>
            <div>
              <label style={S.label}>CSV Watch Directory</label>
              <input style={S.input} value={settings.etlWatchDir} onChange={e => set('etlWatchDir', e.target.value)} placeholder="/data/incoming/" />
              <div style={S.help}>Directory to watch for CSV file drops</div>
            </div>
            <div>
              <label style={S.label}>Poll Interval (seconds)</label>
              <input type="number" style={S.input} value={settings.etlPollInterval} min={30} max={3600}
                onChange={e => set('etlPollInterval', parseInt(e.target.value) || 300)} />
            </div>
          </div>
        )}
      </div>

      {/* Notifications */}
      <div style={S.card}>
        <h3 style={S.sectionTitle}><Bell size={18} style={{ color: '#ef4444' }} /> Notifications</h3>
        <Toggle label="Desktop Notifications" value={settings.enableDesktopNotifications}
          onChange={v => set('enableDesktopNotifications', v)} />
        <Toggle label="Sound Alerts" value={settings.enableSoundAlerts}
          onChange={v => set('enableSoundAlerts', v)} />
        <Toggle label="Email Alerts" value={settings.enableEmailAlerts}
          onChange={v => set('enableEmailAlerts', v)} />
        {settings.enableEmailAlerts && (
          <div style={{ marginTop: '0.5rem' }}>
            <label style={S.label}>Email Recipients (comma-separated)</label>
            <input style={S.input} value={settings.emailRecipients}
              onChange={e => set('emailRecipients', e.target.value)}
              placeholder="ops@example.com, manager@example.com" />
          </div>
        )}
      </div>

      {/* Display */}
      <div style={S.card}>
        <h3 style={S.sectionTitle}><Sliders size={18} style={{ color: '#22c55e' }} /> Display</h3>
        <Toggle label="Compact View" value={settings.compactView} onChange={v => set('compactView', v)} />
        <Toggle label="Show Debug Info" value={settings.showDebugInfo} onChange={v => set('showDebugInfo', v)} />
      </div>
    </div>
  )
}
