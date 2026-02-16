import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  Activity, Thermometer, Gauge, Zap, Wind, RefreshCw, Pause, Play, X
} from 'lucide-react'
import { resolveWsUrl } from '../hooks/useWebSocket'

// ── Config ───────────────────────────────────────────────────────────

const MAX_POINTS = 120 // ~10 min at 5s interval

const SENSOR_CHANNELS = [
  { key: 'suction_pressure', label: 'Suction Press.', unit: 'psi', icon: Gauge, color: '#3b82f6', range: [60, 180] },
  { key: 'discharge_pressure', label: 'Discharge Press.', unit: 'psi', icon: Gauge, color: '#8b5cf6', range: [200, 500] },
  { key: 'suction_line_temp', label: 'Suction Temp', unit: '°F', icon: Thermometer, color: '#06b6d4', range: [30, 70] },
  { key: 'discharge_temp', label: 'Discharge Temp', unit: '°F', icon: Thermometer, color: '#ef4444', range: [100, 200] },
  { key: 'supply_air_temp', label: 'Supply Air', unit: '°F', icon: Wind, color: '#22c55e', range: [40, 80] },
  { key: 'return_air_temp', label: 'Return Air', unit: '°F', icon: Wind, color: '#f59e0b', range: [60, 85] },
  { key: 'superheat', label: 'Superheat', unit: '°F', icon: Activity, color: '#ec4899', range: [0, 30] },
  { key: 'subcool', label: 'Subcool', unit: '°F', icon: Activity, color: '#14b8a6', range: [0, 20] },
  { key: 'compressor_current', label: 'Comp. Current', unit: 'A', icon: Zap, color: '#f97316', range: [0, 30] },
  { key: 'compressor_power', label: 'Comp. Power', unit: 'kW', icon: Zap, color: '#a855f7', range: [0, 10] },
]

// ── Sparkline SVG ────────────────────────────────────────────────────

