import { useState, useEffect, useCallback } from 'react'
import {
  Layers, Shield, Users, CheckCircle, XCircle, AlertTriangle,
  ChevronDown, ChevronRight, Activity, Clock, Zap, Eye,
  ThumbsUp, ThumbsDown, Minus, RefreshCw
} from 'lucide-react'
import { safeRequest } from '../services/apiClient'

// ── Palette ──────────────────────────────────────────────────────────

const COLORS = {
  bg: '#0f172a', card: '#1e293b', border: '#334155',
  text: '#e2e8f0', muted: '#94a3b8', accent: '#3b82f6',
  green: '#22c55e', yellow: '#eab308', red: '#ef4444', orange: '#f97316',
  purple: '#a78bfa', cyan: '#06b6d4',
}

const LAYER_COLORS = {
  layer_0_context: '#06b6d4',
  layer_1_trust: '#8b5cf6',
  layer_2_behavior: '#3b82f6',
  layer_3_diagnosis: '#f97316',
  layer_4_decision: '#ef4444',
}

const OPINION_CONFIG = {
  strongly_agree: { icon: ThumbsUp, color: COLORS.green, label: 'Strongly Agree' },
  agree: { icon: ThumbsUp, color: '#4ade80', label: 'Agree' },
  neutral: { icon: Minus, color: COLORS.muted, label: 'Neutral' },
  disagree: { icon: ThumbsDown, color: COLORS.orange, label: 'Disagree' },
  strongly_disagree: { icon: ThumbsDown, color: COLORS.red, label: 'Strongly Disagree' },
}

const DISPOSITION_CONFIG = {
  auto_monitor: { color: COLORS.green, label: 'Auto Monitor', icon: Eye },
  auto_actionable: { color: COLORS.orange, label: 'Auto Actionable', icon: Zap },
  human_review_required: { color: COLORS.yellow, label: 'Human Review', icon: Users },
}


// ── Sub-components ───────────────────────────────────────────────────

