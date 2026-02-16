import { useState, useEffect, useCallback } from 'react'
import {
  Cpu, CheckCircle2, XCircle, Clock, RefreshCw, AlertTriangle,
  Activity, Layers, GitBranch, BarChart3, Play, Building, Wrench,
  ClipboardList, Zap, ChevronRight, Lightbulb, Target
} from 'lucide-react'
import OrchestrationApi from '../services/orchestrationApi'

const fmt = v => `$${Math.round(v || 0).toLocaleString()}`
const pct = v => `${((v || 0) * 100).toFixed(0)}%`

const ICON_MAP = { building: Building, wrench: Wrench, clipboard: ClipboardList, zap: Zap }

const ALL_KPI_PHASES = [
  'Initialize Platform', 'Collect Data', 'Compute KPI Crews',
  'Enrich with CrewAI', 'Reconcile Double-Counting', 'Generate Scenarios', 'Build Dashboard',
]

// ── Shared Components ──────────────────────────────────────────────

function StatusBadge({ status }) {
  const config = {
    pending: { color: '#94a3b8', bg: '#f1f5f9', label: 'Pending' },
    running: { color: '#3b82f6', bg: '#dbeafe', label: 'Running' },
    completed: { color: '#22c55e', bg: '#dcfce7', label: 'Completed' },
    failed: { color: '#ef4444', bg: '#fee2e2', label: 'Failed' },
    error: { color: '#ef4444', bg: '#fee2e2', label: 'Error' },
  }
  const c = config[status] || config.pending
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 10px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 600,
      background: c.bg, color: c.color,
    }}>
      {status === 'running' && <RefreshCw size={12} className="spin" />}
      {status === 'completed' && <CheckCircle2 size={12} />}
      {(status === 'failed' || status === 'error') && <XCircle size={12} />}
      {c.label}
    </span>
  )
}

function PhaseProgress({ phases, phaseIndex }) {
  const total = phases.length
  const pctVal = total > 0 ? ((phaseIndex + 1) / total) * 100 : 0
  return (
    <div style={{ marginBottom: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: '0.8rem', color: '#475569', fontWeight: 600 }}>
          Phase {phaseIndex + 1} of {total}: {phases[phaseIndex] || ''}
        </span>
        <span style={{ fontSize: '0.8rem', color: '#64748b' }}>{Math.round(pctVal)}%</span>
      </div>
      <div style={{ background: '#e2e8f0', borderRadius: 8, height: 10, overflow: 'hidden' }}>
        <div style={{
          width: `${pctVal}%`, height: '100%', borderRadius: 8,
          background: 'linear-gradient(90deg, #3b82f6, #22c55e)',
          transition: 'width 0.5s ease',
        }} />
      </div>
      <div style={{ display: 'flex', gap: 3, marginTop: 6 }}>
        {phases.map((label, i) => (
          <div key={i} style={{
            flex: 1, height: 4, borderRadius: 2,
            background: i <= phaseIndex ? '#3b82f6' : '#e2e8f0',
            transition: 'background 0.3s',
          }} title={label} />
        ))}
      </div>
    </div>
  )
}

