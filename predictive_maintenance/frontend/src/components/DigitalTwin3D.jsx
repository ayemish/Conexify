import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import {
  Building2, MapPin, Cpu, ChevronRight, ChevronDown, ArrowLeft,
  Activity, AlertTriangle, Wrench, Clock, Shield, ThermometerSun,
  Gauge, ZoomIn, ZoomOut, RotateCcw, X, RefreshCw, FileText,
  Calendar, DollarSign, TrendingDown, CircleDot, Layers, Server,
  Wind, Snowflake, Flame, Box, BarChart3
} from 'lucide-react'
import { useAppContext } from '../context/AppContext'

/* ═══════════════════════════════════════════════════════════════════
   Constants & Helpers
   ═══════════════════════════════════════════════════════════════════ */

const STATUS_COLORS = {
  normal:          { bg: '#f0fdf4', border: '#bbf7d0', text: '#15803d', dot: '#22c55e' },
  watching:        { bg: '#fffbeb', border: '#fde68a', text: '#92400e', dot: '#f59e0b' },
  action_required: { bg: '#fef2f2', border: '#fecaca', text: '#991b1b', dot: '#ef4444' },
  no_data:         { bg: '#f8fafc', border: '#e2e8f0', text: '#64748b', dot: '#94a3b8' },
}

const ASSET_TYPE_ICONS = {
  hvac_rtu:         Wind,
  chiller:          Snowflake,
  boiler:           Flame,
  compressor_rack:  Server,
  walk_in_cooler:   Snowflake,
  walk_in_freezer:  Snowflake,
  ahu:              Wind,
  condensing_unit:  Snowflake,
  vfd:              Cpu,
  pump:             Activity,
  exhaust_fan:      Wind,
  lighting:         CircleDot,
  bms:              Layers,
}

const HVAC_COMPONENTS = [
  { id: 'compressor', name: 'Compressor', x: 150, y: 180, width: 80, height: 80, type: 'mechanical' },
  { id: 'condenser', name: 'Condenser Coil', x: 300, y: 80, width: 120, height: 60, type: 'heat_exchanger' },
  { id: 'condenser_fan', name: 'Condenser Fan', x: 360, y: 30, width: 50, height: 50, type: 'fan' },
  { id: 'expansion_valve', name: 'Expansion Valve', x: 450, y: 180, width: 40, height: 40, type: 'valve' },
  { id: 'evaporator', name: 'Evaporator Coil', x: 300, y: 280, width: 120, height: 60, type: 'heat_exchanger' },
  { id: 'evaporator_fan', name: 'Evaporator Fan', x: 360, y: 340, width: 50, height: 50, type: 'fan' },
  { id: 'filter_drier', name: 'Filter Drier', x: 520, y: 130, width: 30, height: 50, type: 'filter' },
  { id: 'sight_glass', name: 'Sight Glass', x: 480, y: 130, width: 25, height: 25, type: 'indicator' },
]

const REFRIGERANT_LINES = [
  { from: 'compressor', to: 'condenser', type: 'discharge', color: '#ef4444' },
  { from: 'condenser', to: 'filter_drier', type: 'liquid', color: '#3b82f6' },
  { from: 'filter_drier', to: 'expansion_valve', type: 'liquid', color: '#3b82f6' },
  { from: 'expansion_valve', to: 'evaporator', type: 'mixed', color: '#8b5cf6' },
  { from: 'evaporator', to: 'compressor', type: 'suction', color: '#22c55e' },
]

function getComponentCenter(c) {
  return { x: c.x + c.width / 2, y: c.y + c.height / 2 }
}

function healthBand(score) {
  if (score >= 80) return 'normal'
  if (score >= 60) return 'watching'
  if (score >= 40) return 'action_required'
  return 'action_required'
}

function fmtDate(d) {
  if (!d) return '—'
  try { return new Date(d).toLocaleDateString() } catch { return '—' }
}

function fmtCurrency(v) {
  if (v == null) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
}

