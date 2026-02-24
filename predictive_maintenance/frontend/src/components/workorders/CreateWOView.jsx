import { useState } from 'react'
import { Bot, Brain, CheckCircle, Info, Mic, RefreshCw, Send, Sparkles, X, Zap } from 'lucide-react'
import { addDays } from 'date-fns'

import WorkOrderApiService from '../../services/workorderApi'
import { PRIORITY_COLORS, SourceBadge } from './shared'
import { WORKORDER_MOCKS_ENABLED, getMockInterpretation } from '../../services/workorderMockAdapter'

function DraftField({ label, value, onChange }) {
  return (
    <div className="wo-draft-field">
      <label>{label}</label>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

export default function CreateWOView({ onAddWorkOrder }) {
  const [nlInput, setNlInput] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [draft, setDraft] = useState(null)
  const [confidence, setConfidence] = useState(null)
  const [clarifications, setClarifications] = useState([])
  const [submitted, setSubmitted] = useState(false)
  const [llmSource, setLlmSource] = useState(null)
  const [error, setError] = useState('')

  const handleInterpret = async () => {
    if (!nlInput.trim()) return
    setIsProcessing(true)
    setClarifications([])
    setLlmSource(null)
    setError('')

    const { ok, data } = await WorkOrderApiService.interpret({ text: nlInput })
    if (ok && data) {
      const extractedDraft = {
        title: data.title || 'Maintenance Request',
        description: data.description || nlInput,
        asset_id: data.asset_id || 'TBD',
        estate: data.estate || '',
        location: data.location || '',
        priority: data.priority || 'medium',
        problem_type: data.problem_type || 'General',
        source: 'ai_nlp',
        ai_confidence: data.confidence ?? 0.75,
        symptoms: data.symptoms || [],
      }
      setLlmSource(data.raw_llm_response ? 'llm' : 'fallback')
      setDraft(extractedDraft)
      setConfidence(extractedDraft.ai_confidence)
      setClarifications(data.clarifications || [])
      setIsProcessing(false)
      return
    }

    if (WORKORDER_MOCKS_ENABLED) {
      const mockDraft = getMockInterpretation(nlInput)
      setLlmSource('mock_adapter')
      setDraft(mockDraft)
      setConfidence(mockDraft.ai_confidence)
      setClarifications(mockDraft.clarifications || [])
    } else {
      setError('Interpretation service is unavailable. Please retry when the backend is reachable.')
      setDraft(null)
      setConfidence(null)
    }
    setIsProcessing(false)
  }

  const handleSubmit = async () => {
    if (!draft) return

    const woId = `WO-2025-${String(1300 + Math.floor(Math.random() * 100)).padStart(4, '0')}`

    let aiScore = Math.round((draft.ai_confidence || 0.7) * 85)
    let aiAssessment = {
      safety_risk: draft.priority === 'critical' ? 'High' : 'Medium',
      revenue_impact: 0,
      sla_breach_risk: 0.3,
      brand_impact: 'No',
    }
    let aiRationale = `Work order created via NL interpretation with ${((draft.ai_confidence || 0.7) * 100).toFixed(0)}% confidence.`

    const { ok, data: prioData } = await WorkOrderApiService.prioritize({
      work_order_id: woId,
      title: draft.title,
      description: draft.description,
      asset_id: draft.asset_id || 'TBD',
      estate: draft.estate || '',
      location: draft.location || '',
      priority: draft.priority,
      source: 'ai_nlp',
      created_at: new Date().toISOString(),
    })

    if (ok && prioData?.assessment) {
      aiScore = prioData.assessment.priority_score ?? aiScore
      aiAssessment = {
        safety_risk: prioData.assessment.safety_risk || aiAssessment.safety_risk,
        revenue_impact: prioData.assessment.revenue_impact ?? 0,
        sla_breach_risk: prioData.assessment.sla_breach_risk ?? 0.3,
        brand_impact: prioData.assessment.brand_impact || 'No',
      }
      aiRationale = prioData.assessment.rationale || prioData.rationale_summary || aiRationale
    }

    const newWO = {
      id: woId,
      ...draft,
      status: 'open',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      sla_deadline: addDays(new Date(), draft.priority === 'critical' ? 1 : draft.priority === 'high' ? 3 : 7).toISOString(),
      estimated_cost: 0,
      actual_cost: null,
      assigned_provider: null,
      ai_priority_score: aiScore,
      ai_impact_assessment: aiAssessment,
      ai_rationale: aiRationale,
      verification: null,
    }

    onAddWorkOrder(newWO)
    setSubmitted(true)
    setTimeout(() => {
      setSubmitted(false)
      setDraft(null)
      setNlInput('')
      setClarifications([])
      setLlmSource(null)
    }, 3000)
  }

  return (
    <div className="wo-create">
      <div className="wo-create-input-panel">
        <h3><Sparkles size={18} /> Describe the Issue</h3>
        <p className="wo-create-subtitle">Type or speak your maintenance request. AI will interpret and create a structured work order.</p>

        <div className="wo-nl-input-wrapper">
          <textarea
            className="wo-nl-input"
            placeholder="e.g. 'The RTU-001 on the roof of Building A is making a loud grinding noise and the discharge temp is reading 20 degrees above normal. This needs urgent attention.'"
            value={nlInput}
            onChange={(e) => setNlInput(e.target.value)}
            rows={4}
          />
          <div className="wo-nl-actions">
            <button className="wo-btn wo-btn-icon" title="Voice input (coming soon)" disabled>
              <Mic size={16} />
            </button>
            <button className="wo-btn wo-btn-primary" onClick={handleInterpret} disabled={isProcessing || !nlInput.trim()}>
              {isProcessing ? <><RefreshCw size={14} className="wo-spin" /> Interpreting...</> : <><Brain size={14} /> Interpret with AI</>}
            </button>
          </div>
        </div>

        {error ? <div className="wo-clarification" role="alert">{error}</div> : null}

        <div className="wo-signal-box">
          <div className="wo-signal-header">
            <Zap size={16} style={{ color: '#8b5cf6' }} />
            <strong>Autonomous Signal Detection</strong>
          </div>
          <p>The PdM system continuously monitors IoT sensors and will auto-generate work orders when persistent anomalies are detected. Auto-generated WOs appear in the queue with <SourceBadge source="ai_sensor" /> or <SourceBadge source="pdm_alert" /> tags.</p>
        </div>
      </div>

      {draft ? (
        <div className="wo-draft-panel">
          <div className="wo-draft-header">
            <h3><Bot size={18} /> AI-Generated Draft</h3>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {llmSource ? (
                <span className="wo-source-badge" style={{
                  color: llmSource === 'llm' ? '#059669' : '#f59e0b',
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  padding: '0.15rem 0.5rem',
                  background: llmSource === 'llm' ? '#dcfce7' : '#fef9c3',
                  borderRadius: 'var(--radius-full)',
                }}>
                  {llmSource === 'llm' ? '✦ GPT-4 LLM' : llmSource === 'mock_adapter' ? '⚙ Mock Adapter' : '⚡ Server Fallback'}
                </span>
              ) : null}
              <div className="wo-confidence-pill" style={{ background: confidence > 0.8 ? '#dcfce7' : '#fef9c3', color: confidence > 0.8 ? '#166534' : '#854d0e' }}>
                Confidence: {(confidence * 100).toFixed(0)}%
              </div>
            </div>
          </div>

          {clarifications.length > 0 ? (
            <div className="wo-clarifications">
              {clarifications.map((clarification, index) => (
                <div key={index} className="wo-clarification"><Info size={14} /> {clarification}</div>
              ))}
            </div>
          ) : null}

          <div className="wo-draft-fields">
            <DraftField label="Title" value={draft.title} onChange={(v) => setDraft((d) => ({ ...d, title: v }))} />
            <DraftField label="Asset ID" value={draft.asset_id} onChange={(v) => setDraft((d) => ({ ...d, asset_id: v }))} />
            <DraftField label="Location" value={draft.location} onChange={(v) => setDraft((d) => ({ ...d, location: v }))} />
            <DraftField label="Estate" value={draft.estate} onChange={(v) => setDraft((d) => ({ ...d, estate: v }))} />
            <div className="wo-draft-field">
              <label>Priority</label>
              <select value={draft.priority} onChange={(e) => setDraft((d) => ({ ...d, priority: e.target.value }))}>
                {Object.entries(PRIORITY_COLORS).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
              </select>
            </div>
          </div>

          <div className="wo-draft-desc">
            <label>Full Description</label>
            <textarea value={draft.description} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} rows={3} />
          </div>

          <div className="wo-draft-actions">
            <button className="wo-btn wo-btn-secondary" onClick={() => { setDraft(null); setClarifications([]) }}>
              <X size={14} /> Discard
            </button>
            <button className="wo-btn wo-btn-primary" onClick={handleSubmit}>
              <Send size={14} /> Submit Work Order
            </button>
          </div>

          {submitted ? <div className="wo-success-msg"><CheckCircle size={16} /> Work order submitted successfully!</div> : null}
        </div>
      ) : null}
    </div>
  )
}
