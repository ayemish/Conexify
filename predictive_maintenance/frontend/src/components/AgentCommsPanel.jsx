import React, { useState, useMemo } from 'react'
import {
  MessageSquare, ArrowRight, Filter, ChevronDown, ChevronUp,
  Users, BarChart3, Shield, Cpu, Zap, GitBranch, AlertTriangle,
  CheckCircle2, ArrowRightLeft, Send, Radio, Clock,
} from 'lucide-react'

// ═══════════════════════════════════════════════════════════════════
// Agent metadata
// ═══════════════════════════════════════════════════════════════════

const AGENT_META = {
  orchestrator:      { label: 'Orchestrator',           group: 'governance',   icon: Cpu,          color: '#059669' },
  fm:                { label: 'FM Operations',          group: 'stakeholder',  icon: Users,        color: '#2563eb' },
  finance:           { label: 'Finance',                group: 'stakeholder',  icon: Users,        color: '#2563eb' },
  compliance:        { label: 'Compliance',             group: 'stakeholder',  icon: Users,        color: '#2563eb' },
  ops:               { label: 'Operations',             group: 'stakeholder',  icon: Users,        color: '#2563eb' },
  esg:               { label: 'ESG/Sustainability',     group: 'stakeholder',  icon: Users,        color: '#2563eb' },
  opex_modeler:      { label: 'Opex Modeler',           group: 'dimension',    icon: BarChart3,    color: '#7c3aed' },
  capex_modeler:     { label: 'Capex Modeler',          group: 'dimension',    icon: BarChart3,    color: '#7c3aed' },
  risk_modeler:      { label: 'Risk Modeler',           group: 'dimension',    icon: BarChart3,    color: '#7c3aed' },
  strategic_modeler: { label: 'Strategic Modeler',      group: 'dimension',    icon: BarChart3,    color: '#7c3aed' },
  reconciler:        { label: 'Reconciler',             group: 'governance',   icon: Shield,       color: '#059669' },
  optimizer:         { label: 'Optimizer',              group: 'governance',   icon: Zap,          color: '#059669' },
  auditor:           { label: 'Audit Narrator',         group: 'governance',   icon: GitBranch,    color: '#059669' },
}

const MSG_TYPE_META = {
  stage_transition: { label: 'Stage',       color: '#6366f1', icon: Radio },
  delegation:       { label: 'Delegate',    color: '#2563eb', icon: Send },
  context_handoff:  { label: 'Handoff',     color: '#059669', icon: ArrowRightLeft },
  negotiation:      { label: 'Negotiate',   color: '#d97706', icon: AlertTriangle },
  sign_off:         { label: 'Sign-off',    color: '#16a34a', icon: CheckCircle2 },
  tool_call:        { label: 'Tool',        color: '#64748b', icon: Cpu },
}

const STAGE_LABELS = ['Ingest', 'Validate', 'Translate', 'Reconcile', 'Optimize']

const GROUP_COLORS = {
  stakeholder: '#2563eb',
  dimension:   '#7c3aed',
  governance:  '#059669',
}


// ═══════════════════════════════════════════════════════════════════
// Pipeline Flow Diagram
// ═══════════════════════════════════════════════════════════════════

function PipelineFlowDiagram({ messages, theme }) {
  const isDark = theme === 'dark'
  const stageCounts = useMemo(() => {
    const counts = [0, 0, 0, 0, 0]
    ;(messages || []).forEach(m => {
      if (m.stage >= 0 && m.stage <= 4) counts[m.stage]++
    })
    return counts
  }, [messages])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 0,
      padding: '16px 12px', overflowX: 'auto',
    }}>
      {STAGE_LABELS.map((label, i) => {
        const count = stageCounts[i]
        const isActive = count > 0
        return (
          <React.Fragment key={i}>
            {i > 0 && (
              <div style={{
                flex: '0 0 auto', display: 'flex', alignItems: 'center',
                padding: '0 2px',
              }}>
                <ArrowRight size={16} color={isDark ? '#475569' : '#94a3b8'} />
              </div>
            )}
            <div style={{
              flex: '1 1 0', minWidth: 100, maxWidth: 160,
              padding: '10px 12px', borderRadius: 10,
              background: isActive
                ? (isDark ? 'rgba(99,102,241,0.15)' : '#eff6ff')
                : (isDark ? 'rgba(30,41,59,0.5)' : '#f8fafc'),
              border: `1px solid ${isActive
                ? (isDark ? 'rgba(99,102,241,0.35)' : '#bfdbfe')
                : (isDark ? '#334155' : '#e2e8f0')}`,
              textAlign: 'center', transition: 'all 0.2s',
            }}>
              <div style={{
                fontSize: '0.62rem', fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: isActive
                  ? (isDark ? '#818cf8' : '#3b82f6')
                  : (isDark ? '#64748b' : '#94a3b8'),
                marginBottom: 4,
              }}>
                Stage {i}
              </div>
              <div style={{
                fontSize: '0.82rem', fontWeight: 700,
                color: isDark ? '#e2e8f0' : '#0f172a',
              }}>
                {label}
              </div>
              <div style={{
                fontSize: '0.68rem', marginTop: 4,
                color: isDark ? '#94a3b8' : '#64748b',
              }}>
                {count} message{count !== 1 ? 's' : ''}
              </div>
            </div>
          </React.Fragment>
        )
      })}
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Agent Badge
// ═══════════════════════════════════════════════════════════════════

