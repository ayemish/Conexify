/**
 * Governance Dashboard
 *
 * Exposes the 12 loweconex_platform governance modules to the frontend:
 * data quality, lineage, M&V verification, MLOps, AI risk, security,
 * operating model, benchmarking, agent ops, semantic, twin versioning.
 */

import { useState, useEffect } from 'react'
import {
  Shield, Database, GitBranch, Activity, AlertTriangle,
  CheckCircle2, XCircle, RefreshCw, Layers, BarChart3,
  Lock, Users, Cpu, BookOpen, Loader2
} from 'lucide-react'
import { safeRequest } from '../services/apiClient'

const MODULE_CONFIG = {
  lineage:          { icon: GitBranch,     color: '#8b5cf6', label: 'Data Lineage',         desc: 'OpenLineage-compatible digital thread tracking' },
  data_quality:     { icon: Database,      color: '#3b82f6', label: 'Data Quality',          desc: 'ISO 25012 quality gates and expectation suites' },
  mlops:            { icon: Cpu,           color: '#22c55e', label: 'MLOps',                 desc: 'Model registry, versioning, and drift detection' },
  ai_risk:          { icon: AlertTriangle, color: '#ef4444', label: 'AI Risk',               desc: 'NIST AI RMF framework and prompt guards' },
  agent_ops:        { icon: Activity,      color: '#f59e0b', label: 'Agent Ops',             desc: 'Golden tests, runbooks, and replay engine' },
  security:         { icon: Lock,          color: '#991b1b', label: 'Security',              desc: 'ISO 27001, OWASP checks, SLSA provenance' },
  semantic:         { icon: BookOpen,      color: '#0ea5e9', label: 'Semantic Model',        desc: 'Brick/Haystack ontology governance' },
  twin_versioning:  { icon: Layers,        color: '#6366f1', label: 'Twin Versioning',       desc: 'DTDL-inspired schema registry and migrations' },
  mv_verification:  { icon: BarChart3,     color: '#14b8a6', label: 'M&V Verification',      desc: 'IPMVP measurement and verification engine' },
  operating_model:  { icon: Users,         color: '#ec4899', label: 'Operating Model',       desc: 'RACI matrix, SLAs, and review scheduling' },
  benchmarking:     { icon: BarChart3,     color: '#84cc16', label: 'Benchmarking',          desc: 'Cohort governance and normalization' },
  execution:        { icon: CheckCircle2,  color: '#f97316', label: 'Execution Engine',      desc: 'Closed-loop CMMS integration and tracking' },
}

function ModuleCard({ moduleId, config, status, onRefresh }) {
  const Icon = config.icon
  const isActive = status === 'active'

  return (
    <div style={{
      background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0',
      padding: '1.25rem', position: 'relative', overflow: 'hidden',
    }}>
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 3,
        background: isActive ? config.color : '#e2e8f0',
      }} />
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10, flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: `${config.color}15`, color: config.color,
        }}>
          <Icon size={20} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <h4 style={{ margin: 0, fontSize: '0.9rem', color: '#1e293b' }}>{config.label}</h4>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 3,
              padding: '1px 8px', borderRadius: 10, fontSize: '0.65rem', fontWeight: 600,
              background: isActive ? '#dcfce7' : '#f1f5f9',
              color: isActive ? '#166534' : '#94a3b8',
            }}>
              {isActive ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
              {isActive ? 'Active' : 'Inactive'}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: '0.78rem', color: '#64748b', lineHeight: 1.4 }}>
            {config.desc}
          </p>
        </div>
      </div>
    </div>
  )
}

export default function GovernanceDashboard() {
  const [governance, setGovernance] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchGovernance = async () => {
    setLoading(true)
    try {
      const { ok, data } = await safeRequest('/api/v1/governance/status')
      if (ok) {
        setGovernance(data)
      } else {
        // Fallback: check which modules are importable via KPI governance check
        const kpiRes = await safeRequest('/api/v1/kpi/dashboard/default')
        if (kpiRes.ok && kpiRes.data?.governance) {
          setGovernance({
            modules: (kpiRes.data.governance.modules_active || []).reduce((acc, m) => {
              acc[m] = { status: 'active' }
              return acc
            }, {}),
          })
        } else {
          setGovernance({ modules: {} })
        }
      }
    } catch {
      setGovernance({ modules: {} })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchGovernance() }, [])

  if (loading) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>
        <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 1rem' }} />
        <p>Loading governance status...</p>
      </div>
    )
  }

  const modules = governance?.modules || {}
  const activeModules = Object.entries(MODULE_CONFIG).filter(([id]) =>
    modules[id]?.status === 'active' || (Array.isArray(governance?.modules_active) && governance.modules_active.includes(id))
  )
  const allModuleEntries = Object.entries(MODULE_CONFIG)

  return (
    <div style={{
      maxWidth: 1200, margin: '0 auto', padding: '1.5rem',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8, color: '#1e293b' }}>
          <Shield size={24} /> Governance & Compliance
        </h2>
        <button
          onClick={fetchGovernance}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0.4rem 1rem', borderRadius: 8, border: '1px solid #e2e8f0',
            background: '#fff', color: '#475569', fontSize: '0.8rem', fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Page Description */}
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
        marginBottom: '1rem', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> Shows the status of <strong>12 enterprise governance modules</strong> —
        data lineage, semantic ontology, schema versioning, M&amp;V verification, MLOps, AI risk management,
        data quality, execution tracking, security controls, operating model, benchmarking, and agent ops.
        See which modules are active and their compliance posture at a glance.
      </div>

      {/* Summary */}
      <div style={{
        background: 'linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%)',
        borderRadius: 14, padding: '1.25rem 1.5rem', marginBottom: '1.5rem', color: '#fff',
        display: 'flex', gap: '2rem', flexWrap: 'wrap',
      }}>
        <div>
          <div style={{ fontSize: '2rem', fontWeight: 800 }}>{activeModules.length}</div>
          <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>Active Modules</div>
        </div>
        <div>
          <div style={{ fontSize: '2rem', fontWeight: 800 }}>{allModuleEntries.length}</div>
          <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>Total Available</div>
        </div>
        <div>
          <div style={{ fontSize: '2rem', fontWeight: 800 }}>
            {allModuleEntries.length > 0 ? Math.round((activeModules.length / allModuleEntries.length) * 100) : 0}%
          </div>
          <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>Coverage</div>
        </div>
        {governance?.loweconex_bridge && (
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>Loweconex Bridge</div>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '2px 10px', borderRadius: 10, fontSize: '0.75rem', fontWeight: 600,
              background: governance.loweconex_bridge.crewai_orchestration_available ? '#dcfce7' : '#fef3c7',
              color: governance.loweconex_bridge.crewai_orchestration_available ? '#166534' : '#92400e',
              marginTop: 4,
            }}>
              {governance.loweconex_bridge.crewai_orchestration_available ? 'CrewAI Active' : 'Deterministic Only'}
              {governance.loweconex_bridge.crew_count > 0 && ` (${governance.loweconex_bridge.crew_count} crews)`}
            </div>
          </div>
        )}
      </div>

      {/* Module Grid */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
        gap: '1rem',
      }}>
        {allModuleEntries.map(([id, config]) => {
          const isActive = modules[id]?.status === 'active' ||
            (Array.isArray(governance?.modules_active) && governance.modules_active.includes(id))
          return (
            <ModuleCard
              key={id}
              moduleId={id}
              config={config}
              status={isActive ? 'active' : 'inactive'}
              onRefresh={fetchGovernance}
            />
          )
        })}
      </div>
    </div>
  )
}
