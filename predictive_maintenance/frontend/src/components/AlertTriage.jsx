import { useState, useEffect, useCallback } from 'react'
import { 
  AlertTriangle, CheckCircle, XCircle, Clock, Eye, 
  Send, MessageSquare, Wrench, TrendingUp, ChevronRight,
  ThumbsUp, ThumbsDown, FileText, ExternalLink
} from 'lucide-react'
import clsx from 'clsx'
import { formatDistanceToNow, format } from 'date-fns'
import { safeRequest } from '../services/apiClient'

const ALERT_TYPE_CONFIG = {
  watch: { color: '#eab308', label: 'Watch', icon: Eye },
  action: { color: '#f97316', label: 'Action Required', icon: AlertTriangle },
  actionable: { color: '#f97316', label: 'Actionable', icon: AlertTriangle },
  dispatch: { color: '#ef4444', label: 'Dispatch Required', icon: Send },
  sensor_integrity: { color: '#8b5cf6', label: 'Sensor Issue', icon: Wrench },
  human_review: { color: '#3b82f6', label: 'Human Review', icon: MessageSquare },
  resolved: { color: '#22c55e', label: 'Resolved', icon: CheckCircle },
  dismissed: { color: '#6b7280', label: 'Dismissed', icon: XCircle },
}

const SEVERITY_CONFIG = {
  info: { color: '#6b7280', weight: 1 },
  low: { color: '#22c55e', weight: 2 },
  medium: { color: '#eab308', weight: 3 },
  high: { color: '#f97316', weight: 4 },
  critical: { color: '#ef4444', weight: 5 },
}