function AgentBadge({ agentId, theme }) {
  const isDark = theme === 'dark'
  const meta = AGENT_META[agentId]
  if (!meta) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: '2px 8px', borderRadius: 6, fontSize: '0.7rem', fontWeight: 600,
        background: isDark ? '#1e293b' : '#f1f5f9',
        color: isDark ? '#94a3b8' : '#64748b',
      }}>
        {agentId}
      </span>
    )
  }
  const Icon = meta.icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 6, fontSize: '0.7rem', fontWeight: 600,
      background: `${meta.color}${isDark ? '20' : '12'}`,
      color: meta.color,
      border: `1px solid ${meta.color}${isDark ? '30' : '20'}`,
    }}>
      <Icon size={11} />
      {meta.label}
    </span>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Message Type Pill
// ═══════════════════════════════════════════════════════════════════

function TypePill({ type, theme }) {
  const isDark = theme === 'dark'
  const meta = MSG_TYPE_META[type] || { label: type, color: '#64748b', icon: MessageSquare }
  const Icon = meta.icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      padding: '1px 7px', borderRadius: 4, fontSize: '0.62rem',
      fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em',
      background: `${meta.color}${isDark ? '20' : '12'}`,
      color: meta.color,
    }}>
      <Icon size={10} />
      {meta.label}
    </span>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Message Bubble
// ═══════════════════════════════════════════════════════════════════

