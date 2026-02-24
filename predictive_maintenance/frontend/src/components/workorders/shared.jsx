import { AlertTriangle, ArrowDownRight, ArrowUpRight, Brain, CircleDot, User, Zap } from 'lucide-react'

export const PRIORITY_COLORS = {
  critical: { bg: '#fef2f2', border: '#ef4444', text: '#991b1b', label: 'Critical' },
  high: { bg: '#fff7ed', border: '#f97316', text: '#9a3412', label: 'High' },
  medium: { bg: '#fefce8', border: '#eab308', text: '#854d0e', label: 'Medium' },
  low: { bg: '#f0fdf4', border: '#22c55e', text: '#166534', label: 'Low' },
}

export const WO_STATUSES = {
  draft: { color: '#94a3b8', label: 'Draft' },
  open: { color: '#3b82f6', label: 'Open' },
  assigned: { color: '#8b5cf6', label: 'Assigned' },
  in_progress: { color: '#f59e0b', label: 'In Progress' },
  pending_approval: { color: '#ec4899', label: 'Pending Approval' },
  completed: { color: '#22c55e', label: 'Completed' },
  verified: { color: '#059669', label: 'Verified' },
  reopened: { color: '#ef4444', label: 'Reopened' },
}

export function PriorityBadge({ priority }) {
  const cfg = PRIORITY_COLORS[priority] || PRIORITY_COLORS.medium
  return (
    <span className="wo-priority-badge" style={{ background: cfg.bg, borderColor: cfg.border, color: cfg.text }}>
      {cfg.label}
    </span>
  )
}

export function StatusBadge({ status }) {
  const cfg = WO_STATUSES[status] || WO_STATUSES.open
  return (
    <span className="wo-status-badge" style={{ background: `${cfg.color}15`, color: cfg.color }}>
      <CircleDot size={10} /> {cfg.label}
    </span>
  )
}

export function SourceBadge({ source }) {
  const map = {
    ai_sensor: { icon: Zap, label: 'PdM Sensor', color: '#8b5cf6' },
    ai_nlp: { icon: Brain, label: 'AI / NLP', color: '#06b6d4' },
    manual: { icon: User, label: 'Manual', color: '#64748b' },
    pdm_alert: { icon: AlertTriangle, label: 'PdM Alert', color: '#f59e0b' },
  }
  const cfg = map[source] || map.manual
  const Icon = cfg.icon
  return (
    <span className="wo-source-badge" style={{ color: cfg.color }}>
      <Icon size={11} /> {cfg.label}
    </span>
  )
}

export function KpiCard({ icon: Icon, label, value, sub, color, trend }) {
  return (
    <div className="wo-kpi-card">
      <div className="wo-kpi-icon" style={{ background: `${color}12`, color }}><Icon size={20} /></div>
      <div className="wo-kpi-body">
        <div className="wo-kpi-value" style={{ color }}>{value}</div>
        <div className="wo-kpi-label">{label}</div>
        {sub && (
          <div className="wo-kpi-sub">
            {trend === 'up' ? <ArrowUpRight size={12} style={{ color: '#22c55e' }} /> : null}
            {trend === 'down' ? <ArrowDownRight size={12} style={{ color: '#ef4444' }} /> : null}
            {sub}
          </div>
        )}
      </div>
    </div>
  )
}
