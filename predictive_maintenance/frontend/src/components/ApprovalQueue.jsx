import { useState, useEffect, useCallback } from 'react'
import { 
  CheckCircle, XCircle, Edit3, Clock, AlertTriangle, 
  ChevronDown, ChevronUp, User, Shield, Zap, MessageSquare 
} from 'lucide-react'
import clsx from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { safeRequest } from '../services/apiClient'

const RISK_COLORS = {
  LOW: '#22c55e',
  MEDIUM: '#eab308',
  HIGH: '#f97316',
  EXTREME: '#991b1b',
}

const STATUS_CONFIG = {
  pending: { label: 'Pending', color: '#6b7280', icon: Clock },
  explaining: { label: 'Generating Explanation', color: '#3b82f6', icon: MessageSquare },
  validating: { label: 'Validating', color: '#8b5cf6', icon: Shield },
  ready: { label: 'Ready for Review', color: '#22c55e', icon: CheckCircle },
  in_review: { label: 'In Review', color: '#eab308', icon: User },
  approved: { label: 'Approved', color: '#22c55e', icon: CheckCircle },
  rejected: { label: 'Rejected', color: '#ef4444', icon: XCircle },
  escalated: { label: 'Escalated', color: '#f97316', icon: AlertTriangle },
  expired: { label: 'Expired', color: '#6b7280', icon: Clock },
}

