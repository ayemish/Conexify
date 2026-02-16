import { useState, useEffect, useRef, useCallback } from 'react'
import {
  MessageSquare, Send, Loader2, Trash2, Zap, BarChart3, Wrench, AlertTriangle,
  TrendingUp, CheckCircle2, XCircle, Activity, Leaf, Building, ClipboardList,
  Thermometer, DollarSign, Shield, Layers, ChevronRight
} from 'lucide-react'
import AdvisorApiService from '../services/advisorApi'

const TOPICS = [
  {
    id: 'energy', label: 'Energy', icon: Zap, color: '#3b82f6',
    desc: 'Energy reduction, cost sensitivity, condenser fouling',
    actions: [
      { label: 'Run energy reduction analysis', icon: Zap },
      { label: 'What if utility rates increase 20%?', icon: DollarSign },
      { label: 'Estimate condenser fouling impact', icon: Thermometer },
    ],
  },
  {
    id: 'assets', label: 'Asset Health', icon: Activity, color: '#22c55e',
    desc: 'Fleet health, failure prediction, uptime, critical triage',
    actions: [
      { label: 'Show fleet health summary', icon: Activity },
      { label: 'Which assets are critical?', icon: AlertTriangle },
      { label: 'Run uptime maximization scenario', icon: TrendingUp },
      { label: 'Analyze common failure modes across the fleet', icon: ClipboardList },
    ],
  },
  {
    id: 'maintenance', label: 'Maintenance', icon: Wrench, color: '#f59e0b',
    desc: 'Work orders, PM optimization, service bureau, deferral risk',
    actions: [
      { label: 'Run work order optimization scenario', icon: ClipboardList },
      { label: 'Optimize PM intervals using condition data', icon: Wrench },
      { label: 'How much can we save reducing service dispatches?', icon: DollarSign },
      { label: 'What is the risk of deferring maintenance 90 days?', icon: AlertTriangle },
    ],
  },
  {
    id: 'capex', label: 'CapEx', icon: Building, color: '#8b5cf6',
    desc: 'Replacement planning, repair vs replace, budget sensitivity',
    actions: [
      { label: 'Run CapEx planning scenario', icon: BarChart3 },
      { label: 'Should we repair or replace aging RTUs?', icon: Building },
      { label: 'How does a $500K vs $1M budget change fleet NPV?', icon: DollarSign },
    ],
  },
  {
    id: 'food_safety', label: 'Food Safety', icon: Thermometer, color: '#ef4444',
    desc: 'Temperature excursions, cold chain integrity, compliance',
    actions: [
      { label: 'Run food safety protection scenario', icon: AlertTriangle },
      { label: 'Assess cold chain integrity across refrigeration', icon: Thermometer },
      { label: 'How many temperature excursions occurred this month?', icon: Shield },
    ],
  },
  {
    id: 'esg', label: 'ESG & Carbon', icon: Leaf, color: '#10b981',
    desc: 'Carbon reduction, refrigerant GWP, sustainability reporting',
    actions: [
      { label: 'Generate ESG compliance report', icon: Leaf },
      { label: 'Model carbon reduction from fleet optimization', icon: TrendingUp },
      { label: 'Plan refrigerant transition from R-410A', icon: Shield },
    ],
  },
]

function ConfidenceBadge({ confidence }) {
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  let color = '#ef4444'
  if (pct >= 80) color = '#22c55e'
  else if (pct >= 60) color = '#eab308'
  return (
    <span style={{ fontSize: 11, color, fontWeight: 600, marginLeft: 8 }}>
      {pct}% confidence
    </span>
  )
}

function AgentSourceBadge({ source }) {
  if (!source) return null
  const colors = {
    openai: '#6366f1',
    tool_chain: '#8b5cf6',
    scenario_executor: '#f59e0b',
    state_lookup: '#06b6d4',
    rag_fallback: '#64748b',
    offline: '#94a3b8',
    mock: '#a1a1aa',
    error: '#ef4444',
  }
  return (
    <span style={{
      fontSize: 10, color: colors[source] || '#94a3b8',
      background: `${colors[source] || '#94a3b8'}18`,
      padding: '1px 6px', borderRadius: 4, marginLeft: 6, fontWeight: 500,
    }}>
      {source}
    </span>
  )
}