/* Generate deterministic fake work orders & maintenance predictions for an asset */
function generateAssetWorkOrders(assetId) {
  const hash = assetId.split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const types = ['Preventive Maintenance', 'Reactive Repair', 'Emergency', 'Inspection', 'Filter Change']
  const statuses = ['Open', 'In Progress', 'Completed', 'Scheduled']
  const priorities = ['Low', 'Medium', 'High', 'Critical']
  const count = 2 + (hash % 4)
  const wos = []
  for (let i = 0; i < count; i++) {
    const seed = hash + i * 17
    wos.push({
      wo_id: `WO-${String(seed % 9000 + 1000)}`,
      type: types[seed % types.length],
      status: statuses[seed % statuses.length],
      priority: priorities[seed % priorities.length],
      description: `${types[seed % types.length]} for ${assetId}`,
      created: new Date(Date.now() - ((seed % 60) + 1) * 86400000).toISOString(),
      estimated_cost: (seed % 20 + 1) * 250,
    })
  }
  return wos
}

function generateMaintenancePrediction(asset) {
  const hash = (asset.asset_id || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const rul = asset.rul_hours || (hash % 8000 + 500)
  const healthScore = asset.health_score || (hash % 60 + 40)
  const failProb30d = Math.min(0.95, Math.max(0.02, (100 - healthScore) / 100 * 0.8 + (hash % 15) / 100))
  const failProb90d = Math.min(0.99, failProb30d * 1.8)
  return {
    rul_hours: Math.round(rul),
    rul_days: Math.round(rul / 24),
    failure_probability_30d: Math.round(failProb30d * 100),
    failure_probability_90d: Math.round(failProb90d * 100),
    degradation_trend: healthScore < 60 ? 'Accelerating' : healthScore < 80 ? 'Moderate' : 'Stable',
    recommended_action: healthScore < 40 ? 'Immediate replacement recommended'
      : healthScore < 60 ? 'Schedule inspection within 2 weeks'
      : healthScore < 80 ? 'Monitor — next PM due soon' : 'No action required',
    next_pm_date: new Date(Date.now() + ((hash % 30) + 5) * 86400000).toISOString(),
  }
}

/* Group assets by a pseudo-controller (by asset type) for tree display */
function groupAssetsByController(assets) {
  const groups = {}
  for (const a of assets) {
    const type = a.asset_type || 'unknown'
    if (!groups[type]) groups[type] = { controller: type, assets: [] }
    groups[type].assets.push(a)
  }
  return Object.values(groups)
}

/* ═══════════════════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════════════════ */

/* ── Location Card ───────────────────────────────────────────────── */
function LocationCard({ site, assetCount, assetTypes, onSelect }) {
  const typeEntries = Object.entries(assetTypes || {})
  const totalAssets = assetCount || typeEntries.reduce((s, [, c]) => s + c, 0)
  return (
    <button
      onClick={onSelect}
      style={{
        background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12,
        padding: '1.25rem', textAlign: 'left', cursor: 'pointer',
        transition: 'all 0.2s', width: '100%',
        display: 'flex', flexDirection: 'column', gap: 10,
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = '#818cf8'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(99,102,241,0.10)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.boxShadow = 'none' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ background: '#eef2ff', borderRadius: 8, padding: 8, display: 'flex' }}>
          <Building2 size={22} color="#6366f1" />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#1e293b' }}>{site.name}</div>
          {site.address && <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{site.address}</div>}
        </div>
        <ChevronRight size={18} color="#94a3b8" />
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.72rem', color: '#64748b', background: '#f1f5f9', borderRadius: 6, padding: '2px 8px' }}>
          {totalAssets} assets
        </span>
        {site.climate_zone && (
          <span style={{ fontSize: '0.72rem', color: '#64748b', background: '#f1f5f9', borderRadius: 6, padding: '2px 8px' }}>
            Zone {site.climate_zone}
          </span>
        )}
        {site.sqft && (
          <span style={{ fontSize: '0.72rem', color: '#64748b', background: '#f1f5f9', borderRadius: 6, padding: '2px 8px' }}>
            {Number(site.sqft).toLocaleString()} sqft
          </span>
        )}
        {site.store_format && (
          <span style={{ fontSize: '0.72rem', color: '#64748b', background: '#f1f5f9', borderRadius: 6, padding: '2px 8px' }}>
            {site.store_format}
          </span>
        )}
      </div>

      {typeEntries.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {typeEntries.slice(0, 6).map(([type, count]) => {
            const Icon = ASSET_TYPE_ICONS[type] || Box
            return (
              <span key={type} style={{
                fontSize: '0.68rem', color: '#475569', background: '#f8fafc',
                border: '1px solid #e2e8f0', borderRadius: 6, padding: '2px 6px',
                display: 'flex', alignItems: 'center', gap: 3,
              }}>
                <Icon size={11} /> {type.replace(/_/g, ' ')} ({count})
              </span>
            )
          })}
        </div>
      )}
    </button>
  )
}

