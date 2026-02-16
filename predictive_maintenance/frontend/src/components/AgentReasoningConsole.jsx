/**
 * AgentReasoningConsole — Unique UI displaying 12-agent reasoning traces,
 * cross-silo consolidation, and actionable recommendations.
 *
 * User selects an asset or location → system runs the agent crew pipeline →
 * UI reveals each agent's reasoning step-by-step with an animated timeline,
 * a radial cross-silo contribution chart, and prioritized recommendation cards.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Search, Play, Loader2, ChevronDown, ChevronRight, CheckCircle2,
  AlertTriangle, XCircle, Cpu, Users, BarChart3, Shield, Zap,
  Building2, Wrench, DollarSign, Leaf, Scale, GitBranch, ArrowRight,
  Target, Clock, TrendingUp, CircleDot, Layers, FileText, Eye,
  ChevronUp, Activity, Network, MessageSquare
} from 'lucide-react'
import AgentCommsPanel from './AgentCommsPanel'

const API_BASE = '/api/v1/ownership'

// ═══════════════════════════════════════════════════════════════
// Color + Icon Mappings
// ═══════════════════════════════════════════════════════════════

const QUADRANT_COLORS = {
  Q1: { bg: '#0f3460', border: '#3b82f6', text: '#93c5fd', accent: '#60a5fa', label: 'FM / Opex' },
  Q2: { bg: '#1a3a2a', border: '#22c55e', text: '#86efac', accent: '#4ade80', label: 'Finance / Capex' },
  Q3: { bg: '#3d1f1f', border: '#ef4444', text: '#fca5a5', accent: '#f87171', label: 'Compliance / Risk' },
  Q4: { bg: '#2d2347', border: '#a855f7', text: '#d8b4fe', accent: '#c084fc', label: 'Strategic / ESG' },
  all: { bg: '#1e293b', border: '#64748b', text: '#cbd5e1', accent: '#94a3b8', label: 'Cross-Silo' },
  cross: { bg: '#1e293b', border: '#f59e0b', text: '#fde68a', accent: '#fbbf24', label: 'Operations' },
}

const AGENT_ICONS = {
  fm: Wrench, finance: DollarSign, compliance: Shield, ops: Building2, esg: Leaf,
  opex_modeler: BarChart3, capex_modeler: TrendingUp, risk_modeler: AlertTriangle,
  strategic_modeler: Network, reconciler: GitBranch, optimizer: Target, auditor: FileText,
}

const GROUP_ORDER = ['stakeholder', 'dimension', 'governance']
const GROUP_LABELS = { stakeholder: 'Stakeholder Agents', dimension: 'Dimension Modelers', governance: 'Governance Agents' }
const GROUP_ICONS = { stakeholder: Users, dimension: Cpu, governance: Shield }

const CATEGORY_STYLES = {
  compliance: { color: '#f87171', icon: Shield, label: 'Compliance' },
  quick_win: { color: '#4ade80', icon: Zap, label: 'Quick Win' },
  structural: { color: '#60a5fa', icon: Layers, label: 'Structural' },
  capex: { color: '#fbbf24', icon: DollarSign, label: 'CapEx' },
}

// ═══════════════════════════════════════════════════════════════
// Subcomponents
// ═══════════════════════════════════════════════════════════════

function ScopeSelector({ onRun, loading, embedded = false }) {
  const [scopeType, setScopeType] = useState('asset')
  const [scopeId, setScopeId] = useState('')
  const [profiles, setProfiles] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/agent-advisor/profiles`)
      .then(r => r.json())
      .then(setProfiles)
      .catch(() => {})
  }, [])

  const items = profiles
    ? (scopeType === 'asset' ? profiles.sample_assets : profiles.sample_locations)
    : []

  return (
    <div style={embedded ? {
      display: 'flex', flexDirection: 'column', gap: '1rem',
      background: '#fff', border: '1px solid #e2e8f0',
      borderRadius: '12px', padding: '1.25rem',
    } : {
      display: 'flex', flexDirection: 'column', gap: '1rem',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%)',
      border: '1px solid rgba(99, 102, 241, 0.3)',
      borderRadius: '16px', padding: '1.5rem',
      boxShadow: '0 0 40px rgba(99, 102, 241, 0.08)',
    }}>
      {!embedded && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{
              width: 40, height: 40, borderRadius: '12px',
              background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Cpu size={20} color="#fff" />
            </div>
            <div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#e2e8f0' }}>
                Portfolio Optimization
              </div>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                Select an asset or location &middot; 12-agent analysis &middot; Per-scope recommendations
              </div>
            </div>
          </div>

          <div style={{
            background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.2)',
            borderRadius: 10, padding: '10px 14px', fontSize: '0.78rem', color: '#c7d2fe',
            lineHeight: 1.65, marginBottom: '0.25rem',
          }}>
            <strong style={{ color: '#e0e7ff' }}>What this page does:</strong> Drill into a
            <strong> single asset or location</strong> to run the 12-agent AI crew scoped to that specific target.
            See each agent's reasoning trace step-by-step, a cross-silo contribution breakdown, and
            prioritized recommendations tailored to the selected scope.
            <div style={{
              marginTop: 6, padding: '5px 8px', background: 'rgba(251, 191, 36, 0.1)',
              border: '1px solid rgba(251, 191, 36, 0.2)', borderRadius: 6, color: '#fde68a', fontSize: '0.72rem',
            }}>
              <strong>How this differs from Ecosystem Optimizer:</strong> Ecosystem Optimizer (in the sidebar)
              analyzes <strong>all metrics, owners, and cost dimensions enterprise-wide</strong>.
              This page focuses on a <strong>single asset or location</strong> to show granular agent reasoning,
              cross-silo contributions, and targeted action items for that specific scope.
            </div>
          </div>
        </>
      )}

      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'end', flexWrap: 'wrap' }}>
        {/* Scope Type Toggle */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Scope</label>
          <div style={{ display: 'flex', borderRadius: '8px', overflow: 'hidden', border: '1px solid #334155' }}>
            {['asset', 'location'].map(t => (
              <button key={t} onClick={() => { setScopeType(t); setScopeId('') }} style={{
                padding: '0.5rem 1rem', fontSize: '0.8rem', cursor: 'pointer',
                background: scopeType === t ? '#4f46e5' : '#1e293b',
                color: scopeType === t ? '#fff' : '#94a3b8',
                border: 'none', fontWeight: scopeType === t ? 600 : 400,
                transition: 'all 0.2s',
              }}>
                {t === 'asset' ? '🔧 Asset' : '📍 Location'}
              </button>
            ))}
          </div>
        </div>

        {/* Scope ID — dropdown + manual input */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', flex: 1, minWidth: 200 }}>
          <label style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {scopeType === 'asset' ? 'Asset ID' : 'Location ID'}
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <select
              value={scopeId}
              onChange={e => setScopeId(e.target.value)}
              style={{
                flex: 1, padding: '0.5rem 0.75rem', borderRadius: '8px',
                background: '#0f172a', color: '#e2e8f0', fontSize: '0.85rem',
                border: '1px solid #334155', outline: 'none',
              }}
            >
              <option value="">Select or type...</option>
              {items.map(i => (
                <option key={i.id} value={i.id}>{i.id} — {i.label}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Custom ID"
              value={scopeId}
              onChange={e => setScopeId(e.target.value)}
              style={{
                width: 120, padding: '0.5rem 0.75rem', borderRadius: '8px',
                background: '#0f172a', color: '#e2e8f0', fontSize: '0.85rem',
                border: '1px solid #334155', outline: 'none',
              }}
            />
          </div>
        </div>

        {/* Run Button */}
        <button
          onClick={() => scopeId && onRun(scopeType, scopeId)}
          disabled={!scopeId || loading}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.5rem',
            padding: '0.6rem 1.5rem', borderRadius: '10px',
            background: !scopeId || loading ? '#334155' : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            color: '#fff', border: 'none', cursor: !scopeId || loading ? 'default' : 'pointer',
            fontWeight: 600, fontSize: '0.85rem',
            boxShadow: !scopeId || loading ? 'none' : '0 4px 15px rgba(99, 102, 241, 0.3)',
            transition: 'all 0.3s',
          }}
        >
          {loading ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
          {loading ? 'Running 12 Agents...' : 'Run Analysis'}
        </button>
      </div>
    </div>
  )
}


function AgentTraceCard({ trace, index, isExpanded, onToggle }) {
  const Icon = AGENT_ICONS[trace.agent_id] || Cpu
  const qc = QUADRANT_COLORS[trace.quadrant] || QUADRANT_COLORS.all

  return (
    <div style={{
      background: `linear-gradient(135deg, ${qc.bg}dd, #0f172add)`,
      border: `1px solid ${qc.border}40`,
      borderRadius: '12px',
      overflow: 'hidden',
      transition: 'all 0.3s',
      animation: `fadeSlideIn 0.4s ease-out ${index * 0.06}s both`,
    }}>
      {/* Header */}
      <button onClick={onToggle} style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: '0.75rem',
        padding: '0.85rem 1rem', background: 'none', border: 'none',
        cursor: 'pointer', color: '#e2e8f0', textAlign: 'left',
      }}>
        <div style={{
          width: 34, height: 34, borderRadius: '10px',
          background: `${qc.border}20`, border: `1px solid ${qc.border}50`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <Icon size={16} color={qc.accent} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{trace.agent_role}</span>
            <span style={{
              fontSize: '0.6rem', padding: '2px 6px', borderRadius: '4px',
              background: `${qc.border}20`, color: qc.accent, fontWeight: 500,
            }}>
              {qc.label}
            </span>
          </div>
          <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: 2 }}>
            Stage {trace.stage} &middot; {trace.reasoning_steps.length} steps &middot; {trace.duration_ms}ms
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {trace.sign_off ? (
            <CheckCircle2 size={16} color="#4ade80" />
          ) : (
            <AlertTriangle size={16} color="#fbbf24" />
          )}
          {isExpanded ? <ChevronUp size={14} color="#64748b" /> : <ChevronDown size={14} color="#64748b" />}
        </div>
      </button>

      {/* Expanded Detail */}
      {isExpanded && (
        <div style={{ padding: '0 1rem 1rem', borderTop: `1px solid ${qc.border}20` }}>
          {/* Reasoning Steps */}
          <div style={{ marginTop: '0.75rem' }}>
            {trace.reasoning_steps.map((step, si) => (
              <div key={si} style={{
                display: 'flex', gap: '0.75rem', padding: '0.5rem 0',
                borderBottom: si < trace.reasoning_steps.length - 1 ? '1px solid #1e293b' : 'none',
              }}>
                <div style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
                  minWidth: 28,
                }}>
                  <div style={{
                    width: 24, height: 24, borderRadius: '50%',
                    background: step.status === 'completed' ? '#4ade8020' : '#fbbf2420',
                    border: `1px solid ${step.status === 'completed' ? '#4ade80' : '#fbbf24'}50`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '0.65rem', fontWeight: 700, color: step.status === 'completed' ? '#4ade80' : '#fbbf24',
                  }}>
                    {step.step_id}
                  </div>
                  {si < trace.reasoning_steps.length - 1 && (
                    <div style={{ width: 1, flex: 1, background: '#334155' }} />
                  )}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{
                      fontSize: '0.65rem', fontWeight: 600, textTransform: 'uppercase',
                      color: qc.accent, letterSpacing: '0.05em',
                    }}>
                      {step.action}
                    </span>
                    <span style={{
                      fontSize: '0.6rem', color: '#64748b',
                    }}>
                      {step.confidence > 0 ? `${(step.confidence * 100).toFixed(0)}% conf` : ''}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#cbd5e1', marginTop: 2 }}>
                    {step.description}
                  </div>
                  {step.output_data && Object.keys(step.output_data).length > 0 && (
                    <div style={{
                      marginTop: 6, padding: '6px 10px', borderRadius: '6px',
                      background: '#0f172a80', fontSize: '0.7rem', color: '#94a3b8',
                      fontFamily: 'monospace',
                    }}>
                      {Object.entries(step.output_data).slice(0, 4).map(([k, v]) => (
                        <div key={k}>
                          <span style={{ color: '#64748b' }}>{k}:</span>{' '}
                          <span style={{ color: '#e2e8f0' }}>
                            {typeof v === 'object' ? JSON.stringify(v).slice(0, 80) : String(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Conclusion */}
          {trace.conclusion && (
            <div style={{
              marginTop: '0.75rem', padding: '0.6rem 0.8rem', borderRadius: '8px',
              background: `${qc.border}10`, border: `1px solid ${qc.border}30`,
              fontSize: '0.78rem', color: qc.text,
            }}>
              <strong>Conclusion:</strong> {trace.conclusion}
            </div>
          )}

          {/* Key Findings */}
          {trace.key_findings?.length > 0 && (
            <div style={{ marginTop: '0.5rem' }}>
              {trace.key_findings.map((f, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'start', gap: '0.4rem',
                  fontSize: '0.72rem', color: '#94a3b8', padding: '2px 0',
                }}>
                  <CircleDot size={10} color={qc.accent} style={{ marginTop: 3, flexShrink: 0 }} />
                  {f}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}


function CrossSiloView({ crossSilo }) {
  const quads = crossSilo.quadrant_contributions || {}
  const total = crossSilo.unified_savings || 0
  const npv = crossSilo.unified_npv || 0

  return (
    <div style={{
      background: 'linear-gradient(135deg, #0f172a, #1a1a2e)',
      border: '1px solid #334155',
      borderRadius: '16px', padding: '1.25rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <Network size={18} color="#a78bfa" />
        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#e2e8f0' }}>
          Cross-Silo Consolidation
        </span>
      </div>

      {/* Totals Bar */}
      <div style={{
        display: 'flex', gap: '1rem', marginBottom: '1.25rem',
        padding: '0.75rem 1rem', borderRadius: '10px',
        background: 'linear-gradient(90deg, #4f46e520, #7c3aed20)',
        border: '1px solid #6366f130',
      }}>
        <div>
          <div style={{ fontSize: '0.65rem', color: '#94a3b8', textTransform: 'uppercase' }}>Unified Savings</div>
          <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#e2e8f0' }}>${total.toLocaleString()}<span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>/yr</span></div>
        </div>
        <div style={{ borderLeft: '1px solid #334155', paddingLeft: '1rem' }}>
          <div style={{ fontSize: '0.65rem', color: '#94a3b8', textTransform: 'uppercase' }}>NPV (5yr)</div>
          <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#e2e8f0' }}>${npv.toLocaleString()}</div>
        </div>
      </div>

      {/* Quadrant Contribution Bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {['Q1', 'Q2', 'Q3', 'Q4'].map(q => {
          const data = quads[q] || { total_savings: 0, pct_of_total: 0, line_count: 0, cost_type: '' }
          const qc = QUADRANT_COLORS[q]
          return (
            <div key={q}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <div style={{
                    width: 8, height: 8, borderRadius: '50%', background: qc.accent,
                  }} />
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: qc.text }}>
                    {q} — {qc.label}
                  </span>
                  <span style={{ fontSize: '0.65rem', color: '#64748b' }}>
                    {data.line_count} lines
                  </span>
                </div>
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: qc.accent }}>
                  ${data.total_savings?.toLocaleString() || 0}
                </span>
              </div>
              <div style={{
                height: 8, borderRadius: 4, background: '#1e293b',
                overflow: 'hidden',
              }}>
                <div style={{
                  height: '100%', borderRadius: 4,
                  width: `${Math.min(data.pct_of_total || 0, 100)}%`,
                  background: `linear-gradient(90deg, ${qc.border}, ${qc.accent})`,
                  transition: 'width 1s ease-out',
                }} />
              </div>
            </div>
          )
        })}
      </div>

      {/* Overlap Adjustments */}
      {(crossSilo.overlap_adjustments?.length > 0) && (
        <div style={{
          marginTop: '1rem', padding: '0.6rem 0.8rem', borderRadius: '8px',
          background: '#fbbf2410', border: '1px solid #fbbf2430',
          fontSize: '0.72rem', color: '#fde68a',
        }}>
          <strong>{crossSilo.overlap_adjustments.length}</strong> anti-double-counting adjustments applied across quadrants
        </div>
      )}
    </div>
  )
}


function RecommendationCard({ rec, index }) {
  const cat = CATEGORY_STYLES[rec.category] || CATEGORY_STYLES.structural
  const CatIcon = cat.icon
  const qc = QUADRANT_COLORS[rec.quadrant] || QUADRANT_COLORS.all

  return (
    <div style={{
      background: 'linear-gradient(135deg, #0f172a, #1e1b4b20)',
      border: `1px solid ${cat.color}30`,
      borderLeft: `3px solid ${cat.color}`,
      borderRadius: '12px', padding: '1rem',
      animation: `fadeSlideIn 0.5s ease-out ${index * 0.1}s both`,
    }}>
      <div style={{ display: 'flex', alignItems: 'start', gap: '0.75rem' }}>
        {/* Priority Badge */}
        <div style={{
          width: 36, height: 36, borderRadius: '10px',
          background: `${cat.color}20`, border: `1px solid ${cat.color}40`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '0.9rem', fontWeight: 800, color: cat.color,
          flexShrink: 0,
        }}>
          P{rec.priority}
        </div>

        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700, fontSize: '0.88rem', color: '#e2e8f0' }}>
              {rec.title}
            </span>
            <span style={{
              fontSize: '0.6rem', padding: '2px 8px', borderRadius: '10px',
              background: `${cat.color}20`, color: cat.color, fontWeight: 600,
            }}>
              <CatIcon size={10} style={{ verticalAlign: 'middle', marginRight: 3 }} />
              {cat.label}
            </span>
            <span style={{
              fontSize: '0.6rem', padding: '2px 8px', borderRadius: '10px',
              background: `${qc.border}20`, color: qc.accent, fontWeight: 500,
            }}>
              {rec.quadrant}
            </span>
          </div>

          {/* Metrics row */}
          <div style={{ display: 'flex', gap: '1.25rem', margin: '0.6rem 0', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: '0.6rem', color: '#64748b', textTransform: 'uppercase' }}>Annual Savings</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#4ade80' }}>
                ${rec.savings_annual.toLocaleString()}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.6rem', color: '#64748b', textTransform: 'uppercase' }}>Confidence</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: rec.confidence >= 0.7 ? '#60a5fa' : '#fbbf24' }}>
                {(rec.confidence * 100).toFixed(0)}%
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.6rem', color: '#64748b', textTransform: 'uppercase' }}>Timeline</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <Clock size={12} color="#94a3b8" />
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0' }}>
                  {rec.implementation_horizon}
                </span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.6rem', color: '#64748b', textTransform: 'uppercase' }}>Owner</div>
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0' }}>
                {rec.owner || 'Unassigned'}
              </div>
            </div>
          </div>

          {/* Rationale */}
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', lineHeight: 1.4 }}>
            {rec.rationale}
          </div>

          {/* Cross-Silo Impact */}
          {rec.cross_silo_impact?.length > 0 && (
            <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
              {rec.cross_silo_impact.map((c, i) => (
                <span key={i} style={{
                  fontSize: '0.65rem', padding: '3px 8px', borderRadius: '6px',
                  background: '#6366f115', color: '#a5b4fc', border: '1px solid #6366f130',
                }}>
                  ↗ {c}
                </span>
              ))}
            </div>
          )}

          {/* Risk of Deferral */}
          {rec.risk_if_deferred && (
            <div style={{
              marginTop: '0.5rem', padding: '0.4rem 0.6rem', borderRadius: '6px',
              background: '#ef444410', border: '1px solid #ef444425',
              fontSize: '0.7rem', color: '#fca5a5', display: 'flex', alignItems: 'center', gap: '0.4rem',
            }}>
              <AlertTriangle size={12} /> Risk if deferred: {rec.risk_if_deferred}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


function NarrativePanel({ narrative }) {
  const [expanded, setExpanded] = useState(false)
  if (!narrative) return null

  const lines = narrative.split('\n').filter(l => l.trim())
  const preview = lines.slice(0, 3).join('\n')

  return (
    <div style={{
      background: 'linear-gradient(135deg, #0f172a, #1a1a2e)',
      border: '1px solid #334155', borderRadius: '12px', padding: '1rem',
    }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', marginBottom: '0.5rem' }}
        onClick={() => setExpanded(!expanded)}
      >
        <FileText size={16} color="#a78bfa" />
        <span style={{ fontWeight: 700, fontSize: '0.88rem', color: '#e2e8f0' }}>Board Narrative</span>
        <span style={{ fontSize: '0.65rem', color: '#64748b', marginLeft: 'auto' }}>
          {expanded ? 'Collapse' : 'Expand'}
        </span>
        {expanded ? <ChevronUp size={14} color="#64748b" /> : <ChevronDown size={14} color="#64748b" />}
      </div>
      <div style={{
        fontSize: '0.78rem', color: '#cbd5e1', lineHeight: 1.6,
        whiteSpace: 'pre-wrap', maxHeight: expanded ? 'none' : '4.5em',
        overflow: 'hidden', transition: 'max-height 0.3s',
      }}>
        {expanded ? narrative : preview + '...'}
      </div>
    </div>
  )
}


function ParetoOptions({ options, recommendedId }) {
  if (!options?.length) return null

  return (
    <div style={{
      background: 'linear-gradient(135deg, #0f172a, #1a1a2e)',
      border: '1px solid #334155', borderRadius: '12px', padding: '1rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
        <Target size={16} color="#fbbf24" />
        <span style={{ fontWeight: 700, fontSize: '0.88rem', color: '#e2e8f0' }}>
          Pareto-Optimal Options
        </span>
      </div>
      <div style={{ display: 'flex', gap: '0.75rem', overflowX: 'auto', paddingBottom: 4 }}>
        {options.map((opt, i) => {
          const isRec = opt.option_id === recommendedId
          return (
            <div key={i} style={{
              minWidth: 180, padding: '0.75rem', borderRadius: '10px',
              background: isRec ? '#4f46e520' : '#1e293b',
              border: `1px solid ${isRec ? '#6366f1' : '#334155'}`,
              flexShrink: 0,
            }}>
              {isRec && (
                <div style={{
                  fontSize: '0.6rem', color: '#a5b4fc', fontWeight: 700,
                  textTransform: 'uppercase', marginBottom: 4,
                }}>
                  ★ Recommended
                </div>
              )}
              <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#e2e8f0' }}>
                {opt.label || `Option ${i + 1}`}
              </div>
              <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
                <div>
                  <div style={{ fontSize: '0.6rem', color: '#64748b' }}>NPV</div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#4ade80' }}>
                    ${(opt.npv || 0).toLocaleString()}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '0.6rem', color: '#64748b' }}>Risk</div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: (opt.risk_score || 0) > 0.5 ? '#f87171' : '#fbbf24' }}>
                    {((opt.risk_score || 0) * 100).toFixed(0)}%
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}


function ExecutionSummary({ result }) {
  return (
    <div style={{
      display: 'flex', gap: '1rem', flexWrap: 'wrap',
      padding: '0.75rem 1rem', borderRadius: '10px',
      background: '#0f172a', border: '1px solid #334155',
      fontSize: '0.72rem', color: '#94a3b8',
    }}>
      <span><Activity size={12} style={{ verticalAlign: 'middle' }} /> {result.agent_traces?.length || 0} agents executed</span>
      <span>|</span>
      <span>{result.recommendations?.length || 0} recommendations</span>
      <span>|</span>
      <span>{result.pareto_options?.length || 0} Pareto options</span>
      <span>|</span>
      <span><Clock size={12} style={{ verticalAlign: 'middle' }} /> {result.execution_time_ms?.toFixed(0) || 0}ms</span>
      <span>|</span>
      <span>Quadrant validation: {result.quadrant_validation?.passed ? '✅ passed' : '⚠️ issues'}</span>
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════

export default function AgentReasoningConsole({ embedded = false }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expandedAgents, setExpandedAgents] = useState({})
  const [activeTab, setActiveTab] = useState('traces')

  const handleRun = useCallback(async (scopeType, scopeId) => {
    setLoading(true)
    setError(null)
    setResult(null)
    setExpandedAgents({})
    try {
      const resp = await fetch(`${API_BASE}/agent-advisor`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope_type: scopeType, scope_id: scopeId }),
      })
      if (!resp.ok) throw new Error(`API error: ${resp.status}`)
      const data = await resp.json()
      setResult(data)
      setActiveTab('traces')
      // Auto-expand first agent in each group
      const autoExpand = {}
      const seen = new Set()
      for (const t of data.agent_traces || []) {
        if (!seen.has(t.group)) {
          autoExpand[t.agent_id] = true
          seen.add(t.group)
        }
      }
      setExpandedAgents(autoExpand)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const toggleAgent = (agentId) => {
    setExpandedAgents(prev => ({ ...prev, [agentId]: !prev[agentId] }))
  }

  const tabs = [
    { id: 'traces', label: 'Agent Reasoning', icon: Cpu },
    { id: 'comms', label: 'Agent Comms', icon: MessageSquare },
    { id: 'cross-silo', label: 'Cross-Silo View', icon: Network },
    { id: 'recommendations', label: 'Recommendations', icon: Target },
    { id: 'narrative', label: 'Board Narrative', icon: FileText },
  ]

  return (
    <div style={embedded ? {} : { padding: '1.5rem', maxWidth: 1100, margin: '0 auto' }}>
      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .spin { animation: spin 1s linear infinite; }
      `}</style>

      {/* Header + Scope Selector */}
      <ScopeSelector onRun={handleRun} loading={loading} embedded={embedded} />

      {/* Error */}
      {error && (
        <div style={{
          marginTop: '1rem', padding: '0.75rem 1rem', borderRadius: '10px',
          background: '#ef444420', border: '1px solid #ef444450',
          color: '#fca5a5', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.5rem',
        }}>
          <XCircle size={16} /> {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div style={{ marginTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Execution Summary */}
          <ExecutionSummary result={result} />

          {/* Tab Bar */}
          <div style={{
            display: 'flex', gap: '2px', background: '#1e293b',
            borderRadius: '10px', padding: '3px', border: '1px solid #334155',
          }}>
            {tabs.map(tab => {
              const TIcon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
                  flex: 1, padding: '0.55rem 0.75rem',
                  borderRadius: '8px', border: 'none', cursor: 'pointer',
                  background: isActive ? '#4f46e5' : 'transparent',
                  color: isActive ? '#fff' : '#94a3b8',
                  fontWeight: isActive ? 600 : 400, fontSize: '0.78rem',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem',
                  transition: 'all 0.2s',
                }}>
                  <TIcon size={14} />
                  {tab.label}
                </button>
              )
            })}
          </div>

          {/* Tab Content */}
          {activeTab === 'traces' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {GROUP_ORDER.map(group => {
                const GIcon = GROUP_ICONS[group]
                const groupTraces = (result.agent_traces || []).filter(t => t.group === group)
                if (!groupTraces.length) return null
                return (
                  <div key={group}>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: '0.5rem',
                      padding: '0.5rem 0', borderBottom: '1px solid #1e293b', marginBottom: '0.4rem',
                    }}>
                      <GIcon size={14} color="#a78bfa" />
                      <span style={{ fontWeight: 700, fontSize: '0.78rem', color: '#a78bfa', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        {GROUP_LABELS[group]}
                      </span>
                      <span style={{ fontSize: '0.65rem', color: '#64748b' }}>
                        Stage {groupTraces[0]?.stage}
                      </span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      {groupTraces.map((trace, i) => (
                        <AgentTraceCard
                          key={trace.agent_id}
                          trace={trace}
                          index={i}
                          isExpanded={!!expandedAgents[trace.agent_id]}
                          onToggle={() => toggleAgent(trace.agent_id)}
                        />
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {activeTab === 'cross-silo' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <CrossSiloView crossSilo={result.cross_silo || {}} />
              <ParetoOptions
                options={result.pareto_options}
                recommendedId={result.crew_output?.recommended_option_id}
              />
            </div>
          )}

          {activeTab === 'recommendations' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {(result.recommendations || []).length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                  No recommendations generated for this scope.
                </div>
              ) : (
                (result.recommendations || []).map((rec, i) => (
                  <RecommendationCard key={rec.rec_id || i} rec={rec} index={i} />
                ))
              )}
            </div>
          )}

          {activeTab === 'comms' && (
            <AgentCommsPanel
              messages={result.agent_messages || result.crew_output?.agent_messages || []}
              theme="dark"
              showPipelineFlow
            />
          )}

          {activeTab === 'narrative' && (
            <NarrativePanel narrative={result.board_narrative} />
          )}
        </div>
      )}

      {/* Empty State */}
      {!result && !loading && !error && (
        <div style={{
          marginTop: '3rem', textAlign: 'center', padding: '3rem 2rem',
          borderRadius: '16px', border: '1px dashed #334155',
        }}>
          <div style={{
            width: 64, height: 64, borderRadius: '50%', margin: '0 auto 1rem',
            background: 'linear-gradient(135deg, #6366f120, #8b5cf620)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Cpu size={28} color="#a78bfa" />
          </div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#e2e8f0', marginBottom: '0.5rem' }}>
            Select an Asset or Location to Begin
          </div>
          <div style={{ fontSize: '0.8rem', color: '#64748b', maxWidth: 500, margin: '0 auto', lineHeight: 1.5 }}>
            The 12-agent crew will analyze your selection across all four quadrants — FM/Opex, Finance/Capex,
            Compliance/Risk, and Strategic/ESG — then consolidate cross-silo insights into prioritized,
            ownership-aware recommendations.
          </div>
        </div>
      )}
    </div>
  )
}
