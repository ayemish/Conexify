import { addDays, format, formatDistanceToNow } from 'date-fns'
import { AlertTriangle, ArrowRight, BarChart3, Bot, Brain, CheckCircle2, ClipboardList, DollarSign, Plus, TrendingUp } from 'lucide-react'

import { KpiCard, PriorityBadge, SourceBadge, StatusBadge } from './shared'

export default function DashboardView({ workOrders, onNavigate }) {
  const open = workOrders.filter((w) => ['open', 'assigned', 'in_progress', 'reopened'].includes(w.status))
  const critical = open.filter((w) => w.priority === 'critical' || w.priority === 'high')
  const pendingApproval = workOrders.filter((w) => w.status === 'pending_approval')
  const completed = workOrders.filter((w) => w.status === 'completed' || w.status === 'verified')
  const avgScore = open.length > 0 ? Math.round(open.reduce((sum, w) => sum + (w.ai_priority_score || 0), 0) / open.length) : 0
  const slaAtRisk = open.filter((w) => (w.ai_impact_assessment?.sla_breach_risk || 0) > 0.6).length

  const baseline = Math.max(2, Math.round(open.length / 2))
  const forecastDays = Array.from({ length: 7 }, (_, i) => {
    const date = addDays(new Date(), i)
    const predicted = baseline + ((i * 3) % 5)
    const actual = i === 0 ? Math.max(0, baseline - 1) : null
    return {
      day: format(date, 'EEE'),
      predicted,
      actual,
    }
  })
  const maxForecast = Math.max(...forecastDays.map((d) => d.predicted), 1)

  return (
    <div className="wo-dashboard">
      <div className="wo-kpi-row">
        <KpiCard icon={ClipboardList} label="Open Work Orders" value={open.length} sub={`${critical.length} critical/high`} color="#3b82f6" trend="up" />
        <KpiCard icon={AlertTriangle} label="SLA At Risk" value={slaAtRisk} sub="Breach within 24h" color="#ef4444" trend="down" />
        <KpiCard icon={DollarSign} label="Pending Approvals" value={pendingApproval.length} sub={`$${pendingApproval.reduce((sum, w) => sum + (w.estimated_cost || 0), 0).toLocaleString()} total`} color="#f59e0b" />
        <KpiCard icon={CheckCircle2} label="Completed (30d)" value={completed.length} sub={`${Math.round(completed.filter((w) => w.status === 'verified').length / Math.max(1, completed.length) * 100)}% verified`} color="#22c55e" trend="up" />
        <KpiCard icon={Brain} label="Avg AI Priority" value={avgScore} sub="Score 0–100" color="#8b5cf6" />
      </div>

      <div className="wo-dashboard-grid">
        <div className="wo-panel">
          <div className="wo-panel-header">
            <h3><AlertTriangle size={16} /> Critical & High Priority</h3>
            <button className="wo-link-btn" onClick={() => onNavigate('queue')}>View All <ArrowRight size={14} /></button>
          </div>
          <div className="wo-panel-body">
            {critical.slice(0, 5).map((wo) => (
              <div key={wo.id} className="wo-mini-row">
                <div className="wo-mini-left">
                  <PriorityBadge priority={wo.priority} />
                  <div>
                    <div className="wo-mini-id">{wo.id}</div>
                    <div className="wo-mini-title">{wo.title}</div>
                  </div>
                </div>
                <div className="wo-mini-right">
                  <StatusBadge status={wo.status} />
                  <span className="wo-mini-asset">{wo.asset_id}</span>
                </div>
              </div>
            ))}
            {critical.length === 0 ? <div className="wo-empty">No critical work orders. All clear.</div> : null}
          </div>
        </div>

        <div className="wo-panel">
          <div className="wo-panel-header">
            <h3><Bot size={16} /> Recent AI-Generated</h3>
            <button className="wo-link-btn" onClick={() => onNavigate('create')}>Create New <Plus size={14} /></button>
          </div>
          <div className="wo-panel-body">
            {workOrders.filter((w) => w.source === 'ai_sensor' || w.source === 'pdm_alert').slice(0, 5).map((wo) => (
              <div key={wo.id} className="wo-mini-row">
                <div className="wo-mini-left">
                  <SourceBadge source={wo.source} />
                  <div>
                    <div className="wo-mini-id">{wo.id}</div>
                    <div className="wo-mini-title">{wo.title}</div>
                  </div>
                </div>
                <div className="wo-mini-right">
                  <span className="wo-mini-time">{formatDistanceToNow(new Date(wo.created_at), { addSuffix: true })}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="wo-panel">
          <div className="wo-panel-header">
            <h3><TrendingUp size={16} /> 7-Day WO Forecast</h3>
            <button className="wo-link-btn" onClick={() => onNavigate('forecasting')}>Details <ArrowRight size={14} /></button>
          </div>
          <div className="wo-panel-body">
            <div className="wo-forecast-mini">
              {forecastDays.map((dayData, i) => (
                <div key={dayData.day} className="wo-forecast-bar-col">
                  <div className="wo-forecast-bar-wrapper">
                    <div className="wo-forecast-bar" style={{ height: `${(dayData.predicted / maxForecast) * 100}%`, background: i === 0 ? '#6366f1' : '#c7d2fe' }} />
                  </div>
                  <span className="wo-forecast-bar-val">{dayData.predicted}</span>
                  <span className="wo-forecast-bar-day">{dayData.day}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="wo-panel">
          <div className="wo-panel-header">
            <h3><DollarSign size={16} /> Pending Approvals</h3>
            <button className="wo-link-btn" onClick={() => onNavigate('approvals')}>Review <ArrowRight size={14} /></button>
          </div>
          <div className="wo-panel-body">
            {pendingApproval.slice(0, 4).map((wo) => (
              <div key={wo.id} className="wo-mini-row">
                <div className="wo-mini-left">
                  <div>
                    <div className="wo-mini-id">{wo.id}</div>
                    <div className="wo-mini-title">{wo.title}</div>
                  </div>
                </div>
                <div className="wo-mini-right">
                  <span className="wo-mini-cost">${(wo.estimated_cost || 0).toLocaleString()}</span>
                </div>
              </div>
            ))}
            {pendingApproval.length === 0 ? <div className="wo-empty">No pending approvals.</div> : null}
          </div>
        </div>
      </div>
    </div>
  )
}