function CrewStatusTable({ crewStatuses }) {
  if (!crewStatuses || Object.keys(crewStatuses).length === 0) return null
  const entries = Object.entries(crewStatuses).sort((a, b) => {
    const order = { completed: 0, running: 1, pending: 2, failed: 3 }
    return (order[a[1].status] || 4) - (order[b[1].status] || 4)
  })
  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem', marginBottom: '1.5rem' }}>
      <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Layers size={18} /> KPI Crew Status
      </h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
            <th style={{ textAlign: 'left', padding: '0.5rem', color: '#64748b', fontWeight: 600 }}>KPI Crew</th>
            <th style={{ textAlign: 'center', padding: '0.5rem', color: '#64748b', fontWeight: 600 }}>Status</th>
            <th style={{ textAlign: 'right', padding: '0.5rem', color: '#64748b', fontWeight: 600 }}>Duration</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([kpiName, info]) => (
            <tr key={kpiName} style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: '0.5rem', color: '#1e293b', fontWeight: 500 }}>{kpiName.replace(/_/g, ' ')}</td>
              <td style={{ padding: '0.5rem', textAlign: 'center' }}><StatusBadge status={info.status || 'pending'} /></td>
              <td style={{ padding: '0.5rem', textAlign: 'right', color: '#64748b', fontSize: '0.8rem' }}>
                {info.duration_ms ? `${(info.duration_ms / 1000).toFixed(1)}s` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Pipeline Type Card ──────────────────────────────────────────────

function PipelineCard({ pipeline, selected, onClick, onRun, running }) {
  const Icon = ICON_MAP[pipeline.icon] || Cpu
  return (
    <div
      onClick={() => onClick(pipeline.pipeline_type)}
      style={{
        background: selected ? `${pipeline.color}10` : '#fff',
        border: selected ? `2px solid ${pipeline.color}` : '1px solid #e2e8f0',
        borderRadius: 12, padding: '1rem 1.25rem', cursor: 'pointer',
        transition: 'all 0.15s', position: 'relative',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: `${pipeline.color}20`, color: pipeline.color,
        }}>
          <Icon size={20} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: '0.9rem', color: '#1e293b' }}>{pipeline.name}</div>
          <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{pipeline.kpi_count} KPI crews</div>
        </div>
        <button
          onClick={e => { e.stopPropagation(); onRun(pipeline.pipeline_type) }}
          disabled={running}
          style={{
            padding: '0.35rem 0.75rem', borderRadius: 8, border: 'none', cursor: running ? 'wait' : 'pointer',
            background: pipeline.color, color: '#fff', fontSize: '0.75rem', fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 4, opacity: running ? 0.6 : 1,
          }}
        >
          {running ? <RefreshCw size={12} className="spin" /> : <Play size={12} />}
          {running ? 'Running...' : 'Run'}
        </button>
      </div>
      <p style={{ margin: 0, fontSize: '0.78rem', color: '#64748b', lineHeight: 1.4 }}>{pipeline.description}</p>
      {pipeline.run_count > 0 && (
        <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: 6 }}>
          {pipeline.run_count} previous run{pipeline.run_count !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  )
}

// ── Pipeline Run Result Detail ──────────────────────────────────────

