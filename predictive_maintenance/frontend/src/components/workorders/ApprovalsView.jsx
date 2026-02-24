import { useCallback, useEffect, useState } from 'react'
import clsx from 'clsx'
import { ArrowUpRight, Brain, Building, CheckCircle, DollarSign, ThumbsDown, ThumbsUp, Wrench } from 'lucide-react'

import WorkOrderApiService from '../../services/workorderApi'
import { PriorityBadge } from './shared'
import { getMockApprovalRecommendation, WORKORDER_MOCKS_ENABLED } from '../../services/workorderMockAdapter'

export default function ApprovalsView({ workOrders }) {
  const pending = workOrders.filter((w) => w.status === 'pending_approval')
  const [decisions, setDecisions] = useState({})
  const [aiRecs, setAiRecs] = useState({})

  const getAiRecommendation = useCallback(async (workOrder) => {
    if (aiRecs[workOrder.id]) return aiRecs[workOrder.id]

    const { ok, data } = await WorkOrderApiService.recommendCost({
      work_order_id: workOrder.id,
      title: workOrder.title,
      description: workOrder.description,
      asset_id: workOrder.asset_id,
      priority: workOrder.priority,
      estimated_cost: workOrder.estimated_cost,
      provider_name: workOrder.assigned_provider?.name || null,
    })

    if (ok && data?.recommendation) {
      const recommendation = {
        action: data.recommendation.action || 'review',
        confidence: data.recommendation.confidence ?? 0.7,
        reason: data.recommendation.reason || '',
        historical_comparison: data.recommendation.historical_comparison || '',
        source: data.raw_llm_response ? 'llm' : 'fallback',
      }
      setAiRecs((prev) => ({ ...prev, [workOrder.id]: recommendation }))
      return recommendation
    }

    const fallbackRecommendation = WORKORDER_MOCKS_ENABLED
      ? { ...getMockApprovalRecommendation(workOrder), source: 'mock_adapter' }
      : {
        action: 'review',
        confidence: 0,
        reason: 'Recommendation service unavailable. Escalate for manual triage.',
        source: 'error',
      }
    setAiRecs((prev) => ({ ...prev, [workOrder.id]: fallbackRecommendation }))
    return fallbackRecommendation
  }, [aiRecs])

  useEffect(() => {
    pending.forEach((workOrder) => {
      if (!aiRecs[workOrder.id]) {
        getAiRecommendation(workOrder)
      }
    })
  }, [pending.length])

  const handleDecision = (workOrderId, action) => {
    setDecisions((prev) => ({ ...prev, [workOrderId]: action }))
  }

  return (
    <div className="wo-approvals">
      <h3><DollarSign size={18} /> Approval Queue &mdash; AI Cost Recommendations</h3>
      <p className="wo-approvals-subtitle">AI analyzes historical spend, outcomes, and compliance rules to recommend approval decisions.</p>

      {pending.length === 0 ? <div className="wo-empty">No work orders pending approval.</div> : null}

      <div className="wo-approval-list">
        {pending.map((workOrder) => {
          const recommendation = aiRecs[workOrder.id] || { action: 'review', confidence: 0, reason: 'Loading AI recommendation...', source: 'loading' }
          const decided = decisions[workOrder.id]
          return (
            <div key={workOrder.id} className={clsx('wo-approval-card', { decided })}>
              <div className="wo-approval-top">
                <div>
                  <div className="wo-queue-id-row">
                    <span className="wo-queue-id">{workOrder.id}</span>
                    <PriorityBadge priority={workOrder.priority} />
                  </div>
                  <div className="wo-queue-title">{workOrder.title}</div>
                  <div className="wo-queue-meta">
                    <span><Building size={11} /> {workOrder.estate}</span>
                    <span><Wrench size={11} /> {workOrder.asset_id}</span>
                  </div>
                </div>
                <div className="wo-approval-cost">
                  <div className="wo-cost-amount">${(workOrder.estimated_cost || 0).toLocaleString()}</div>
                  <div className="wo-cost-label">Estimated</div>
                </div>
              </div>

              <div className={clsx('wo-ai-rec', recommendation.action)}>
                <div className="wo-ai-rec-header">
                  <Brain size={14} />
                  <strong>AI Recommendation: {recommendation.action === 'approve' ? 'Approve' : 'Manual Review'}</strong>
                  <span className="wo-ai-rec-conf">{(recommendation.confidence * 100).toFixed(0)}% confidence</span>
                </div>
                <p>{recommendation.reason}</p>
              </div>

              {!decided ? (
                <div className="wo-approval-actions">
                  <button className="wo-btn wo-btn-approve" onClick={() => handleDecision(workOrder.id, 'approved')}>
                    <ThumbsUp size={14} /> Approve
                  </button>
                  <button className="wo-btn wo-btn-reject" onClick={() => handleDecision(workOrder.id, 'rejected')}>
                    <ThumbsDown size={14} /> Reject
                  </button>
                  <button className="wo-btn wo-btn-secondary" onClick={() => handleDecision(workOrder.id, 'escalated')}>
                    <ArrowUpRight size={14} /> Escalate
                  </button>
                </div>
              ) : (
                <div className={clsx('wo-decision-result', decided)}>
                  <CheckCircle size={14} /> {decided.charAt(0).toUpperCase() + decided.slice(1)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