function AlertCard({ alert, expanded, onToggle, onAction }) {
  const displayType =
    alert.status === 'resolved'
      ? 'resolved'
      : (alert.status === 'dismissed' || alert.status === 'suppressed')
        ? 'dismissed'
        : alert.alert_type
  const typeConfig = ALERT_TYPE_CONFIG[displayType] || ALERT_TYPE_CONFIG.watch
  const sevConfig = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.medium
  const TypeIcon = typeConfig.icon
  
  const isActive = !['resolved', 'dismissed', 'suppressed'].includes(alert.status || '')
  
  return (
    <div className={clsx('alert-card', displayType, { expanded, active: isActive })}>
      <div className="alert-card-header" onClick={onToggle}>
        <div className="alert-icon" style={{ backgroundColor: `${typeConfig.color}20`, color: typeConfig.color }}>
          <TypeIcon size={20} />
        </div>
        
        <div className="alert-main">
          <div className="alert-title">
            <span className="alert-id">{alert.alert_id}</span>
            <span className="alert-type-badge" style={{ color: typeConfig.color }}>
              {typeConfig.label}
            </span>
            <span className="alert-severity" style={{ color: sevConfig.color }}>
              {alert.severity}
            </span>
          </div>
          <div className="alert-subtitle">
            <span className="alert-asset">{alert.asset_id}</span>
            <span className="alert-fault">{alert.primary_fault || 'Unknown Fault'}</span>
          </div>
        </div>
        
        <div className="alert-meta">
          <div className="alert-confidence">
            <span className="label">Confidence</span>
            <span className="value">{Math.round((alert.confidence || 0) * 100)}%</span>
          </div>
          <div className="alert-fa-prob">
            <span className="label">FA Prob</span>
            <span className="value">{Math.round((alert.false_alarm_probability || 0) * 100)}%</span>
          </div>
          <div className="alert-time">
            {alert.created_at && formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
          </div>
          <ChevronRight size={16} className={clsx('expand-icon', { expanded })} />
        </div>
      </div>
      
      {expanded && (
        <div className="alert-card-details">
          <div className="alert-section evidence-section">
            <h4><FileText size={14} /> Evidence Summary</h4>
            <ul className="evidence-list">
              {(alert.evidence_summary || []).map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
              {(!alert.evidence_summary || alert.evidence_summary.length === 0) && (
                <li className="muted">No evidence details available</li>
              )}
            </ul>
          </div>
          
          <div className="alert-section fault-section">
            <h4><TrendingUp size={14} /> Fault Hypothesis</h4>
            <div className="fault-distribution">
              {(alert.fault_beliefs || alert.fault_belief) && Object.entries(alert.fault_beliefs || alert.fault_belief)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 5)
                .map(([fault, prob]) => (
                  <div key={fault} className="fault-bar">
                    <span className="fault-name">{fault}</span>
                    <div className="fault-bar-track">
                      <div 
                        className="fault-bar-fill" 
                        style={{ width: `${prob * 100}%` }}
                      />
                    </div>
                    <span className="fault-prob">{Math.round(prob * 100)}%</span>
                  </div>
                ))}
            </div>
          </div>
          
          {alert.recommended_action && (
            <div className="alert-section action-section">
              <h4><Wrench size={14} /> Recommended Action</h4>
              <p>{alert.recommended_action}</p>
            </div>
          )}
          
          {alert.rul_estimate && (
            <div className="alert-section rul-section">
              <h4><Clock size={14} /> RUL Estimate</h4>
              <div className="rul-info">
                <span className="rul-value">
                  {alert.rul_estimate.rul_hours === Infinity || alert.rul_estimate.rul_hours > 9999
                    ? '∞'
                    : `${Math.round(alert.rul_estimate.rul_hours)} hours`}
                </span>
                <span className="rul-range">
                  ({Math.round(alert.rul_estimate.rul_lower_bound_hours || 0)}h - 
                  {alert.rul_estimate.rul_upper_bound_hours > 9999 
                    ? '∞' 
                    : `${Math.round(alert.rul_estimate.rul_upper_bound_hours || 0)}h`})
                </span>
              </div>
            </div>
          )}
          
          <div className="alert-actions">
            {isActive && (
              <>
                <button 
                  className="btn btn-primary"
                  onClick={() => onAction(alert, 'acknowledge')}
                >
                  <Eye size={16} />
                  Acknowledge
                </button>
                
                {alert.alert_type === 'dispatch' && (
                  <button 
                    className="btn btn-dispatch"
                    onClick={() => onAction(alert, 'dispatch')}
                  >
                    <Send size={16} />
                    Create Work Order
                  </button>
                )}
                
                <button 
                  className="btn btn-resolve"
                  onClick={() => onAction(alert, 'resolve')}
                >
                  <CheckCircle size={16} />
                  Resolve
                </button>
                
                <button 
                  className="btn btn-dismiss"
                  onClick={() => onAction(alert, 'dismiss')}
                >
                  <XCircle size={16} />
                  Dismiss
                </button>
              </>
            )}
            
            <button 
              className="btn btn-secondary"
              onClick={() => onAction(alert, 'view_asset')}
            >
              <ExternalLink size={16} />
              View Asset
            </button>
          </div>
          
          <div className="alert-feedback">
            <span>Was this alert helpful?</span>
            <button 
              className="feedback-btn"
              onClick={() => onAction(alert, 'feedback_positive')}
            >
              <ThumbsUp size={14} />
            </button>
            <button 
              className="feedback-btn"
              onClick={() => onAction(alert, 'feedback_negative')}
            >
              <ThumbsDown size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function ResolveModal({ alert, onClose, onSubmit }) {
  const [outcome, setOutcome] = useState('')
  const [notes, setNotes] = useState('')
  const [actualFault, setActualFault] = useState('')
  const [submitting, setSubmitting] = useState(false)
  
  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      await onSubmit({
        outcome,
        notes,
        actual_fault: actualFault,
      })
      onClose()
    } catch (err) {
      console.error('Failed to resolve alert:', err)
    } finally {
      setSubmitting(false)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <h3>Resolve Alert</h3>
        
        <div className="modal-body">
          <p>Alert: <strong>{alert.alert_id}</strong></p>
          <p>Predicted Fault: <strong>{alert.primary_fault}</strong></p>
          
          <div className="form-field">
            <label>Resolution Outcome *</label>
            <select value={outcome} onChange={e => setOutcome(e.target.value)} required>
              <option value="">Select outcome...</option>
              <option value="true_positive">True Positive - Fault Confirmed</option>
              <option value="false_positive">False Positive - No Issue Found</option>
              <option value="partial_match">Partial Match - Different Fault Found</option>
              <option value="deferred">Deferred - Monitoring Continues</option>
            </select>
          </div>
          
          {outcome === 'partial_match' && (
            <div className="form-field">
              <label>Actual Fault Type</label>
              <select value={actualFault} onChange={e => setActualFault(e.target.value)}>
                <option value="">Select actual fault...</option>
                <option value="refrigerant_leak">Refrigerant Leak</option>
                <option value="compressor_degradation">Compressor Degradation</option>
                <option value="condenser_fouling">Condenser Fouling</option>
                <option value="evaporator_fouling">Evaporator Fouling</option>
                <option value="fan_degradation">Fan Degradation</option>
                <option value="electrical_issue">Electrical Issue</option>
                <option value="sensor_fault">Sensor Fault</option>
                <option value="other">Other</option>
              </select>
            </div>
          )}
          
          <div className="form-field">
            <label>Resolution Notes</label>
            <textarea 
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Describe what was found and actions taken..."
              rows={4}
            />
          </div>
        </div>
        
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button 
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={submitting || !outcome}
          >
            {submitting ? 'Submitting...' : 'Resolve Alert'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AlertTriage({ assetId, wsConnection, onAssetSelect }) {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)
  const [modalState, setModalState] = useState({ open: false, alert: null, action: null })
  const [filter, setFilter] = useState('active')
  const [sortBy, setSortBy] = useState('severity')
  
  const fetchAlerts = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (assetId) params.set('asset_id', assetId)
      if (filter === 'active') params.set('active', 'true')
      
      const { ok, data } = await safeRequest(`/api/v1/alerts?${params}`)
      if (ok && data) {
        setAlerts(data.alerts || [])
      }
    } catch (err) {
      console.error('Failed to fetch alerts:', err)
    } finally {
      setLoading(false)
    }
  }, [assetId, filter])
  
  useEffect(() => {
    fetchAlerts()
    const interval = setInterval(fetchAlerts, 20000)
    return () => clearInterval(interval)
  }, [fetchAlerts])
  
  useEffect(() => {
    if (!wsConnection) return
    
    const handleMessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'alert_new') {
          setAlerts(prev => [data.alert, ...prev])
        } else if (data.type === 'alert_update') {
          setAlerts(prev => prev.map(a => 
            a.alert_id === data.alert.alert_id ? data.alert : a
          ))
        }
      } catch (err) {
        console.error('WebSocket parse error:', err)
      }
    }
    
    wsConnection.addEventListener('message', handleMessage)
    return () => wsConnection.removeEventListener('message', handleMessage)
  }, [wsConnection])
  
  const handleAction = async (alert, action) => {
    switch (action) {
      case 'acknowledge':
        await safeRequest(`/api/v1/alerts/${alert.alert_id}/acknowledge`, {
          method: 'POST',
          body: JSON.stringify({ acknowledged_by: 'operator_ui' }),
        })
        fetchAlerts()
        break
      case 'resolve':
        setModalState({ open: true, alert, action: 'resolve' })
        break
      case 'dismiss':
        await safeRequest(`/api/v1/alerts/${alert.alert_id}/dismiss`, {
          method: 'POST',
          body: JSON.stringify({ dismissed_by: 'operator_ui', notes: 'dismissed_from_triage' }),
        })
        fetchAlerts()
        break
      case 'dispatch':
        window.open(`/dispatch?alert_id=${alert.alert_id}`, '_blank')
        break
      case 'view_asset':
        onAssetSelect?.(alert.asset_id)
        break
      case 'feedback_positive':
      case 'feedback_negative':
        await safeRequest('/api/v1/feedback', {
          method: 'POST',
          body: JSON.stringify({
            alert_id: alert.alert_id,
            outcome: action === 'feedback_positive' ? 'confirmed_fault' : 'no_issue_found',
            feedback_by: 'operator_ui',
          }),
        })
        fetchAlerts()
        break
      default:
        break
    }
  }
  
  const handleResolve = async (resolution) => {
    const { alert } = modalState
    await safeRequest(`/api/v1/alerts/${alert.alert_id}/resolve`, {
      method: 'POST',
      body: JSON.stringify(resolution),
    })
    fetchAlerts()
  }
  
  const sortedAlerts = [...alerts].sort((a, b) => {
    if (sortBy === 'severity') {
      const aWeight = SEVERITY_CONFIG[a.severity]?.weight || 0
      const bWeight = SEVERITY_CONFIG[b.severity]?.weight || 0
      return bWeight - aWeight
    }
    if (sortBy === 'confidence') {
      return (b.confidence || 0) - (a.confidence || 0)
    }
    if (sortBy === 'time') {
      return new Date(b.created_at) - new Date(a.created_at)
    }
    return 0
  })
  
  const activeCount = alerts.filter(
    (a) => !['resolved', 'dismissed', 'suppressed'].includes(a.status || '')
  ).length
  
  if (loading) {
    return <div className="alert-loading">Loading alerts...</div>
  }
  
  return (
    <div className="alert-triage">
      <div className="alert-triage-header">
        <h2>
          Alert Triage
          {activeCount > 0 && <span className="active-badge">{activeCount}</span>}
        </h2>
        
        <div className="alert-controls">
          <select value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="active">Active Alerts</option>
            <option value="all">All Alerts</option>
            <option value="resolved">Resolved</option>
          </select>
          <select value={sortBy} onChange={e => setSortBy(e.target.value)}>
            <option value="severity">Sort by Severity</option>
            <option value="confidence">Sort by Confidence</option>
            <option value="time">Sort by Time</option>
          </select>
        </div>
      </div>
      
      <div className="alert-list">
        {sortedAlerts.map(alert => (
          <AlertCard
            key={alert.alert_id}
            alert={alert}
            expanded={expandedId === alert.alert_id}
            onToggle={() => setExpandedId(expandedId === alert.alert_id ? null : alert.alert_id)}
            onAction={handleAction}
          />
        ))}
        
        {sortedAlerts.length === 0 && (
          <div className="alert-empty">
            <CheckCircle size={48} />
            <p>No alerts matching current filter.</p>
          </div>
        )}
      </div>
      
      {modalState.open && modalState.action === 'resolve' && (
        <ResolveModal
          alert={modalState.alert}
          onClose={() => setModalState({ open: false, alert: null, action: null })}
          onSubmit={handleResolve}
        />
      )}
    </div>
  )
}
