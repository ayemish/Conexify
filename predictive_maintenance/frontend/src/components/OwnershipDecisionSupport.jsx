import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Users, DollarSign, BarChart3, Shield, Zap, Leaf, TrendingUp,
  Settings, ChevronDown, ChevronUp, RefreshCw, Download, Filter,
  AlertTriangle, CheckCircle, Info, Layers, Target, Sliders,
  ArrowRight, Eye, GitBranch, PieChart, Building2, MapPin,
  Wallet, Scale, Briefcase, Clock, FileText, Search, X,
  ChevronRight, Loader2, Cpu, MessageSquare
} from 'lucide-react'
import AgentReasoningConsole from './AgentReasoningConsole'
import AgentCommsPanel from './AgentCommsPanel'
import BudgetPage from './BudgetPage'

const API = '/api/v1/ownership'

const fmt = v => {
  if (v == null || isNaN(v)) return '$0'
  return '$' + Math.round(v).toLocaleString()
}
const pct = v => v != null ? `${(v * 100).toFixed(1)}%` : '—'
const pctRaw = v => v != null ? `${v.toFixed(1)}%` : '—'

const QUADRANT_META = {
  Q1: { label: 'FM-Controlled Opex', color: '#2563eb', bg: '#eff6ff', icon: Sliders },
  Q2: { label: 'Finance-Controlled Capex', color: '#7c3aed', bg: '#f5f3ff', icon: DollarSign },
  Q3: { label: 'Compliance-Driven Risk', color: '#dc2626', bg: '#fef2f2', icon: Shield },
  Q4: { label: 'Cross-Silo Strategic', color: '#059669', bg: '#ecfdf5', icon: Layers },
}

const OWNER_META = {
  fm: { label: 'Facilities Management', color: '#2563eb' },
  finance: { label: 'Finance', color: '#7c3aed' },
  ops: { label: 'Operations', color: '#0891b2' },
  food_safety: { label: 'Food Safety / Compliance', color: '#dc2626' },
  esg: { label: 'ESG / Sustainability', color: '#059669' },
  vendor: { label: 'Vendor', color: '#d97706' },
  executive: { label: 'Executive', color: '#475569' },
}

const COST_TYPE_META = {
  opex: { label: 'Opex', color: '#2563eb' },
  capex: { label: 'Capex', color: '#7c3aed' },
  risk: { label: 'Risk', color: '#dc2626' },
  strategic: { label: 'Strategic', color: '#059669' },
}

const PHASES = [
  {
    id: 'configure', label: 'Configure', icon: Settings,
    description: 'Set budgets, tune parameters, assign ownership',
    views: [
      { id: 'budget', label: 'Budget', icon: Wallet },
      { id: 'parameters', label: 'Parameters', icon: Sliders },
      { id: 'ownership', label: 'Ownership Map', icon: Users },
    ],
  },
  {
    id: 'analyze', label: 'Analyze', icon: BarChart3,
    description: 'Translate metrics into cost lines and consolidated ROI',
    views: [
      { id: 'coststack', label: 'Cost Stack', icon: BarChart3 },
      { id: 'roi', label: 'ROI Summary', icon: TrendingUp },
      { id: 'scenarios', label: 'Scenarios', icon: GitBranch },
    ],
  },
  {
    id: 'optimize', label: 'Optimize', icon: Zap,
    description: '12-agent AI crew for Pareto-optimal recommendations',
    views: [
      { id: 'advisory', label: 'AI Advisory', icon: Zap },
    ],
  },
]

// ── Sample metric inputs for demo ────────────────────────────────
const SAMPLE_METRIC_INPUTS = {
  m_reactive_jobs: { wo_count: 120, cost_per_wo: 380, reduction_pct: 0.25 },
  m_ppm_frequency: { baseline_pm_tasks: 500, optimized_pm_tasks: 400, pm_cost_per_task: 150, avoided_reactive_savings: 15000 },
  m_wo_volume: { wo_volume: 200, avg_vendor_rate: 250, vendor_reduction_pct: 0.15, admin_overhead_per_wo: 45, admin_reduction_pct: 0.20 },
  m_service_bureau: { call_volume: 800, cost_per_call: 25, deflection_rate: 0.30 },
  m_replacement_cycle: { replacement_count: 5, avg_replacement_cost: 18000, avoided_failure_cost: 25000 },
  m_lifecycle_model: { keep_lcc_npv: 250000, replace_lcc_npv: 180000 },
  m_temp_breaches: { breach_count: 15, avg_spoilage_per_breach: 2500, penalty_probability: 0.15, avg_penalty: 10000, audit_risk_cost: 5000 },
  m_product_discard: { discard_volume: 500, avg_cogs_per_unit: 8, discard_events: 30, labor_per_event: 120, disposal_cost_per_unit: 1.5 },
  m_regulatory_penalties: { penalty_events: 2, avg_fine: 15000, remediation_cost: 8000 },
  m_energy_reduction: { kwh_reduction: 500000, electricity_rate: 0.12, carbon_factor: 0.0004, carbon_price: 50 },
  m_emissions_reduction: { emissions_reduced_tco2e: 200, carbon_price: 50, compliance_reporting_value: 10000 },
}

// ═══════════════════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════════════════

function StatCard({ icon: Icon, title, value, subtitle, color = '#2563eb' }) {
  return (
    <div style={{
      background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0',
      padding: '1rem 1.25rem', flex: 1, minWidth: 180,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{ background: color + '18', borderRadius: 8, padding: 6, display: 'flex' }}>
          <Icon size={18} style={{ color }} />
        </div>
        <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>{title}</span>
      </div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#0f172a' }}>{value}</div>
      {subtitle && <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: 2 }}>{subtitle}</div>}
    </div>
  )
}

function QuadrantBadge({ quadrant, small }) {
  const meta = QUADRANT_META[quadrant] || QUADRANT_META.Q1
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: small ? '2px 6px' : '3px 10px',
      borderRadius: 6, fontSize: small ? '0.65rem' : '0.72rem',
      fontWeight: 600, background: meta.bg, color: meta.color,
      border: `1px solid ${meta.color}30`,
    }}>
      {quadrant}
    </span>
  )
}

function OwnerBadge({ role, small }) {
  const meta = OWNER_META[role] || { label: role, color: '#64748b' }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: small ? '2px 6px' : '3px 10px',
      borderRadius: 6, fontSize: small ? '0.65rem' : '0.72rem',
      fontWeight: 600, background: meta.color + '15', color: meta.color,
      border: `1px solid ${meta.color}30`,
    }}>
      {meta.label}
    </span>
  )
}

function HorizontalBar({ items, height = 28 }) {
  const total = items.reduce((s, i) => s + Math.abs(i.value), 0)
  if (total === 0) return null
  return (
    <div style={{ display: 'flex', borderRadius: 6, overflow: 'hidden', height, width: '100%' }}>
      {items.map((item, idx) => {
        const w = (Math.abs(item.value) / total) * 100
        if (w < 0.5) return null
        return (
          <div
            key={idx}
            title={`${item.label}: ${fmt(item.value)} (${w.toFixed(1)}%)`}
            style={{
              width: `${w}%`, background: item.color, minWidth: 2,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.65rem', color: '#fff', fontWeight: 600,
              transition: 'width 0.3s',
            }}
          >
            {w > 12 ? item.label : ''}
          </div>
        )
      })}
    </div>
  )
}