function MessageBubble({ msg, index, theme }) {
  const isDark = theme === 'dark'
  const [expanded, setExpanded] = useState(false)
  const hasData = msg.data_summary && Object.keys(msg.data_summary).length > 0

  const isNegotiation = msg.message_type === 'negotiation'
  const isSignOff = msg.message_type === 'sign_off'

  let borderColor = isDark ? '#334155' : '#e2e8f0'
  let bgColor = isDark ? 'rgba(15,23,42,0.6)' : '#fff'
  if (isNegotiation) {
    borderColor = isDark ? 'rgba(217,119,6,0.35)' : '#fde68a'
    bgColor = isDark ? 'rgba(217,119,6,0.06)' : '#fffbeb'
  } else if (isSignOff) {
    const signed = msg.data_summary?.signed_off
    borderColor = signed
      ? (isDark ? 'rgba(22,163,74,0.35)' : '#bbf7d0')
      : (isDark ? 'rgba(220,38,38,0.35)' : '#fecaca')
    bgColor = signed
      ? (isDark ? 'rgba(22,163,74,0.06)' : '#f0fdf4')
      : (isDark ? 'rgba(220,38,38,0.06)' : '#fef2f2')
  }

  return (
    <div style={{
      display: 'flex', gap: '10px', padding: '10px 0',
      borderBottom: `1px solid ${isDark ? '#1e293b' : '#f1f5f9'}`,
      animation: `fadeSlideIn 0.3s ease-out ${index * 0.03}s both`,
    }}>
      {/* Sequence number */}
      <div style={{
        width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '0.62rem', fontWeight: 700,
        background: isDark ? '#1e293b' : '#f1f5f9',
        color: isDark ? '#64748b' : '#94a3b8',
        border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
        marginTop: 2,
      }}>
        {index + 1}
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Header row: sender → receiver + type pill */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          flexWrap: 'wrap', marginBottom: 4,
        }}>
          <AgentBadge agentId={msg.sender} theme={theme} />
          <ArrowRight size={12} color={isDark ? '#475569' : '#94a3b8'} />
          <AgentBadge agentId={msg.receiver} theme={theme} />
          <TypePill type={msg.message_type} theme={theme} />
          <span style={{
            fontSize: '0.6rem', color: isDark ? '#475569' : '#94a3b8',
            marginLeft: 'auto', flexShrink: 0,
          }}>
            S{msg.stage}
          </span>
        </div>

        {/* Message content */}
        <div style={{
          padding: '8px 12px', borderRadius: 8,
          background: bgColor,
          border: `1px solid ${borderColor}`,
          fontSize: '0.78rem', lineHeight: 1.5,
          color: isDark ? '#cbd5e1' : '#334155',
        }}>
          {msg.content}

          {/* Expandable data payload */}
          {hasData && (
            <div style={{ marginTop: 6 }}>
              <button
                onClick={() => setExpanded(!expanded)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  background: 'none', border: 'none', padding: 0,
                  cursor: 'pointer', fontSize: '0.68rem', fontWeight: 600,
                  color: isDark ? '#818cf8' : '#3b82f6',
                }}
              >
                {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                {expanded ? 'Hide' : 'Show'} data
              </button>
              {expanded && (
                <div style={{
                  marginTop: 6, padding: '6px 10px', borderRadius: 6,
                  background: isDark ? '#0f172a' : '#f8fafc',
                  border: `1px solid ${isDark ? '#1e293b' : '#e2e8f0'}`,
                  fontSize: '0.7rem', fontFamily: 'monospace',
                  color: isDark ? '#94a3b8' : '#475569',
                  overflowX: 'auto',
                }}>
                  {Object.entries(msg.data_summary).map(([k, v]) => (
                    <div key={k} style={{ padding: '1px 0' }}>
                      <span style={{ color: isDark ? '#64748b' : '#94a3b8' }}>{k}:</span>{' '}
                      <span style={{ color: isDark ? '#e2e8f0' : '#0f172a' }}>
                        {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Filter Bar
// ═══════════════════════════════════════════════════════════════════

function FilterBar({ filters, onChange, theme }) {
  const isDark = theme === 'dark'

  const pillStyle = (active) => ({
    padding: '4px 10px', borderRadius: 6,
    fontSize: '0.7rem', fontWeight: active ? 700 : 500,
    cursor: 'pointer', transition: 'all 0.15s',
    background: active
      ? (isDark ? 'rgba(99,102,241,0.2)' : '#eff6ff')
      : (isDark ? '#1e293b' : '#f8fafc'),
    color: active
      ? (isDark ? '#818cf8' : '#2563eb')
      : (isDark ? '#64748b' : '#94a3b8'),
    border: `1px solid ${active
      ? (isDark ? 'rgba(99,102,241,0.3)' : '#bfdbfe')
      : (isDark ? '#334155' : '#e2e8f0')}`,
  })

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
      padding: '8px 0',
    }}>
      <Filter size={13} color={isDark ? '#64748b' : '#94a3b8'} />

      {/* Stage filters */}
      <span style={{ fontSize: '0.65rem', fontWeight: 600, color: isDark ? '#475569' : '#94a3b8', textTransform: 'uppercase' }}>Stage:</span>
      {STAGE_LABELS.map((label, i) => (
        <button
          key={`s${i}`}
          onClick={() => onChange({ ...filters, stage: filters.stage === i ? null : i })}
          style={pillStyle(filters.stage === i)}
        >
          {i}: {label}
        </button>
      ))}

      <span style={{ width: 1, height: 16, background: isDark ? '#334155' : '#e2e8f0' }} />

      {/* Type filters */}
      <span style={{ fontSize: '0.65rem', fontWeight: 600, color: isDark ? '#475569' : '#94a3b8', textTransform: 'uppercase' }}>Type:</span>
      {Object.entries(MSG_TYPE_META).map(([type, meta]) => (
        <button
          key={type}
          onClick={() => onChange({ ...filters, type: filters.type === type ? null : type })}
          style={pillStyle(filters.type === type)}
        >
          {meta.label}
        </button>
      ))}

      <span style={{ width: 1, height: 16, background: isDark ? '#334155' : '#e2e8f0' }} />

      {/* Group filters */}
      <span style={{ fontSize: '0.65rem', fontWeight: 600, color: isDark ? '#475569' : '#94a3b8', textTransform: 'uppercase' }}>Group:</span>
      {Object.entries(GROUP_COLORS).map(([group, color]) => (
        <button
          key={group}
          onClick={() => onChange({ ...filters, group: filters.group === group ? null : group })}
          style={{
            ...pillStyle(filters.group === group),
            color: filters.group === group ? color : (isDark ? '#64748b' : '#94a3b8'),
            borderColor: filters.group === group ? `${color}40` : (isDark ? '#334155' : '#e2e8f0'),
            background: filters.group === group ? `${color}15` : (isDark ? '#1e293b' : '#f8fafc'),
          }}
        >
          {group.charAt(0).toUpperCase() + group.slice(1)}
        </button>
      ))}
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════
// Main AgentCommsPanel
// ═══════════════════════════════════════════════════════════════════

export default function AgentCommsPanel({ messages = [], theme = 'light', showPipelineFlow = true }) {
  const [filters, setFilters] = useState({ stage: null, type: null, group: null })
  const isDark = theme === 'dark'

  const filtered = useMemo(() => {
    let msgs = messages || []
    if (filters.stage !== null) {
      msgs = msgs.filter(m => m.stage === filters.stage)
    }
    if (filters.type) {
      msgs = msgs.filter(m => m.message_type === filters.type)
    }
    if (filters.group) {
      msgs = msgs.filter(m => {
        const senderMeta = AGENT_META[m.sender]
        const receiverMeta = AGENT_META[m.receiver]
        return (senderMeta?.group === filters.group) || (receiverMeta?.group === filters.group)
      })
    }
    return msgs
  }, [messages, filters])

  const hasActiveFilters = filters.stage !== null || filters.type || filters.group

  if (!messages || messages.length === 0) {
    return (
      <div style={{
        textAlign: 'center', padding: '2rem',
        color: isDark ? '#64748b' : '#94a3b8',
        fontSize: '0.85rem',
      }}>
        <MessageSquare size={32} style={{ marginBottom: 8, opacity: 0.4 }} />
        <div>No agent messages available. Run the pipeline to see inter-agent communication.</div>
      </div>
    )
  }

  return (
    <div>
      {/* Pipeline Flow Diagram */}
      {showPipelineFlow && (
        <div style={{
          marginBottom: 12, borderRadius: 10,
          background: isDark ? 'rgba(15,23,42,0.5)' : '#f8fafc',
          border: `1px solid ${isDark ? '#1e293b' : '#e2e8f0'}`,
        }}>
          <PipelineFlowDiagram messages={messages} theme={theme} />
        </div>
      )}

      {/* Stats bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 16,
        padding: '8px 0', marginBottom: 4,
        fontSize: '0.72rem', color: isDark ? '#94a3b8' : '#64748b',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <MessageSquare size={13} />
          <strong style={{ color: isDark ? '#e2e8f0' : '#0f172a' }}>{messages.length}</strong> messages
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Users size={13} />
          <strong style={{ color: isDark ? '#e2e8f0' : '#0f172a' }}>
            {new Set(messages.map(m => m.sender)).size}
          </strong> agents active
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Clock size={13} />
          Stages 0–4
        </div>
        {hasActiveFilters && (
          <button
            onClick={() => setFilters({ stage: null, type: null, group: null })}
            style={{
              marginLeft: 'auto', padding: '3px 10px', borderRadius: 6,
              background: isDark ? '#1e293b' : '#f1f5f9',
              border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
              color: isDark ? '#94a3b8' : '#64748b',
              fontSize: '0.68rem', cursor: 'pointer',
            }}
          >
            Clear filters ({filtered.length}/{messages.length})
          </button>
        )}
      </div>

      {/* Filter bar */}
      <FilterBar filters={filters} onChange={setFilters} theme={theme} />

      {/* Message timeline */}
      <div style={{
        marginTop: 8, maxHeight: 600, overflowY: 'auto',
        paddingRight: 4,
      }}>
        {filtered.map((msg, i) => (
          <MessageBubble key={msg.message_id || i} msg={msg} index={i} theme={theme} />
        ))}
        {filtered.length === 0 && hasActiveFilters && (
          <div style={{
            textAlign: 'center', padding: '1.5rem',
            color: isDark ? '#64748b' : '#94a3b8',
            fontSize: '0.82rem',
          }}>
            No messages match the current filters.
          </div>
        )}
      </div>
    </div>
  )
}