/* ── Asset Row in tree ───────────────────────────────────────────── */
function AssetRow({ asset, selected, onSelect }) {
  const st = STATUS_COLORS[asset.status] || STATUS_COLORS.no_data
  const Icon = ASSET_TYPE_ICONS[asset.asset_type] || Box
  return (
    <button
      onClick={onSelect}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, width: '100%',
        padding: '0.55rem 0.75rem', background: selected ? '#eef2ff' : '#fff',
        border: selected ? '1px solid #a5b4fc' : '1px solid transparent',
        borderRadius: 8, cursor: 'pointer', textAlign: 'left',
        transition: 'all 0.15s',
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = '#f8fafc' }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = '#fff' }}
    >
      <div style={{ background: st.bg, border: `1px solid ${st.border}`, borderRadius: 6, padding: 5, display: 'flex' }}>
        <Icon size={16} color={st.dot} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: '0.8rem', color: '#1e293b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {asset.asset_id}
        </div>
        <div style={{ fontSize: '0.7rem', color: '#64748b' }}>
          {asset.manufacturer} {asset.model}
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: '0.72rem', fontWeight: 600, color: st.text }}>
          {Math.round(asset.health_score || 0)}%
        </div>
        <div style={{ fontSize: '0.65rem', color: '#94a3b8' }}>health</div>
      </div>
    </button>
  )
}