function MetricCard({ label, value, sub, color }) {
  return (
    <div style={{ background: COLORS.card, borderRadius: 10, padding: '0.75rem 1rem', border: `1px solid ${COLORS.border}` }}>
      <div style={{ fontSize: '0.7rem', color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, color: color || COLORS.text, marginTop: 2 }}>{value}</div>
      {sub && <div style={{ fontSize: '0.7rem', color: COLORS.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function AgentNode({ agentId, role, weight, latestResult }) {
  const layerKey = Object.keys(LAYER_COLORS).find(k => {
    if (role === 'regime_detector') return k === 'layer_0_context'
    if (role === 'sensor_trust') return k === 'layer_1_trust'
    if (role === 'behavior_model' || role === 'change_detection') return k === 'layer_2_behavior'
    if (role === 'fault_hypothesis') return k === 'layer_3_diagnosis'
    if (role === 'decision_policy') return k === 'layer_4_decision'
    return false
  })
  const color = LAYER_COLORS[layerKey] || COLORS.accent

  return (
    <div style={{
      background: COLORS.card, borderRadius: 10, padding: '0.75rem 1rem',
      border: `1px solid ${color}40`, borderLeft: `3px solid ${color}`,
      minWidth: 160,
    }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color }}>{role.replace(/_/g, ' ')}</div>
      <div style={{ fontSize: '0.65rem', color: COLORS.muted, marginTop: 2 }}>{agentId}</div>
      {weight && <div style={{ fontSize: '0.65rem', color: COLORS.muted }}>Weight: {weight}×</div>}
    </div>
  )
}

function VoteCard({ vote }) {
  const cfg = OPINION_CONFIG[vote.opinion] || OPINION_CONFIG.neutral
  const Icon = cfg.icon

  return (
    <div style={{
      background: COLORS.card, borderRadius: 8, padding: '0.6rem 0.8rem',
      border: `1px solid ${COLORS.border}`, marginBottom: '0.4rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon size={14} style={{ color: cfg.color }} />
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: COLORS.text }}>
            {vote.agent_role.replace(/_/g, ' ')}
          </span>
          <span style={{
            fontSize: '0.6rem', padding: '1px 6px', borderRadius: 4,
            background: `${cfg.color}20`, color: cfg.color,
          }}>
            {cfg.label}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '0.7rem', color: COLORS.muted }}>
            conf: {(vote.confidence * 100).toFixed(0)}%
          </span>
          <span style={{ fontSize: '0.7rem', color: COLORS.muted }}>
            wt: {vote.weight}×
          </span>
        </div>
      </div>
      <div style={{ fontSize: '0.75rem', color: COLORS.muted, lineHeight: 1.4 }}>
        {vote.rationale}
      </div>
    </div>
  )
}

function GuardianMergeCard({ guardian }) {
  if (!guardian) return null
  const disp = DISPOSITION_CONFIG[guardian.disposition] || DISPOSITION_CONFIG.auto_monitor
  const DispIcon = disp.icon

  return (
    <div style={{
      background: `linear-gradient(135deg, ${COLORS.card} 0%, #1a2744 100%)`,
      borderRadius: 12, padding: '1rem 1.25rem',
      border: `1px solid ${disp.color}40`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: '0.75rem' }}>
        <Shield size={20} style={{ color: disp.color }} />
        <span style={{ fontSize: '0.95rem', fontWeight: 700, color: COLORS.text }}>Guardian Merge</span>
        <span style={{
          fontSize: '0.7rem', padding: '2px 8px', borderRadius: 6,
          background: `${disp.color}20`, color: disp.color, fontWeight: 600,
        }}>
          {disp.label}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
        <div>
          <div style={{ fontSize: '0.65rem', color: COLORS.muted }}>Final Alert Type</div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: COLORS.text }}>{guardian.final_alert_type}</div>
        </div>
        <div>
          <div style={{ fontSize: '0.65rem', color: COLORS.muted }}>Confidence</div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: COLORS.text }}>{(guardian.confidence * 100).toFixed(0)}%</div>
        </div>
        <div>
          <div style={{ fontSize: '0.65rem', color: COLORS.muted }}>False Alarm Prob</div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: COLORS.text }}>{(guardian.false_alarm_probability * 100).toFixed(0)}%</div>
        </div>
        <div>
          <div style={{ fontSize: '0.65rem', color: COLORS.muted }}>Advisories Used</div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: COLORS.text }}>{guardian.advisories_used?.length || 0}</div>
        </div>
      </div>

      {guardian.recommended_action && (
        <div style={{ fontSize: '0.8rem', color: COLORS.text, padding: '0.5rem', background: `${COLORS.bg}80`, borderRadius: 6, marginBottom: '0.5rem' }}>
          <strong>Action:</strong> {guardian.recommended_action}
        </div>
      )}

      {guardian.reasons?.length > 0 && (
        <div style={{ fontSize: '0.7rem', color: COLORS.muted }}>
          {guardian.reasons.map((r, i) => (
            <div key={i} style={{ padding: '2px 0' }}>• {r}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function KpiPipelineRow({ result, expanded, onToggle }) {
  const statusColor = result.status === 'completed' ? COLORS.green : result.status === 'failed' ? COLORS.red : COLORS.yellow
  const crewEntries = Object.entries(result.crew_statuses || {})
  const savings = result.total_savings_medium || 0

  return (
    <div style={{ marginBottom: '0.5rem' }}>
      <div
        onClick={onToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.75rem',
          padding: '0.6rem 0.8rem', borderRadius: expanded ? '10px 10px 0 0' : 10,
          background: COLORS.card, border: `1px solid ${COLORS.border}`,
          borderBottom: expanded ? 'none' : `1px solid ${COLORS.border}`,
          cursor: 'pointer', transition: 'background 0.1s',
        }}
      >
        {expanded ? <ChevronDown size={14} style={{ color: COLORS.muted }} /> : <ChevronRight size={14} style={{ color: COLORS.muted }} />}
        <span style={{ fontSize: '0.75rem', color: COLORS.muted, minWidth: 55 }}>
          {new Date(result.timestamp).toLocaleTimeString()}
        </span>
        <span style={{
          fontSize: '0.65rem', padding: '1px 6px', borderRadius: 4,
          background: `${statusColor}20`, color: statusColor, fontWeight: 600,
        }}>
          {result.status}
        </span>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: COLORS.accent }}>
          KPI Pipeline
        </span>
        <span style={{ fontSize: '0.75rem', color: COLORS.text }}>
          {result.kpi_count || crewEntries.length} KPIs
        </span>
        {savings > 0 && (
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: COLORS.green }}>
            ${Math.round(savings).toLocaleString()}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: '0.65rem', color: COLORS.muted }}>
          {result.duration_seconds ? `${result.duration_seconds.toFixed(1)}s` : `${result.processing_time_ms?.toFixed(0)}ms`}
        </span>
        <span style={{ fontSize: '0.65rem', color: COLORS.muted }}>
          {result.site_id}
        </span>
      </div>

      {expanded && (
        <div style={{
          padding: '1rem', background: COLORS.bg,
          border: `1px solid ${COLORS.border}`, borderTop: 'none',
          borderRadius: '0 0 10px 10px',
        }}>
          {/* Summary metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
            <div style={{ padding: '0.5rem', background: COLORS.card, borderRadius: 8, textAlign: 'center' }}>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: COLORS.accent }}>{result.kpi_count || crewEntries.length}</div>
              <div style={{ fontSize: '0.65rem', color: COLORS.muted }}>KPIs Computed</div>
            </div>
            <div style={{ padding: '0.5rem', background: COLORS.card, borderRadius: 8, textAlign: 'center' }}>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: COLORS.green }}>
                ${Math.round(savings).toLocaleString()}
              </div>
              <div style={{ fontSize: '0.65rem', color: COLORS.muted }}>Total Savings (Medium)</div>
            </div>
            <div style={{ padding: '0.5rem', background: COLORS.card, borderRadius: 8, textAlign: 'center' }}>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: COLORS.text }}>
                {result.duration_seconds ? `${result.duration_seconds.toFixed(2)}s` : '—'}
              </div>
              <div style={{ fontSize: '0.65rem', color: COLORS.muted }}>Duration</div>
            </div>
            <div style={{ padding: '0.5rem', background: COLORS.card, borderRadius: 8, textAlign: 'center' }}>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: statusColor }}>{result.phase || 'complete'}</div>
              <div style={{ fontSize: '0.65rem', color: COLORS.muted }}>Phase</div>
            </div>
          </div>

          {/* Crew statuses table */}
          {crewEntries.length > 0 && (
            <div>
              <h4 style={{ fontSize: '0.8rem', color: COLORS.accent, margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Activity size={14} /> KPI Crew Results
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.3rem' }}>
                {crewEntries.map(([name, info]) => (
                  <div key={name} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '0.35rem 0.6rem', background: COLORS.card, borderRadius: 6,
                    borderLeft: `3px solid ${info.status === 'completed' ? COLORS.green : COLORS.red}`,
                  }}>
                    <span style={{ fontSize: '0.75rem', color: COLORS.text }}>{name.replace(/_/g, ' ')}</span>
                    <span style={{
                      fontSize: '0.6rem', padding: '1px 5px', borderRadius: 4,
                      background: info.status === 'completed' ? `${COLORS.green}20` : `${COLORS.red}20`,
                      color: info.status === 'completed' ? COLORS.green : COLORS.red,
                    }}>
                      {info.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {result.error_message && (
            <div style={{
              marginTop: '0.75rem', padding: '0.5rem', borderRadius: 6,
              background: `${COLORS.red}10`, border: `1px solid ${COLORS.red}30`,
              fontSize: '0.75rem', color: COLORS.red,
            }}>
              {result.error_message}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ResultRow({ result, expanded, onToggle }) {
  const guardian = result.guardian_decision
  const disp = guardian ? (DISPOSITION_CONFIG[guardian.disposition] || DISPOSITION_CONFIG.auto_monitor) : null

  return (
    <div style={{ marginBottom: '0.5rem' }}>
      <div
        onClick={onToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.75rem',
          padding: '0.6rem 0.8rem', borderRadius: expanded ? '10px 10px 0 0' : 10,
          background: COLORS.card, border: `1px solid ${COLORS.border}`,
          borderBottom: expanded ? 'none' : `1px solid ${COLORS.border}`,
          cursor: 'pointer', transition: 'background 0.1s',
        }}
      >
        {expanded ? <ChevronDown size={14} style={{ color: COLORS.muted }} /> : <ChevronRight size={14} style={{ color: COLORS.muted }} />}
        <span style={{ fontSize: '0.75rem', color: COLORS.muted, minWidth: 55 }}>
          {new Date(result.timestamp).toLocaleTimeString()}
        </span>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: COLORS.text, minWidth: 70 }}>{result.asset_id}</span>

        {result.should_alert ? (
          <span style={{
            fontSize: '0.65rem', padding: '1px 6px', borderRadius: 4,
            background: `${COLORS.orange}20`, color: COLORS.orange, fontWeight: 600,
          }}>
            {result.alert_type}
          </span>
        ) : (
          <span style={{ fontSize: '0.65rem', padding: '1px 6px', borderRadius: 4, background: `${COLORS.green}20`, color: COLORS.green }}>
            no alert
          </span>
        )}

        <span style={{ fontSize: '0.7rem', color: COLORS.cyan }}>{result.regime}</span>

        {result.fault_hypothesis && (
          <span style={{ fontSize: '0.7rem', color: COLORS.orange }}>
            {result.fault_hypothesis} ({(result.fault_probability * 100).toFixed(0)}%)
          </span>
        )}

        <span style={{ marginLeft: 'auto', fontSize: '0.65rem', color: COLORS.muted }}>
          {result.processing_time_ms?.toFixed(0)}ms
        </span>

        {disp && (
          <span style={{
            fontSize: '0.6rem', padding: '1px 6px', borderRadius: 4,
            background: `${disp.color}20`, color: disp.color,
          }}>
            {disp.label}
          </span>
        )}
      </div>

      {expanded && (
        <div style={{
          padding: '1rem', background: COLORS.bg,
          border: `1px solid ${COLORS.border}`, borderTop: 'none',
          borderRadius: '0 0 10px 10px',
        }}>
          {/* Collaborative Decision */}
          {result.collaborative_decision && (
            <div style={{ marginBottom: '1rem' }}>
              <h4 style={{ fontSize: '0.8rem', color: COLORS.accent, margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Users size={14} /> Collaborative Vote
                {result.collaborative_decision.consensus_reached ? (
                  <CheckCircle size={12} style={{ color: COLORS.green }} />
                ) : (
                  <XCircle size={12} style={{ color: COLORS.red }} />
                )}
                <span style={{ fontSize: '0.65rem', color: COLORS.muted, fontWeight: 400 }}>
                  {result.collaborative_decision.consensus_reached ? 'Consensus' : 'No Consensus'} —
                  agg. confidence: {(result.collaborative_decision.aggregate_confidence * 100).toFixed(0)}% —
                  decision: {result.collaborative_decision.final_decision}
                </span>
              </h4>
              {result.collaborative_decision.votes?.map((v, i) => <VoteCard key={i} vote={v} />)}
            </div>
          )}

          {/* Guardian Merge */}
          <GuardianMergeCard guardian={result.guardian_decision} />

          {/* Recommendations & Concerns */}
          {(result.recommendations?.length > 0 || result.concerns?.length > 0) && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginTop: '0.75rem' }}>
              {result.recommendations?.length > 0 && (
                <div style={{ padding: '0.5rem', background: `${COLORS.green}10`, borderRadius: 8, border: `1px solid ${COLORS.green}30` }}>
                  <div style={{ fontSize: '0.7rem', fontWeight: 600, color: COLORS.green, marginBottom: 4 }}>Recommendations</div>
                  {result.recommendations.map((r, i) => (
                    <div key={i} style={{ fontSize: '0.7rem', color: COLORS.muted, padding: '1px 0' }}>• {r}</div>
                  ))}
                </div>
              )}
              {result.concerns?.length > 0 && (
                <div style={{ padding: '0.5rem', background: `${COLORS.yellow}10`, borderRadius: 8, border: `1px solid ${COLORS.yellow}30` }}>
                  <div style={{ fontSize: '0.7rem', fontWeight: 600, color: COLORS.yellow, marginBottom: 4 }}>Concerns</div>
                  {result.concerns.map((c, i) => (
                    <div key={i} style={{ fontSize: '0.7rem', color: COLORS.muted, padding: '1px 0' }}>• {c}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Pipeline Diagram ─────────────────────────────────────────────────

function PipelineDiagram({ agents, config }) {
  const layers = [
    { key: 'layer_0_context', label: 'L0: Regime', agents: ['regime_detector'] },
    { key: 'layer_1_trust', label: 'L1: Trust', agents: ['sensor_trust'] },
    { key: 'layer_2_behavior', label: 'L2: Behavior', agents: ['behavior_model', 'change_detection'] },
    { key: 'layer_3_diagnosis', label: 'L3: Diagnosis', agents: ['fault_hypothesis'] },
    { key: 'layer_4_decision', label: 'L4: Decision', agents: ['decision_policy'] },
  ]

  return (
    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start', overflowX: 'auto', padding: '0.5rem 0' }}>
      {layers.map((layer, li) => (
        <div key={layer.key} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            <div style={{
              fontSize: '0.6rem', fontWeight: 700, color: LAYER_COLORS[layer.key],
              textTransform: 'uppercase', letterSpacing: '0.05em', textAlign: 'center',
            }}>
              {layer.label}
            </div>
            {layer.agents.map(aid => {
              const a = agents?.[aid]
              const weight = config?.role_weights?.[a?.role || aid]
              return (
                <AgentNode
                  key={aid}
                  agentId={aid}
                  role={a?.role || aid}
                  weight={weight}
                  latestResult={a?.latest_result}
                />
              )
            })}
          </div>
          {li < layers.length - 1 && (
            <div style={{ color: COLORS.muted, fontSize: '1.2rem', padding: '0 0.25rem' }}>→</div>
          )}
        </div>
      ))}

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <div style={{ color: COLORS.muted, fontSize: '1.2rem', padding: '0 0.25rem' }}>→</div>
        <div style={{
          background: `linear-gradient(135deg, #1a2744 0%, ${COLORS.card} 100%)`,
          borderRadius: 10, padding: '0.75rem 1rem',
          border: `1px solid ${COLORS.yellow}40`, borderLeft: `3px solid ${COLORS.yellow}`,
          minWidth: 140,
        }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 700, color: COLORS.yellow, display: 'flex', alignItems: 'center', gap: 4 }}>
            <Shield size={14} /> Guardian Merge
          </div>
          <div style={{ fontSize: '0.6rem', color: COLORS.muted, marginTop: 4 }}>Monotonic safety</div>
        </div>
      </div>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────────

export default function OrchestrationVisibility() {
  const [data, setData] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState('all') // all | alerts | no_alerts

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [statusResult, historyResult] = await Promise.all([
        safeRequest('/api/v1/orchestration/status'),
        safeRequest('/api/v1/orchestration/history?limit=50'),
      ])

      const status = statusResult.data || { available: false, site_id: 'default', agents: {}, metrics: {}, config: {} }
      const history = historyResult.data || { results: [], total: 0 }
      setData({ status, history })
    } catch (e) {
      console.error('Orchestration data fetch failed:', e)
      setData({
        status: { available: false, site_id: 'default', agents: {}, metrics: {}, config: {} },
        history: { results: [], total: 0 },
      })
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (!data) return <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.muted }}>Loading orchestration data...</div>

  const { status, history } = data
  const metrics = status.metrics || {}
  const results = (history.results || []).filter(r => {
    if (filter === 'alerts') return r.should_alert
    if (filter === 'no_alerts') return !r.should_alert
    return true
  })

  return (
    <div style={{
      maxWidth: 1400, margin: '0 auto', padding: '1.5rem',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      color: COLORS.text, background: COLORS.bg, minHeight: '100vh',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0, color: COLORS.text }}>
          <Layers size={24} style={{ color: COLORS.accent }} /> Orchestration Visibility
        </h2>
        <button
          onClick={fetchData}
          disabled={loading}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0.4rem 0.8rem', borderRadius: 8, border: `1px solid ${COLORS.border}`,
            background: COLORS.card, color: COLORS.text, fontSize: '0.8rem', cursor: 'pointer',
          }}
        >
          <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      {/* Page Description */}
      <div style={{
        background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.2)',
        borderRadius: 10, padding: '10px 14px', fontSize: '0.78rem', color: '#c7d2fe',
        marginBottom: '1rem', lineHeight: 1.6,
      }}>
        <strong style={{ color: '#e0e7ff' }}>What this page does:</strong> Monitor the
        <strong> 5-layer agent orchestration pipeline</strong> in real time — readings processed,
        alerts dispatched, agent consensus scores, and processing latency. View decision trails
        for individual runs to audit how each agent layer contributed to the final recommendation.
      </div>

      {/* Metrics Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <MetricCard label="Readings Processed" value={metrics.total_processed || 0} color={COLORS.accent} />
        <MetricCard label="Alerts Today" value={metrics.alerts_today || 0} sub={`/ ${status.config?.max_alerts_per_day || 10} limit`} color={COLORS.orange} />
        <MetricCard label="Dispatches (Week)" value={metrics.dispatches_this_week || 0} sub={`/ ${status.config?.max_dispatches_per_week || 3} limit`} color={COLORS.red} />
        <MetricCard label="Agents" value={metrics.agents_count || 6} color={COLORS.purple} />
        <MetricCard label="Avg Latency" value={`${(metrics.avg_processing_time_ms || 0).toFixed(0)}ms`} color={COLORS.cyan} />
        <MetricCard label="Consensus Threshold" value={`${((status.config?.consensus_threshold || 0.6) * 100).toFixed(0)}%`} color={COLORS.green} />
      </div>

      {/* Pipeline Diagram */}
      <div style={{
        background: COLORS.card, borderRadius: 12, padding: '1rem 1.25rem',
        border: `1px solid ${COLORS.border}`, marginBottom: '1.5rem',
      }}>
        <h3 style={{ fontSize: '0.85rem', color: COLORS.muted, margin: '0 0 0.75rem', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Activity size={14} /> Agent Pipeline
        </h3>
        <PipelineDiagram agents={status.agents} config={status.config} />
      </div>

      {/* Decision History */}
      <div style={{
        background: COLORS.card, borderRadius: 12, padding: '1rem 1.25rem',
        border: `1px solid ${COLORS.border}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
          <h3 style={{ fontSize: '0.85rem', color: COLORS.muted, margin: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Clock size={14} /> Decision History
            <span style={{ fontSize: '0.7rem', color: COLORS.muted }}>({results.length} of {history.total})</span>
          </h3>
          <div style={{ display: 'flex', gap: '0.4rem' }}>
            {['all', 'alerts', 'no_alerts'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: '2px 8px', borderRadius: 6, border: `1px solid ${filter === f ? COLORS.accent : COLORS.border}`,
                  background: filter === f ? `${COLORS.accent}20` : 'transparent',
                  color: filter === f ? COLORS.accent : COLORS.muted,
                  fontSize: '0.7rem', cursor: 'pointer',
                }}
              >
                {f === 'all' ? 'All' : f === 'alerts' ? 'Alerts Only' : 'No Alerts'}
              </button>
            ))}
          </div>
        </div>

        {results.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.muted, fontSize: '0.85rem' }}>
            No orchestration results yet. Run a KPI pipeline or process telemetry to see decisions here.
          </div>
        ) : (
          results.map(r => {
            const isKpiPipeline = r.regime === 'kpi_pipeline' || r.kpi_count > 0
            const Row = isKpiPipeline ? KpiPipelineRow : ResultRow
            return (
              <Row
                key={r.result_id}
                result={r}
                expanded={expandedId === r.result_id}
                onToggle={() => setExpandedId(expandedId === r.result_id ? null : r.result_id)}
              />
            )
          })
        )}
      </div>
    </div>
  )
}