function Sparkline({ points, color, range, width = 220, height = 48 }) {
  if (!points || points.length < 2) {
    return (
      <svg width={width} height={height}>
        <text x={width / 2} y={height / 2 + 4} textAnchor="middle" fill="#64748b" fontSize={10}>
          Waiting for data...
        </text>
      </svg>
    )
  }

  const [minR, maxR] = range
  const padding = 2
  const w = width - padding * 2
  const h = height - padding * 2

  // Auto-scale Y if data exceeds range
  const vals = points.map(p => p.v)
  const dataMin = Math.min(minR, ...vals)
  const dataMax = Math.max(maxR, ...vals)
  const yRange = dataMax - dataMin || 1

  const pathD = points.map((p, i) => {
    const x = padding + (i / (points.length - 1)) * w
    const y = padding + h - ((p.v - dataMin) / yRange) * h
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')

  // Gradient fill
  const fillD = `${pathD} L${(padding + w).toFixed(1)},${(padding + h).toFixed(1)} L${padding},${(padding + h).toFixed(1)} Z`

  const latest = points[points.length - 1]

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <defs>
        <linearGradient id={`grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={fillD} fill={`url(#grad-${color.replace('#', '')})`} />
      <path d={pathD} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      {/* Latest value dot */}
      {latest && (() => {
        const x = padding + w
        const y = padding + h - ((latest.v - dataMin) / yRange) * h
        return <circle cx={x} cy={y} r={3} fill={color} />
      })()}
    </svg>
  )
}

// ── Channel Card ─────────────────────────────────────────────────────

function ChannelCard({ channel, points, onRemove }) {
  const Icon = channel.icon
  const latest = points?.length > 0 ? points[points.length - 1] : null
  const prev = points?.length > 1 ? points[points.length - 2] : null
  const delta = latest && prev ? latest.v - prev.v : 0

  return (
    <div style={{
      background: '#1e293b', borderRadius: 10, padding: '0.6rem 0.8rem',
      border: `1px solid #334155`, position: 'relative',
    }}>
      {onRemove && (
        <button
          onClick={() => onRemove(channel.key)}
          style={{
            position: 'absolute', top: 4, right: 4,
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#64748b', padding: 2,
          }}
        >
          <X size={12} />
        </button>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <Icon size={13} style={{ color: channel.color }} />
        <span style={{ fontSize: '0.7rem', fontWeight: 600, color: '#e2e8f0' }}>{channel.label}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 4 }}>
        <div>
          <span style={{ fontSize: '1.2rem', fontWeight: 700, color: channel.color }}>
            {latest ? latest.v.toFixed(1) : '—'}
          </span>
          <span style={{ fontSize: '0.65rem', color: '#94a3b8', marginLeft: 3 }}>{channel.unit}</span>
        </div>
        {delta !== 0 && (
          <span style={{
            fontSize: '0.65rem',
            color: delta > 0 ? '#f59e0b' : '#22c55e',
          }}>
            {delta > 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}
          </span>
        )}
      </div>

      <Sparkline points={points} color={channel.color} range={channel.range} />

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
        <span style={{ fontSize: '0.55rem', color: '#64748b' }}>
          {points?.length || 0} pts
        </span>
        {latest && (
          <span style={{ fontSize: '0.55rem', color: '#64748b' }}>
            {new Date(latest.t).toLocaleTimeString()}
          </span>
        )}
      </div>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────────

export default function TelemetrySparklines({ assetId: propAssetId, wsConnection }) {
  const [assetId, setAssetId] = useState(propAssetId || '')
  const [activeChannels, setActiveChannels] = useState(
    SENSOR_CHANNELS.slice(0, 6).map(c => c.key)
  )
  const [paused, setPaused] = useState(false)
  const [data, setData] = useState({}) // { channelKey: [{ t, v }] }
  const wsRef = useRef(null)
  const pausedRef = useRef(false)

  useEffect(() => { pausedRef.current = paused }, [paused])

  // Subscribe to WebSocket for asset telemetry
  useEffect(() => {
    if (!assetId) return

    const url = resolveWsUrl(`/api/v1/ws/dashboard/${assetId}`)

    let ws
    try {
      ws = new WebSocket(url)
    } catch {
      return
    }

    ws.onmessage = (evt) => {
      if (pausedRef.current) return
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === 'telemetry_update' && msg.telemetry) {
          const t = msg.timestamp || new Date().toISOString()
          setData(prev => {
            const next = { ...prev }
            for (const ch of SENSOR_CHANNELS) {
              const val = msg.telemetry[ch.key]
              if (val != null) {
                const arr = [...(next[ch.key] || [])]
                arr.push({ t, v: parseFloat(val) })
                if (arr.length > MAX_POINTS) arr.shift()
                next[ch.key] = arr
              }
            }
            return next
          })
        }
      } catch {}
    }

    ws.onclose = () => {
      // Reconnect after 3s
      setTimeout(() => {
        if (wsRef.current === ws) wsRef.current = null
      }, 3000)
    }

    wsRef.current = ws

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [assetId])

  // Also accept data from parent wsConnection
  useEffect(() => {
    if (!wsConnection) return
    const handler = (evt) => {
      if (pausedRef.current) return
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === 'telemetry_update' && msg.asset_id === assetId && msg.telemetry) {
          const t = msg.timestamp || new Date().toISOString()
          setData(prev => {
            const next = { ...prev }
            for (const ch of SENSOR_CHANNELS) {
              const val = msg.telemetry[ch.key]
              if (val != null) {
                const arr = [...(next[ch.key] || [])]
                arr.push({ t, v: parseFloat(val) })
                if (arr.length > MAX_POINTS) arr.shift()
                next[ch.key] = arr
              }
            }
            return next
          })
        }
      } catch {}
    }
    wsConnection.addEventListener('message', handler)
    return () => wsConnection.removeEventListener('message', handler)
  }, [wsConnection, assetId])

  // Generate simulated data for demo mode
  useEffect(() => {
    if (!assetId) return

    // Check if we're getting real data
    const hasRealData = Object.values(data).some(arr => arr.length > 0)
    if (hasRealData) return

    // Simulate data if no real WebSocket data after 3s
    const timeout = setTimeout(() => {
      const interval = setInterval(() => {
        if (pausedRef.current) return
        const t = new Date().toISOString()
        setData(prev => {
          const next = { ...prev }
          for (const ch of SENSOR_CHANNELS) {
            const arr = [...(next[ch.key] || [])]
            const base = (ch.range[0] + ch.range[1]) / 2
            const spread = (ch.range[1] - ch.range[0]) * 0.3
            const lastVal = arr.length > 0 ? arr[arr.length - 1].v : base
            // Random walk with mean reversion
            const drift = (base - lastVal) * 0.05
            const noise = (Math.random() - 0.5) * spread * 0.1
            const newVal = Math.max(ch.range[0], Math.min(ch.range[1], lastVal + drift + noise))
            arr.push({ t, v: newVal })
            if (arr.length > MAX_POINTS) arr.shift()
            next[ch.key] = arr
          }
          return next
        })
      }, 5000)

      return () => clearInterval(interval)
    }, 3000)

    return () => clearTimeout(timeout)
  }, [assetId])

  const toggleChannel = useCallback((key) => {
    setActiveChannels(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    )
  }, [])

  const channels = useMemo(
    () => SENSOR_CHANNELS.filter(c => activeChannels.includes(c.key)),
    [activeChannels]
  )

  return (
    <div style={{
      background: '#0f172a', borderRadius: 12, padding: '1rem 1.25rem',
      border: '1px solid #334155',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Activity size={18} style={{ color: '#3b82f6' }} />
          <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#e2e8f0' }}>
            Live Telemetry
          </span>
          {assetId && (
            <span style={{
              fontSize: '0.7rem', padding: '1px 8px', borderRadius: 6,
              background: '#3b82f620', color: '#3b82f6',
            }}>
              {assetId}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {!propAssetId && (
            <input
              type="text"
              value={assetId}
              onChange={e => setAssetId(e.target.value)}
              placeholder="Asset ID"
              style={{
                padding: '3px 8px', borderRadius: 6, border: '1px solid #334155',
                background: '#1e293b', color: '#e2e8f0', fontSize: '0.75rem', width: 90,
              }}
            />
          )}
          <button
            onClick={() => setPaused(!paused)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '3px 8px', borderRadius: 6, border: '1px solid #334155',
              background: paused ? '#ef444420' : '#1e293b',
              color: paused ? '#ef4444' : '#94a3b8', fontSize: '0.7rem', cursor: 'pointer',
            }}
          >
            {paused ? <><Play size={12} /> Resume</> : <><Pause size={12} /> Pause</>}
          </button>
        </div>
      </div>

      {/* Channel toggles */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: '0.75rem' }}>
        {SENSOR_CHANNELS.map(ch => {
          const active = activeChannels.includes(ch.key)
          return (
            <button
              key={ch.key}
              onClick={() => toggleChannel(ch.key)}
              style={{
                padding: '1px 6px', borderRadius: 4, fontSize: '0.6rem',
                border: `1px solid ${active ? ch.color : '#334155'}`,
                background: active ? `${ch.color}15` : 'transparent',
                color: active ? ch.color : '#64748b',
                cursor: 'pointer',
              }}
            >
              {ch.label}
            </button>
          )
        })}
      </div>

      {/* Sparkline Grid */}
      {assetId ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '0.6rem' }}>
          {channels.map(ch => (
            <ChannelCard
              key={ch.key}
              channel={ch}
              points={data[ch.key] || []}
              onRemove={toggleChannel}
            />
          ))}
        </div>
      ) : (
        <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b', fontSize: '0.85rem' }}>
          Enter an Asset ID to start streaming telemetry data.
        </div>
      )}
    </div>
  )
}