/* ── HVAC Schematic (preserved from original) ────────────────────── */
function HvacSchematic({ asset }) {
  const svgRef = useRef(null)
  const [zoom, setZoom] = useState(1)
  const [selectedComp, setSelectedComp] = useState(null)
  const healthScore = asset?.health_score || 75
  const compStatus = (id) => {
    if (id === 'compressor') return healthBand(healthScore)
    if (id === 'evaporator') return healthBand(healthScore + 5)
    if (id === 'condenser') return healthBand(healthScore + 10)
    return 'normal'
  }
  const compColor = (id) => {
    const b = compStatus(id)
    return STATUS_COLORS[b]?.dot || '#94a3b8'
  }

  return (
    <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid #e2e8f0', background: '#fff' }}>
        <span style={{ fontWeight: 600, fontSize: '0.82rem', color: '#1e293b' }}>HVAC/R System Schematic</span>
        <div style={{ display: 'flex', gap: 4 }}>
          <button onClick={() => setZoom(z => Math.max(z - 0.2, 0.5))} style={ctrlBtnStyle}><ZoomOut size={14} /></button>
          <span style={{ fontSize: '0.7rem', color: '#64748b', padding: '2px 6px' }}>{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom(z => Math.min(z + 0.2, 2))} style={ctrlBtnStyle}><ZoomIn size={14} /></button>
          <button onClick={() => setZoom(1)} style={ctrlBtnStyle}><RotateCcw size={14} /></button>
        </div>
      </div>
      <svg ref={svgRef} viewBox="0 0 600 420" style={{ width: '100%', transform: `scale(${zoom})`, transformOrigin: 'top left', display: 'block' }}>
        <rect x="0" y="0" width="600" height="420" fill="#f8fafc" />
        {REFRIGERANT_LINES.map(line => {
          const from = HVAC_COMPONENTS.find(c => c.id === line.from)
          const to = HVAC_COMPONENTS.find(c => c.id === line.to)
          if (!from || !to) return null
          const fc = getComponentCenter(from), tc = getComponentCenter(to)
          const mx = (fc.x + tc.x) / 2, my = (fc.y + tc.y) / 2
          return (
            <g key={`${line.from}-${line.to}`}>
              <path d={`M ${fc.x} ${fc.y} Q ${mx} ${my - 30} ${tc.x} ${tc.y}`} fill="none" stroke={line.color} strokeWidth={3} strokeDasharray={line.type === 'mixed' ? '5,5' : 'none'} opacity={0.6} />
              <circle r={3} fill={line.color}>
                <animateMotion dur="2s" repeatCount="indefinite" path={`M ${fc.x} ${fc.y} Q ${mx} ${my - 30} ${tc.x} ${tc.y}`} />
              </circle>
            </g>
          )
        })}
        {HVAC_COMPONENTS.map(comp => {
          const c = compColor(comp.id)
          const sel = selectedComp === comp.id
          return (
            <g key={comp.id} style={{ cursor: 'pointer' }} onClick={() => setSelectedComp(sel ? null : comp.id)}>
              {comp.type === 'mechanical' ? (
                <><circle cx={comp.x + comp.width / 2} cy={comp.y + comp.height / 2} r={comp.width / 2} fill={`${c}20`} stroke={c} strokeWidth={sel ? 3 : 2} />
                  <circle cx={comp.x + comp.width / 2} cy={comp.y + comp.height / 2} r={comp.width / 4} fill={c} /></>
              ) : comp.type === 'fan' ? (
                <><circle cx={comp.x + comp.width / 2} cy={comp.y + comp.height / 2} r={comp.width / 2} fill={`${c}20`} stroke={c} strokeWidth={sel ? 3 : 2} />
                  {[0, 60, 120, 180, 240, 300].map(a => <line key={a} x1={comp.x + comp.width / 2} y1={comp.y + comp.height / 2} x2={comp.x + comp.width / 2 + Math.cos(a * Math.PI / 180) * comp.width / 2.5} y2={comp.y + comp.height / 2 + Math.sin(a * Math.PI / 180) * comp.height / 2.5} stroke={c} strokeWidth={2} />)}</>
              ) : comp.type === 'valve' ? (
                <polygon points={`${comp.x},${comp.y + comp.height / 2} ${comp.x + comp.width / 2},${comp.y} ${comp.x + comp.width},${comp.y + comp.height / 2} ${comp.x + comp.width / 2},${comp.y + comp.height}`} fill={`${c}20`} stroke={c} strokeWidth={sel ? 3 : 2} />
              ) : (
                <rect x={comp.x} y={comp.y} width={comp.width} height={comp.height} rx={4} fill={`${c}20`} stroke={c} strokeWidth={sel ? 3 : 2} />
              )}
              <text x={comp.x + comp.width / 2} y={comp.y + comp.height + 14} textAnchor="middle" fontSize="10" fill="#64748b">{comp.name}</text>
            </g>
          )
        })}
        <g transform="translate(20, 395)">
          <text x="0" y="0" fontSize="10" fill="#64748b">Status:</text>
          {[['Normal', '#22c55e'], ['Watching', '#f59e0b'], ['Critical', '#ef4444']].map(([l, c], i) => (
            <g key={l} transform={`translate(${55 + i * 85}, -4)`}>
              <circle r="5" fill={c} /><text x="10" y="4" fontSize="9" fill="#64748b">{l}</text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  )
}

const ctrlBtnStyle = {
  background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 4,
  padding: '3px 5px', cursor: 'pointer', display: 'flex', alignItems: 'center',
}

/* ── Work Orders Table ───────────────────────────────────────────── */
function WorkOrdersPanel({ workOrders }) {
  const priorityColor = { Critical: '#ef4444', High: '#f97316', Medium: '#f59e0b', Low: '#22c55e' }
  const statusColor = { Open: '#3b82f6', 'In Progress': '#f59e0b', Completed: '#22c55e', Scheduled: '#8b5cf6' }
  return (
    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Wrench size={16} color="#6366f1" />
        <span style={{ fontWeight: 700, fontSize: '0.85rem', color: '#1e293b' }}>Outstanding Work Orders</span>
        <span style={{ marginLeft: 'auto', fontSize: '0.72rem', background: '#eef2ff', color: '#4f46e5', borderRadius: 10, padding: '1px 8px', fontWeight: 600 }}>
          {workOrders.filter(w => w.status !== 'Completed').length} open
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
          <thead>
            <tr style={{ background: '#f8fafc' }}>
              {['WO #', 'Type', 'Priority', 'Status', 'Created', 'Est. Cost'].map(h => (
                <th key={h} style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: '#475569', borderBottom: '1px solid #e2e8f0', fontSize: '0.72rem' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {workOrders.map(wo => (
              <tr key={wo.wo_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={tdStyle}><span style={{ fontWeight: 600, color: '#6366f1' }}>{wo.wo_id}</span></td>
                <td style={tdStyle}>{wo.type}</td>
                <td style={tdStyle}>
                  <span style={{ color: priorityColor[wo.priority] || '#64748b', fontWeight: 600, fontSize: '0.72rem' }}>{wo.priority}</span>
                </td>
                <td style={tdStyle}>
                  <span style={{ background: `${statusColor[wo.status] || '#94a3b8'}18`, color: statusColor[wo.status] || '#64748b', padding: '1px 8px', borderRadius: 8, fontSize: '0.7rem', fontWeight: 600 }}>
                    {wo.status}
                  </span>
                </td>
                <td style={tdStyle}>{fmtDate(wo.created)}</td>
                <td style={tdStyle}>{fmtCurrency(wo.estimated_cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const tdStyle = { padding: '8px 10px', color: '#334155' }

/* ── Maintenance Likelihood Panel ────────────────────────────────── */
function MaintenancePredictionPanel({ prediction }) {
  const p = prediction
  const probColor = v => v > 70 ? '#ef4444' : v > 40 ? '#f59e0b' : '#22c55e'
  return (
    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: 8 }}>
        <TrendingDown size={16} color="#6366f1" />
        <span style={{ fontWeight: 700, fontSize: '0.85rem', color: '#1e293b' }}>Maintenance Likelihood</span>
      </div>
      <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <StatBox label="Remaining Useful Life" value={`${p.rul_days} days`} sub={`${p.rul_hours} operating hours`} icon={Clock} color="#3b82f6" />
        <StatBox label="Degradation Trend" value={p.degradation_trend} sub="Based on recent telemetry" icon={TrendingDown}
          color={p.degradation_trend === 'Accelerating' ? '#ef4444' : p.degradation_trend === 'Moderate' ? '#f59e0b' : '#22c55e'} />
        <div style={{ ...statBoxBase, borderColor: probColor(p.failure_probability_30d) + '40' }}>
          <div style={{ fontSize: '0.7rem', color: '#64748b', marginBottom: 4 }}>Failure Probability (30 day)</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ flex: 1, height: 8, background: '#f1f5f9', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ width: `${p.failure_probability_30d}%`, height: '100%', background: probColor(p.failure_probability_30d), borderRadius: 4, transition: 'width 0.5s' }} />
            </div>
            <span style={{ fontWeight: 700, fontSize: '0.85rem', color: probColor(p.failure_probability_30d) }}>{p.failure_probability_30d}%</span>
          </div>
        </div>
        <div style={{ ...statBoxBase, borderColor: probColor(p.failure_probability_90d) + '40' }}>
          <div style={{ fontSize: '0.7rem', color: '#64748b', marginBottom: 4 }}>Failure Probability (90 day)</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ flex: 1, height: 8, background: '#f1f5f9', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ width: `${p.failure_probability_90d}%`, height: '100%', background: probColor(p.failure_probability_90d), borderRadius: 4, transition: 'width 0.5s' }} />
            </div>
            <span style={{ fontWeight: 700, fontSize: '0.85rem', color: probColor(p.failure_probability_90d) }}>{p.failure_probability_90d}%</span>
          </div>
        </div>
      </div>
      <div style={{ padding: '0 14px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, padding: '8px 12px', fontSize: '0.78rem', color: '#92400e', display: 'flex', gap: 8, alignItems: 'start' }}>
          <AlertTriangle size={15} style={{ marginTop: 1, flexShrink: 0 }} />
          <div><strong>Recommendation:</strong> {p.recommended_action}</div>
        </div>
        <div style={{ fontSize: '0.72rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Calendar size={13} /> Next scheduled PM: {fmtDate(p.next_pm_date)}
        </div>
      </div>
    </div>
  )
}

const statBoxBase = { background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }

function StatBox({ label, value, sub, icon: Icon, color }) {
  return (
    <div style={statBoxBase}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <Icon size={14} color={color} />
        <span style={{ fontSize: '0.7rem', color: '#64748b' }}>{label}</span>
      </div>
      <div style={{ fontWeight: 700, fontSize: '1rem', color: color || '#1e293b' }}>{value}</div>
      {sub && <div style={{ fontSize: '0.68rem', color: '#94a3b8', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

/* ── Technical Specifications Panel ──────────────────────────────── */
function TechSpecsPanel({ asset }) {
  const specs = [
    { label: 'Asset ID', value: asset.asset_id },
    { label: 'Type', value: (asset.asset_type || '').replace(/_/g, ' ').toUpperCase() },
    { label: 'Manufacturer', value: asset.manufacturer || '—' },
    { label: 'Model', value: asset.model || '—' },
    { label: 'Site', value: asset.site_id || '—' },
    { label: 'Estate', value: asset.estate || '—' },
    { label: 'Location', value: asset.location || '—' },
    { label: 'Status', value: asset.status || '—' },
    { label: 'Health Score', value: `${Math.round(asset.health_score || 0)}%` },
    { label: 'RUL', value: asset.rul_hours ? `${Math.round(asset.rul_hours)} hrs` : '—' },
    { label: 'Sensor Trust', value: asset.sensor_health || '—' },
    { label: 'Active Alert', value: asset.active_alert ? asset.active_alert.primary_fault : 'None' },
  ]
  return (
    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: 8 }}>
        <FileText size={16} color="#6366f1" />
        <span style={{ fontWeight: 700, fontSize: '0.85rem', color: '#1e293b' }}>Technical Specifications</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', fontSize: '0.78rem' }}>
        {specs.map((s, i) => (
          <div key={s.label} style={{ padding: '8px 14px', borderBottom: '1px solid #f1f5f9', background: i % 4 < 2 ? '#fff' : '#fafbfc' }}>
            <div style={{ color: '#64748b', fontSize: '0.7rem', marginBottom: 2 }}>{s.label}</div>
            <div style={{ color: '#1e293b', fontWeight: 600 }}>{s.value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════
   Main Component
   ═══════════════════════════════════════════════════════════════════ */

export default function DigitalTwin3D({ assetId }) {
  const { availableSites, siteId } = useAppContext()
  const [sites, setSites] = useState([])
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedSite, setSelectedSite] = useState(null)
  const [selectedAsset, setSelectedAsset] = useState(null)
  const [expandedControllers, setExpandedControllers] = useState(new Set())

  // Fetch sites from API (with rich asset type data)
  useEffect(() => {
    async function fetchSites() {
      setLoading(true)
      try {
        const res = await fetch('/api/v1/fleet/sites')
        if (res.ok) {
          const data = await res.json()
          if (data.sites && data.sites.length > 0) {
            setSites(data.sites)
            setLoading(false)
            return
          }
        }
      } catch { /* fall through */ }
      // Fallback to AppContext availableSites
      if (availableSites && availableSites.length > 0) {
        setSites(availableSites.map(s => ({ ...s, asset_count: 0, asset_types: {} })))
      }
      setLoading(false)
    }
    fetchSites()
  }, [availableSites])

  // Fetch assets when a site is selected
  useEffect(() => {
    if (!selectedSite) { setAssets([]); return }
    async function fetchAssets() {
      try {
        const res = await fetch(`/api/v1/fleet/assets?site_id=${encodeURIComponent(selectedSite.id)}&limit=500`)
        if (res.ok) {
          const data = await res.json()
          if (data.assets && data.assets.length > 0) {
            setAssets(data.assets)
            // Auto-expand all controllers
            const types = new Set(data.assets.map(a => a.asset_type || 'unknown'))
            setExpandedControllers(types)
            return
          }
        }
      } catch { /* fall through */ }
      // Generate sample assets as fallback
      const sampleTypes = ['hvac_rtu', 'chiller', 'boiler', 'compressor_rack', 'ahu']
      const fakeAssets = []
      const count = (selectedSite.asset_count || 8)
      for (let i = 0; i < count; i++) {
        const type = sampleTypes[i % sampleTypes.length]
        const hash = (selectedSite.id + i).split('').reduce((a, c) => a + c.charCodeAt(0), 0)
        fakeAssets.push({
          asset_id: `${type.toUpperCase().replace(/_/g, '-')}-${String(hash % 900 + 100)}`,
          site_id: selectedSite.id,
          asset_type: type,
          manufacturer: ['Carrier', 'Trane', 'Lennox', 'Daikin', 'York'][i % 5],
          model: `Model-${hash % 500 + 100}`,
          status: ['normal', 'normal', 'watching', 'normal', 'action_required'][i % 5],
          health_score: 40 + (hash % 55),
          rul_hours: 1000 + (hash % 7000),
          sensor_health: `${8 + (hash % 5)}/12 sensors trusted`,
          estate: selectedSite.name,
          location: selectedSite.name,
          active_alert: i % 5 === 4 ? { primary_fault: 'High discharge temp', confidence: 0.82 } : null,
        })
      }
      setAssets(fakeAssets)
      setExpandedControllers(new Set(sampleTypes))
    }
    fetchAssets()
  }, [selectedSite])

  // If assetId prop is provided and we have no selection, try to auto-select
  useEffect(() => {
    if (assetId && assets.length > 0 && !selectedAsset) {
      const match = assets.find(a => a.asset_id === assetId)
      if (match) setSelectedAsset(match)
    }
  }, [assetId, assets, selectedAsset])

  const controllerGroups = useMemo(() => groupAssetsByController(assets), [assets])

  const toggleController = (type) => {
    setExpandedControllers(prev => {
      const next = new Set(prev)
      next.has(type) ? next.delete(type) : next.add(type)
      return next
    })
  }

  const workOrders = useMemo(() => selectedAsset ? generateAssetWorkOrders(selectedAsset.asset_id) : [], [selectedAsset])
  const prediction = useMemo(() => selectedAsset ? generateMaintenancePrediction(selectedAsset) : null, [selectedAsset])

  /* ── Breadcrumb ─────────────────────────────────────────────────── */
  const breadcrumb = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', color: '#64748b', marginBottom: 16 }}>
      <button onClick={() => { setSelectedSite(null); setSelectedAsset(null); setAssets([]) }}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6366f1', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4, padding: 0 }}>
        <Building2 size={14} /> All Locations
      </button>
      {selectedSite && (
        <>
          <ChevronRight size={14} />
          <button onClick={() => setSelectedAsset(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: selectedAsset ? '#6366f1' : '#1e293b', fontWeight: 600, padding: 0 }}>
            {selectedSite.name}
          </button>
        </>
      )}
      {selectedAsset && (
        <>
          <ChevronRight size={14} />
          <span style={{ color: '#1e293b', fontWeight: 600 }}>{selectedAsset.asset_id}</span>
        </>
      )}
    </div>
  )

  /* ── View: All Locations ────────────────────────────────────────── */
  if (!selectedSite) {
    return (
      <div style={{ padding: '1.5rem', maxWidth: 1200, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <div style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', borderRadius: 10, padding: 10, display: 'flex' }}>
            <Layers size={26} color="#fff" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 800, color: '#1e293b', fontFamily: 'var(--font-display)' }}>Digital Twin Explorer</h1>
            <p style={{ margin: 0, fontSize: '0.82rem', color: '#64748b' }}>Locations, controllers, and asset twins across the portfolio</p>
          </div>
          {loading && <RefreshCw size={18} color="#6366f1" style={{ marginLeft: 'auto', animation: 'spin 1s linear infinite' }} />}
        </div>

        {/* Summary bar */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 20 }}>
          {[
            { label: 'Locations', value: sites.length, icon: MapPin, color: '#6366f1' },
            { label: 'Total Assets', value: sites.reduce((s, st) => s + (st.asset_count || 0), 0), icon: Box, color: '#3b82f6' },
            { label: 'Asset Types', value: new Set(sites.flatMap(s => Object.keys(s.asset_types || {}))).size, icon: Layers, color: '#8b5cf6' },
          ].map(item => (
            <div key={item.label} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ background: `${item.color}15`, borderRadius: 8, padding: 8, display: 'flex' }}>
                <item.icon size={20} color={item.color} />
              </div>
              <div>
                <div style={{ fontWeight: 800, fontSize: '1.2rem', color: '#1e293b' }}>{item.value}</div>
                <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{item.label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Location grid */}
        {sites.length === 0 && !loading && (
          <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
            <Building2 size={40} style={{ marginBottom: 10, opacity: 0.5 }} />
            <p>No locations found. Start the backend and ingest asset data.</p>
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 14 }}>
          {sites.map(site => (
            <LocationCard key={site.id} site={site} assetCount={site.asset_count} assetTypes={site.asset_types} onSelect={() => setSelectedSite(site)} />
          ))}
        </div>
      </div>
    )
  }

  /* ── View: Site selected → Controller/Asset tree + optional detail ─ */
  return (
    <div style={{ padding: '1.5rem', maxWidth: 1400, margin: '0 auto' }}>
      {breadcrumb}

      <div style={{ display: 'grid', gridTemplateColumns: selectedAsset ? '300px 1fr' : '1fr', gap: 20 }}>
        {/* Left: Asset tree */}
        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden', maxHeight: 'calc(100vh - 140px)', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #e2e8f0', background: '#fafbfc' }}>
            <div style={{ fontWeight: 700, fontSize: '0.92rem', color: '#1e293b' }}>{selectedSite.name}</div>
            <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: 2 }}>{assets.length} assets · {controllerGroups.length} controller groups</div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
            {controllerGroups.map(group => {
              const Icon = ASSET_TYPE_ICONS[group.controller] || Cpu
              const expanded = expandedControllers.has(group.controller)
              return (
                <div key={group.controller} style={{ marginBottom: 4 }}>
                  <button
                    onClick={() => toggleController(group.controller)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                      padding: '8px 10px', background: expanded ? '#f1f5f9' : 'transparent',
                      border: 'none', borderRadius: 8, cursor: 'pointer', textAlign: 'left',
                    }}
                  >
                    {expanded ? <ChevronDown size={14} color="#64748b" /> : <ChevronRight size={14} color="#64748b" />}
                    <Icon size={15} color="#6366f1" />
                    <span style={{ fontWeight: 600, fontSize: '0.8rem', color: '#334155', flex: 1 }}>
                      {group.controller.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    </span>
                    <span style={{ fontSize: '0.68rem', color: '#94a3b8', background: '#f1f5f9', borderRadius: 8, padding: '1px 7px' }}>
                      {group.assets.length}
                    </span>
                  </button>
                  {expanded && (
                    <div style={{ paddingLeft: 18 }}>
                      {group.assets.map(asset => (
                        <AssetRow
                          key={asset.asset_id}
                          asset={asset}
                          selected={selectedAsset?.asset_id === asset.asset_id}
                          onSelect={() => setSelectedAsset(asset)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {controllerGroups.length === 0 && (
              <div style={{ textAlign: 'center', padding: 30, color: '#94a3b8', fontSize: '0.82rem' }}>
                <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite', marginBottom: 8 }} />
                <p>Loading assets…</p>
              </div>
            )}
          </div>
        </div>

        {/* Right: Asset detail (only when asset selected) */}
        {selectedAsset && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxHeight: 'calc(100vh - 140px)', overflowY: 'auto' }}>
            {/* Header */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{
                background: STATUS_COLORS[selectedAsset.status]?.bg || '#f8fafc',
                border: `1px solid ${STATUS_COLORS[selectedAsset.status]?.border || '#e2e8f0'}`,
                borderRadius: 10, padding: 10, display: 'flex',
              }}>
                {(() => { const I = ASSET_TYPE_ICONS[selectedAsset.asset_type] || Box; return <I size={26} color={STATUS_COLORS[selectedAsset.status]?.dot || '#94a3b8'} /> })()}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 800, fontSize: '1.1rem', color: '#1e293b' }}>{selectedAsset.asset_id}</div>
                <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
                  {selectedAsset.manufacturer} {selectedAsset.model} · {(selectedAsset.asset_type || '').replace(/_/g, ' ')}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 800, fontSize: '1.5rem', color: STATUS_COLORS[selectedAsset.status]?.dot || '#94a3b8' }}>
                  {Math.round(selectedAsset.health_score || 0)}%
                </div>
                <div style={{ fontSize: '0.7rem', color: '#64748b' }}>Health Score</div>
              </div>
            </div>

            {/* Schematic */}
            <HvacSchematic asset={selectedAsset} />

            {/* Tech Specs */}
            <TechSpecsPanel asset={selectedAsset} />

            {/* Work Orders */}
            <WorkOrdersPanel workOrders={workOrders} />

            {/* Maintenance Likelihood */}
            {prediction && <MaintenancePredictionPanel prediction={prediction} />}
          </div>
        )}

        {/* Placeholder when no asset selected */}
        {!selectedAsset && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 60,
            color: '#94a3b8', textAlign: 'center',
          }}>
            <Layers size={48} style={{ marginBottom: 16, opacity: 0.4 }} />
            <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#64748b', fontWeight: 600 }}>Select an Asset</h3>
            <p style={{ margin: '8px 0 0', fontSize: '0.82rem', maxWidth: 320 }}>
              Choose an asset from the controller tree on the left to view its digital twin — schematics, specifications, work orders, and maintenance predictions.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
