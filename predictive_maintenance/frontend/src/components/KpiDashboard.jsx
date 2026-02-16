import { useState, useEffect } from 'react'
import {
  BarChart3, TrendingUp, TrendingDown, Shield, AlertTriangle,
  CheckCircle2, XCircle, ChevronDown, ChevronUp, MapPin,
  Lightbulb, DollarSign, Percent, Activity, Layers, Target,
  Wrench, Clock, Zap, RefreshCw, Download, Loader2, Info, BookOpen, X,
  FlaskConical, ListChecks, Database, Briefcase, FileDown, ChevronRight as ChevronRightIcon
} from 'lucide-react'
import KpiApi from '../services/kpiApi'
import BusinessCasePage from './BusinessCasePage'


// ── Currency formatter ───────────────────────────────────────────────
const fmt = (v) => `$${Math.round(v).toLocaleString()}`
const pct = (v) => `${(v * 100).toFixed(0)}%`

// ── Confidence badge ─────────────────────────────────────────────────
function ConfidenceBadge({ value }) {
  const color = value >= 0.7 ? '#22c55e' : value >= 0.5 ? '#eab308' : '#ef4444'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.8rem', color }}>
      <Activity size={12} /> {pct(value)}
    </span>
  )
}

// ── Status badge ─────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const cfg = {
    approved:  { bg: '#dcfce7', color: '#166534', icon: CheckCircle2 },
    rejected:  { bg: '#fee2e2', color: '#991b1b', icon: XCircle },
    pending:   { bg: '#fef3c7', color: '#92400e', icon: Clock },
  }[status] || { bg: '#f1f5f9', color: '#64748b', icon: Clock }
  const Icon = cfg.icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 600,
      background: cfg.bg, color: cfg.color,
    }}>
      <Icon size={12} />
      {status.toUpperCase()}
    </span>
  )
}

// ── KPI Scorecard ────────────────────────────────────────────────────
function KpiScorecard({ kpi, onSelect, selected }) {
  const borderColor = kpi.status === 'approved' ? '#22c55e' : kpi.status === 'rejected' ? '#ef4444' : '#eab308'
  return (
    <div
      onClick={() => onSelect(kpi.kpi_name)}
      style={{
        background: selected ? '#eff6ff' : '#fff',
        border: selected ? '2px solid #3b82f6' : '1px solid #e2e8f0',
        borderLeft: `4px solid ${borderColor}`,
        borderRadius: 10,
        padding: '1rem 1.25rem',
        cursor: 'pointer',
        transition: 'all 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <h4 style={{ margin: 0, fontSize: '0.9rem', color: '#1e293b' }}>{kpi.display_name}</h4>
          <ResearchInfoIcon research={kpi.research_basis} assumptions={kpi.assumptions} supportingMetrics={kpi.supporting_metrics} confidence={kpi.confidence} dataGrounded={kpi.data_grounded} />
        </div>
        <StatusBadge status={kpi.status} />
      </div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#1d4ed8', marginBottom: 4 }}>
        {fmt(kpi.savings_medium)}
      </div>
      <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: 6 }}>
        Range: {fmt(kpi.savings_low)} — {fmt(kpi.savings_high)}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <ConfidenceBadge value={kpi.confidence} />
        <span style={{ fontSize: '0.7rem', color: '#94a3b8', fontStyle: 'italic' }}>{kpi.category}</span>
      </div>
    </div>
  )
}

// ── Smart metric formatter ────────────────────────────────────────────
function formatMetricValue(key, val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'object') return null // skip nested objects in summary
  if (typeof val === 'number') {
    if (key.includes('pct') || key.includes('rate') || key.includes('reduction')) return `${(val * 100).toFixed(1)}%`
    if (key.includes('cost') || key.includes('savings') || key.includes('avoided')) return `$${Math.round(val).toLocaleString()}`
    if (key.includes('kwh')) return `${Math.round(val).toLocaleString()} kWh`
    if (key.includes('kw') && !key.includes('kwh')) return `${val.toFixed(1)} kW`
    if (key.includes('tco2') || key.includes('co2e')) return `${val.toFixed(1)} tCO\u2082e`
    if (key.includes('gwp')) return val.toLocaleString()
    if (Number.isInteger(val)) return val.toLocaleString()
    return val.toFixed(2)
  }
  return String(val)
}

