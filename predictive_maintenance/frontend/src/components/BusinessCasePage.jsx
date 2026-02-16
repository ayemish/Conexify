import { useState, useEffect, useRef } from 'react'
import {
  Briefcase, CheckSquare, Square, RefreshCw, FileText, Download,
  TrendingUp, DollarSign, AlertTriangle, Zap, ChevronDown, ChevronUp,
  Sparkles, Edit3, Save, BarChart3, Shield, Clock
} from 'lucide-react'

const API_BASE = '/api/v1'
const fmt = (v) => {
  if (v == null || isNaN(v)) return '$0'
  return '$' + Math.round(v).toLocaleString()
}

const card = {
  background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0',
  padding: '1.25rem', marginBottom: '1rem',
}
const btnPrimary = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '0.5rem 1.25rem', borderRadius: 8, border: 'none',
  background: '#1d4ed8', color: '#fff', cursor: 'pointer',
  fontWeight: 600, fontSize: '0.85rem',
}
const btnSecondary = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '0.4rem 1rem', borderRadius: 8,
  border: '1px solid #e2e8f0', background: '#fff',
  color: '#475569', cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600,
}

export default function BusinessCasePage({ embedded = false }) {
  const [dashboardData, setDashboardData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedRecs, setSelectedRecs] = useState(new Set())
  const [generating, setGenerating] = useState(false)
  const [businessCase, setBusinessCase] = useState(null)
  const [editMode, setEditMode] = useState(false)
  const [editedText, setEditedText] = useState('')
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState(null)
  const textRef = useRef(null)

  // Load KPI dashboard data (ROI, recommendations, budget)
  useEffect(() => {
    async function loadData() {
      setLoading(true)
      try {
        const res = await fetch(`${API_BASE}/kpi/default/dashboard`)
        if (!res.ok) throw new Error('Failed to load dashboard data')
        const data = await res.json()
        setDashboardData(data)
        // Auto-select all recommendations
        const recs = data.decision_advisory?.strategic_recommendations || []
        setSelectedRecs(new Set(recs.map((_, i) => i)))
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  const recommendations = dashboardData?.decision_advisory?.strategic_recommendations || []
  const roi = dashboardData?.roi || {}
  const budget = dashboardData?.budget || {}
  const execSummary = dashboardData?.executive_summary || {}
  const scorecards = dashboardData?.scorecards || []

  const toggleRec = (idx) => {
    setSelectedRecs(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedRecs.size === recommendations.length) {
      setSelectedRecs(new Set())
    } else {
      setSelectedRecs(new Set(recommendations.map((_, i) => i)))
    }
  }

  const selectedTotal = [...selectedRecs].reduce((s, i) => {
    return s + (recommendations[i]?.savings_impact || 0)
  }, 0)

  // Generate business case
  const handleGenerate = async () => {
    if (selectedRecs.size === 0) return
    setGenerating(true)
    setError(null)
    setBusinessCase(null)

    const selectedItems = [...selectedRecs].map(i => {
      const r = recommendations[i]
      // Try to find matching scorecard for confidence
      const sc = scorecards.find(s => s.kpi_name === r.kpi_name)
      return {
        title: r.title || '',
        kpi_name: r.kpi_name || '',
        savings_impact: r.savings_impact || 0,
        rationale: r.rationale || '',
        priority: r.priority || 0,
        confidence: sc?.confidence || 0,
        category: sc?.category || '',
      }
    })

    try {
      const res = await fetch(`${API_BASE}/business-case/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_recommendations: selectedItems,
          roi_summary: roi,
          budget: budget,
          executive_summary: execSummary,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Generation failed')
      }
      const result = await res.json()
      setBusinessCase(result)
      setEditedText(result.business_case_text)
    } catch (e) {
      setError(e.message)
    } finally {
      setGenerating(false)
    }
  }

  // Export as Word doc
  const handleExport = async () => {
    setExporting(true)
    try {
      const textToExport = editMode ? editedText : (businessCase?.business_case_text || '')
      const res = await fetch(`${API_BASE}/business-case/export-docx`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ business_case_text: textToExport }),
      })
      if (!res.ok) throw new Error('Export failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const contentDisp = res.headers.get('content-disposition') || ''
      const match = contentDisp.match(/filename=(.+)/)
      a.href = url
      a.download = match ? match[1] : `Business_Case_${new Date().toISOString().slice(0, 10)}.docx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e.message)
    } finally {
      setExporting(false)
    }
  }

  // Simple markdown-to-HTML renderer
  const renderMarkdown = (text) => {
    if (!text) return null
    const lines = text.split('\n')
    const elements = []
    let inTable = false
    let tableRows = []

    const flushTable = () => {
      if (tableRows.length > 0) {
        const headerCells = tableRows[0]
        const bodyRows = tableRows.slice(2) // skip separator row
        elements.push(
          <div key={`table-${elements.length}`} style={{ overflowX: 'auto', marginBottom: '1rem' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                  {headerCells.map((c, j) => (
                    <th key={j} style={{ textAlign: 'left', padding: '0.4rem 0.6rem', color: '#475569', fontWeight: 600 }}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bodyRows.map((row, ri) => (
                  <tr key={ri} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    {row.map((cell, ci) => (
                      <td key={ci} style={{ padding: '0.4rem 0.6rem', color: '#1e293b' }}>{renderInline(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
        tableRows = []
      }
      inTable = false
    }

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      const trimmed = line.trim()

      if (trimmed.startsWith('|')) {
        inTable = true
        const cells = trimmed.split('|').filter(Boolean).map(c => c.trim())
        tableRows.push(cells)
        continue
      } else if (inTable) {
        flushTable()
      }

      if (!trimmed) {
        elements.push(<div key={i} style={{ height: '0.5rem' }} />)
      } else if (trimmed.startsWith('## ')) {
        elements.push(
          <h2 key={i} style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1e293b', margin: '1.5rem 0 0.5rem', borderBottom: '2px solid #e2e8f0', paddingBottom: '0.4rem' }}>
            {trimmed.slice(3)}
          </h2>
        )
      } else if (trimmed.startsWith('### ')) {
        elements.push(
          <h3 key={i} style={{ fontSize: '0.95rem', fontWeight: 700, color: '#334155', margin: '1rem 0 0.4rem' }}>
            {trimmed.slice(4)}
          </h3>
        )
      } else if (trimmed.startsWith('# ')) {
        elements.push(
          <h1 key={i} style={{ fontSize: '1.4rem', fontWeight: 700, color: '#0f172a', margin: '1.5rem 0 0.75rem' }}>
            {trimmed.slice(2)}
          </h1>
        )
      } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        elements.push(
          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 4, paddingLeft: '1rem' }}>
            <span style={{ color: '#94a3b8' }}>•</span>
            <span style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.5 }}>{renderInline(trimmed.slice(2))}</span>
          </div>
        )
      } else {
        elements.push(
          <p key={i} style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.6, margin: '0.25rem 0' }}>
            {renderInline(trimmed)}
          </p>
        )
      }
    }
    if (inTable) flushTable()
    return elements
  }

  const renderInline = (text) => {
    if (!text) return text
    const parts = text.split(/(\*\*[^*]+\*\*)/)
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i}>{part.slice(2, -2)}</strong>
      }
      return part
    })
  }

  if (loading) return (
    <div style={{ padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>
      <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 1rem' }} />
      <p>Loading analysis data...</p>
    </div>
  )

  if (error && !dashboardData) return (
    <div style={{ maxWidth: 600, margin: '3rem auto', padding: '2rem', textAlign: 'center' }}>
      <AlertTriangle size={48} style={{ color: '#ef4444', margin: '0 auto 1rem' }} />
      <h3 style={{ color: '#1e293b', margin: '0 0 0.5rem' }}>Unable to Load Data</h3>
      <p style={{ color: '#64748b', fontSize: '0.9rem' }}>{error}</p>
      <p style={{ color: '#94a3b8', fontSize: '0.82rem', marginTop: '0.5rem' }}>
        Run the Estate Intelligence analysis first to generate KPI recommendations.
      </p>
    </div>
  )

  return (
    <div style={embedded ? {} : { maxWidth: 1200, margin: '0 auto', padding: '1.5rem', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      {/* Header — hidden when embedded */}
      {!embedded && (
        <>
          <div style={{ marginBottom: '1.5rem' }}>
            <h1 style={{ margin: 0, fontSize: '1.5rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 10 }}>
              <Briefcase size={28} style={{ color: '#3b82f6' }} /> Business Case Builder
            </h1>
            <p style={{ margin: '0.25rem 0 0', color: '#64748b', fontSize: '0.85rem' }}>
              Select budget recommendations from the KPI analysis, then generate a professional business case document.
            </p>
          </div>

          <div style={{
            background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
            padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
            marginBottom: '1rem', lineHeight: 1.6,
          }}>
            <strong>What this page does:</strong> Pulls <strong>strategic recommendations from KPI analysis</strong>,
            lets you select which to include, then generates a <strong>professional business case document</strong> (Word export)
            with ROI justification, savings projections, and implementation rationale — ready for executive review.
          </div>
        </>
      )}

      {/* ROI Overview */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '1.25rem' }}>
        {[
          { icon: DollarSign, label: 'Annual Savings', value: fmt(execSummary.total_savings_medium), color: '#22c55e' },
          { icon: Clock, label: 'Payback', value: `${roi.payback_months || 0} mo`, color: '#3b82f6' },
          { icon: TrendingUp, label: 'ROI Multiple', value: `${roi.savings_to_cost_multiple || 0}x`, color: '#8b5cf6' },
          { icon: BarChart3, label: 'KPIs Analyzed', value: execSummary.kpi_count || 0, color: '#f59e0b' },
        ].map((c, i) => {
          const Icon = c.icon
          return (
            <div key={i} style={card}>
              <Icon size={18} style={{ color: c.color, marginBottom: 8 }} />
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#1e293b' }}>{c.value}</div>
              <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{c.label}</div>
            </div>
          )
        })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: businessCase ? '380px 1fr' : '1fr', gap: '1.25rem' }}>
        {/* Left: Recommendations Selection */}
        <div>
          <div style={card}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileText size={18} /> Budget Recommendations
              </h3>
              <button onClick={toggleAll} style={{ ...btnSecondary, padding: '0.25rem 0.5rem', fontSize: '0.72rem' }}>
                {selectedRecs.size === recommendations.length ? 'Deselect All' : 'Select All'}
              </button>
            </div>

            {recommendations.length === 0 ? (
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', textAlign: 'center', padding: '1.5rem 0' }}>
                No recommendations available. Run the Estate Intelligence analysis first.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {recommendations.map((rec, i) => {
                  const isSelected = selectedRecs.has(i)
                  const sc = scorecards.find(s => s.kpi_name === rec.kpi_name)
                  return (
                    <div
                      key={i}
                      onClick={() => toggleRec(i)}
                      style={{
                        display: 'flex', gap: '0.75rem', padding: '0.75rem',
                        borderRadius: 8, cursor: 'pointer', transition: 'all 0.15s',
                        border: isSelected ? '2px solid #3b82f6' : '1px solid #e2e8f0',
                        background: isSelected ? '#eff6ff' : '#fff',
                      }}
                    >
                      <div style={{ flexShrink: 0, paddingTop: 2 }}>
                        {isSelected
                          ? <CheckSquare size={18} style={{ color: '#3b82f6' }} />
                          : <Square size={18} style={{ color: '#cbd5e1' }} />
                        }
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.85rem', marginBottom: 2 }}>
                          {rec.title}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: '#64748b', marginBottom: 4 }}>
                          {rec.rationale?.slice(0, 120)}{rec.rationale?.length > 120 ? '...' : ''}
                        </div>
                        <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.7rem' }}>
                          <span style={{ color: '#16a34a', fontWeight: 600 }}>{fmt(rec.savings_impact)}/yr</span>
                          <span style={{ color: '#64748b' }}>Priority {rec.priority}</span>
                          {sc && <span style={{ color: '#64748b' }}>Confidence {(sc.confidence * 100).toFixed(0)}%</span>}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Selection summary */}
            <div style={{ marginTop: '1rem', padding: '0.75rem', background: '#f8fafc', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.82rem', color: '#475569' }}>
                <strong>{selectedRecs.size}</strong> of {recommendations.length} selected
              </span>
              <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#1d4ed8' }}>
                {fmt(selectedTotal)}/yr
              </span>
            </div>

            {/* Generate button */}
            <div style={{ marginTop: '1rem', display: 'flex', gap: 8 }}>
              <button
                style={{
                  ...btnPrimary, flex: 1, justifyContent: 'center',
                  opacity: selectedRecs.size === 0 || generating ? 0.6 : 1,
                }}
                onClick={handleGenerate}
                disabled={selectedRecs.size === 0 || generating}
              >
                {generating
                  ? <><RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> Generating...</>
                  : <><Sparkles size={14} /> Generate Business Case</>
                }
              </button>
            </div>

            {error && (
              <div style={{ marginTop: '0.75rem', padding: '0.5rem 0.75rem', background: '#fef2f2', borderRadius: 6, fontSize: '0.78rem', color: '#991b1b', display: 'flex', alignItems: 'center', gap: 6 }}>
                <AlertTriangle size={14} /> {error}
              </div>
            )}
          </div>
        </div>

        {/* Right: Generated Business Case */}
        {businessCase && (
          <div style={card}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Briefcase size={18} /> Generated Business Case
              </h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  style={btnSecondary}
                  onClick={() => {
                    if (editMode) {
                      setBusinessCase(prev => ({ ...prev, business_case_text: editedText }))
                    }
                    setEditMode(!editMode)
                  }}
                >
                  {editMode ? <><Save size={14} /> Save Edits</> : <><Edit3 size={14} /> Edit</>}
                </button>
                <button
                  style={{ ...btnPrimary, background: '#16a34a' }}
                  onClick={handleExport}
                  disabled={exporting}
                >
                  {exporting
                    ? <><RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> Exporting...</>
                    : <><Download size={14} /> Download .docx</>
                  }
                </button>
              </div>
            </div>

            {/* Metadata bar */}
            <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '1rem', padding: '0.5rem 0.75rem', background: '#f8fafc', borderRadius: 6, fontSize: '0.72rem', color: '#64748b' }}>
              <span>Generated: {new Date(businessCase.generated_at).toLocaleString()}</span>
              <span>Model: {businessCase.model_used}</span>
              <span>Sections: {businessCase.sections?.length || 0}</span>
            </div>

            {/* Business case content */}
            {editMode ? (
              <textarea
                ref={textRef}
                value={editedText}
                onChange={e => setEditedText(e.target.value)}
                style={{
                  width: '100%', minHeight: 600, padding: '1rem', borderRadius: 8,
                  border: '1px solid #e2e8f0', fontSize: '0.85rem', lineHeight: 1.6,
                  fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
                  resize: 'vertical', outline: 'none', color: '#334155',
                }}
              />
            ) : (
              <div style={{ maxHeight: 700, overflowY: 'auto', padding: '0.5rem' }}>
                {renderMarkdown(businessCase.business_case_text)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