function renderStructuredData(data) {
  if (!data) return null

  // Scenario execution result
  if (data.success !== undefined && data.decision_recommendation) {
    const dr = data.decision_recommendation
    return (
      <div className="advisor-structured-data">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          {data.success
            ? <CheckCircle2 size={16} color="#22c55e" />
            : <XCircle size={16} color="#ef4444" />}
          <strong style={{ fontSize: 13 }}>Scenario: {data.scenario_id}</strong>
        </div>
        {dr.executive_summary && <p style={{ fontSize: 12, margin: '4px 0 8px' }}>{dr.executive_summary}</p>}
        {dr.recommended_actions?.length > 0 && (
          <div style={{ marginBottom: 6 }}>
            <strong style={{ fontSize: 11 }}>Recommended Actions:</strong>
            <ul style={{ margin: '2px 0', paddingLeft: 18, fontSize: 12 }}>
              {dr.recommended_actions.map((a, i) => (
                <li key={i}><strong>{a.action}</strong> — {a.description} <span style={{ color: '#6366f1' }}>({a.impact})</span></li>
              ))}
            </ul>
          </div>
        )}
        {dr.total_expected_impact != null && (
          <div style={{ fontSize: 12, display: 'flex', gap: 16 }}>
            <span><strong>Impact:</strong> ${Number(dr.total_expected_impact).toLocaleString()}</span>
            <span><strong>Confidence:</strong> {Math.round((dr.overall_confidence || 0) * 100)}%</span>
            <span><strong>Risk:</strong> {dr.risk_assessment}</span>
          </div>
        )}
      </div>
    )
  }

  // Fleet health state
  if (data.fleet_summary) {
    const fs = data.fleet_summary
    return (
      <div className="advisor-structured-data">
        <strong style={{ fontSize: 13 }}>Fleet Health Summary</strong>
        <table style={{ width: '100%', fontSize: 12, marginTop: 6, borderCollapse: 'collapse' }}>
          <tbody>
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: '4px 8px', fontWeight: 600 }}>Total Assets</td>
              <td style={{ textAlign: 'right', padding: '4px 8px' }}>{fs.total_assets}</td>
            </tr>
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: '4px 8px', fontWeight: 600 }}>Avg Health Score</td>
              <td style={{ textAlign: 'right', padding: '4px 8px' }}>{fs.avg_health_score?.toFixed(1)}</td>
            </tr>
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: '4px 8px', fontWeight: 600 }}>Degraded Assets</td>
              <td style={{ textAlign: 'right', padding: '4px 8px', color: fs.degraded_count > 0 ? '#f59e0b' : undefined }}>{fs.degraded_count}</td>
            </tr>
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: '4px 8px', fontWeight: 600 }}>Critical Assets</td>
              <td style={{ textAlign: 'right', padding: '4px 8px', color: fs.critical_count > 0 ? '#ef4444' : undefined }}>{fs.critical_count}</td>
            </tr>
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: '4px 8px', fontWeight: 600 }}>Avg RUL</td>
              <td style={{ textAlign: 'right', padding: '4px 8px' }}>{Number(fs.avg_rul_hours).toLocaleString()}h</td>
            </tr>
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: '4px 8px', fontWeight: 600 }}>Open Work Orders</td>
              <td style={{ textAlign: 'right', padding: '4px 8px' }}>{fs.open_work_orders}</td>
            </tr>
            <tr>
              <td style={{ padding: '4px 8px', fontWeight: 600 }}>Reactive WO %</td>
              <td style={{ textAlign: 'right', padding: '4px 8px' }}>{Math.round((fs.reactive_wo_pct || 0) * 100)}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    )
  }

  // Tool chain results
  if (typeof data === 'object' && !Array.isArray(data)) {
    const toolKeys = Object.keys(data).filter(k => typeof data[k] === 'object')
    if (toolKeys.length > 0 && toolKeys.some(k => k.includes('_'))) {
      return (
        <div className="advisor-structured-data">
          {toolKeys.map(k => (
            <details key={k} style={{ marginBottom: 4 }}>
              <summary style={{ fontSize: 12, cursor: 'pointer', fontWeight: 600 }}>{k}</summary>
              <pre style={{ fontSize: 11, overflow: 'auto', maxHeight: 200, margin: '4px 0', padding: 6, background: '#f8fafc', borderRadius: 4 }}>
                {JSON.stringify(data[k], null, 2)}
              </pre>
            </details>
          ))}
        </div>
      )
    }
  }

  return null
}