function ApprovalItemCard({ item, expanded, onToggle, onAction }) {
  const statusConfig = STATUS_CONFIG[item.status] || STATUS_CONFIG.pending
  const StatusIcon = statusConfig.icon
  const riskColor = RISK_COLORS[item.risk_tier] || '#6b7280'
  
  const canApprove = ['ready', 'in_review'].includes(item.status)
  const canReject = ['ready', 'in_review'].includes(item.status)
  const canEdit = ['ready', 'in_review'].includes(item.status)
  
  return (
    <div className={clsx('approval-item', item.status, { expanded })}>
      <div className="approval-item-header" onClick={onToggle}>
        <div className="approval-item-main">
          <span className="approval-id">{item.item_id || item.approval_id}</span>
          <span className="approval-risk" style={{ backgroundColor: `${riskColor}20`, color: riskColor }}>
            {item.risk_tier}
          </span>
          <span className="approval-status" style={{ color: statusConfig.color }}>
            <StatusIcon size={14} />
            {statusConfig.label}
          </span>
        </div>
        
        <div className="approval-item-meta">
          <span className="approval-asset">{item.asset_id}</span>
          <span className="approval-time">
            {item.created_at && formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
          </span>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>
      
      <div className="approval-item-summary">
        <p>{item.action_summary}</p>
      </div>
      
      {expanded && (
        <div className="approval-item-details">
          <div className="approval-section">
            <h4>Proposed Actions</h4>
            <ul className="action-list">
              {(item.proposed_actions || []).map((action, idx) => (
                <li key={idx} className="action-item">
                  <span className="action-type">{action.action_type || action.type}</span>
                  <span className="action-target">{action.point_id || action.target}</span>
                  {action.value !== undefined && (
                    <span className="action-value">→ {action.value}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
          
          {item.explanation && (
            <div className="approval-section llm-explanation">
              <h4>
                <MessageSquare size={14} />
                AI Explanation
              </h4>
              <div className="explanation-content">
                <p className="explanation-summary">{item.explanation.summary}</p>
                
                {item.explanation.why_needed && (
                  <div className="explanation-block">
                    <strong>Why This Action?</strong>
                    <p>{item.explanation.why_needed}</p>
                  </div>
                )}
                
                {item.explanation.expected_outcome && (
                  <div className="explanation-block">
                    <strong>Expected Outcome</strong>
                    <p>{item.explanation.expected_outcome}</p>
                  </div>
                )}
                
                {item.explanation.risks && (
                  <div className="explanation-block">
                    <strong>Potential Risks</strong>
                    <p>{item.explanation.risks}</p>
                  </div>
                )}
                
                {item.explanation.alternatives && (
                  <div className="explanation-block">
                    <strong>Alternatives Considered</strong>
                    <p>{item.explanation.alternatives}</p>
                  </div>
                )}
              </div>
            </div>
          )}
          
          {item.validation && (
            <div className="approval-section llm-validation">
              <h4>
                <Shield size={14} />
                Validation Results
              </h4>
              <div className={clsx('validation-result', { passed: item.validation.passed })}>
                {item.validation.passed ? (
                  <CheckCircle size={16} className="validation-icon passed" />
                ) : (
                  <AlertTriangle size={16} className="validation-icon warning" />
                )}
                <span>{item.validation.passed ? 'All checks passed' : 'Review required'}</span>
              </div>
              
              {item.validation.checks && (
                <ul className="validation-checks">
                  {item.validation.checks.map((check, idx) => (
                    <li key={idx} className={clsx('check-item', { passed: check.passed })}>
                      {check.passed ? <CheckCircle size={12} /> : <XCircle size={12} />}
                      <span>{check.name}: {check.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          
          {item.telemetry_snapshot && Object.keys(item.telemetry_snapshot).length > 0 && (
            <div className="approval-section">
              <h4>Telemetry Snapshot</h4>
              <div className="telemetry-grid">
                {Object.entries(item.telemetry_snapshot).slice(0, 8).map(([key, value]) => (
                  <div key={key} className="telemetry-item">
                    <span className="telemetry-key">{key}</span>
                    <span className="telemetry-value">
                      {typeof value === 'number' ? value.toFixed(2) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          <div className="approval-actions">
            {canApprove && (
              <button 
                className="btn btn-approve"
                onClick={() => onAction(item, 'approve')}
              >
                <CheckCircle size={16} />
                Approve
              </button>
            )}
            {canEdit && (
              <button 
                className="btn btn-edit"
                onClick={() => onAction(item, 'edit')}
              >
                <Edit3 size={16} />
                Modify & Approve
              </button>
            )}
            {canReject && (
              <button 
                className="btn btn-reject"
                onClick={() => onAction(item, 'reject')}
              >
                <XCircle size={16} />
                Reject
              </button>
            )}
          </div>
          
          <div className="approval-feedback">
            <label>
              <input type="checkbox" id={`helpful-${item.item_id}`} />
              AI explanation was helpful
            </label>
            <label>
              <input type="checkbox" id={`accurate-${item.item_id}`} />
              Validation was accurate
            </label>
          </div>
        </div>
      )}
    </div>
  )
}

function ApprovalModal({ item, action, onClose, onSubmit }) {
  const [notes, setNotes] = useState('')
  const [reason, setReason] = useState('')
  const [modifiedParams, setModifiedParams] = useState({})
  const [submitting, setSubmitting] = useState(false)
  
  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      await onSubmit({
        action,
        notes,
        reason,
        modified_params: action === 'edit' ? modifiedParams : undefined,
        llm_explanation_helpful: document.getElementById(`helpful-${item.item_id}`)?.checked,
        llm_validation_accurate: document.getElementById(`accurate-${item.item_id}`)?.checked,
      })
      onClose()
    } catch (err) {
      console.error('Submission failed:', err)
    } finally {
      setSubmitting(false)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <h3>
          {action === 'approve' && 'Approve Action'}
          {action === 'reject' && 'Reject Action'}
          {action === 'edit' && 'Modify & Approve'}
        </h3>
        
        <div className="modal-body">
          <p>Item: <strong>{item.item_id}</strong></p>
          <p>Asset: <strong>{item.asset_id}</strong></p>
          
          {action === 'reject' && (
            <div className="form-field">
              <label>Rejection Reason *</label>
              <select value={reason} onChange={e => setReason(e.target.value)} required>
                <option value="">Select reason...</option>
                <option value="incorrect_diagnosis">Incorrect Diagnosis</option>
                <option value="wrong_action">Wrong Action Proposed</option>
                <option value="bad_timing">Bad Timing</option>
                <option value="insufficient_evidence">Insufficient Evidence</option>
                <option value="operator_override">Operator Override</option>
                <option value="other">Other</option>
              </select>
            </div>
          )}
          
          {action === 'edit' && (
            <div className="form-field">
              <label>Modified Parameters (JSON)</label>
              <textarea 
                value={JSON.stringify(modifiedParams, null, 2)}
                onChange={e => {
                  try {
                    setModifiedParams(JSON.parse(e.target.value))
                  } catch {}
                }}
                rows={4}
              />
            </div>
          )}
          
          <div className="form-field">
            <label>Notes</label>
            <textarea 
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Add any notes about this decision..."
              rows={3}
            />
          </div>
        </div>
        
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button 
            className={clsx('btn', {
              'btn-approve': action === 'approve' || action === 'edit',
              'btn-reject': action === 'reject',
            })}
            onClick={handleSubmit}
            disabled={submitting || (action === 'reject' && !reason)}
          >
            {submitting ? 'Submitting...' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ApprovalQueue({ wsConnection }) {
  const [items, setItems] = useState([])
  const [stats, setStats] = useState({})
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)
  const [modalState, setModalState] = useState({ open: false, item: null, action: null })
  const [filter, setFilter] = useState('pending')
  
  const fetchQueue = useCallback(async () => {
    try {
      const [queueResult, statsResult] = await Promise.all([
        safeRequest(`/api/v1/approval-queue?status=${filter}`),
        safeRequest('/api/v1/approval-queue/stats'),
      ])
      
      if (queueResult.ok) {
        setItems(queueResult.data.items || [])
      }
      
      if (statsResult.ok) {
        setStats(statsResult.data)
      }
    } catch (err) {
      console.error('Failed to fetch approval queue:', err)
    } finally {
      setLoading(false)
    }
  }, [filter])
  
  useEffect(() => {
    fetchQueue()
    const interval = setInterval(fetchQueue, 15000)
    return () => clearInterval(interval)
  }, [fetchQueue])
  
  useEffect(() => {
    if (!wsConnection) return
    
    const handleMessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'approval_update') {
          setItems(prev => {
            const idx = prev.findIndex(i => i.item_id === data.item_id)
            if (idx >= 0) {
              const updated = [...prev]
              updated[idx] = { ...updated[idx], ...data.update }
              return updated
            }
            return prev
          })
        } else if (data.type === 'approval_added') {
          setItems(prev => [data.item, ...prev])
        }
      } catch (err) {
        console.error('WebSocket message parse error:', err)
      }
    }
    
    wsConnection.addEventListener('message', handleMessage)
    return () => wsConnection.removeEventListener('message', handleMessage)
  }, [wsConnection])
  
  const handleAction = (item, action) => {
    setModalState({ open: true, item, action })
  }
  
  const handleSubmitDecision = async (decision) => {
    const { item, action } = modalState
    
    const endpoint = action === 'reject' 
      ? `/api/v1/approval-queue/${item.item_id}/reject`
      : `/api/v1/approval-queue/${item.item_id}/approve`
    
    const { ok } = await safeRequest(endpoint, {
      method: 'POST',
      body: JSON.stringify({
        reviewer_id: 'current_user',
        ...decision,
      }),
    })
    
    if (!ok) {
      throw new Error('Failed to submit decision')
    }
    
    fetchQueue()
  }
  
  const pendingCount = stats.pending_count || 0
  const readyCount = items.filter(i => i.status === 'ready').length
  
  if (loading) {
    return <div className="approval-loading">Loading approval queue...</div>
  }
  
  return (
    <div className="approval-queue">
      <div className="approval-header">
        <h2>
          Approval Queue
          {pendingCount > 0 && (
            <span className="pending-badge">{pendingCount}</span>
          )}
        </h2>
        
        <div className="approval-controls">
          <select value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="pending">Pending Review</option>
            <option value="ready">Ready for Review</option>
            <option value="in_review">In Review</option>
            <option value="approved">Recently Approved</option>
            <option value="rejected">Recently Rejected</option>
          </select>
        </div>
      </div>
      
      <div className="approval-stats">
        <div className="stat">
          <Zap size={16} />
          <span>Avg Review Time: {stats.avg_review_time_seconds ? `${Math.round(stats.avg_review_time_seconds)}s` : '—'}</span>
        </div>
        <div className="stat">
          <MessageSquare size={16} />
          <span>AI Helpful: {stats.llm_explanation_helpful_rate ? `${Math.round(stats.llm_explanation_helpful_rate * 100)}%` : '—'}</span>
        </div>
        <div className="stat">
          <Shield size={16} />
          <span>Validation Accurate: {stats.llm_validation_accurate_rate ? `${Math.round(stats.llm_validation_accurate_rate * 100)}%` : '—'}</span>
        </div>
      </div>
      
      <div className="approval-list">
        {items.map(item => (
          <ApprovalItemCard
            key={item.item_id || item.approval_id}
            item={item}
            expanded={expandedId === (item.item_id || item.approval_id)}
            onToggle={() => setExpandedId(
              expandedId === (item.item_id || item.approval_id) ? null : (item.item_id || item.approval_id)
            )}
            onAction={handleAction}
          />
        ))}
        
        {items.length === 0 && (
          <div className="approval-empty">
            <CheckCircle size={48} />
            <p>No items in queue matching current filter.</p>
          </div>
        )}
      </div>
      
      {modalState.open && (
        <ApprovalModal
          item={modalState.item}
          action={modalState.action}
          onClose={() => setModalState({ open: false, item: null, action: null })}
          onSubmit={handleSubmitDecision}
        />
      )}
    </div>
  )
}