function ConfidenceDot({ value }) {
  const color = value >= 0.7 ? '#16a34a' : value >= 0.4 ? '#d97706' : '#dc2626'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.72rem' }}>
      <span style={{
        width: 8, height: 8, borderRadius: '50%', background: color,
        display: 'inline-block',
      }} />
      {(value * 100).toFixed(0)}%
    </span>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Parameters Tab
// ═══════════════════════════════════════════════════════════════════

function ParametersTab({ params, sliders, onOverride, resolvedParams }) {
  const [filterCat, setFilterCat] = useState('')
  const [scope, setScope] = useState({ region: '', banner: '', store: '' })

  const categories = useMemo(() => {
    const cats = new Set()
    ;(params || []).forEach(p => cats.add(p.category))
    return [...cats].sort()
  }, [params])

  const filteredParams = useMemo(() => {
    if (!params) return []
    if (!filterCat) return params
    return params.filter(p => p.category === filterCat)
  }, [params, filterCat])

  const sliderParams = useMemo(() => sliders || [], [sliders])

  return (
    <div>
      {/* Quick Sliders */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Sliders size={18} style={{ color: '#2563eb' }} />
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>High-Impact Parameters</h3>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
          {sliderParams.map(p => (
            <div key={p.param_id} style={{ padding: '0.75rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#334155' }}>{p.name}</span>
                <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#2563eb' }}>
                  {resolvedParams?.[p.param_id]?.value ?? p.default_value} {p.unit}
                </span>
              </div>
              <input
                type="range"
                min={p.min_value ?? 0}
                max={p.max_value ?? 100}
                step={p.step ?? 1}
                value={resolvedParams?.[p.param_id]?.value ?? p.default_value}
                onChange={e => onOverride(p.param_id, parseFloat(e.target.value))}
                style={{ width: '100%', accentColor: '#2563eb' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', color: '#94a3b8' }}>
                <span>{p.min_value}{p.unit}</span>
                <span>{p.max_value}{p.unit}</span>
              </div>
              {p.affects_quadrants?.length > 0 && (
                <div style={{ marginTop: 4, display: 'flex', gap: 4 }}>
                  {p.affects_quadrants.map(q => <QuadrantBadge key={q} quadrant={q} small />)}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Scope Selector */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <MapPin size={18} style={{ color: '#0891b2' }} />
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Scope & Inheritance</h3>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Global → Region → Banner → Store</span>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          {['region', 'banner', 'store'].map(level => (
            <div key={level} style={{ flex: 1 }}>
              <label style={labelStyle}>{level.charAt(0).toUpperCase() + level.slice(1)}</label>
              <input
                style={inputStyle}
                placeholder={`All ${level}s`}
                value={scope[level]}
                onChange={e => setScope(s => ({ ...s, [level]: e.target.value }))}
              />
            </div>
          ))}
        </div>
      </div>

      {/* All Parameters */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Settings size={18} style={{ color: '#64748b' }} />
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>All Parameters</h3>
          <select
            style={{ ...inputStyle, width: 'auto', marginLeft: 'auto', padding: '4px 8px', fontSize: '0.78rem' }}
            value={filterCat}
            onChange={e => setFilterCat(e.target.value)}
          >
            <option value="">All Categories</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Parameter</th>
                <th style={thStyle}>Category</th>
                <th style={thStyle}>Value</th>
                <th style={thStyle}>Unit</th>
                <th style={thStyle}>Source</th>
                <th style={thStyle}>Quadrants</th>
              </tr>
            </thead>
            <tbody>
              {filteredParams.map(p => {
                const resolved = resolvedParams?.[p.param_id]
                return (
                  <tr key={p.param_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={tdStyle}>{p.name}</td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: '0.7rem', padding: '2px 6px', borderRadius: 4, background: '#f1f5f9', color: '#475569' }}>
                        {p.category}
                      </span>
                    </td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>
                      {resolved?.value ?? p.default_value}
                    </td>
                    <td style={tdStyle}>{p.unit}</td>
                    <td style={tdStyle}>
                      <span style={{
                        fontSize: '0.68rem', color: resolved?.is_default ? '#94a3b8' : '#2563eb',
                        fontWeight: resolved?.is_default ? 400 : 600,
                      }}>
                        {resolved?.source || 'default'}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', gap: 3 }}>
                        {(p.affects_quadrants || []).map(q => <QuadrantBadge key={q} quadrant={q} small />)}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Ownership Map Tab
// ═══════════════════════════════════════════════════════════════════

function OwnershipTab({ metrics, ownershipMap }) {
  const [filterQuadrant, setFilterQuadrant] = useState('')
  const [filterOwner, setFilterOwner] = useState('')

  const filteredMetrics = useMemo(() => {
    if (!metrics) return []
    let filtered = metrics
    if (filterQuadrant) filtered = filtered.filter(m => m.quadrant === filterQuadrant)
    if (filterOwner) filtered = filtered.filter(m => m.default_owner_role === filterOwner)
    return filtered
  }, [metrics, filterQuadrant, filterOwner])

  // Group metrics by quadrant
  const byQuadrant = useMemo(() => {
    const grouped = { Q1: [], Q2: [], Q3: [], Q4: [] }
    ;(metrics || []).forEach(m => {
      if (grouped[m.quadrant]) grouped[m.quadrant].push(m)
    })
    return grouped
  }, [metrics])

  return (
    <div>
      {/* Quadrant Overview Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {Object.entries(QUADRANT_META).map(([q, meta]) => {
          const Icon = meta.icon
          const count = byQuadrant[q]?.length || 0
          return (
            <div
              key={q}
              onClick={() => setFilterQuadrant(filterQuadrant === q ? '' : q)}
              style={{
                background: filterQuadrant === q ? meta.bg : '#fff',
                borderRadius: 12, border: `2px solid ${filterQuadrant === q ? meta.color : '#e2e8f0'}`,
                padding: '1rem', cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Icon size={20} style={{ color: meta.color }} />
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: meta.color }}>{q}</span>
              </div>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#334155' }}>{meta.label}</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: meta.color, marginTop: 4 }}>
                {count} <span style={{ fontSize: '0.72rem', fontWeight: 500, color: '#94a3b8' }}>metrics</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Owner Filter */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Users size={18} style={{ color: '#2563eb' }} />
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Metric Ownership Map</h3>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            <select
              style={{ ...inputStyle, width: 'auto', padding: '4px 8px', fontSize: '0.78rem' }}
              value={filterOwner}
              onChange={e => setFilterOwner(e.target.value)}
            >
              <option value="">All Owners</option>
              {Object.entries(OWNER_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Metric</th>
                <th style={thStyle}>Quadrant</th>
                <th style={thStyle}>Accountable</th>
                <th style={thStyle}>Responsible</th>
                <th style={thStyle}>Source</th>
                <th style={thStyle}>Frequency</th>
                <th style={thStyle}>KPI Crew</th>
              </tr>
            </thead>
            <tbody>
              {filteredMetrics.map(m => {
                const ownership = ownershipMap?.[m.metric_id] || {}
                return (
                  <tr key={m.metric_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={tdStyle}>
                      <div style={{ fontWeight: 600, fontSize: '0.82rem' }}>{m.name}</div>
                      <div style={{ fontSize: '0.68rem', color: '#94a3b8', marginTop: 2 }}>{m.description?.slice(0, 80)}</div>
                    </td>
                    <td style={tdStyle}><QuadrantBadge quadrant={m.quadrant} /></td>
                    <td style={tdStyle}><OwnerBadge role={ownership.accountable || m.default_owner_role} /></td>
                    <td style={tdStyle}><OwnerBadge role={ownership.responsible || ''} small /></td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: '0.72rem', color: '#64748b' }}>{m.source_type}</span>
                    </td>
                    <td style={tdStyle}>
                      <span style={{ fontSize: '0.72rem', color: '#64748b' }}>{m.measurement_frequency}</span>
                    </td>
                    <td style={tdStyle}>
                      {m.kpi_crew_name ? (
                        <span style={{ fontSize: '0.68rem', padding: '2px 6px', borderRadius: 4, background: '#f0fdf4', color: '#16a34a', fontWeight: 600 }}>
                          {m.kpi_crew_name}
                        </span>
                      ) : (
                        <span style={{ fontSize: '0.68rem', color: '#cbd5e1' }}>—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Cost Stack Tab
// ═══════════════════════════════════════════════════════════════════

function CostStackTab({ costStack, loading }) {
  const [expandedLine, setExpandedLine] = useState(null)

  if (loading) return <div style={{ textAlign: 'center', padding: 40 }}><Loader2 size={24} className="spin" style={{ color: '#2563eb' }} /> Loading cost stack...</div>

  const cs = costStack
  if (!cs || !cs.lines) return <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>No cost stack data. Click "Compute" on the ROI tab.</div>

  const byType = cs.by_cost_type || {}
  const byOwner = cs.by_owner || {}
  const byQuadrant = cs.by_quadrant || {}

  return (
    <div>
      {/* Summary Bar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <StatCard icon={DollarSign} title="Total Annual Impact" value={fmt(cs.total?.amount)} subtitle={`${cs.line_count} line items`} color="#2563eb" />
        <StatCard icon={TrendingUp} title="Total NPV" value={fmt(cs.total?.npv)} subtitle={`${cs.total?.count || 0} items`} color="#059669" />
        <StatCard icon={AlertTriangle} title="Missing Data" value={cs.missing_data_count || 0} subtitle="lines with gaps" color="#d97706" />
        <StatCard icon={Info} title="Assumption-Based" value={cs.assumption_based_count || 0} subtitle="lines using defaults" color="#94a3b8" />
      </div>

      {/* Cost Type Distribution */}
      <div style={cardStyle}>
        <h3 style={{ margin: '0 0 12px', fontSize: '1rem', fontWeight: 700 }}>Cost Distribution by Type</h3>
        <HorizontalBar
          height={36}
          items={Object.entries(COST_TYPE_META).map(([key, meta]) => ({
            label: meta.label,
            value: byType[key]?.amount || 0,
            color: meta.color,
          }))}
        />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginTop: 16 }}>
          {Object.entries(COST_TYPE_META).map(([key, meta]) => (
            <div key={key} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.72rem', color: '#64748b', fontWeight: 600 }}>{meta.label}</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: meta.color }}>{fmt(byType[key]?.amount)}</div>
              <div style={{ fontSize: '0.68rem', color: '#94a3b8' }}>NPV: {fmt(byType[key]?.npv)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Owner Distribution */}
      <div style={cardStyle}>
        <h3 style={{ margin: '0 0 12px', fontSize: '1rem', fontWeight: 700 }}>Cost Distribution by Owner</h3>
        <HorizontalBar
          height={36}
          items={Object.entries(byOwner).map(([key, data]) => ({
            label: OWNER_META[key]?.label || key,
            value: data.amount || 0,
            color: OWNER_META[key]?.color || '#94a3b8',
          }))}
        />
        <div style={{ display: 'flex', gap: 16, marginTop: 12, flexWrap: 'wrap' }}>
          {Object.entries(byOwner).map(([key, data]) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <OwnerBadge role={key} small />
              <span style={{ fontSize: '0.82rem', fontWeight: 700 }}>{fmt(data.amount)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Line Items */}
      <div style={cardStyle}>
        <h3 style={{ margin: '0 0 12px', fontSize: '1rem', fontWeight: 700 }}>Cost Line Items ({cs.lines.length})</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Line Item</th>
                <th style={thStyle}>Type</th>
                <th style={thStyle}>Quadrant</th>
                <th style={thStyle}>Owner</th>
                <th style={thStyle}>Annual</th>
                <th style={thStyle}>NPV</th>
                <th style={thStyle}>Confidence</th>
                <th style={thStyle}>Flags</th>
              </tr>
            </thead>
            <tbody>
              {cs.lines.map((line, idx) => (
                <>
                  <tr
                    key={line.line_id}
                    style={{ borderBottom: '1px solid #f1f5f9', cursor: 'pointer', background: expandedLine === idx ? '#f8fafc' : 'transparent' }}
                    onClick={() => setExpandedLine(expandedLine === idx ? null : idx)}
                  >
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <ChevronRight size={14} style={{ transform: expandedLine === idx ? 'rotate(90deg)' : 'none', transition: '0.15s', color: '#94a3b8' }} />
                        <span style={{ fontWeight: 600, fontSize: '0.82rem' }}>{line.name}</span>
                      </div>
                    </td>
                    <td style={tdStyle}>
                      <span style={{
                        fontSize: '0.7rem', padding: '2px 6px', borderRadius: 4,
                        background: COST_TYPE_META[line.cost_type]?.color + '15',
                        color: COST_TYPE_META[line.cost_type]?.color,
                        fontWeight: 600,
                      }}>
                        {line.cost_type}
                      </span>
                    </td>
                    <td style={tdStyle}><QuadrantBadge quadrant={line.quadrant} small /></td>
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                        {(line.owner_roles || []).map(r => <OwnerBadge key={r} role={r} small />)}
                      </div>
                    </td>
                    <td style={{ ...tdStyle, fontWeight: 700, color: line.is_savings ? '#16a34a' : '#dc2626' }}>
                      {line.is_savings ? '+' : ''}{fmt(line.amount)}
                    </td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{fmt(line.npv)}</td>
                    <td style={tdStyle}><ConfidenceDot value={line.confidence} /></td>
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {line.missing_inputs?.length > 0 && (
                          <span title={`Missing: ${line.missing_inputs.join(', ')}`} style={{ cursor: 'help' }}>
                            <AlertTriangle size={14} style={{ color: '#d97706' }} />
                          </span>
                        )}
                        {line.is_assumption_based && (
                          <span title="Uses default assumptions" style={{ cursor: 'help' }}>
                            <Info size={14} style={{ color: '#94a3b8' }} />
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedLine === idx && (
                    <tr key={`${line.line_id}-detail`}>
                      <td colSpan={8} style={{ padding: '12px 16px', background: '#f8fafc', fontSize: '0.78rem' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                          <div>
                            <strong>Range:</strong> {fmt(line.amount_low)} — {fmt(line.amount_high)}<br />
                            <strong>Formula:</strong> {line.calculation_formula_ref || '—'}<br />
                            <strong>Source Metrics:</strong> {(line.input_metric_ids || []).join(', ') || '—'}
                          </div>
                          <div>
                            <strong>Assumptions:</strong>
                            <ul style={{ margin: '4px 0', paddingLeft: 16 }}>
                              {(line.assumptions || []).map((a, i) => <li key={i}>{a}</li>)}
                            </ul>
                            <strong>Data Sources:</strong> {(line.data_sources || []).join(', ') || '—'}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Consolidated ROI Tab
// ═══════════════════════════════════════════════════════════════════

function ROITab({ roi, loading, onCompute }) {
  if (loading) return <div style={{ textAlign: 'center', padding: 40 }}><Loader2 size={24} className="spin" style={{ color: '#2563eb' }} /> Computing ROI...</div>

  if (!roi || roi.line_count === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <TrendingUp size={48} style={{ color: '#cbd5e1', marginBottom: 16 }} />
        <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#64748b', marginBottom: 8 }}>No ROI data yet</div>
        <p style={{ fontSize: '0.82rem', color: '#94a3b8', maxWidth: 440, margin: '0 auto 16px' }}>
          This builds the cost stack and consolidated ROI from metric inputs using
          deterministic translation rules. No AI agents are involved.
        </p>
        <button onClick={onCompute} style={btnPrimary}>
          <RefreshCw size={16} /> Step 1: Build Cost Stack &amp; ROI
        </button>
      </div>
    )
  }

  return (
    <div>
      {/* Executive Summary Cards */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <StatCard icon={TrendingUp} title="Total ROI" value={pctRaw(roi.roi_pct)} subtitle="Return on investment" color="#059669" />
        <StatCard icon={DollarSign} title="Net Benefit" value={fmt(roi.net_benefit)} subtitle={`Savings: ${fmt(roi.total_savings)}`} color="#2563eb" />
        <StatCard icon={Target} title="NPV" value={fmt(roi.npv)} subtitle={roi.irr ? `IRR: ${(roi.irr * 100).toFixed(1)}%` : ''} color="#7c3aed" />
        <StatCard icon={Clock} title="Payback" value={roi.payback_months ? `${roi.payback_months.toFixed(1)} mo` : '—'} subtitle="Months to recover" color="#d97706" />
      </div>

      {/* Confidence band */}
      <div style={cardStyle}>
        <h3 style={{ margin: '0 0 8px', fontSize: '1rem', fontWeight: 700 }}>Savings Range</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: '0.82rem', color: '#64748b' }}>Low: <strong>{fmt(roi.savings_low)}</strong></span>
          <div style={{ flex: 1, height: 12, background: '#e2e8f0', borderRadius: 6, position: 'relative' }}>
            <div style={{
              position: 'absolute', left: '25%', right: '25%', top: 0, bottom: 0,
              background: 'linear-gradient(90deg, #bfdbfe, #2563eb)', borderRadius: 6,
            }} />
          </div>
          <span style={{ fontSize: '0.82rem', color: '#64748b' }}>High: <strong>{fmt(roi.savings_high)}</strong></span>
        </div>
        <div style={{ textAlign: 'center', fontSize: '0.75rem', color: '#94a3b8', marginTop: 4 }}>
          Confidence-weighted: {(roi.confidence_weighted_avg * 100).toFixed(0)}%
        </div>
      </div>

      {/* ROI by Owner */}
      <div style={cardStyle}>
        <h3 style={{ margin: '0 0 12px', fontSize: '1rem', fontWeight: 700 }}>ROI by Owner</h3>
        {(roi.roi_by_owner || []).map(b => (
          <div key={b.dimension_value} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #f1f5f9' }}>
            <div style={{ width: 160 }}><OwnerBadge role={b.dimension_value} /></div>
            <div style={{ flex: 1 }}>
              <div style={{ height: 10, background: '#e2e8f0', borderRadius: 5, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 5,
                  width: `${Math.min(100, Math.max(2, (b.npv / (roi.npv || 1)) * 100))}%`,
                  background: OWNER_META[b.dimension_value]?.color || '#94a3b8',
                  transition: 'width 0.3s',
                }} />
              </div>
            </div>
            <div style={{ width: 100, textAlign: 'right', fontWeight: 700, fontSize: '0.85rem' }}>{fmt(b.npv)}</div>
            <div style={{ width: 60, textAlign: 'right', fontSize: '0.78rem', color: '#64748b' }}>{b.line_count} lines</div>
          </div>
        ))}
      </div>

      {/* ROI by Quadrant */}
      <div style={cardStyle}>
        <h3 style={{ margin: '0 0 12px', fontSize: '1rem', fontWeight: 700 }}>ROI by Quadrant</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {(roi.roi_by_quadrant || []).map(b => {
            const meta = QUADRANT_META[b.dimension_value] || {}
            return (
              <div key={b.dimension_value} style={{
                background: meta.bg || '#f8fafc', borderRadius: 10, padding: '1rem',
                border: `1px solid ${(meta.color || '#e2e8f0')}30`,
              }}>
                <div style={{ fontSize: '0.78rem', fontWeight: 700, color: meta.color }}>{b.dimension_value}</div>
                <div style={{ fontSize: '0.68rem', color: '#64748b', marginBottom: 8 }}>{meta.label}</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: meta.color }}>{fmt(b.npv)}</div>
                <div style={{ fontSize: '0.68rem', color: '#94a3b8' }}>
                  {b.line_count} lines | {pctRaw(b.roi_pct)} ROI
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Year-by-Year Cash Flow */}
      {roi.year_by_year_cashflow?.length > 0 && (
        <div style={cardStyle}>
          <h3 style={{ margin: '0 0 12px', fontSize: '1rem', fontWeight: 700 }}>Year-by-Year Cash Flow</h3>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Year</th>
                {Object.keys(COST_TYPE_META).map(ct => (
                  <th key={ct} style={{ ...thStyle, color: COST_TYPE_META[ct].color }}>{COST_TYPE_META[ct].label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {roi.year_by_year_cashflow.map(yc => (
                <tr key={yc.year} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ ...tdStyle, fontWeight: 700 }}>Year {yc.year}</td>
                  {Object.keys(COST_TYPE_META).map(ct => (
                    <td key={ct} style={tdStyle}>{fmt(yc[`${ct}_cost`] || 0)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Recompute */}
      <div style={{ textAlign: 'center', marginTop: 20 }}>
        <button onClick={onCompute} style={btnSecondary} title="Rebuild cost stack and ROI from current metric inputs and parameter overrides">
          <RefreshCw size={14} /> Rebuild Cost Stack &amp; ROI
        </button>
        <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: 6 }}>
          Deterministic calculation only — no AI agents. To run the full multi-agent analysis, go to the AI Advisory tab.
        </div>
      </div>
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Scenarios Tab
// ═══════════════════════════════════════════════════════════════════

function ScenariosTab({ scenarios, onCreateScenario, onRunScenario }) {
  return (
    <div>
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <GitBranch size={18} style={{ color: '#7c3aed' }} />
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Scenario Comparison</h3>
          <button onClick={onCreateScenario} style={{ ...btnPrimary, marginLeft: 'auto', padding: '6px 12px', fontSize: '0.78rem' }}>
            + New Scenario
          </button>
        </div>

        {(!scenarios || scenarios.length === 0) ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
            No scenarios created yet. Click "New Scenario" to get started.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
            {scenarios.map(s => (
              <div key={s.scenario_id} style={{
                background: '#f8fafc', borderRadius: 10, padding: '1rem',
                border: '1px solid #e2e8f0',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: '0.92rem' }}>{s.name}</span>
                  <span style={{
                    fontSize: '0.65rem', padding: '2px 8px', borderRadius: 10,
                    background: s.status === 'approved' ? '#dcfce7' : s.status === 'review' ? '#fef9c3' : '#f1f5f9',
                    color: s.status === 'approved' ? '#16a34a' : s.status === 'review' ? '#ca8a04' : '#64748b',
                    fontWeight: 600,
                  }}>
                    {s.status}
                  </span>
                </div>
                <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: 12 }}>
                  {s.description || 'No description'}
                </div>
                {Object.keys(s.parameter_overrides || {}).length > 0 && (
                  <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginBottom: 8 }}>
                    {Object.keys(s.parameter_overrides).length} parameter overrides
                  </div>
                )}
                <button
                  onClick={() => onRunScenario(s.scenario_id)}
                  style={{ ...btnSecondary, width: '100%', justifyContent: 'center' }}
                >
                  <Zap size={14} /> Run Scenario
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// AI Advisory Tab (Multi-Agent Crew)
// ═══════════════════════════════════════════════════════════════════

function AIAdvisoryTab({ crewResult, loading, onRun }) {
  const [expandedSection, setExpandedSection] = useState(null)
  const [advisoryScope, setAdvisoryScope] = useState('enterprise')
  const toggle = (s) => setExpandedSection(prev => prev === s ? null : s)

  // Scope selector — enterprise vs single asset/location
  const scopeSelector = (
    <div style={{
      display: 'flex', gap: 4, marginBottom: 16, background: '#f1f5f9',
      borderRadius: 10, padding: 4, width: 'fit-content',
    }}>
      {[
        { id: 'enterprise', label: 'Enterprise-Wide', icon: Layers },
        { id: 'asset', label: 'Single Asset / Location', icon: Cpu },
      ].map(opt => {
        const Icon = opt.icon
        const isActive = advisoryScope === opt.id
        return (
          <button
            key={opt.id}
            onClick={() => setAdvisoryScope(opt.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '7px 14px', borderRadius: 8, border: 'none',
              background: isActive ? '#fff' : 'transparent',
              color: isActive ? '#0f172a' : '#64748b',
              fontWeight: isActive ? 700 : 500,
              fontSize: '0.82rem', cursor: 'pointer',
              boxShadow: isActive ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
              transition: 'all 0.15s',
            }}
          >
            <Icon size={15} />
            {opt.label}
          </button>
        )
      })}
    </div>
  )

  // When scoped to single asset, render AgentReasoningConsole
  if (advisoryScope === 'asset') {
    return (
      <div>
        {scopeSelector}
        <div style={{
          background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
          padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
          marginBottom: '1rem', lineHeight: 1.6,
        }}>
          Drill into a <strong>single asset or location</strong> to run the 12-agent AI crew
          scoped to that specific target. See each agent's reasoning trace step-by-step,
          cross-silo contributions, and prioritized recommendations.
        </div>
        <AgentReasoningConsole embedded />
      </div>
    )
  }

  const AGENT_GROUP_META = {
    stakeholder: { label: 'Stakeholder Agents', color: '#2563eb', icon: Users },
    dimension: { label: 'Dimension Agents', color: '#7c3aed', icon: BarChart3 },
    governance: { label: 'Governance Agents', color: '#059669', icon: Shield },
  }

  if (!crewResult) {
    return (
      <div>
        {scopeSelector}
        <div style={cardStyle}>
        <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
          <div style={{
            width: 64, height: 64, borderRadius: '50%', background: '#eff6ff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
          }}>
            <Zap size={28} style={{ color: '#2563eb' }} />
          </div>
          <h3 style={{ margin: '0 0 8px', fontSize: '1.1rem', fontWeight: 700, color: '#0f172a' }}>
            Step 2: Multi-Agent Decision Advisory
          </h3>
          <p style={{ margin: '0 0 16px', fontSize: '0.85rem', color: '#64748b', maxWidth: 520, marginInline: 'auto' }}>
            Runs <strong>12 specialized AI agents</strong> across 5 stages: stakeholder validation,
            cost translation, reconciliation, <strong>Pareto optimization</strong>, and audit narrative.
            Produces competing investment options, negotiation outcomes, and a board-ready narrative.
          </p>
          <button onClick={onRun} disabled={loading} style={{
            ...btnPrimary, padding: '10px 28px', fontSize: '0.9rem',
            opacity: loading ? 0.6 : 1,
          }}>
            {loading ? <><Loader2 size={16} className="animate-spin" /> Running Agent Crew...</>
              : <><Zap size={16} /> Step 2: Run AI Agent Analysis</>}
          </button>
        </div>
        </div>
      </div>
    )
  }

  const cr = crewResult
  const neg = cr.negotiation_log || {}
  const pareto = cr.pareto_options || []
  const positions = cr.stakeholder_positions || []
  const assumptions = cr.assumption_register || []
  const recommended = pareto.find(o => o.option_id === cr.recommended_option_id)

  return (
    <div>
      {scopeSelector}
      {/* Summary Stats */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <StatCard icon={Users} title="Agents" value={cr.agent_count || 12} subtitle={`${cr.task_count || 13} tasks`} color="#2563eb" />
        <StatCard icon={TrendingUp} title="Recommended NPV" value={fmt(recommended?.npv || 0)} subtitle={recommended?.label || ''} color="#059669" />
        <StatCard icon={Target} title="Pareto Options" value={pareto.length} subtitle="Non-dominated solutions" color="#7c3aed" />
        <StatCard icon={Scale} title="Conflicts Resolved" value={neg.conflicts_resolved || 0} subtitle={`${neg.rounds || 0} negotiation rounds`} color="#d97706" />
        <StatCard icon={Clock} title="Execution" value={`${cr.execution_time_ms || 0}ms`} subtitle={cr.crewai_used ? 'CrewAI' : 'Deterministic'} color="#64748b" />
      </div>

      {/* NPV Methodology Explainer */}
      <div style={{
        background: '#f0fdf4', borderRadius: 10, border: '1px solid #bbf7d0',
        padding: '0.85rem 1rem', marginBottom: 16, fontSize: '0.78rem',
        color: '#475569', lineHeight: 1.6,
      }}>
        <div style={{ fontWeight: 700, color: '#166534', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
          <TrendingUp size={14} style={{ color: '#059669' }} />
          How this NPV is calculated
        </div>
        <div>
          The <strong>Recommended NPV</strong> is computed by the multi-objective Pareto optimizer
          across <strong>ownership-mapped cost lines</strong>. Each cost line's NPV is discounted
          at <strong>8% over 5 years</strong>, then the <strong>$250K implementation cost</strong> is
          deducted:{' '}
          <span style={{ fontFamily: 'monospace', background: '#dcfce7', padding: '1px 5px', borderRadius: 4 }}>
          NPV = Σ(line.amount × annuity factor) − Implementation Cost</span>.
          The recommended option is the one with the highest NPV among all non-dominated Pareto solutions.
        </div>
        <div style={{ marginTop: 6 }}>
          <strong>Data source:</strong> Metric catalog inputs → translation rules → cost line items
          per owner/quadrant. Only lines selected by the optimizer (within budget constraints) are included.
        </div>
        <div style={{ marginTop: 6, color: '#64748b', fontStyle: 'italic' }}>
          The KPI Overview page uses the same 8% discount rate, 5-year horizon, and $250K implementation cost
          but computes NPV from <strong>fleet-wide KPI crew savings totals</strong> (14 dimensions).
          Both views share aligned financial parameters; differences reflect the scope of inputs each pipeline analyzes.
        </div>
      </div>

      {/* Re-run button */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Re-run the full 12-agent pipeline with current inputs</span>
        <button onClick={onRun} disabled={loading} style={{ ...btnSecondary, gap: 6 }}>
          {loading ? <Loader2 size={14} /> : <RefreshCw size={14} />} Re-run AI Agent Analysis
        </button>
      </div>

      {/* Pareto Options */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, cursor: 'pointer' }}
          onClick={() => toggle('pareto')}>
          <Target size={18} style={{ color: '#7c3aed' }} />
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Pareto-Optimal Options</h3>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8', marginLeft: 'auto' }}>
            {pareto.length} options
          </span>
          {expandedSection === 'pareto' ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(pareto.length, 4)}, 1fr)`, gap: 12 }}>
          {pareto.map(opt => {
            const isRec = opt.option_id === cr.recommended_option_id
            return (
              <div key={opt.option_id} style={{
                padding: '1rem', borderRadius: 10,
                border: isRec ? '2px solid #2563eb' : '1px solid #e2e8f0',
                background: isRec ? '#eff6ff' : '#fff',
                position: 'relative',
              }}>
                {isRec && (
                  <span style={{
                    position: 'absolute', top: -10, right: 12, background: '#2563eb',
                    color: '#fff', fontSize: '0.65rem', fontWeight: 700, padding: '2px 8px',
                    borderRadius: 6,
                  }}>RECOMMENDED</span>
                )}
                <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>
                  {opt.label}
                </div>
                <div style={{ display: 'grid', gap: 6, fontSize: '0.78rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>NPV</span>
                    <span style={{ fontWeight: 700, color: '#059669' }}>{fmt(opt.npv)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>ROI</span>
                    <span style={{ fontWeight: 600 }}>{pctRaw(opt.roi_pct)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>Risk</span>
                    <ConfidenceDot value={1 - opt.risk_score} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>Lines</span>
                    <span>{opt.selected_line_count}</span>
                  </div>
                  {opt.compliance_gap > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#dc2626', fontSize: '0.72rem' }}>
                      <AlertTriangle size={12} /> Gap: {fmt(opt.compliance_gap)}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Board Narrative */}
      {cr.board_narrative && (
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <FileText size={18} style={{ color: '#0891b2' }} />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Board Narrative</h3>
          </div>
          <pre style={{
            background: '#f8fafc', padding: '1rem', borderRadius: 8,
            fontSize: '0.82rem', lineHeight: 1.6, color: '#334155',
            whiteSpace: 'pre-wrap', fontFamily: 'inherit', margin: 0,
            border: '1px solid #e2e8f0',
          }}>
            {cr.board_narrative}
          </pre>
        </div>
      )}

      {/* Stakeholder Positions */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, cursor: 'pointer' }}
          onClick={() => toggle('positions')}>
          <Users size={18} style={{ color: '#2563eb' }} />
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Stakeholder Positions</h3>
          <span style={{ fontSize: '0.72rem', color: '#94a3b8', marginLeft: 'auto' }}>
            {positions.length} agents
          </span>
          {expandedSection === 'positions' ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
        {(expandedSection === 'positions' || !expandedSection) && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
            {positions.map(pos => (
              <div key={pos.agent_id} style={{
                padding: '0.85rem', borderRadius: 8, border: '1px solid #e2e8f0',
                background: '#f8fafc',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: '0.82rem', color: '#0f172a' }}>
                    {pos.agent_role || pos.agent_id}
                  </span>
                  <QuadrantBadge quadrant={pos.quadrant_authority} small />
                </div>
                {pos.non_negotiables?.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#dc2626' }}>NON-NEGOTIABLE</span>
                    {pos.non_negotiables.map((c, i) => (
                      <div key={i} style={{ fontSize: '0.72rem', color: '#475569', marginTop: 2 }}>
                        • {c.description}
                      </div>
                    ))}
                  </div>
                )}
                {pos.preferences?.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#d97706' }}>PREFERENCES</span>
                    {pos.preferences.map((c, i) => (
                      <div key={i} style={{ fontSize: '0.72rem', color: '#475569', marginTop: 2 }}>
                        • {c.description} <span style={{ color: '#94a3b8' }}>(w={c.weight})</span>
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6 }}>
                  {pos.sign_off
                    ? <><CheckCircle size={12} style={{ color: '#16a34a' }} /><span style={{ fontSize: '0.7rem', color: '#16a34a' }}>Signed off</span></>
                    : <><AlertTriangle size={12} style={{ color: '#dc2626' }} /><span style={{ fontSize: '0.7rem', color: '#dc2626' }}>Objections</span></>
                  }
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Negotiation Log */}
      {neg.conflicts_detected?.length > 0 && (
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, cursor: 'pointer' }}
            onClick={() => toggle('negotiation')}>
            <Scale size={18} style={{ color: '#d97706' }} />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Negotiation Log</h3>
            <span style={{ fontSize: '0.72rem', color: '#94a3b8', marginLeft: 'auto' }}>
              {neg.conflicts_detected.length} conflicts, {neg.conflicts_resolved} resolved
            </span>
            {expandedSection === 'negotiation' ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          {expandedSection === 'negotiation' && (
            <table style={tableStyle}>
              <thead><tr>
                <th style={thStyle}>Agents</th>
                <th style={thStyle}>Type</th>
                <th style={thStyle}>Description</th>
                <th style={thStyle}>Resolution</th>
              </tr></thead>
              <tbody>
                {neg.conflicts_detected.map((c, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={tdStyle}>{(c.agents_involved || []).join(', ')}</td>
                    <td style={tdStyle}>
                      <span style={{
                        padding: '2px 6px', borderRadius: 4, fontSize: '0.7rem', fontWeight: 600,
                        background: c.conflict_type === 'priority' ? '#fef3c7' : '#e0e7ff',
                        color: c.conflict_type === 'priority' ? '#92400e' : '#3730a3',
                      }}>{c.conflict_type}</span>
                    </td>
                    <td style={{ ...tdStyle, fontSize: '0.78rem', maxWidth: 300 }}>{c.description}</td>
                    <td style={{ ...tdStyle, fontSize: '0.78rem', color: c.resolution ? '#16a34a' : '#dc2626' }}>
                      {c.resolution || 'Unresolved'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Agent Communication */}
      {(cr.agent_messages || []).length > 0 && (
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, cursor: 'pointer' }}
            onClick={() => toggle('comms')}>
            <MessageSquare size={18} style={{ color: '#6366f1' }} />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Agent Communication</h3>
            <span style={{ fontSize: '0.72rem', color: '#94a3b8', marginLeft: 'auto' }}>
              {cr.agent_messages.length} messages
            </span>
            {expandedSection === 'comms' ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          {expandedSection === 'comms' && (
            <AgentCommsPanel
              messages={cr.agent_messages}
              theme="light"
              showPipelineFlow
            />
          )}
        </div>
      )}

      {/* Assumptions */}
      {assumptions.length > 0 && (
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, cursor: 'pointer' }}
            onClick={() => toggle('assumptions')}>
            <Info size={18} style={{ color: '#64748b' }} />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Assumption Register</h3>
            <span style={{ fontSize: '0.72rem', color: '#94a3b8', marginLeft: 'auto' }}>
              {assumptions.length} assumptions
            </span>
            {expandedSection === 'assumptions' ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          {expandedSection === 'assumptions' && (
            <table style={tableStyle}>
              <thead><tr>
                <th style={thStyle}>Description</th>
                <th style={thStyle}>Source</th>
                <th style={thStyle}>Owner</th>
                <th style={thStyle}>Status</th>
              </tr></thead>
              <tbody>
                {assumptions.slice(0, 30).map((a, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ ...tdStyle, fontSize: '0.78rem', maxWidth: 400 }}>{a.description}</td>
                    <td style={tdStyle}><span style={{ fontSize: '0.72rem', color: '#64748b' }}>{a.source}</span></td>
                    <td style={tdStyle}><span style={{ fontSize: '0.72rem' }}>{a.owner_agent}</span></td>
                    <td style={tdStyle}>
                      <span style={{
                        padding: '2px 6px', borderRadius: 4, fontSize: '0.68rem', fontWeight: 600,
                        background: a.status === 'accepted' ? '#dcfce7' : '#f1f5f9',
                        color: a.status === 'accepted' ? '#166534' : '#475569',
                      }}>{a.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Lineage */}
      {cr.lineage_summary && (
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <GitBranch size={18} style={{ color: '#059669' }} />
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Lineage Summary</h3>
          </div>
          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', fontSize: '0.82rem' }}>
            <div><span style={{ color: '#64748b' }}>Metrics used:</span> <strong>{cr.lineage_summary.metrics_used?.length || 0}</strong></div>
            <div><span style={{ color: '#64748b' }}>Rules applied:</span> <strong>{cr.lineage_summary.translation_rules_applied?.length || 0}</strong></div>
            <div><span style={{ color: '#64748b' }}>Cost lines:</span> <strong>{cr.lineage_summary.cost_lines_produced || 0}</strong></div>
            <div><span style={{ color: '#64748b' }}>Adjustments:</span> <strong>{cr.lineage_summary.adjustments_applied || 0}</strong></div>
            <div><span style={{ color: '#64748b' }}>Dependency edges:</span> <strong>{cr.lineage_summary.dependency_edges || 0}</strong></div>
          </div>
        </div>
      )}
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════

export default function OwnershipDecisionSupport() {
  const [activeTab, setActiveTab] = useState('budget')
  const [metrics, setMetrics] = useState(null)
  const [ownershipMap, setOwnershipMap] = useState(null)
  const [params, setParams] = useState(null)
  const [sliders, setSliders] = useState(null)
  const [resolvedParams, setResolvedParams] = useState(null)
  const [costStack, setCostStack] = useState(null)
  const [roi, setRoi] = useState(null)
  const [scenarios, setScenarios] = useState(null)
  const [loading, setLoading] = useState(false)
  const [initialLoaded, setInitialLoaded] = useState(false)
  const [crewResult, setCrewResult] = useState(null)
  const [crewLoading, setCrewLoading] = useState(false)

  // ── Initial data load ────────────────────────────────────────
  useEffect(() => {
    if (initialLoaded) return
    async function load() {
      try {
        const [mRes, oRes, pRes, sRes, scRes] = await Promise.all([
          fetch(`${API}/metrics`),
          fetch(`${API}/owners`),
          fetch(`${API}/parameters`),
          fetch(`${API}/parameters/sliders`),
          fetch(`${API}/scenarios`),
        ])
        if (mRes.ok) {
          const d = await mRes.json()
          setMetrics(d.metrics || [])
        }
        if (oRes.ok) {
          const d = await oRes.json()
          setOwnershipMap(d.ownership_map || {})
        }
        if (pRes.ok) {
          const d = await pRes.json()
          setParams(d.parameters || [])
        }
        if (sRes.ok) {
          const d = await sRes.json()
          setSliders(d.sliders || [])
        }
        if (scRes.ok) {
          const d = await scRes.json()
          setScenarios(d.scenarios || [])
        }
        // Resolve params at global scope
        const rRes = await fetch(`${API}/parameters/resolve`)
        if (rRes.ok) setResolvedParams(await rRes.json())
      } catch (e) {
        console.warn('Failed to load ownership data:', e)
      }
      setInitialLoaded(true)
    }
    load()
  }, [initialLoaded])

  // ── Parameter override handler ───────────────────────────────
  const handleParamOverride = useCallback(async (paramId, value) => {
    try {
      await fetch(`${API}/parameters/${paramId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level: 'global', entity: '', value, reason: 'UI slider', created_by: 'user' }),
      })
      // Re-resolve
      const rRes = await fetch(`${API}/parameters/resolve`)
      if (rRes.ok) setResolvedParams(await rRes.json())
    } catch (e) {
      console.warn('Failed to set override:', e)
    }
  }, [])

  // ── Compute cost stack + ROI ─────────────────────────────────
  const handleCompute = useCallback(async () => {
    setLoading(true)
    try {
      const [csRes, roiRes] = await Promise.all([
        fetch(`${API}/cost-stack`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ metric_inputs: SAMPLE_METRIC_INPUTS }),
        }),
        fetch(`${API}/roi`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ metric_inputs: SAMPLE_METRIC_INPUTS }),
        }),
      ])
      if (csRes.ok) setCostStack(await csRes.json())
      if (roiRes.ok) setRoi(await roiRes.json())

      // Auto-navigate to cost stack after compute
      if (activeTab === 'roi' && !costStack) setActiveTab('coststack')
    } catch (e) {
      console.warn('Compute failed:', e)
    }
    setLoading(false)
  }, [activeTab, costStack])

  // ── AI Advisory (Crew) handler ─────────────────────────────
  const handleRunCrew = useCallback(async () => {
    setCrewLoading(true)
    try {
      const res = await fetch(`${API}/crew/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ metric_inputs: SAMPLE_METRIC_INPUTS, constraints: {} }),
      })
      if (res.ok) setCrewResult(await res.json())
    } catch (e) {
      console.warn('Crew run failed:', e)
    }
    setCrewLoading(false)
  }, [])

  // ── Scenario handlers ────────────────────────────────────────
  const handleCreateScenario = useCallback(async () => {
    const name = prompt('Scenario name:')
    if (!name) return
    try {
      const res = await fetch(`${API}/scenarios`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description: '', created_by: 'user' }),
      })
      if (res.ok) {
        const scRes = await fetch(`${API}/scenarios`)
        if (scRes.ok) {
          const d = await scRes.json()
          setScenarios(d.scenarios || [])
        }
      }
    } catch (e) {
      console.warn('Create scenario failed:', e)
    }
  }, [])

  const handleRunScenario = useCallback(async (scenarioId) => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/scenarios/${scenarioId}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_metric_inputs: SAMPLE_METRIC_INPUTS }),
      })
      if (res.ok) {
        const data = await res.json()
        setCostStack(data.cost_stack)
        setRoi(data.roi)
        setActiveTab('roi')
      }
    } catch (e) {
      console.warn('Run scenario failed:', e)
    }
    setLoading(false)
  }, [])

  // Derive which phase the current tab belongs to
  const activePhase = useMemo(() => {
    for (const phase of PHASES) {
      if (phase.views.some(v => v.id === activeTab)) return phase.id
    }
    return 'configure'
  }, [activeTab])

  // Phase completion indicators
  const phaseStatus = useMemo(() => ({
    configure: initialLoaded ? 'done' : 'pending',
    analyze: roi ? 'done' : costStack ? 'partial' : 'pending',
    optimize: crewResult ? 'done' : 'pending',
  }), [initialLoaded, costStack, roi, crewResult])

  const STATUS_ICON = { done: CheckCircle, partial: AlertTriangle, pending: null }
  const STATUS_COLOR = { done: '#16a34a', partial: '#d97706', pending: '#cbd5e1' }

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1400, margin: '0 auto' }}>
      {/* ── Header ───────────────────────────────────── */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: '0 0 4px', fontSize: '1.5rem', fontWeight: 800, color: '#0f172a' }}>
          Ecosystem Optimizer
        </h1>
        <p style={{ margin: 0, fontSize: '0.82rem', color: '#64748b', maxWidth: 720 }}>
          Configure inputs, analyze cost &amp; ROI across every owner and quadrant,
          then let the 12-agent AI crew find Pareto-optimal investment strategies.
        </p>
      </div>

      {/* ── Workflow Stepper ─────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'stretch', gap: 0, marginBottom: 24,
        background: '#f8fafc', borderRadius: 14, border: '1px solid #e2e8f0',
        overflow: 'hidden',
      }}>
        {PHASES.map((phase, idx) => {
          const PhaseIcon = phase.icon
          const isActive = activePhase === phase.id
          const status = phaseStatus[phase.id]
          const SIcon = STATUS_ICON[status]
          return (
            <div
              key={phase.id}
              onClick={() => setActiveTab(phase.views[0].id)}
              style={{
                flex: 1, display: 'flex', alignItems: 'center', gap: 12,
                padding: '14px 20px', cursor: 'pointer', position: 'relative',
                background: isActive ? '#fff' : 'transparent',
                borderBottom: isActive ? '3px solid #2563eb' : '3px solid transparent',
                transition: 'all 0.2s',
              }}
            >
              {/* Step number circle */}
              <div style={{
                width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: isActive ? '#2563eb' : status === 'done' ? '#dcfce7' : '#f1f5f9',
                color: isActive ? '#fff' : status === 'done' ? '#16a34a' : '#94a3b8',
                fontWeight: 800, fontSize: '0.85rem',
                border: isActive ? 'none' : `2px solid ${STATUS_COLOR[status]}`,
                transition: 'all 0.2s',
              }}>
                {status === 'done' && !isActive
                  ? <CheckCircle size={18} />
                  : <PhaseIcon size={18} />
                }
              </div>

              <div style={{ minWidth: 0 }}>
                <div style={{
                  fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  color: isActive ? '#2563eb' : '#94a3b8',
                }}>
                  Step {idx + 1}
                </div>
                <div style={{
                  fontSize: '0.92rem', fontWeight: isActive ? 700 : 600,
                  color: isActive ? '#0f172a' : '#475569',
                }}>
                  {phase.label}
                </div>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: 1 }}>
                  {phase.description}
                </div>
              </div>

              {/* Connector arrow between phases */}
              {idx < PHASES.length - 1 && (
                <div style={{
                  position: 'absolute', right: -8, top: '50%', transform: 'translateY(-50%)',
                  zIndex: 2, width: 16, height: 16, borderRadius: '50%',
                  background: '#f1f5f9', border: '2px solid #e2e8f0',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <ArrowRight size={10} style={{ color: '#94a3b8' }} />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Sub-view pills for active phase ──────────── */}
      {(() => {
        const phase = PHASES.find(p => p.id === activePhase)
        if (!phase || phase.views.length <= 1) return null
        return (
          <div style={{
            display: 'flex', gap: 4, marginBottom: 16,
            background: '#f1f5f9', borderRadius: 10, padding: 3, width: 'fit-content',
          }}>
            {phase.views.map(v => {
              const VIcon = v.icon
              const isActive = activeTab === v.id
              return (
                <button
                  key={v.id}
                  onClick={() => setActiveTab(v.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '7px 14px', borderRadius: 8, border: 'none',
                    background: isActive ? '#fff' : 'transparent',
                    color: isActive ? '#0f172a' : '#64748b',
                    fontWeight: isActive ? 700 : 500,
                    fontSize: '0.82rem', cursor: 'pointer',
                    boxShadow: isActive ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                    transition: 'all 0.15s', whiteSpace: 'nowrap',
                  }}
                >
                  <VIcon size={15} />
                  {v.label}
                </button>
              )
            })}
          </div>
        )
      })()}

      {/* ── Phase transition CTAs ────────────────────── */}
      {activePhase === 'configure' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16,
          padding: '12px 16px', background: '#eff6ff', borderRadius: 10,
          border: '1px solid #bfdbfe',
        }}>
          <div style={{ flex: 1, fontSize: '0.82rem', color: '#1e40af' }}>
            <strong>Next:</strong> When your inputs are ready, build the cost stack and ROI model.
          </div>
          <button onClick={() => { handleCompute(); setActiveTab('coststack') }} style={{
            ...btnPrimary, padding: '8px 18px', fontSize: '0.82rem',
            display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0,
          }}>
            <BarChart3 size={15} /> Build Cost Stack &amp; ROI
            <ArrowRight size={14} />
          </button>
        </div>
      )}

      {activePhase === 'analyze' && !crewResult && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16,
          padding: '12px 16px', background: '#f5f3ff', borderRadius: 10,
          border: '1px solid #ddd6fe',
        }}>
          <div style={{ flex: 1, fontSize: '0.82rem', color: '#5b21b6' }}>
            <strong>Next:</strong> Run the 12-agent AI crew for Pareto-optimal investment recommendations.
          </div>
          <button onClick={() => { handleRunCrew(); setActiveTab('advisory') }} disabled={crewLoading} style={{
            ...btnPrimary, padding: '8px 18px', fontSize: '0.82rem',
            background: '#7c3aed', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0,
            opacity: crewLoading ? 0.6 : 1,
          }}>
            <Zap size={15} /> Run AI Optimization
            <ArrowRight size={14} />
          </button>
        </div>
      )}

      {/* ── Tab Content ──────────────────────────────── */}
      {activeTab === 'budget' && (
        <BudgetPage embedded />
      )}
      {activeTab === 'parameters' && (
        <ParametersTab
          params={params}
          sliders={sliders}
          resolvedParams={resolvedParams}
          onOverride={handleParamOverride}
        />
      )}
      {activeTab === 'ownership' && (
        <OwnershipTab
          metrics={metrics}
          ownershipMap={ownershipMap}
        />
      )}
      {activeTab === 'coststack' && (
        <CostStackTab
          costStack={costStack}
          loading={loading}
        />
      )}
      {activeTab === 'roi' && (
        <ROITab
          roi={roi}
          loading={loading}
          onCompute={handleCompute}
        />
      )}
      {activeTab === 'scenarios' && (
        <ScenariosTab
          scenarios={scenarios}
          onCreateScenario={handleCreateScenario}
          onRunScenario={handleRunScenario}
        />
      )}
      {activeTab === 'advisory' && (
        <AIAdvisoryTab
          crewResult={crewResult}
          loading={crewLoading}
          onRun={handleRunCrew}
        />
      )}
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Shared Styles
// ═══════════════════════════════════════════════════════════════════

const cardStyle = {
  background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0',
  padding: '1.25rem', marginBottom: '1rem',
}
const inputStyle = {
  width: '100%', padding: '0.5rem 0.75rem', borderRadius: 8,
  border: '1px solid #e2e8f0', fontSize: '0.85rem', outline: 'none',
}
const labelStyle = {
  display: 'block', fontSize: '0.75rem', fontWeight: 600,
  color: '#64748b', marginBottom: 4,
}
const btnPrimary = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '0.5rem 1.25rem', borderRadius: 8, border: 'none',
  background: '#1d4ed8', color: '#fff', cursor: 'pointer',
  fontWeight: 600, fontSize: '0.85rem',
}
const btnSecondary = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '0.4rem 0.75rem', borderRadius: 6,
  border: '1px solid #e2e8f0', background: '#fff',
  color: '#64748b', cursor: 'pointer', fontSize: '0.8rem',
}
const tableStyle = {
  width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem',
}
const thStyle = {
  textAlign: 'left', padding: '8px 12px', fontSize: '0.72rem',
  fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
  borderBottom: '2px solid #e2e8f0', whiteSpace: 'nowrap',
}
const tdStyle = {
  padding: '8px 12px', verticalAlign: 'middle',
}