function PipelineRunDetail({ run }) {
  if (!run) return (
    <div style={{ padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>
      <Target size={48} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
      <p>Select a pipeline and click <strong>Run</strong> to see results, or select a past run from history.</p>
    </div>
  )

  const summary = run.executive_summary || {}
  const phases = run.phases || ALL_KPI_PHASES
  const color = run.pipeline_color || '#3b82f6'

  return (
    <div>
      {/* Header */}
      <div style={{
        background: `linear-gradient(135deg, ${color}dd 0%, ${color}99 100%)`,
        borderRadius: 14, padding: '1.25rem 1.5rem', marginBottom: '1.25rem', color: '#fff',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>{run.pipeline_name || 'Pipeline Run'}</div>
          <StatusBadge status={run.status} />
        </div>
        {run.pipeline_goal && (
          <p style={{ margin: '0 0 0.75rem', fontSize: '0.82rem', opacity: 0.9, lineHeight: 1.4 }}>
            <Target size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            {run.pipeline_goal}
          </p>
        )}
        <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>{fmt(summary.total_savings_medium)}</div>
            <div style={{ fontSize: '0.7rem', opacity: 0.75 }}>Annual Savings</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>{summary.kpi_count || 0}</div>
            <div style={{ fontSize: '0.7rem', opacity: 0.75 }}>KPI Crews</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>{summary.approved_kpis || 0}</div>
            <div style={{ fontSize: '0.7rem', opacity: 0.75 }}>Approved</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>{pct(summary.avg_confidence)}</div>
            <div style={{ fontSize: '0.7rem', opacity: 0.75 }}>Avg Confidence</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>{run.duration_seconds?.toFixed(1) || '—'}s</div>
            <div style={{ fontSize: '0.7rem', opacity: 0.75 }}>Duration</div>
          </div>
        </div>
      </div>

      {/* Narrative */}
      {summary.narrative && (
        <div style={{
          background: '#f8fafc', borderRadius: 10, padding: '1rem', marginBottom: '1.25rem',
          fontSize: '0.85rem', color: '#475569', fontStyle: 'italic', borderLeft: `4px solid ${color}`,
        }}>
          {summary.narrative}
        </div>
      )}

      {/* Phase Progress */}
      <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem', marginBottom: '1.25rem' }}>
        <PhaseProgress phases={phases} phaseIndex={run.phase_index ?? phases.length - 1} />
      </div>

      {/* Scorecards */}
      {run.scorecards && run.scorecards.length > 0 && (
        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem', marginBottom: '1.25rem' }}>
          <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
            <BarChart3 size={18} /> KPI Scorecards
          </h3>
          <div style={{ display: 'grid', gap: '0.75rem' }}>
            {run.scorecards.map(sc => (
              <div key={sc.kpi_name} style={{
                display: 'flex', alignItems: 'center', gap: '1rem', padding: '0.75rem',
                background: '#f8fafc', borderRadius: 10, borderLeft: `4px solid ${sc.status === 'approved' ? '#22c55e' : '#eab308'}`,
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#1e293b' }}>{sc.display_name}</div>
                  <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 2 }}>{sc.narrative?.slice(0, 120)}{sc.narrative?.length > 120 ? '...' : ''}</div>
                </div>
                <div style={{ textAlign: 'right', minWidth: 100 }}>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1d4ed8' }}>{fmt(sc.savings_medium)}</div>
                  <div style={{ fontSize: '0.7rem', color: '#64748b' }}>conf: {pct(sc.confidence)}</div>
                </div>
                <StatusBadge status={sc.status} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Crew Status */}
      <CrewStatusTable crewStatuses={run.crew_statuses} />

      {/* Recommendations */}
      {run.recommendations && run.recommendations.length > 0 && (
        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: '1.25rem' }}>
          <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Lightbulb size={18} /> Recommendations
          </h3>
          {run.recommendations.map((rec, i) => (
            <div key={i} style={{
              display: 'flex', gap: '0.75rem', padding: '0.75rem', borderRadius: 8, marginBottom: '0.5rem',
              background: rec.impact === 'high' ? '#fef3c7' : '#f1f5f9',
              borderLeft: `3px solid ${rec.impact === 'high' ? '#f59e0b' : '#94a3b8'}`,
            }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: rec.impact === 'high' ? '#f59e0b' : '#64748b', color: '#fff', fontWeight: 700, fontSize: '0.75rem', flexShrink: 0,
              }}>{rec.priority}</div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#1e293b' }}>{rec.title}</div>
                <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 2 }}>{rec.rationale}</div>
                {rec.savings_impact > 0 && (
                  <div style={{ fontSize: '0.75rem', color: '#166534', fontWeight: 600, marginTop: 4 }}>
                    Impact: {fmt(rec.savings_impact)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Run History Sidebar Item ────────────────────────────────────────

function RunHistoryItem({ run, onClick, selected, color }) {
  const summary = run.executive_summary || {}
  return (
    <div
      onClick={() => onClick(run)}
      style={{
        background: selected ? `${color}10` : '#fff',
        border: selected ? `2px solid ${color}` : '1px solid #e2e8f0',
        borderRadius: 10, padding: '0.6rem 0.75rem', cursor: 'pointer',
        marginBottom: '0.4rem', transition: 'all 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: '0.8rem', color: '#1e293b' }}>
          {run.run_id?.slice(0, 8) || 'Run'}
        </span>
        <StatusBadge status={run.status} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748b', marginTop: 3 }}>
        <span>{run.started_at ? new Date(run.started_at).toLocaleString() : ''}</span>
        <span style={{ fontWeight: 600, color: '#1d4ed8' }}>{fmt(summary.total_savings_medium)}</span>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Main OrchestrationView
// ═══════════════════════════════════════════════════════════════════════

export default function OrchestrationView() {
  const [pipelines, setPipelines] = useState([])
  const [selectedType, setSelectedType] = useState(null)
  const [selectedRun, setSelectedRun] = useState(null)
  const [runHistory, setRunHistory] = useState({})
  const [legacyRuns, setLegacyRuns] = useState([])
  const [runningPipeline, setRunningPipeline] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Fetch pipeline types + legacy history
  const fetchData = useCallback(async () => {
    try {
      const [pipelinesResult, legacyResult] = await Promise.all([
        OrchestrationApi.getPipelines(),
        OrchestrationApi.getHistory(null, 10),
      ])
      if (pipelinesResult.ok) {
        setPipelines(pipelinesResult.data.pipelines || [])
      }
      if (legacyResult.ok) {
        setLegacyRuns(legacyResult.data.results || [])
      }
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  // Run a focused pipeline
  const handleRunPipeline = useCallback(async (pipelineType) => {
    setRunningPipeline(pipelineType)
    try {
      const { ok, data: result } = await OrchestrationApi.runPipeline(pipelineType)
      if (ok && result) {
        setRunHistory(prev => {
          const runs = [...(prev[pipelineType] || []), result]
          return { ...prev, [pipelineType]: runs }
        })
        setSelectedRun(result)
        setSelectedType(pipelineType)
        // Refresh pipeline list to update run counts
        fetchData()
      }
    } catch (e) {
      console.error('Pipeline run failed:', e)
    } finally {
      setRunningPipeline(null)
    }
  }, [fetchData])

  // Fetch history for a specific pipeline type
  const handleSelectType = useCallback(async (pipelineType) => {
    setSelectedType(pipelineType)
    setSelectedRun(null)
    try {
      const { ok, data } = await OrchestrationApi.getHistory(pipelineType, 10)
      if (ok && data) {
        setRunHistory(prev => ({ ...prev, [pipelineType]: data.runs || [] }))
        // Auto-select latest run if available
        if (data.runs && data.runs.length > 0) {
          setSelectedRun(data.runs[0])
        }
      }
    } catch (e) {
      console.error('History fetch failed:', e)
    }
  }, [])

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>Loading orchestration pipelines...</div>

  if (error) return (
    <div style={{ maxWidth: 600, margin: '3rem auto', padding: '2rem', textAlign: 'center' }}>
      <AlertTriangle size={48} style={{ color: '#ef4444', margin: '0 auto 1rem' }} />
      <h3 style={{ color: '#1e293b', margin: '0 0 0.5rem' }}>Orchestration Service Unavailable</h3>
      <p style={{ color: '#64748b', fontSize: '0.9rem' }}>{error}</p>
    </div>
  )

  const currentPipeline = pipelines.find(p => p.pipeline_type === selectedType)
  const currentHistory = runHistory[selectedType] || []
  const currentColor = currentPipeline?.color || '#3b82f6'

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: '1.5rem', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 0.75rem', color: '#1e293b' }}>
        <Cpu size={24} /> Orchestration Pipelines
      </h2>
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
        marginBottom: '1.25rem', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> View and trigger the <strong>multi-stage analysis pipelines</strong> —
        health scoring, fault hypothesis, decision policy, and composite analysis. See run history,
        execution timings, and step-by-step results for each pipeline type. Use this to manually
        initiate or re-run specific pipeline stages.
      </div>

      {/* Pipeline Type Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        {pipelines.map(p => (
          <PipelineCard
            key={p.pipeline_type}
            pipeline={p}
            selected={selectedType === p.pipeline_type}
            onClick={handleSelectType}
            onRun={handleRunPipeline}
            running={runningPipeline === p.pipeline_type}
          />
        ))}
      </div>

      {/* Selected pipeline detail area */}
      {selectedType ? (
        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '1.5rem' }}>
          {/* Run History Sidebar */}
          <div>
            <h3 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Clock size={16} /> Run History
            </h3>
            {currentHistory.length === 0 ? (
              <div style={{ padding: '1.5rem 1rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.82rem' }}>
                <Play size={24} style={{ margin: '0 auto 0.5rem', opacity: 0.3 }} />
                <p style={{ margin: 0 }}>Click <strong>Run</strong> to execute this pipeline</p>
              </div>
            ) : (
              currentHistory.map((run, i) => (
                <RunHistoryItem
                  key={run.run_id || i}
                  run={run}
                  onClick={setSelectedRun}
                  selected={selectedRun?.run_id === run.run_id}
                  color={currentColor}
                />
              ))
            )}
          </div>

          {/* Run Detail */}
          <PipelineRunDetail run={selectedRun} />
        </div>
      ) : (
        /* Legacy full-KPI runs when no pipeline type is selected */
        <div>
          <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Clock size={18} /> Recent Full-KPI Pipeline Runs
          </h3>
          {legacyRuns.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.85rem' }}>
              <Cpu size={32} style={{ margin: '0 auto 0.75rem', opacity: 0.3 }} />
              <p style={{ margin: '0 0 0.5rem', fontWeight: 600, color: '#64748b' }}>Select a pipeline above to get started</p>
              <p style={{ margin: 0 }}>Each pipeline focuses on a specific operational goal and runs only the relevant KPI crews.</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '0.75rem' }}>
              {legacyRuns.map((run, i) => (
                <div key={run.run_id || i} style={{
                  background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '0.75rem 1rem',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#1e293b' }}>
                      {(run.run_id || '').slice(0, 8)}
                    </span>
                    <StatusBadge status={run.status} />
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 4 }}>
                    {run.timestamp ? new Date(run.timestamp).toLocaleString() : ''}
                    {run.kpi_count ? ` · ${run.kpi_count} KPIs` : ''}
                    {run.total_savings_medium ? ` · ${fmt(run.total_savings_medium)}` : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