export default function ScenarioAdvisorChat() {
  const [activeTopic, setActiveTopic] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

  // Load status on mount
  useEffect(() => {
    AdvisorApiService.getStatus()
      .then(setStatus)
      .catch(() => setStatus({ status: 'offline', openai_available: false }))
  }, [])

  // Create a single unified session on mount
  useEffect(() => {
    AdvisorApiService.createSession('maintenance')
      .then(res => {
        setSessionId(res.session_id)
        setMessages([{
          role: 'assistant',
          content: 'Welcome to LoweConex iQ Advisor. I can help with energy optimization, asset health, maintenance planning, CapEx decisions, food safety, and ESG reporting. Select a topic below or ask me anything.',
          agent_source: 'system',
          confidence: 1.0,
        }])
      })
      .catch(err => setError(err.message))
  }, [])

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || !sessionId || loading) return
    const userMsg = { role: 'user', content: text.trim() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const res = await AdvisorApiService.sendMessage(sessionId, text.trim())
      const r = res.response
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: r.message,
        ecosystem: r.ecosystem,
        scenario_ids: r.scenario_ids,
        data: r.data,
        actions: r.actions,
        agent_source: r.agent_source,
        confidence: r.confidence,
      }])
    } catch (err) {
      setError(err.message)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.message}`,
        agent_source: 'error',
        confidence: 0,
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }, [sessionId, loading])

  const handleQuickAction = useCallback((label) => {
    sendMessage(label)
  }, [sendMessage])

  const handleNewSession = useCallback(() => {
    setMessages([])
    setSessionId(null)
    setActiveTopic(null)
    AdvisorApiService.createSession('maintenance')
      .then(res => {
        setSessionId(res.session_id)
        setMessages([{
          role: 'assistant',
          content: 'New session started. Select a topic or ask me anything about your HVAC/R fleet.',
          agent_source: 'system',
          confidence: 1.0,
        }])
      })
      .catch(err => setError(err.message))
  }, [])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }, [input, sendMessage])

  const currentTopic = TOPICS.find(t => t.id === activeTopic)
  const quickActions = currentTopic ? currentTopic.actions : []

  return (
    <div className="advisor-chat-container">
      {/* Header */}
      <div className="advisor-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Layers size={18} style={{ color: '#60a5fa' }} />
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
            <span>LoweConex </span><span style={{ color: '#60a5fa' }}>iQ</span>
            <span style={{ fontWeight: 400, color: '#64748b', fontSize: 13, marginLeft: 6 }}>Advisor</span>
          </h2>
          {status && (
            <span style={{
              fontSize: 10, padding: '2px 8px', borderRadius: 10,
              background: status.openai_available ? '#dcfce7' : '#fef9c3',
              color: status.openai_available ? '#166534' : '#854d0e',
            }}>
              {status.openai_available ? 'Online' : 'Offline'}
            </span>
          )}
        </div>
        <button className="advisor-icon-btn" onClick={handleNewSession} title="New session">
          <Trash2 size={14} />
        </button>
      </div>

      {/* Page Description */}
      <div style={{
        padding: '8px 12px', margin: '0 12px 4px', borderRadius: 8,
        background: '#f0f9ff', border: '1px solid #bae6fd',
        fontSize: '0.75rem', color: '#0c4a6e', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> Conversational AI advisor for your HVAC/R fleet.
        Ask questions about energy optimization, asset health, maintenance planning, CapEx decisions,
        food safety, or ESG reporting. The advisor uses RAG-powered context from your telemetry
        and KPI data to provide targeted, data-backed recommendations.
      </div>

      {/* Messages */}
      <div className="advisor-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`advisor-msg ${msg.role}`}>
            <div className="advisor-msg-bubble">
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.55 }}>{msg.content}</div>
              {msg.role === 'assistant' && msg.data && renderStructuredData(msg.data)}
              {msg.role === 'assistant' && (
                <div style={{ display: 'flex', alignItems: 'center', marginTop: 4 }}>
                  <ConfidenceBadge confidence={msg.confidence} />
                  <AgentSourceBadge source={msg.agent_source} />
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="advisor-msg assistant">
            <div className="advisor-msg-bubble" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Loader2 size={14} className="advisor-spin" />
              <span style={{ fontSize: 12, color: '#94a3b8' }}>Thinking...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Topic Pills + Quick Actions */}
      <div style={{ borderTop: '1px solid #e2e8f0', padding: '8px 12px 4px' }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: quickActions.length > 0 ? 6 : 0 }}>
          {TOPICS.map(topic => {
            const Icon = topic.icon
            const isActive = activeTopic === topic.id
            return (
              <button
                key={topic.id}
                onClick={() => setActiveTopic(isActive ? null : topic.id)}
                title={topic.desc}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '4px 10px', borderRadius: 16, border: 'none', cursor: 'pointer',
                  fontSize: 12, fontWeight: 600, transition: 'all 0.15s',
                  background: isActive ? `${topic.color}18` : '#f1f5f9',
                  color: isActive ? topic.color : '#64748b',
                  outline: isActive ? `2px solid ${topic.color}40` : 'none',
                }}
              >
                <Icon size={13} /> {topic.label}
              </button>
            )
          })}
        </div>
        {quickActions.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '2px 0 4px' }}>
            {quickActions.map((action, i) => {
              const Icon = action.icon
              return (
                <button
                  key={i}
                  className="advisor-quick-btn"
                  onClick={() => handleQuickAction(action.label)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '5px 10px', borderRadius: 8, border: '1px solid #e2e8f0',
                    background: '#fff', cursor: 'pointer', fontSize: 12, color: '#334155',
                    textAlign: 'left', width: '100%', transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                  onMouseLeave={e => e.currentTarget.style.background = '#fff'}
                >
                  <Icon size={13} style={{ color: currentTopic?.color || '#64748b', flexShrink: 0 }} />
                  <span style={{ flex: 1 }}>{action.label}</span>
                  <ChevronRight size={12} style={{ color: '#94a3b8' }} />
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: '6px 16px', background: '#fef2f2', color: '#b91c1c', fontSize: 12 }}>
          {error}
        </div>
      )}

      {/* Input */}
      <div className="advisor-input-bar">
        <textarea
          ref={inputRef}
          className="advisor-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about energy, assets, maintenance, CapEx, food safety, ESG..."
          rows={1}
          disabled={loading || !sessionId}
        />
        <button
          className="advisor-send-btn"
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim() || !sessionId}
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