// ── Research Basis Popover ────────────────────────────────────────────
function ResearchInfoIcon({ research, assumptions, supportingMetrics, confidence, dataGrounded }) {
  const [open, setOpen] = useState(false)
  const hasResearch = research && research.citations && research.citations.length > 0
  const hasAssumptions = assumptions && assumptions.length > 0
  if (!hasResearch && !hasAssumptions) return null

  // Pick the most informative supporting metrics to show (skip nested objects)
  const metricEntries = supportingMetrics
    ? Object.entries(supportingMetrics).filter(([k, v]) => {
        if (v === null || v === undefined) return false
        if (typeof v === 'object' && !Array.isArray(v)) return false
        if (k === 'distribution_source' || k === 'gwp_source') return true
        return typeof v === 'number' || typeof v === 'boolean' || typeof v === 'string'
      })
    : []

  return (
    <>
      <button
        onClick={e => { e.stopPropagation(); setOpen(true) }}
        title="View research basis, assumptions & citations"
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 20, height: 20, borderRadius: '50%', border: '1px solid #cbd5e1',
          background: '#f1f5f9', color: '#64748b', cursor: 'pointer', padding: 0,
          flexShrink: 0, transition: 'all 0.15s',
        }}
        onMouseEnter={e => { e.currentTarget.style.background = '#dbeafe'; e.currentTarget.style.color = '#2563eb'; e.currentTarget.style.borderColor = '#93c5fd' }}
        onMouseLeave={e => { e.currentTarget.style.background = '#f1f5f9'; e.currentTarget.style.color = '#64748b'; e.currentTarget.style.borderColor = '#cbd5e1' }}
      >
        <Info size={12} />
      </button>
      {open && (
        <div onClick={e => e.stopPropagation()} style={{
          position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(2px)',
        }}>
          <div style={{
            background: '#fff', borderRadius: 16, maxWidth: 620, width: '92vw', maxHeight: '85vh',
            overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.2)', padding: '1.5rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.05rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
                <BookOpen size={18} style={{ color: '#2563eb' }} /> Research Basis & Assumptions
              </h3>
              <button onClick={() => setOpen(false)} style={{
                border: 'none', background: '#f1f5f9', borderRadius: 8, padding: '0.3rem', cursor: 'pointer', color: '#64748b',
              }}><X size={16} /></button>
            </div>

            {/* Data Quality Indicator */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '0.5rem 0.75rem',
              background: dataGrounded ? '#f0fdf4' : '#fffbeb', borderRadius: 8,
              border: `1px solid ${dataGrounded ? '#bbf7d0' : '#fde68a'}`,
              marginBottom: '1rem', fontSize: '0.78rem',
            }}>
              <Database size={14} style={{ color: dataGrounded ? '#16a34a' : '#d97706', flexShrink: 0 }} />
              <span style={{ color: dataGrounded ? '#166534' : '#92400e', fontWeight: 600 }}>
                {dataGrounded ? 'Data-Grounded' : 'Assumption-Based'}
              </span>
              <span style={{ color: '#64748b' }}>
                {confidence !== undefined && `· Confidence: ${(confidence * 100).toFixed(0)}%`}
              </span>
            </div>

            {/* Methodology */}
            {hasResearch && research.methodology && (
              <div style={{ background: '#f8fafc', borderRadius: 10, padding: '0.85rem', marginBottom: '1rem', borderLeft: '4px solid #2563eb' }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#2563eb', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>Methodology</div>
                <p style={{ margin: 0, fontSize: '0.85rem', color: '#475569', lineHeight: 1.55 }}>{research.methodology}</p>
              </div>
            )}

            {/* Assumptions */}
            {hasAssumptions && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <ListChecks size={13} style={{ color: '#8b5cf6' }} /> Assumptions & Parameters
                </div>
                <div style={{ display: 'grid', gap: '0.35rem' }}>
                  {assumptions.map((a, i) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'flex-start', gap: 8,
                      padding: '0.45rem 0.65rem', background: i % 2 === 0 ? '#faf5ff' : '#f8fafc',
                      borderRadius: 8, fontSize: '0.82rem', color: '#475569', lineHeight: 1.45,
                      borderLeft: '3px solid #c4b5fd',
                    }}>
                      <span style={{ color: '#8b5cf6', fontWeight: 700, fontSize: '0.7rem', flexShrink: 0, marginTop: 2 }}>{i + 1}</span>
                      <span>{a}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Key Baselines */}
            {hasResearch && research.key_baselines && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>Key Baselines & Literature Data</div>
                <div style={{ display: 'grid', gap: '0.4rem' }}>
                  {Object.entries(research.key_baselines).map(([key, val]) => (
                    <div key={key} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                      padding: '0.4rem 0.65rem', background: '#f8fafc', borderRadius: 8, fontSize: '0.82rem',
                      gap: '1rem',
                    }}>
                      <span style={{ color: '#64748b', flexShrink: 0 }}>{key.replace(/_/g, ' ')}</span>
                      <span style={{ fontWeight: 600, color: '#1e293b', textAlign: 'right', wordBreak: 'break-word' }}>{val}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Supporting Metrics */}
            {metricEntries.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <FlaskConical size={13} style={{ color: '#0ea5e9' }} /> Computed Metrics
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.35rem' }}>
                  {metricEntries.map(([key, val]) => {
                    const formatted = formatMetricValue(key, val)
                    if (!formatted) return null
                    return (
                      <div key={key} style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '0.35rem 0.55rem', background: '#f0f9ff', borderRadius: 6,
                        fontSize: '0.78rem', border: '1px solid #e0f2fe',
                      }}>
                        <span style={{ color: '#64748b' }}>{key.replace(/_/g, ' ')}</span>
                        <span style={{ fontWeight: 600, color: '#0c4a6e' }}>{formatted}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Citations */}
            {hasResearch && (
              <>
                <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>Citations ({research.citations.length})</div>
                <div style={{ display: 'grid', gap: '0.5rem' }}>
                  {research.citations.map((cite, i) => (
                    <div key={i} style={{
                      padding: '0.65rem 0.85rem', background: '#fafbfc', borderRadius: 10,
                      border: '1px solid #e2e8f0', fontSize: '0.82rem',
                    }}>
                      <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 2 }}>{cite.title}</div>
                      <div style={{ fontSize: '0.75rem', color: '#6366f1', marginBottom: 4 }}>{cite.source} ({cite.year})</div>
                      <div style={{ color: '#64748b', lineHeight: 1.45, fontStyle: 'italic' }}>"{cite.finding}"</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}

// ── KPI Detail Panel ─────────────────────────────────────────────────
function KpiDetailPanel({ kpi, onApprove }) {
  if (!kpi) return (
    <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>
      <BarChart3 size={48} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
      <p>Select a KPI scorecard to view details</p>
    </div>
  )

  const isPending = kpi.status === 'pending'
  const isRejected = kpi.status === 'rejected'

  return (
    <div style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={{ margin: 0, color: '#1e293b' }}>{kpi.display_name}</h3>
        <StatusBadge status={kpi.status} />
      </div>
      <div style={{ background: '#f8fafc', borderRadius: 8, padding: '1rem', marginBottom: '1rem', fontStyle: 'italic', color: '#475569', fontSize: '0.9rem' }}>
        {kpi.narrative}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
        <div style={{ textAlign: 'center', padding: '0.75rem', background: '#fef3c7', borderRadius: 8 }}>
          <div style={{ fontSize: '0.7rem', color: '#92400e', textTransform: 'uppercase' }}>Low</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#92400e' }}>{fmt(kpi.savings_low)}</div>
        </div>
        <div style={{ textAlign: 'center', padding: '0.75rem', background: '#dbeafe', borderRadius: 8 }}>
          <div style={{ fontSize: '0.7rem', color: '#1e40af', textTransform: 'uppercase' }}>Medium</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1e40af' }}>{fmt(kpi.savings_medium)}</div>
        </div>
        <div style={{ textAlign: 'center', padding: '0.75rem', background: '#dcfce7', borderRadius: 8 }}>
          <div style={{ fontSize: '0.7rem', color: '#166534', textTransform: 'uppercase' }}>High</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#166534' }}>{fmt(kpi.savings_high)}</div>
        </div>
      </div>
      <div style={{ marginBottom: '1rem' }}>
        <strong style={{ fontSize: '0.8rem', color: '#475569' }}>Confidence:</strong>
        <div style={{ background: '#e2e8f0', borderRadius: 8, height: 8, marginTop: 4 }}>
          <div style={{
            width: `${kpi.confidence * 100}%`, height: '100%', borderRadius: 8,
            background: kpi.confidence >= 0.7 ? '#22c55e' : kpi.confidence >= 0.5 ? '#eab308' : '#ef4444',
          }} />
        </div>
        <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 2 }}>{pct(kpi.confidence)}</div>
      </div>
      {kpi.assumptions && kpi.assumptions.length > 0 && (
        <div style={{ marginBottom: '1rem' }}>
          <strong style={{ fontSize: '0.8rem', color: '#475569' }}>Assumptions:</strong>
          <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem', fontSize: '0.8rem', color: '#64748b' }}>
            {kpi.assumptions.map((a, i) => <li key={i} style={{ marginBottom: 2 }}>{a}</li>)}
          </ul>
        </div>
      )}

      {/* Research Basis */}
      {kpi.research_basis && kpi.research_basis.citations && kpi.research_basis.citations.length > 0 && (
        <div style={{ marginBottom: '1rem' }}>
          <strong style={{ fontSize: '0.8rem', color: '#475569', display: 'flex', alignItems: 'center', gap: 6 }}>
            <BookOpen size={14} style={{ color: '#2563eb' }} /> Research Basis
          </strong>
          <p style={{ fontSize: '0.78rem', color: '#64748b', margin: '0.25rem 0 0.5rem', lineHeight: 1.45 }}>
            {kpi.research_basis.methodology}
          </p>
          {kpi.research_basis.key_baselines && (
            <div style={{ display: 'grid', gap: '0.25rem', marginBottom: '0.5rem' }}>
              {Object.entries(kpi.research_basis.key_baselines).map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '0.2rem 0.5rem', background: '#f8fafc', borderRadius: 6 }}>
                  <span style={{ color: '#64748b' }}>{k.replace(/_/g, ' ')}</span>
                  <span style={{ fontWeight: 600, color: '#1e293b' }}>{v}</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
            {kpi.research_basis.citations.length} citation{kpi.research_basis.citations.length !== 1 ? 's' : ''}: {kpi.research_basis.citations.map(c => `${c.source} (${c.year})`).join('; ')}
          </div>
        </div>
      )}

      {/* Approval Actions */}
      <div style={{
        background: isPending ? '#fffbeb' : isRejected ? '#fef2f2' : '#f0fdf4',
        border: `1px solid ${isPending ? '#fde68a' : isRejected ? '#fecaca' : '#bbf7d0'}`,
        borderRadius: 10, padding: '1rem', marginTop: '0.5rem',
      }}>
        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: 6 }}>
          {isPending ? 'Approval Required' : isRejected ? 'Rejected' : 'Approved'}
        </div>
        <p style={{ fontSize: '0.75rem', color: '#64748b', margin: '0 0 0.75rem' }}>
          {isPending
            ? `This KPI has ${pct(kpi.confidence)} confidence — below the auto-approval threshold. Review the narrative and assumptions above, then approve to include in ROI reports or reject to exclude.`
            : isRejected
            ? 'This KPI was manually rejected. It is excluded from ROI totals. You can re-approve it at any time.'
            : `This KPI was ${kpi.confidence >= 0.5 ? 'auto-' : 'manually '}approved with ${pct(kpi.confidence)} confidence.`
          }
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          {kpi.status !== 'approved' && (
            <button onClick={() => onApprove?.(kpi.kpi_name, 'approve')} style={{
              padding: '0.4rem 1rem', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: '#22c55e', color: '#fff', fontSize: '0.8rem', fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <CheckCircle2 size={14} /> Approve
            </button>
          )}
          {kpi.status !== 'rejected' && (
            <button onClick={() => onApprove?.(kpi.kpi_name, 'reject')} style={{
              padding: '0.4rem 1rem', borderRadius: 6, border: '1px solid #fecaca', cursor: 'pointer',
              background: '#fff', color: '#991b1b', fontSize: '0.8rem', fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <XCircle size={14} /> Reject
            </button>
          )}
          {(kpi.status === 'approved' || kpi.status === 'rejected') && (
            <button onClick={() => onApprove?.(kpi.kpi_name, 'pending')} style={{
              padding: '0.4rem 1rem', borderRadius: 6, border: '1px solid #e2e8f0', cursor: 'pointer',
              background: '#fff', color: '#64748b', fontSize: '0.8rem', fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <RefreshCw size={14} /> Reset to Auto
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── ROI Confidence ───────────────────────────────────────────────────
function ScenarioComparison({ scenarios, roi, budget }) {
  if (!scenarios || scenarios.length === 0) return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '2rem', textAlign: 'center' }}>
      <Layers size={40} style={{ color: '#94a3b8', margin: '0 auto 1rem', opacity: 0.4 }} />
      <h3 style={{ margin: '0 0 0.5rem', color: '#1e293b' }}>No Scenario Data</h3>
      <p style={{ color: '#64748b', fontSize: '0.85rem' }}>Upload data to generate scenario comparisons.</p>
    </div>
  )
  const maxSavings = Math.max(...scenarios.map(s => s.total_savings_medium), 1)
  const barColors = { baseline: '#94a3b8', conservative: '#3b82f6', moderate: '#8b5cf6', aggressive: '#22c55e' }
  const moderate = scenarios.find(s => s.scenario_name === 'moderate')
  const conservative = scenarios.find(s => s.scenario_name === 'conservative')
  const aggressive = scenarios.find(s => s.scenario_name === 'aggressive')

  return (
    <div>
      {/* ROI Summary Cards */}
      {roi && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '0.75rem' }}>
          {[
            { label: 'Payback Period', value: `${roi.payback_months?.toFixed(1)} mo`, color: '#3b82f6', icon: Clock },
            { label: 'ROI Multiple', value: `${roi.savings_to_cost_multiple?.toFixed(1)}x`, color: '#22c55e', icon: TrendingUp },
            { label: 'Net Present Value', value: fmt(roi.npv || 0), color: '#8b5cf6', icon: DollarSign },
            { label: 'Internal Rate of Return', value: roi.irr ? `${roi.irr.toFixed(1)}%` : '—', color: '#f59e0b', icon: Percent },
          ].map((card, i) => {
            const Icon = card.icon
            return (
              <div key={i} style={{ background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0', padding: '1rem' }}>
                <Icon size={18} style={{ color: card.color, marginBottom: 8 }} />
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
                <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{card.label}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* ROI Methodology Explainer */}
      {roi && (
        <div style={{
          background: '#f8fafc', borderRadius: 10, border: '1px solid #e2e8f0',
          padding: '0.85rem 1rem', marginBottom: '1.25rem', fontSize: '0.78rem',
          color: '#475569', lineHeight: 1.6,
        }}>
          <div style={{ fontWeight: 700, color: '#334155', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
            <DollarSign size={14} style={{ color: '#8b5cf6' }} />
            How this NPV is calculated
          </div>
          <div>
            This <strong>Net Present Value</strong> represents the total projected return from deploying the
            PdM platform across <strong>all {roi.assumptions?.data_source ? '14 KPI dimensions' : 'KPI dimensions'}</strong> fleet-wide.
            It is computed as: <span style={{ fontFamily: 'monospace', background: '#e2e8f0', padding: '1px 5px', borderRadius: 4 }}>
            NPV = −Implementation Cost + Σ(Annual Savings / (1 + r)<sup>y</sup>)</span> for
            each year <em>y</em> = 1…{roi.assumptions?.horizon_years || 5}.
          </div>
          <div style={{ marginTop: 6 }}>
            <strong>Assumptions:</strong>{' '}
            Discount rate = {((roi.assumptions?.discount_rate || 0.08) * 100).toFixed(0)}%,{' '}
            Horizon = {roi.assumptions?.horizon_years || 5} years,{' '}
            Implementation cost = {fmt(roi.assumptions?.implementation_cost || 250000)},{' '}
            Annual savings input = {fmt(roi.assumptions?.annual_savings_input || 0)}.
          </div>
          <div style={{ marginTop: 6, color: '#64748b', fontStyle: 'italic' }}>
            The Decision Support page uses the same discount rate, horizon, and implementation cost
            but computes NPV from <strong>ownership-mapped cost lines</strong> (per-metric translation rules)
            rather than fleet-wide KPI crew totals. Both views are aligned on financial parameters;
            differences reflect the scope of inputs each pipeline analyzes.
          </div>
        </div>
      )}

      {/* Scenario Bars */}
      <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem', marginBottom: '1.25rem' }}>
        <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Layers size={18} /> ROI Confidence Intervals
        </h3>
        {scenarios.map((s, i) => {
          const isBaseline = s.scenario_name === 'baseline'
          const barColor = barColors[s.scenario_name] || ['#94a3b8', '#3b82f6', '#8b5cf6', '#22c55e'][i] || '#64748b'
          return (
            <div key={i} style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: barColor,
                  }} />
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#334155' }}>
                    {s.scenario_name.charAt(0).toUpperCase() + s.scenario_name.slice(1)}
                  </span>
                </div>
                <span style={{ fontSize: '0.9rem', fontWeight: 700, color: isBaseline ? '#94a3b8' : '#1e293b' }}>
                  {isBaseline ? 'Current State' : fmt(s.total_savings_medium)}
                </span>
              </div>
              <div style={{ background: '#f1f5f9', borderRadius: 6, height: 28, position: 'relative', overflow: 'hidden' }}>
                <div style={{
                  width: isBaseline ? '100%' : `${maxSavings > 0 ? (s.total_savings_medium / maxSavings * 100) : 0}%`,
                  height: '100%', borderRadius: 6,
                  background: isBaseline
                    ? 'repeating-linear-gradient(45deg, #e2e8f0, #e2e8f0 8px, #f1f5f9 8px, #f1f5f9 16px)'
                    : barColor,
                  transition: 'width 0.5s ease',
                  display: 'flex', alignItems: 'center', paddingLeft: 8,
                }} />
              </div>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: 2, fontStyle: 'italic' }}>
                {s.description}
              </div>
            </div>
          )
        })}
      </div>

      {/* Confidence Range */}
      {conservative && aggressive && (
        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem' }}>
          <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Shield size={18} /> Confidence Range Analysis
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
            <div style={{ textAlign: 'center', padding: '1rem', background: '#eff6ff', borderRadius: 10 }}>
              <div style={{ fontSize: '0.7rem', color: '#1e40af', textTransform: 'uppercase', marginBottom: 4 }}>Conservative (P10)</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#1e40af' }}>{fmt(conservative.total_savings_medium)}</div>
              <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: 4 }}>Low-risk, shorter rollout</div>
            </div>
            <div style={{ textAlign: 'center', padding: '1rem', background: '#f5f3ff', borderRadius: 10, border: '2px solid #8b5cf6' }}>
              <div style={{ fontSize: '0.7rem', color: '#6d28d9', textTransform: 'uppercase', marginBottom: 4 }}>Moderate (P50)</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#6d28d9' }}>{fmt(moderate?.total_savings_medium || 0)}</div>
              <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: 4 }}>Balanced assumptions</div>
            </div>
            <div style={{ textAlign: 'center', padding: '1rem', background: '#f0fdf4', borderRadius: 10 }}>
              <div style={{ fontSize: '0.7rem', color: '#166534', textTransform: 'uppercase', marginBottom: 4 }}>Aggressive (P90)</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#166534' }}>{fmt(aggressive.total_savings_medium)}</div>
              <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: 4 }}>Full optimization</div>
            </div>
          </div>
          {moderate && (
            <div style={{ marginTop: '1rem', padding: '0.75rem', background: '#f8fafc', borderRadius: 8, fontSize: '0.82rem', color: '#475569', lineHeight: 1.5 }}>
              <strong>Interpretation:</strong> With 80% confidence, annual savings fall between {fmt(conservative.total_savings_medium)} and {fmt(aggressive.total_savings_medium)}.
              The moderate scenario ({fmt(moderate.total_savings_medium)}) represents the most likely outcome based on current baselines and balanced assumptions.
              {roi && roi.payback_months && ` At moderate estimates, the program pays back in ${roi.payback_months.toFixed(1)} months with a ${roi.savings_to_cost_multiple?.toFixed(1)}x return on investment.`}
            </div>
          )}
        </div>
      )}

      {/* Budget Context */}
      {budget && (budget.overall_capex > 0 || budget.overall_opex > 0) && (
        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem', marginTop: '1.25rem' }}>
          <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
            <DollarSign size={18} /> Budget Context
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
            <div style={{ padding: '0.75rem', background: '#eff6ff', borderRadius: 8, textAlign: 'center' }}>
              <div style={{ fontSize: '0.7rem', color: '#1e40af', textTransform: 'uppercase', marginBottom: 4 }}>CapEx Budget</div>
              <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#1e40af' }}>{fmt(budget.overall_capex)}</div>
              <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: 2 }}>Implementation cost basis</div>
            </div>
            <div style={{ padding: '0.75rem', background: '#f0fdf4', borderRadius: 8, textAlign: 'center' }}>
              <div style={{ fontSize: '0.7rem', color: '#166534', textTransform: 'uppercase', marginBottom: 4 }}>OpEx Budget</div>
              <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#166534' }}>{fmt(budget.overall_opex)}</div>
              <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: 2 }}>Annual operations</div>
            </div>
            <div style={{ padding: '0.75rem', background: '#faf5ff', borderRadius: 8, textAlign: 'center' }}>
              <div style={{ fontSize: '0.7rem', color: '#6d28d9', textTransform: 'uppercase', marginBottom: 4 }}>Total Budget</div>
              <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#6d28d9' }}>{fmt(budget.overall_capex + budget.overall_opex)}</div>
              <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: 2 }}>CapEx + OpEx</div>
            </div>
          </div>
          {budget.by_location && budget.by_location.length > 0 && (
            <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '0.5rem' }}>
              <strong>{budget.by_location.length} locations</strong> with allocated budgets
              ({fmt(budget.by_location.reduce((s, l) => s + (l.capex || 0) + (l.opex || 0), 0))} allocated)
            </div>
          )}
          {budget.by_asset_type && budget.by_asset_type.length > 0 && (
            <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
              <strong>{budget.by_asset_type.length} asset types</strong> with allocated budgets
              ({fmt(budget.by_asset_type.reduce((s, t) => s + (t.capex || 0) + (t.opex || 0), 0))} allocated)
            </div>
          )}
          {roi && moderate && budget.overall_capex > 0 && (
            <div style={{ marginTop: '0.75rem', padding: '0.5rem 0.75rem', background: '#f8fafc', borderRadius: 6, fontSize: '0.78rem', color: '#475569' }}>
              ROI calculated against {fmt(budget.overall_capex)} CapEx investment.
              Moderate savings of {fmt(moderate.total_savings_medium)}/yr yield {roi.savings_to_cost_multiple?.toFixed(1)}x return over 5 years.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Decision Advisory ────────────────────────────────────────────────
function DecisionAdvisory({ advisory }) {
  if (!advisory || !advisory.strategic_recommendations) return null
  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem', marginBottom: '1.5rem' }}>
      <h3 style={{ margin: '0 0 0.5rem', fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Lightbulb size={18} /> Decision Advisory
      </h3>
      {advisory.executive_narrative && (
        <p style={{ fontSize: '0.85rem', color: '#475569', fontStyle: 'italic', margin: '0 0 1rem', background: '#f8fafc', padding: '0.75rem', borderRadius: 8 }}>
          {advisory.executive_narrative}
        </p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {advisory.strategic_recommendations.map((rec, i) => (
          <div key={i} style={{
            display: 'flex', gap: '1rem', alignItems: 'flex-start',
            padding: '0.75rem', borderRadius: 8,
            background: rec.impact === 'high' ? '#fef3c7' : '#f1f5f9',
            borderLeft: `3px solid ${rec.impact === 'high' ? '#f59e0b' : '#94a3b8'}`,
          }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: rec.impact === 'high' ? '#f59e0b' : '#64748b', color: '#fff', fontWeight: 700, fontSize: '0.8rem', flexShrink: 0,
            }}>
              {rec.priority}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: '#1e293b', marginBottom: 2 }}>{rec.title}</div>
              <div style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: 4 }}>{rec.rationale}</div>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#1d4ed8' }}>
                <DollarSign size={12} style={{ verticalAlign: -1 }} /> {fmt(rec.savings_impact)}/year
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Format location ID for display ──────────────────────────────────
function formatLocationId(id) {
  if (!id) return 'Unknown'
  return id.replace(/^test site\s*/i, 'Location ')
}

// ── Location Ranking ─────────────────────────────────────────────────
function LocationRanking({ locations, capexData }) {
  const [expandedLoc, setExpandedLoc] = useState(null)

  if (!locations || locations.length === 0) return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '2rem', textAlign: 'center' }}>
      <MapPin size={40} style={{ color: '#94a3b8', margin: '0 auto 1rem', opacity: 0.4 }} />
      <h3 style={{ margin: '0 0 0.5rem', color: '#1e293b' }}>No Location Data</h3>
      <p style={{ color: '#64748b', fontSize: '0.85rem', margin: '0 0 0.5rem', maxWidth: 480, marginInline: 'auto' }}>
        Location ranking requires assets assigned to different sites. Upload an <strong>Asset Inventory</strong> CSV
        with distinct <code>site_id</code> values (e.g., store numbers or building IDs) via the Data Upload page.
      </p>
    </div>
  )

  // Build asset lookup from capex data (if available) keyed by site_id
  const assetsBySite = {}
  if (capexData?.optimized_plan?.items) {
    for (const item of capexData.optimized_plan.items) {
      const siteId = item.asset?.site_id
      if (siteId) {
        if (!assetsBySite[siteId]) assetsBySite[siteId] = []
        assetsBySite[siteId].push(item)
      }
    }
  }

  // Summary stats
  const totalSavings = locations.reduce((s, l) => s + (l.total_savings || 0), 0)
  const totalAssets = locations.reduce((s, l) => s + (l.asset_count || 0), 0)
  const totalDegraded = locations.reduce((s, l) => s + (l.degraded_count || 0), 0)

  return (
    <div>
      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '1.25rem' }}>
        {[
          { icon: MapPin, label: 'Locations', value: locations.length, color: '#3b82f6' },
          { icon: Wrench, label: 'Total Assets', value: totalAssets, color: '#8b5cf6' },
          { icon: DollarSign, label: 'Total Savings', value: fmt(totalSavings), color: '#22c55e' },
          { icon: AlertTriangle, label: 'Degraded Assets', value: totalDegraded, color: '#ef4444' },
        ].map((card, i) => {
          const Icon = card.icon
          return (
            <div key={i} style={{ background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0', padding: '1rem' }}>
              <Icon size={18} style={{ color: card.color, marginBottom: 8 }} />
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
              <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{card.label}</div>
            </div>
          )
        })}
      </div>

      {/* Location cards with expandable asset list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {locations.map((loc, i) => {
          const isExpanded = expandedLoc === loc.location_id
          const siteAssets = assetsBySite[loc.location_id] || []
          const locName = formatLocationId(loc.location_id)
          const topKpi = loc.top_kpi?.replace(/_/g, ' ')

          return (
            <div key={loc.location_id} style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', overflow: 'hidden' }}>
              {/* Location header */}
              <div
                onClick={() => setExpandedLoc(isExpanded ? null : loc.location_id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '1rem', padding: '1rem 1.25rem',
                  cursor: 'pointer', background: isExpanded ? '#f8fafc' : '#fff', transition: 'background 0.15s',
                }}
              >
                <span style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 28, height: 28, borderRadius: '50%', fontSize: '0.8rem', fontWeight: 700, flexShrink: 0,
                  background: i === 0 ? '#dbeafe' : i <= 2 ? '#f0fdf4' : '#f1f5f9',
                  color: i === 0 ? '#1d4ed8' : i <= 2 ? '#166534' : '#64748b',
                }}>
                  {i + 1}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <MapPin size={14} style={{ color: '#3b82f6' }} />
                    <span style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.9rem' }}>{locName}</span>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: 2 }}>
                    {loc.asset_count || 0} asset{(loc.asset_count || 0) !== 1 ? 's' : ''}
                    {loc.degraded_count > 0 && <span style={{ color: '#ef4444', marginLeft: 8 }}>· {loc.degraded_count} degraded</span>}
                    {topKpi && <span style={{ marginLeft: 8 }}>· Top: {topKpi}</span>}
                  </div>
                </div>
                <div style={{ textAlign: 'right', marginRight: '0.5rem' }}>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1d4ed8' }}>{fmt(loc.total_savings)}</div>
                  <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>{loc.kpi_count} KPIs</div>
                </div>
                {isExpanded ? <ChevronUp size={16} style={{ color: '#94a3b8' }} /> : <ChevronDown size={16} style={{ color: '#94a3b8' }} />}
              </div>

              {/* Expanded asset list */}
              {isExpanded && (
                <div style={{ borderTop: '1px solid #e2e8f0', padding: '0.75rem 1.25rem', background: '#fafbfc' }}>
                  {siteAssets.length > 0 ? (
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                          <th style={{ textAlign: 'left', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Asset ID</th>
                          <th style={{ textAlign: 'left', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Type</th>
                          <th style={{ textAlign: 'center', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Age</th>
                          <th style={{ textAlign: 'center', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Priority</th>
                          <th style={{ textAlign: 'center', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Risk</th>
                          <th style={{ textAlign: 'center', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Decision</th>
                          <th style={{ textAlign: 'right', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>NPV</th>
                        </tr>
                      </thead>
                      <tbody>
                        {siteAssets.map((item, j) => {
                          const a = item.asset || {}
                          const sc = item.score || {}
                          const pi = item.plan_item || {}
                          const surv = item.survival_analysis || {}
                          const rec = item.recommendation || pi
                          const decision = rec.decision || pi.decision || 'N/A'
                          const riskColor = surv.risk_category === 'critical' ? '#ef4444' : surv.risk_category === 'high' ? '#f97316' : surv.risk_category === 'elevated' ? '#eab308' : '#22c55e'
                          const decColor = decision === 'REPLACE' ? '#dc2626' : decision === 'INSPECT' ? '#f59e0b' : '#64748b'
                          return (
                            <tr key={j} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '0.4rem 0.5rem', fontWeight: 600, color: '#1e293b' }}>
                                {a.asset_id?.replace(loc.location_id + '_', '') || a.asset_id}
                              </td>
                              <td style={{ padding: '0.4rem 0.5rem', color: '#64748b', fontSize: '0.75rem' }}>
                                {(a.asset_type || 'Unknown').replace(/_/g, ' ')}
                              </td>
                              <td style={{ padding: '0.4rem 0.5rem', textAlign: 'center' }}>{a.age_years || '—'}y</td>
                              <td style={{ padding: '0.4rem 0.5rem', textAlign: 'center' }}>
                                <span style={{
                                  display: 'inline-block', padding: '1px 6px', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600,
                                  background: sc.replace_priority_score >= 60 ? '#fee2e2' : sc.replace_priority_score >= 40 ? '#fef3c7' : '#dbeafe',
                                  color: sc.replace_priority_score >= 60 ? '#991b1b' : sc.replace_priority_score >= 40 ? '#92400e' : '#1e40af',
                                }}>{sc.replace_priority_score || 0}</span>
                              </td>
                              <td style={{ padding: '0.4rem 0.5rem', textAlign: 'center', fontSize: '0.72rem', fontWeight: 600, color: riskColor, textTransform: 'uppercase' }}>
                                {surv.risk_category || 'N/A'}
                              </td>
                              <td style={{ padding: '0.4rem 0.5rem', textAlign: 'center' }}>
                                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: decColor }}>{decision}</span>
                              </td>
                              <td style={{ padding: '0.4rem 0.5rem', textAlign: 'right', fontWeight: 600, color: (pi.npv_p50 || 0) > 0 ? '#16a34a' : '#64748b' }}>
                                {pi.npv_p50 ? fmt(pi.npv_p50) : '—'}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  ) : (
                    <div style={{ padding: '0.75rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.82rem' }}>
                      {loc.asset_count || 0} asset{(loc.asset_count || 0) !== 1 ? 's' : ''} at this location.
                      Run the Asset Replacement analysis for detailed asset-level data.
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Average device costs (HVAC/R industry research) ─────────────────
const DEVICE_COSTS = {
  RTU:               { label: 'Rooftop Unit (RTU)',         cost: 18000, failureCost: 15000 },
  HVAC_RTU:          { label: 'HVAC RTU',                   cost: 18000, failureCost: 15000 },
  AHU:               { label: 'Air Handling Unit',          cost: 25000, failureCost: 20000 },
  COMPRESSOR_RACK:   { label: 'Compressor Rack',            cost: 30000, failureCost: 25000 },
  CONDENSING_UNIT:   { label: 'Condensing Unit',            cost: 15000, failureCost: 12000 },
  WALK_IN_COOLER:    { label: 'Walk-in Cooler',             cost: 12000, failureCost: 10000 },
  WALK_IN_FREEZER:   { label: 'Walk-in Freezer',            cost: 14000, failureCost: 12000 },
  REACH_IN_CASE:     { label: 'Reach-in Display Case',      cost:  8000, failureCost:  8000 },
  CHILLER:           { label: 'Chiller (Scroll/Screw)',     cost: 45000, failureCost: 30000 },
  HVAC_SPLIT_SYSTEM: { label: 'Split System (HVAC)',        cost: 12000, failureCost: 10000 },
  HVAC_VRF:          { label: 'VRF System',                 cost: 35000, failureCost: 28000 },
  HEAT_PUMP:         { label: 'Heat Pump',                  cost: 14000, failureCost: 12000 },
  DISPLAY_CASE:      { label: 'Display Case',               cost: 10000, failureCost:  8000 },
  COOLER_COMPRESSOR: { label: 'Cooler Compressor',          cost:  8000, failureCost:  6000 },
}

// ── Asset Replacement Dashboard ─────────────────────────────────────
function CapExPlanning({ siteId, onCapexLoaded }) {
  const [capex, setCapex] = useState(null)
  const [loading, setLoading] = useState(false)
  const [budget, setBudget] = useState(500000)
  const [error, setError] = useState(null)
  const [showCosts, setShowCosts] = useState(false)

  const runAnalysis = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await KpiApi.getCapex(siteId || 'default', { budget, objective: 'max_expected_npv' })
      setCapex(result)
      onCapexLoaded?.(result)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { runAnalysis() }, [siteId])

  if (error) return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <AlertTriangle size={36} style={{ color: '#ef4444', margin: '0 auto 1rem' }} />
      <h3 style={{ color: '#1e293b', margin: '0 0 0.5rem' }}>Asset Replacement Analysis Unavailable</h3>
      <p style={{ color: '#64748b', fontSize: '0.9rem', margin: '0 0 1rem' }}>{error}</p>
      <p style={{ color: '#94a3b8', fontSize: '0.8rem', margin: '0 0 1rem', maxWidth: 500, marginInline: 'auto' }}>
        Asset replacement analysis requires asset data. Upload an <strong>Asset Inventory</strong> CSV via the Data Upload page
        with columns: asset_id, asset_type, install_date, site_id. Then upload <strong>Telemetry</strong> data
        so the engine can assess asset health and compute replacement priorities.
      </p>
      <button onClick={runAnalysis} style={{
        marginTop: '0.5rem', padding: '0.5rem 1.5rem', borderRadius: 8, border: 'none',
        background: '#1d4ed8', color: '#fff', cursor: 'pointer', fontWeight: 600,
      }}>Retry</button>
    </div>
  )

  if (loading || !capex) return (
    <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>
      <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 1rem' }} />
      <p>Running asset replacement analysis...</p>
    </div>
  )

  const s = capex.summary || {}
  const plan = capex.optimized_plan || {}
  const sensitivity = capex.sensitivity || []
  const nextBest = capex.next_best_assets || []
  const allItems = plan.items || []
  const replaceItems = allItems.filter(i => i.plan_item?.is_in_budget || i.recommendation?.decision === 'REPLACE' || i.plan_item?.decision === 'REPLACE')
  const inspectItems = allItems.filter(i => (i.recommendation?.decision === 'INSPECT' || i.plan_item?.decision === 'INSPECT') && !replaceItems.includes(i))
  const deferItems = allItems.filter(i => !replaceItems.includes(i) && !inspectItems.includes(i))
  const maxSens = Math.max(...sensitivity.map(p => p.total_npv), 1)

  // Group all items by location
  const byLocation = {}
  for (const item of allItems) {
    const siteId = item.asset?.site_id || 'Unknown'
    if (!byLocation[siteId]) byLocation[siteId] = []
    byLocation[siteId].push(item)
  }
  // Sort locations by total NPV descending
  const sortedLocations = Object.entries(byLocation).sort((a, b) => {
    const npvA = a[1].reduce((s, i) => s + (i.plan_item?.npv_p50 || 0), 0)
    const npvB = b[1].reduce((s, i) => s + (i.plan_item?.npv_p50 || 0), 0)
    return npvB - npvA
  })

  // Compute totals for all actionable items
  const totalReplaceCost = replaceItems.reduce((s, i) => {
    const cost = i.plan_item?.capex_cost || i.option_evaluations?.[0]?.capex || DEVICE_COSTS[i.asset?.asset_type]?.cost || 12000
    return s + cost
  }, 0)
  const totalReplaceNPV = replaceItems.reduce((s, i) => s + (i.plan_item?.npv_p50 || i.option_evaluations?.[0]?.npv || 0), 0)

  return (
    <div>
      {/* Budget Control */}
      <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1rem 1.25rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <Target size={20} style={{ color: '#1d4ed8' }} />
        <span style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.9rem' }}>Replacement Budget:</span>
        <input
          type="number" value={budget} onChange={e => setBudget(Number(e.target.value))} step={50000} min={10000}
          style={{ width: 140, padding: '0.4rem 0.75rem', borderRadius: 6, border: '1px solid #e2e8f0', fontSize: '0.9rem' }}
        />
        <button onClick={runAnalysis} style={{
          padding: '0.4rem 1.25rem', borderRadius: 8, border: 'none',
          background: '#1d4ed8', color: '#fff', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem',
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <Zap size={14} /> Re-Analyze
        </button>
        <button onClick={() => setShowCosts(!showCosts)} style={{
          padding: '0.4rem 0.75rem', borderRadius: 6, border: '1px solid #e2e8f0',
          background: showCosts ? '#eff6ff' : '#fff', color: '#64748b', cursor: 'pointer', fontSize: '0.78rem',
        }}>
          {showCosts ? 'Hide' : 'Show'} Device Cost Reference
        </button>
        <span style={{ marginLeft: 'auto', fontSize: '0.8rem', color: '#64748b' }}>
          {s.assets_analyzed || 0} assets across {sortedLocations.length} locations
        </span>
      </div>

      {/* Device Cost Reference (collapsible) */}
      {showCosts && (
        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1rem 1.25rem', marginBottom: '1rem' }}>
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.85rem', color: '#475569' }}>Average HVAC/R Device Costs (Installed)</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
            {Object.entries(DEVICE_COSTS).map(([key, v]) => (
              <div key={key} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.3rem 0.6rem', background: '#f8fafc', borderRadius: 6, fontSize: '0.78rem' }}>
                <span style={{ color: '#64748b' }}>{v.label}</span>
                <span style={{ fontWeight: 600, color: '#1e293b' }}>{fmt(v.cost)}</span>
              </div>
            ))}
          </div>
          <p style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: '0.5rem', fontStyle: 'italic' }}>
            Based on ASHRAE, RS Means, and industry survey data. Includes equipment + installation. Regional variance ±20%.
          </p>
        </div>
      )}

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '0.75rem', marginBottom: '1.25rem' }}>
        {[
          { icon: DollarSign, label: 'Est. Replacement Cost', value: fmt(s.total_capex_selected || totalReplaceCost), sub: `Budget: ${fmt(budget)}`, color: '#3b82f6' },
          { icon: TrendingUp, label: 'Expected NPV', value: fmt(s.total_expected_npv || totalReplaceNPV), sub: `${fmt(s.total_annual_savings || Math.round(totalReplaceNPV / 5))}/yr savings`, color: '#22c55e' },
          { icon: Wrench, label: 'Replace', value: replaceItems.length, sub: `of ${allItems.length} analyzed`, color: '#dc2626' },
          { icon: Clock, label: 'Inspect', value: inspectItems.length, sub: 'Recommend inspection', color: '#eab308' },
          { icon: Shield, label: 'Monitor', value: deferItems.length, sub: 'Continue monitoring', color: '#64748b' },
        ].map((card, i) => (
          <div key={i} style={{ background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0', padding: '1rem' }}>
            <card.icon size={18} style={{ color: card.color, marginBottom: 8 }} />
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
            <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{card.label}</div>
            <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: 2 }}>{card.sub}</div>
          </div>
        ))}
      </div>

      {/* Assets ranked by location */}
      <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem', marginBottom: '1.25rem' }}>
        <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Wrench size={18} /> Asset Replacement Ranking by Location ({allItems.length} assets)
        </h3>
        {sortedLocations.map(([locId, locItems], li) => {
          const locName = formatLocationId(locId)
          const locReplace = locItems.filter(i => i.recommendation?.decision === 'REPLACE' || i.plan_item?.decision === 'REPLACE')
          const locNPV = locItems.reduce((s, i) => s + (i.plan_item?.npv_p50 || 0), 0)
          // Sort items within location by priority score descending
          const sorted = [...locItems].sort((a, b) => (b.score?.replace_priority_score || 0) - (a.score?.replace_priority_score || 0))
          return (
            <div key={locId} style={{ marginBottom: li < sortedLocations.length - 1 ? '1.25rem' : 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: '0.5rem', padding: '0.5rem 0', borderBottom: '2px solid #e2e8f0' }}>
                <MapPin size={14} style={{ color: '#3b82f6' }} />
                <span style={{ fontWeight: 700, color: '#1e293b', fontSize: '0.9rem' }}>{locName}</span>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  {locItems.length} assets · {locReplace.length} recommended for replacement
                </span>
                <span style={{ marginLeft: 'auto', fontWeight: 700, color: '#1d4ed8', fontSize: '0.85rem' }}>
                  NPV: {fmt(locNPV)}
                </span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    <th style={{ textAlign: 'left', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Asset</th>
                    <th style={{ textAlign: 'left', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Type</th>
                    <th style={{ textAlign: 'center', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Age</th>
                    <th style={{ textAlign: 'center', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Priority</th>
                    <th style={{ textAlign: 'center', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Risk</th>
                    <th style={{ textAlign: 'center', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Decision</th>
                    <th style={{ textAlign: 'right', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>Est. Cost</th>
                    <th style={{ textAlign: 'right', padding: '0.4rem 0.5rem', color: '#64748b', fontWeight: 600 }}>NPV</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((it, i) => {
                    const a = it.asset || {}
                    const sc = it.score || {}
                    const pi = it.plan_item || {}
                    const surv = it.survival_analysis || {}
                    const rec = it.recommendation || pi
                    const decision = rec.decision || pi.decision || 'N/A'
                    const riskColor = surv.risk_category === 'critical' ? '#ef4444' : surv.risk_category === 'high' ? '#f97316' : surv.risk_category === 'elevated' ? '#eab308' : '#22c55e'
                    const decColor = decision === 'REPLACE' ? '#dc2626' : decision === 'INSPECT' ? '#f59e0b' : '#94a3b8'
                    const decBg = decision === 'REPLACE' ? '#fef2f2' : decision === 'INSPECT' ? '#fffbeb' : 'transparent'
                    const estCost = pi.capex_cost || DEVICE_COSTS[a.asset_type]?.cost || 12000
                    return (
                      <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', background: decBg }}>
                        <td style={{ padding: '0.5rem' }}>
                          <div style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.78rem' }}>{a.asset_id?.replace(locId + '_', '') || a.asset_id}</div>
                          <div style={{ fontSize: '0.65rem', color: '#94a3b8' }}>{a.manufacturer || ''} {a.model_number || ''}</div>
                        </td>
                        <td style={{ padding: '0.5rem', color: '#64748b', fontSize: '0.75rem' }}>{(a.asset_type || 'Unknown').replace(/_/g, ' ')}</td>
                        <td style={{ textAlign: 'center', padding: '0.5rem' }}>{a.age_years || '—'}y</td>
                        <td style={{ textAlign: 'center', padding: '0.5rem' }}>
                          <span style={{
                            display: 'inline-block', padding: '2px 8px', borderRadius: 10, fontSize: '0.75rem', fontWeight: 600,
                            background: sc.replace_priority_score >= 60 ? '#fee2e2' : sc.replace_priority_score >= 40 ? '#fef3c7' : '#dbeafe',
                            color: sc.replace_priority_score >= 60 ? '#991b1b' : sc.replace_priority_score >= 40 ? '#92400e' : '#1e40af',
                          }}>{sc.replace_priority_score || 0}</span>
                        </td>
                        <td style={{ textAlign: 'center', padding: '0.5rem' }}>
                          <span style={{ fontSize: '0.7rem', fontWeight: 600, color: riskColor, textTransform: 'uppercase' }}>
                            {surv.risk_category || 'N/A'}
                          </span>
                        </td>
                        <td style={{ textAlign: 'center', padding: '0.5rem' }}>
                          <span style={{ fontSize: '0.72rem', fontWeight: 700, color: decColor, padding: '1px 6px', borderRadius: 4, background: decision === 'REPLACE' ? '#fee2e2' : decision === 'INSPECT' ? '#fef3c7' : '#f1f5f9' }}>
                            {decision}
                          </span>
                        </td>
                        <td style={{ textAlign: 'right', padding: '0.5rem', fontWeight: 600, fontSize: '0.8rem' }}>{fmt(estCost)}</td>
                        <td style={{ textAlign: 'right', padding: '0.5rem', fontWeight: 600, color: (pi.npv_p50 || 0) > 0 ? '#16a34a' : '#64748b' }}>
                          {fmt(pi.npv_p50 || 0)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
        {/* Sensitivity Analysis */}
        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem' }}>
          <h3 style={{ margin: '0 0 0.75rem', fontSize: '1rem', color: '#1e293b' }}>Budget Sensitivity</h3>
          {sensitivity.length > 0 ? sensitivity.map((pt, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
              <div style={{ width: 80, fontSize: '0.8rem', color: '#475569', fontWeight: pt.budget_multiplier === 1 ? 700 : 400 }}>
                {pt.budget_multiplier === 1 ? '→ ' : ''}{fmt(pt.budget)}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ background: '#e2e8f0', borderRadius: 4, height: 16, position: 'relative' }}>
                  <div style={{
                    width: `${maxSens > 0 ? (Math.max(pt.total_npv, 0) / maxSens * 100) : 0}%`,
                    height: '100%', borderRadius: 4,
                    background: pt.budget_multiplier === 1 ? '#3b82f6' : '#94a3b8',
                  }} />
                </div>
              </div>
              <div style={{ width: 40, textAlign: 'right', fontSize: '0.75rem', fontWeight: 600, color: '#1e293b' }}>
                {pt.assets_selected}
              </div>
            </div>
          )) : (
            <p style={{ color: '#94a3b8', fontSize: '0.82rem' }}>No sensitivity data available.</p>
          )}
        </div>

        {/* Next Best */}
        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem' }}>
          <h3 style={{ margin: '0 0 0.75rem', fontSize: '1rem', color: '#1e293b' }}>Next Best (if budget expanded)</h3>
          {nextBest.length > 0 ? nextBest.map((nb, i) => (
            <div key={i} style={{ padding: '0.5rem 0', borderBottom: i < nextBest.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                <span style={{ fontWeight: 600, color: '#1e293b' }}>{(nb.asset_type || '').replace(/_/g, ' ')}</span>
                <span style={{ color: '#16a34a', fontWeight: 600 }}>+{fmt(nb.additional_npv || 0)}</span>
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                Cost: {fmt(nb.additional_cost || 0)} · NPV/$ {nb.npv_per_dollar?.toFixed(2) || 'N/A'}
              </div>
            </div>
          )) : (
            <p style={{ color: '#94a3b8', fontSize: '0.82rem' }}>All beneficial replacements fit within current budget.</p>
          )}
        </div>
      </div>
    </div>
  )
}


// ══════════════════════════════════════════════════════════════════════
// Main KPI Dashboard
// ══════════════════════════════════════════════════════════════════════
export default function KpiDashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [selectedKpi, setSelectedKpi] = useState(null)
  const [activeTab, setActiveTab] = useState('scorecards')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(null)
  const [capexData, setCapexData] = useState(null)
  const [showBusinessCase, setShowBusinessCase] = useState(false)

  const handleApproveKpi = async (kpiName, action) => {
    try {
      const result = await KpiApi.approveKpi(data.site_id || 'default', kpiName, action)
      // Update local scorecard status
      setData(prev => ({
        ...prev,
        scorecards: prev.scorecards.map(sc =>
          sc.kpi_name === kpiName ? { ...sc, status: result.new_status } : sc
        ),
      }))
    } catch (e) {
      console.error('KPI approval error:', e)
    }
  }

  const handleExportROI = async () => {
    setExporting(true)
    setExportError(null)
    try {
      const url = await KpiApi.exportRoiWorkbook({
        first_year_scenario: 'Medium',
        discount_rate: data?.roi?.discount_rate || 0.08,
      })
      const filename = `ROI_Workbook_${new Date().toISOString().slice(0,10)}.xlsx`
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('ROI export failed:', e)
      setExportError(e.message)
    } finally {
      setExporting(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const json = await KpiApi.getDashboard('default')
        if (!cancelled) {
          setData(json)
          setError(null)
        }
      } catch (e) {
        console.error('KPI dashboard load failed:', e)
        if (!cancelled) setError(e.message)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  if (error) return (
    <div style={{ maxWidth: 600, margin: '3rem auto', padding: '2rem', textAlign: 'center' }}>
      <AlertTriangle size={48} style={{ color: '#ef4444', margin: '0 auto 1rem' }} />
      <h3 style={{ color: '#1e293b', margin: '0 0 0.5rem' }}>KPI Dashboard Unavailable</h3>
      <p style={{ color: '#64748b', fontSize: '0.9rem', margin: '0 0 1rem' }}>{error}</p>
      <p style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
        Ensure the backend is running and data has been uploaded via the Data Upload page.
      </p>
    </div>
  )

  if (!data) return <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>Loading KPI data...</div>

  const summary = data.executive_summary
  const selected = data.scorecards.find(k => k.kpi_name === selectedKpi)

  const tabs = [
    { id: 'scorecards', label: 'Scorecards & ROI Analysis', icon: BarChart3 },
    { id: 'capex', label: 'Asset Replacement', icon: Target },
    { id: 'scenarios', label: 'ROI', icon: Layers },
    { id: 'advisory', label: 'Advisory', icon: Lightbulb },
    { id: 'locations', label: 'Locations', icon: MapPin },
  ]

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: '1.5rem', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      {/* Page Description */}
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
        marginBottom: '1rem', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> Aggregates <strong>14 KPI scorecards</strong> from
        fleet-wide telemetry data — energy efficiency, refrigerant health, compressor performance,
        and more. Shows consolidated ROI with savings estimates, asset replacement analysis,
        scenario comparisons, location rankings, and strategic advisory recommendations.
      </div>

      {/* Executive Summary Banner */}
      <div style={{
        background: 'linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%)',
        borderRadius: 16, padding: '1.5rem 2rem', marginBottom: '1.5rem', color: '#fff',
      }}>
        <div style={{ fontSize: '0.85rem', opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>
          Composite ROI Analysis — {summary.kpi_count} KPIs ({summary.approved_kpis} approved)
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '1.5rem', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '2.5rem', fontWeight: 800 }}>{fmt(summary.total_savings_medium)}</div>
            <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>Annual Savings (Medium)</div>
          </div>
          <div style={{ fontSize: '0.9rem', opacity: 0.8 }}>
            Range: {fmt(summary.total_savings_low)} — {fmt(summary.total_savings_high)}
          </div>
          {data.roi && (
            <div style={{ display: 'flex', gap: '1.5rem', marginLeft: 'auto', alignItems: 'center' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.3rem', fontWeight: 700 }}>{data.roi.payback_months?.toFixed(1)}mo</div>
                <div style={{ fontSize: '0.7rem', opacity: 0.7 }}>Payback</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.3rem', fontWeight: 700 }}>{data.roi.savings_to_cost_multiple?.toFixed(1)}x</div>
                <div style={{ fontSize: '0.7rem', opacity: 0.7 }}>ROI Multiple</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.3rem', fontWeight: 700 }}>{fmt(data.roi.npv)}</div>
                <div style={{ fontSize: '0.7rem', opacity: 0.7 }}>NPV</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Persistent Action Bar: Reports & Exports ────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.75rem',
        padding: '0.65rem 1rem', marginBottom: '1rem',
        background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10,
      }}>
        <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Reports & Exports
        </span>
        <div style={{ width: 1, height: 20, background: '#cbd5e1' }} />

        {/* Excel ROI Export */}
        <button
          onClick={handleExportROI}
          disabled={exporting}
          title={exportError || 'Download ROI Workbook (.xlsx)'}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0.4rem 0.85rem', borderRadius: 8,
            border: '1px solid #e2e8f0',
            background: exportError ? '#fef2f2' : '#fff',
            color: exportError ? '#dc2626' : '#1d4ed8',
            fontSize: '0.8rem', fontWeight: 600,
            cursor: exporting ? 'wait' : 'pointer',
            transition: 'all 0.15s',
          }}
        >
          {exporting
            ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Exporting...</>
            : <><FileDown size={14} /> ROI Workbook (.xlsx)</>
          }
        </button>

        {/* Business Case Builder */}
        <button
          onClick={() => setShowBusinessCase(prev => !prev)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0.4rem 0.85rem', borderRadius: 8,
            border: showBusinessCase ? '1px solid #1d4ed8' : '1px solid #e2e8f0',
            background: showBusinessCase ? '#eff6ff' : '#fff',
            color: showBusinessCase ? '#1d4ed8' : '#475569',
            fontSize: '0.8rem', fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
        >
          <Briefcase size={14} />
          Business Case (.docx)
          <ChevronDown size={14} style={{
            transform: showBusinessCase ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.2s',
          }} />
        </button>
      </div>

      {/* ── Collapsible Business Case Panel ────────────────── */}
      {showBusinessCase && (
        <div style={{
          border: '1px solid #bfdbfe', borderRadius: 12, padding: '1.25rem',
          background: '#fafcff', marginBottom: '1.25rem',
          animation: 'fadeSlideIn 0.2s ease-out',
        }}>
          <style>{`@keyframes fadeSlideIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }`}</style>
          <BusinessCasePage embedded />
        </div>
      )}

      {/* Tab Navigation */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '2px solid #e2e8f0', paddingBottom: '0.5rem' }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '0.5rem 1rem', borderRadius: 8, border: 'none', cursor: 'pointer',
              fontSize: '0.85rem', fontWeight: 600,
              background: activeTab === tab.id ? '#1d4ed8' : 'transparent',
              color: activeTab === tab.id ? '#fff' : '#64748b',
              transition: 'all 0.15s',
            }}
          >
            <tab.icon size={16} /> {tab.label}
          </button>
        ))}

        {data.governance?.modules_active?.length > 0 && (
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.75rem', color: '#22c55e' }}>
            <Shield size={14} /> {data.governance.modules_active.length} governance modules active
          </div>
        )}
      </div>

      {/* Tab Content */}
      {activeTab === 'scorecards' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              {data.scorecards.map(kpi => (
                <KpiScorecard
                  key={kpi.kpi_name}
                  kpi={kpi}
                  onSelect={setSelectedKpi}
                  selected={selectedKpi === kpi.kpi_name}
                />
              ))}
            </div>
          </div>
          <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', position: 'sticky', top: '1rem', alignSelf: 'start' }}>
            <KpiDetailPanel kpi={selected} onApprove={handleApproveKpi} />
          </div>
        </div>
      )}

      {activeTab === 'capex' && (
        <CapExPlanning siteId={data.site_id || 'default'} onCapexLoaded={setCapexData} />
      )}

      {activeTab === 'scenarios' && (
        <ScenarioComparison scenarios={data.scenario_comparison} roi={data.roi} budget={data.budget} />
      )}

      {activeTab === 'advisory' && (
        <DecisionAdvisory advisory={data.decision_advisory} />
      )}

      {activeTab === 'locations' && (
        <LocationRanking locations={data.location_ranking} capexData={capexData} />
      )}

    </div>
  )
}
