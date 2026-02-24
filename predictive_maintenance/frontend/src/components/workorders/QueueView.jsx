import { useState } from 'react'
import { AlertCircle, Building, Calendar, ChevronDown, ChevronRight, Clock, FileText, Gauge, MessageSquare, Search, Truck, Wrench } from 'lucide-react'

import { PRIORITY_COLORS, PriorityBadge, SourceBadge, StatusBadge, WO_STATUSES } from './shared'

export default function QueueView({ workOrders }) {
  const [filterPriority, setFilterPriority] = useState('all')
  const [filterStatus, setFilterStatus] = useState('all')
  const [sortBy, setSortBy] = useState('ai_score')
  const [expandedWO, setExpandedWO] = useState(null)

  const filtered = workOrders.filter((workOrder) => {
    if (filterPriority !== 'all' && workOrder.priority !== filterPriority) return false
    if (filterStatus !== 'all' && workOrder.status !== filterStatus) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === 'ai_score') return (b.ai_priority_score || 0) - (a.ai_priority_score || 0)
    if (sortBy === 'priority') {
      const order = { critical: 0, high: 1, medium: 2, low: 3 }
      return (order[a.priority] ?? 4) - (order[b.priority] ?? 4)
    }
    if (sortBy === 'sla') return new Date(a.sla_deadline) - new Date(b.sla_deadline)
    if (sortBy === 'created') return new Date(b.created_at) - new Date(a.created_at)
    return 0
  })

  return (
    <div className="wo-queue">
      <div className="wo-queue-controls">
        <select value={filterPriority} onChange={(e) => setFilterPriority(e.target.value)}>
          <option value="all">All Priorities</option>
          {Object.entries(PRIORITY_COLORS).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
        </select>
        <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="all">All Statuses</option>
          {Object.entries(WO_STATUSES).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="ai_score">Sort: AI Priority Score</option>
          <option value="priority">Sort: Priority Level</option>
          <option value="sla">Sort: SLA Deadline</option>
          <option value="created">Sort: Newest First</option>
        </select>
        <span className="wo-queue-count">{sorted.length} work orders</span>
      </div>

      <div className="wo-queue-list">
        {sorted.map((wo) => {
          const isExpanded = expandedWO === wo.id
          const slaDate = new Date(wo.sla_deadline)
          const slaOverdue = slaDate < new Date() && !['completed', 'verified'].includes(wo.status)

          return (
            <div key={wo.id} className={"wo-queue-card"}>
              <div className="wo-queue-card-main" onClick={() => setExpandedWO(isExpanded ? null : wo.id)}>
                <div className="wo-queue-left">
                  <button className="wo-expand-btn">{isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</button>
                  <div>
                    <div className="wo-queue-id-row">
                      <span className="wo-queue-id">{wo.id}</span>
                      <PriorityBadge priority={wo.priority} />
                      <StatusBadge status={wo.status} />
                      <SourceBadge source={wo.source} />
                    </div>
                    <div className="wo-queue-title">{wo.title}</div>
                    <div className="wo-queue-meta">
                      <span><Building size={11} /> {wo.estate}</span>
                      <span><Wrench size={11} /> {wo.asset_id}</span>
                      <span><Clock size={11} /> SLA {slaDate.toLocaleDateString()}</span>
                    </div>
                  </div>
                </div>
                <div className="wo-queue-right">
                  <div className="wo-ai-score" style={{ color: wo.ai_priority_score > 80 ? '#ef4444' : wo.ai_priority_score > 60 ? '#f59e0b' : '#22c55e' }}>
                    <Gauge size={13} /> {wo.ai_priority_score}
                  </div>
                  {slaOverdue ? <div className="wo-sla-overdue"><AlertCircle size={12} /> Overdue</div> : null}
                </div>
              </div>

              {isExpanded ? (
                <div className="wo-queue-expanded">
                  <div className="wo-detail-grid">
                    <div className="wo-detail-item"><span className="label">Priority</span><span className="value">{wo.priority}</span></div>
                    <div className="wo-detail-item"><span className="label">Status</span><span className="value">{wo.status}</span></div>
                    <div className="wo-detail-item"><span className="label">Estimated Cost</span><span className="value">${(wo.estimated_cost || 0).toLocaleString()}</span></div>
                    <div className="wo-detail-item"><span className="label">Revenue Impact</span><span className="value">${(wo.ai_impact_assessment?.revenue_impact || 0).toLocaleString()}</span></div>
                    <div className="wo-detail-item"><span className="label">SLA Breach Risk</span><span className="value">{Math.round((wo.ai_impact_assessment?.sla_breach_risk || 0) * 100)}%</span></div>
                    <div className="wo-detail-item"><span className="label">Brand Impact</span><span className="value">{wo.ai_impact_assessment?.brand_impact || 'No'}</span></div>
                  </div>
                  <div className="wo-detail-section">
                    <h4><MessageSquare size={14} /> AI Rationale</h4>
                    <p className="wo-rationale">{wo.ai_rationale}</p>
                  </div>
                  <div className="wo-detail-section">
                    <h4><FileText size={14} /> Description</h4>
                    <p className="wo-desc-text">{wo.description}</p>
                  </div>
                  {wo.assigned_provider ? (
                    <div className="wo-detail-section">
                      <h4><Truck size={14} /> Assigned Provider</h4>
                      <p>{wo.assigned_provider.name} - FTFR {(wo.assigned_provider.ftfr * 100).toFixed(0)}% · Avg ${wo.assigned_provider.avgCost}</p>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          )
        })}
        {sorted.length === 0 ? <div className="wo-empty">No work orders match the current filters.</div> : null}
      </div>
    </div>
  )
}
