import { useState } from 'react'
import {
  Bot, Layers, Shield, Eye, Activity, Brain, Thermometer,
  Zap, AlertTriangle, ClipboardCheck, Radio, GitBranch,
  ChevronDown, ChevronRight, MessageSquare, Cpu, Database,
  BarChart3, Settings, Users, Wrench, DollarSign, Leaf,
  Scale, Target, FileText, Building2, TrendingUp, Network
} from 'lucide-react'

const AGENT_LAYERS = [
  {
    id: 'layer-0',
    layer: 'Layer 0',
    title: 'Context',
    color: '#6366f1',
    bg: 'rgba(99, 102, 241, 0.08)',
    border: 'rgba(99, 102, 241, 0.2)',
    description: 'Foundation layer — classifies operating state before any analysis begins.',
    agents: [
      {
        id: 'regime-detection',
        name: 'Regime Detection Agent',
        role: 'regime_detector',
        icon: Radio,
        status: 'active',
        description: 'Classifies equipment operating regime (OFF, STARTUP, STEADY_COOL, DEFROST, etc.). All downstream analysis is regime-aware to prevent false positives from comparing different operating modes.',
        capabilities: ['Regime classification', 'Steady-state detection', 'Transient filtering', 'Regime duration tracking'],
        dependencies: ['Telemetry stream'],
      },
      {
        id: 'context-builder',
        name: 'Context Builder Agent',
        role: 'context_builder',
        icon: Database,
        status: 'active',
        description: 'Builds environmental and operational context (ambient conditions, load profiles, time-of-day patterns) to enable context-aware analysis.',
        capabilities: ['Environmental context', 'Load profile estimation', 'Temporal pattern detection'],
        dependencies: ['Telemetry stream', 'Weather data'],
      },
    ],
  },
  {
    id: 'layer-1',
    layer: 'Layer 1',
    title: 'Data Quality',
    color: '#0ea5e9',
    bg: 'rgba(14, 165, 233, 0.08)',
    border: 'rgba(14, 165, 233, 0.2)',
    description: 'Validates sensor data before analysis — the first line of defense against false alarms.',
    agents: [
      {
        id: 'sensor-trust',
        name: 'Sensor Trust Agent',
        role: 'sensor_trust',
        icon: Eye,
        status: 'active',
        description: 'Evaluates sensor data trustworthiness. Distinguishes equipment faults from sensor problems (stuck readings, drift, communication glitches). Prevents "bad telemetry = fault alarm" — the primary source of false positives.',
        capabilities: ['Stuck sensor detection', 'Drift likelihood scoring', 'Trust score per channel', 'Untrusted sensor flagging'],
        dependencies: ['Regime Detection Agent'],
      },
      {
        id: 'data-quality',
        name: 'Data Quality Agent',
        role: 'data_quality',
        icon: Shield,
        status: 'active',
        description: 'Overall data quality assessment using ISO 25012 quality dimensions. Evaluates completeness, consistency, and timeliness of incoming data streams.',
        capabilities: ['Completeness scoring', 'Consistency checks', 'Timeliness validation', 'Quality gate enforcement'],
        dependencies: ['Regime Detection Agent'],
      },
    ],
  },
  {
    id: 'layer-2',
    layer: 'Layer 2',
    title: 'Behavioral Analysis',
    color: '#f59e0b',
    bg: 'rgba(245, 158, 11, 0.08)',
    border: 'rgba(245, 158, 11, 0.2)',
    description: 'Predicts expected behavior and detects persistent deviations — not point anomalies.',
    agents: [
      {
        id: 'behavior-model',
        name: 'Behavior Model Agent',
        role: 'behavior_model',
        icon: Activity,
        status: 'active',
        description: 'Predicts expected sensor values under current regime and context using hierarchical models (global + per-unit fingerprint). Computes residuals to detect deviations from normal behavior.',
        capabilities: ['Hierarchical prediction', 'Residual computation', 'Z-score deviation', 'Equipment fingerprinting'],
        dependencies: ['Regime Detection Agent', 'Sensor Trust Agent'],
      },
      {
        id: 'residual-analysis',
        name: 'Residual Analysis Agent',
        role: 'residual_analysis',
        icon: BarChart3,
        status: 'active',
        description: 'Models residual error distributions to establish dynamic thresholds. Adapts to seasonal and operational variations.',
        capabilities: ['Distribution modeling', 'Dynamic thresholds', 'Seasonal adaptation', 'Variance tracking'],
        dependencies: ['Behavior Model Agent'],
      },
      {
        id: 'change-detection',
        name: 'Change Detection Agent',
        role: 'change_detection',
        icon: AlertTriangle,
        status: 'active',
        description: 'Runs sequential change detection (CUSUM/GLR) on residual streams. Detects PERSISTENT changes, not transient spikes. Inspired by radar detection theory — a single spike is not an alarm.',
        capabilities: ['CUSUM detection', 'GLR detection', 'Persistence scoring', 'Multi-regime observation'],
        dependencies: ['Behavior Model Agent'],
      },
    ],
  },
  {
    id: 'layer-3',
    layer: 'Layer 3',
    title: 'Diagnostics',
    color: '#ef4444',
    bg: 'rgba(239, 68, 68, 0.08)',
    border: 'rgba(239, 68, 68, 0.2)',
    description: 'Probabilistic fault diagnosis — maintains belief states, not hard classifications.',
    agents: [
      {
        id: 'fault-hypothesis',
        name: 'Fault Hypothesis Agent',
        role: 'fault_hypothesis',
        icon: Brain,
        status: 'active',
        description: 'Bayesian fault diagnosis — maintains probability distributions over fault hypotheses. Alarms only when probability mass is concentrated and evidence is consistent. "I don\'t know yet" is a valid answer.',
        capabilities: ['Bayesian updating', 'Multi-fault tracking', 'Confidence thresholding', 'Evidence consistency checks'],
        dependencies: ['Change Detection Agent'],
      },
      {
        id: 'energy-impact',
        name: 'Energy Impact Agent',
        role: 'energy_impact',
        icon: Zap,
        status: 'active',
        description: 'Estimates energy penalty from detected faults and degradation. Translates technical deviations into kWh and dollar impacts for business justification.',
        capabilities: ['Energy penalty estimation', 'Cost impact calculation', 'Baseline comparison', 'Efficiency tracking'],
        dependencies: ['Fault Hypothesis Agent', 'Behavior Model Agent'],
      },
      {
        id: 'comfort-impact',
        name: 'Comfort Impact Agent',
        role: 'comfort_impact',
        icon: Thermometer,
        status: 'active',
        description: 'Estimates comfort and food safety impact from detected issues. Tracks zone temperature deviations and product temperature risks.',
        capabilities: ['Zone comfort scoring', 'Food safety risk', 'Temperature excursion tracking', 'Regulatory compliance'],
        dependencies: ['Fault Hypothesis Agent'],
      },
    ],
  },
  {
    id: 'layer-4',
    layer: 'Layer 4',
    title: 'Decision',
    color: '#22c55e',
    bg: 'rgba(34, 197, 94, 0.08)',
    border: 'rgba(34, 197, 94, 0.2)',
    description: 'Collaborative voting and final decision — enforces Neyman-Pearson false positive budget.',
    agents: [
      {
        id: 'decision-policy',
        name: 'Decision Policy Agent',
        role: 'decision_policy',
        icon: ClipboardCheck,
        status: 'active',
        description: 'Enforces the false alarm budget using Neyman-Pearson framework. Aggregates weighted votes from all agents via collaborative consensus protocol. Makes final alarm/dispatch/watch decisions.',
        capabilities: ['FA budget enforcement', 'Weighted vote aggregation', 'Consensus protocol', 'Guardian safety merge'],
        dependencies: ['All upstream agents'],
      },
      {
        id: 'maintenance-recommendation',
        name: 'Maintenance Recommendation Agent',
        role: 'maintenance_recommendation',
        icon: Settings,
        status: 'active',
        description: 'Generates actionable maintenance recommendations with severity, urgency, and estimated time-to-failure. Produces human-readable rationales for technician dispatch.',
        capabilities: ['Recommendation generation', 'Severity classification', 'TTF estimation', 'Technician briefing'],
        dependencies: ['Decision Policy Agent', 'Fault Hypothesis Agent'],
      },
    ],
  },
]

const ORCHESTRATION_AGENTS = [
  {
    id: 'pdm-orchestrator',
    name: 'PDM Model Orchestrator',
    icon: Layers,
    status: 'active',
    description: 'Coordinates all model agents through the 5-layer pipeline. Manages agent lifecycle, dependency resolution, and result propagation.',
    capabilities: ['Layer sequencing', 'Dependency resolution', 'Result propagation', 'Agent lifecycle management'],
  },
  {
    id: 'collaborative-crew',
    name: 'Collaborative Decision Crew',
    icon: Users,
    status: 'active',
    description: 'CrewAI Crew orchestrating multi-agent collaborative decision-making. Implements voting, escalation, and consensus protocols.',
    capabilities: ['Voting protocol', 'Escalation protocol', 'Consensus protocol', 'Feedback loop'],
  },
  {
    id: 'scenario-advisor',
    name: 'Scenario Advisor',
    icon: MessageSquare,
    status: 'active',
    description: 'Conversational AI advisory agent. Provides interactive scenario analysis, Bayesian investment guidance, and natural language explanations of system state.',
    capabilities: ['Conversational interface', 'Scenario simulation', 'RAG-augmented responses', 'Tool-calling orchestration'],
  },
  {
    id: 'kpi-crew',
    name: 'KPI Enrichment Crew',
    icon: BarChart3,
    status: 'active',
    description: 'CrewAI pipeline for KPI calculation and validation. Enriches base KPI results with agent-driven benchmarking, QA checks, and savings estimation.',
    capabilities: ['KPI calculation', 'Benchmark validation', 'QA gate enforcement', 'Savings estimation'],
  },
  {
    id: 'operations-autopilot',
    name: 'Operations Autopilot',
    icon: Cpu,
    status: 'active',
    description: 'Playbook-driven remediation orchestrator. Executes approved maintenance actions via BMS/CMMS connectors with F-gas compliance enforcement.',
    capabilities: ['Playbook DSL execution', 'BMS/CMMS integration', 'F-gas compliance', 'Human-in-the-loop approvals'],
  },
]

// ═══════════════════════════════════════════════════════════════════
// Ecosystem Optimizer Crew — 12 agents for ownership-aware decision optimization
// ═══════════════════════════════════════════════════════════════════

const ECOSYSTEM_OPTIMIZER_GROUPS = [
  {
    id: 'eco-stakeholder',
    group: 'Stakeholder Agents',
    color: '#2563eb',
    bg: 'rgba(37, 99, 235, 0.08)',
    border: 'rgba(37, 99, 235, 0.2)',
    description: 'Protect ownership boundaries and validate metrics per quadrant. Each agent represents a stakeholder perspective and emits constraints + positions.',
    agents: [
      {
        id: 'eco-fm',
        name: 'FM Operations Agent',
        role: 'fm',
        icon: Wrench,
        status: 'active',
        description: 'Authority over Q1 (FM-Controlled Opex) metrics. Owns reactive work orders, PPM frequency, work order volume, technician utilization, and vendor costs. Enforces operational feasibility constraints and P1/P2/P3 response times.',
        capabilities: ['Q1 metric validation', 'Service geography constraints', 'Technician coverage floors', 'Vendor cost governance'],
        dependencies: ['Metric Catalog', 'Ownership Map'],
      },
      {
        id: 'eco-finance',
        name: 'Finance Agent',
        role: 'finance',
        icon: DollarSign,
        status: 'active',
        description: 'Authority over Q2 (Finance-Controlled Capex) metrics. Owns asset replacement cycles, lifecycle cost models, and capital efficiency. Enforces discount rate policy, hurdle rates, and capex budget ceilings.',
        capabilities: ['Q2 metric validation', 'Discount rate enforcement', 'Capex ceiling constraints', 'Depreciation schedules'],
        dependencies: ['Metric Catalog', 'Parameter Set'],
      },
      {
        id: 'eco-compliance',
        name: 'Compliance / Food Safety Agent',
        role: 'compliance',
        icon: Shield,
        status: 'active',
        description: 'Authority over Q3 (Compliance-Driven Risk) metrics. Owns temperature breaches, product discard, regulatory penalties, and refrigerant leakage. Constraints are NON-NEGOTIABLE — regulatory thresholds cannot be relaxed for budget reasons.',
        capabilities: ['Q3 metric validation', 'Regulatory threshold enforcement', 'Penalty schedule governance', 'Hard constraint emission'],
        dependencies: ['Metric Catalog', 'Regulatory Rules'],
      },
      {
        id: 'eco-ops',
        name: 'Operations Agent',
        role: 'ops',
        icon: Building2,
        status: 'active',
        description: 'Protects uptime, store operations, and shrinkage drivers. Validates operational disruption costs, maintenance window constraints, and manager burden. Sets uptime floor constraints.',
        capabilities: ['Uptime floor constraints', 'Disruption cost validation', 'Maintenance window checks', 'Scheduling conflict flags'],
        dependencies: ['Metric Catalog', 'Ownership Map'],
      },
      {
        id: 'eco-esg',
        name: 'ESG / Sustainability Agent',
        role: 'esg',
        icon: Leaf,
        status: 'active',
        description: 'Owns energy and emissions metrics. Validates energy reduction valuations, carbon pricing assumptions, and Scope 1/2 emissions calculations. Flags conflicts between energy efficiency and compliance buffers.',
        capabilities: ['Energy valuation', 'Carbon pricing validation', 'Scope 1/2 boundaries', 'Efficiency-compliance conflict detection'],
        dependencies: ['Metric Catalog', 'Parameter Set'],
      },
    ],
  },
  {
    id: 'eco-dimension',
    group: 'Dimension Agents',
    color: '#7c3aed',
    bg: 'rgba(124, 58, 237, 0.08)',
    border: 'rgba(124, 58, 237, 0.2)',
    description: 'Compute cost lines per quadrant with confidence bands. Each agent translates validated metrics into financial impact using deterministic formulas.',
    agents: [
      {
        id: 'eco-opex-modeler',
        name: 'Opex Cost Modeler',
        role: 'opex_modeler',
        icon: BarChart3,
        status: 'active',
        description: 'Translates Q1 metrics into Opex cost lines: labor, travel, overtime, parts, call center, dispatch, and vendor invoice costs. Applies service geography effects and travel time multipliers.',
        capabilities: ['Q1 cost translation', 'Service geography modeling', 'Low/base/high bands', 'Vendor cost breakdown'],
        dependencies: ['FM Operations Agent', 'Parameter Set'],
      },
      {
        id: 'eco-capex-modeler',
        name: 'Capex / Lifecycle Modeler',
        role: 'capex_modeler',
        icon: TrendingUp,
        status: 'active',
        description: 'Translates Q2 metrics into Capex cost lines: replacement schedules, depreciation, residual values, and lifecycle NPV comparisons (keep vs replace per ASTM E917). Applies discount rates and hurdle rate constraints.',
        capabilities: ['Q2 cost translation', 'Lifecycle NPV analysis', 'Depreciation modeling', 'Keep-vs-replace comparison'],
        dependencies: ['Finance Agent', 'Parameter Set'],
      },
      {
        id: 'eco-risk-modeler',
        name: 'Risk / Compliance EV Modeler',
        role: 'risk_modeler',
        icon: AlertTriangle,
        status: 'active',
        description: 'Translates Q3 metrics into Risk cost lines: temperature breach → spoilage + penalties + audit risk, product discard, regulatory penalties, and refrigerant leakage. Applies probability-weighted damage models.',
        capabilities: ['Q3 cost translation', 'Expected value modeling', 'Penalty schedule application', 'Probability-weighted damages'],
        dependencies: ['Compliance Agent', 'Parameter Set'],
      },
      {
        id: 'eco-strategic-modeler',
        name: 'Strategic Cross-Silo Modeler',
        role: 'strategic_modeler',
        icon: Network,
        status: 'active',
        description: 'Computes Q4 bundled cross-silo value: aggregated benefits across Q1+Q2+Q3 plus energy/emissions. Models the "weakest asset limits bank optimization" (AI bank effect) and avoided disruption costs.',
        capabilities: ['Q4 cross-silo aggregation', 'AI bank effect modeling', 'Dependency graph overlap checks', 'Avoided disruption valuation'],
        dependencies: ['All Dimension Agents', 'Dependency Graph'],
      },
    ],
  },
  {
    id: 'eco-governance',
    group: 'Governance Agents',
    color: '#059669',
    bg: 'rgba(5, 150, 105, 0.08)',
    border: 'rgba(5, 150, 105, 0.2)',
    description: 'Reconcile, optimize, and explain. Merge cost lines, run multi-objective optimization, and produce board-ready narratives with full lineage.',
    agents: [
      {
        id: 'eco-reconciler',
        name: 'Reconciliation Agent',
        role: 'reconciler',
        icon: GitBranch,
        status: 'active',
        description: 'Merges cost lines from all dimension agents into a unified cost stack. Applies anti-double-counting adjustments using the dependency graph. Allocates shared benefits across owners with configurable weighting.',
        capabilities: ['Cost line merging', 'Anti-double-counting', 'Shared benefit allocation', 'Dependency graph enforcement'],
        dependencies: ['All Dimension Agents'],
      },
      {
        id: 'eco-optimizer',
        name: 'Optimizer Agent',
        role: 'optimizer',
        icon: Target,
        status: 'active',
        description: 'Selects optimal action portfolio under budget and stakeholder constraints. Produces 3–5 Pareto-optimal options across NPV, risk-adjusted ROI, compliance risk, and min-opex objectives. Compliance lines always prioritized.',
        capabilities: ['Multi-objective optimization', 'Pareto frontier generation', 'Budget constraint enforcement', 'Compliance-first selection'],
        dependencies: ['Reconciliation Agent', 'Negotiation Engine'],
      },
      {
        id: 'eco-auditor',
        name: 'Audit / Explainability Narrator',
        role: 'auditor',
        icon: FileText,
        status: 'active',
        description: 'Produces the final board-ready narrative (400–600 words), assumption register with lineage, and consolidated ROI report. Traces every number back to its source metric, translation rule, and assumption.',
        capabilities: ['Board narrative generation', 'Assumption register', 'Full lineage tracing', 'Low-confidence highlighting'],
        dependencies: ['Optimizer Agent', 'All Stakeholder Agents'],
      },
      {
        id: 'eco-orchestrator',
        name: 'Decision Orchestrator',
        role: 'orchestrator',
        icon: Layers,
        status: 'active',
        description: 'Coordinates the full decision pipeline: builds parameter set, manages stakeholder validation, triggers cost translation, orchestrates reconciliation and optimization, resolves conflicts via negotiation engine.',
        capabilities: ['Pipeline coordination', 'Conflict resolution', 'Negotiation orchestration', 'Artifact-first execution'],
        dependencies: ['All Crew Agents'],
      },
    ],
  },
]

const PROTOCOL_AGENTS = [
  {
    id: 'voting-protocol',
    name: 'Voting Protocol',
    icon: GitBranch,
    status: 'active',
    description: 'Implements weighted voting among agents with confidence-scaled weights. Supports STRONGLY_AGREE through STRONGLY_DISAGREE with ABSTAIN option.',
  },
  {
    id: 'escalation-protocol',
    name: 'Escalation Protocol',
    icon: AlertTriangle,
    status: 'active',
    description: 'Risk-tiered escalation from automated action to human-in-the-loop approval queue. Higher-risk decisions require explicit human authorization.',
  },
  {
    id: 'consensus-protocol',
    name: 'Consensus Protocol',
    icon: Shield,
    status: 'active',
    description: 'Determines whether agent consensus is reached based on configurable threshold. Tracks dissenting agents and their rationale for audit trail.',
  },
]

const s = {
  page: {
    padding: '0.5rem 0',
  },
  header: {
    marginBottom: '1.5rem',
  },
  title: {
    fontSize: '1.25rem',
    fontWeight: 700,
    color: '#1e293b',
    margin: 0,
    display: 'flex',
    alignItems: 'center',
    gap: '0.6rem',
  },
  subtitle: {
    fontSize: '0.82rem',
    color: '#64748b',
    marginTop: '0.35rem',
  },
  sectionGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
  },
  layerCard: (color, bg, border) => ({
    background: '#fff',
    border: `1px solid #e2e8f0`,
    borderLeft: `3px solid ${color}`,
    borderRadius: '10px',
    overflow: 'hidden',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  }),
  layerHeader: (color, bg) => ({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.75rem 1rem',
    background: '#fafbfc',
    cursor: 'pointer',
    userSelect: 'none',
    borderBottom: '1px solid #f1f5f9',
  }),
  layerBadge: (color) => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: '0.4rem',
    fontSize: '0.68rem',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    color: color,
    background: color + '12',
    padding: '0.2rem 0.6rem',
    borderRadius: '6px',
  }),
  layerTitle: {
    fontSize: '0.92rem',
    fontWeight: 650,
    color: '#1e293b',
    marginLeft: '0.5rem',
  },
  layerDesc: {
    fontSize: '0.75rem',
    color: '#64748b',
    marginLeft: 'auto',
    marginRight: '0.75rem',
    maxWidth: '40%',
    textAlign: 'right',
  },
  agentsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
    gap: '0.65rem',
    padding: '0.75rem 1rem 1rem',
  },
  agentCard: {
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    padding: '0.85rem 1rem',
    transition: 'box-shadow 0.15s, border-color 0.15s',
  },
  agentHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    marginBottom: '0.4rem',
  },
  agentName: {
    fontSize: '0.85rem',
    fontWeight: 650,
    color: '#1e293b',
  },
  statusDot: (status) => ({
    width: 7,
    height: 7,
    borderRadius: '50%',
    background: status === 'active' ? '#22c55e' : status === 'idle' ? '#f59e0b' : '#94a3b8',
    marginLeft: 'auto',
    flexShrink: 0,
    boxShadow: status === 'active' ? '0 0 0 2px rgba(34,197,94,0.2)' : 'none',
  }),
  agentDesc: {
    fontSize: '0.75rem',
    color: '#475569',
    lineHeight: 1.5,
    marginBottom: '0.5rem',
  },
  capsLabel: {
    fontSize: '0.65rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: '#94a3b8',
    marginBottom: '0.25rem',
  },
  capsList: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.3rem',
  },
  capBadge: {
    fontSize: '0.65rem',
    color: '#475569',
    background: '#f1f5f9',
    padding: '0.15rem 0.5rem',
    borderRadius: '4px',
    whiteSpace: 'nowrap',
  },
  sectionTitle: {
    fontSize: '0.78rem',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    color: '#94a3b8',
    marginBottom: '0.75rem',
    marginTop: '0.5rem',
  },
  orchestrationGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: '0.65rem',
  },
  chevron: {
    color: '#94a3b8',
    flexShrink: 0,
    transition: 'transform 0.15s',
  },
  statsRow: {
    display: 'flex',
    gap: '0.75rem',
    marginBottom: '1.5rem',
    flexWrap: 'wrap',
  },
  statCard: (color) => ({
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    padding: '0.85rem 1.25rem',
    flex: '1 1 140px',
    minWidth: 140,
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  }),
  statValue: (color) => ({
    fontSize: '1.5rem',
    fontWeight: 700,
    color: color,
  }),
  statLabel: {
    fontSize: '0.7rem',
    color: '#64748b',
    marginTop: '0.15rem',
    fontWeight: 500,
  },
}

function AgentCard({ agent, accentColor }) {
  const Icon = agent.icon
  return (
    <div style={s.agentCard}>
      <div style={s.agentHeader}>
        <Icon size={16} style={{ color: accentColor || '#60a5fa', flexShrink: 0 }} />
        <span style={s.agentName}>{agent.name}</span>
        <div style={s.statusDot(agent.status)} title={agent.status} />
      </div>
      <div style={s.agentDesc}>{agent.description}</div>
      {agent.capabilities && (
        <>
          <div style={s.capsLabel}>Capabilities</div>
          <div style={s.capsList}>
            {agent.capabilities.map(c => (
              <span key={c} style={s.capBadge}>{c}</span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default function AgentsPage() {
  const [expanded, setExpanded] = useState(
    Object.fromEntries(AGENT_LAYERS.map(l => [l.id, true]))
  )

  const toggleLayer = (id) => {
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }))
  }

  const totalPdmAgents = AGENT_LAYERS.reduce((sum, l) => sum + l.agents.length, 0)
    + ORCHESTRATION_AGENTS.length
    + PROTOCOL_AGENTS.length
  const totalEcoAgents = ECOSYSTEM_OPTIMIZER_GROUPS.reduce((sum, g) => sum + g.agents.length, 0)
  const totalAgents = totalPdmAgents + totalEcoAgents

  const [ecoExpanded, setEcoExpanded] = useState(
    Object.fromEntries(ECOSYSTEM_OPTIMIZER_GROUPS.map(g => [g.id, true]))
  )
  const toggleEco = (id) => {
    setEcoExpanded(prev => ({ ...prev, [id]: !prev[id] }))
  }

  return (
    <div style={s.page}>
      <div style={s.header}>
        <h1 style={s.title}>
          <Bot size={22} style={{ color: '#6366f1' }} />
          Agent Ecosystem
        </h1>
        <p style={s.subtitle}>
          Multi-agent architecture for predictive maintenance and ecosystem-wide investment optimization.
          5-layer inference pipeline, CrewAI orchestration, and a 12-agent decision support crew.
        </p>
      </div>

      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
        marginBottom: '1rem', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> Catalog of the <strong>entire agent ecosystem</strong> — 5 PdM inference
        layers (Regime, Sensor Trust, Behavior/Change, Fault Hypothesis, Decision Policy), orchestration
        agents, consensus protocols, and the <strong>12-agent Ecosystem Optimizer crew</strong> for ownership-aware
        investment optimization. See each agent's role, capabilities, and how they collaborate.
      </div>

      <div style={s.statsRow}>
        <div style={s.statCard('#6366f1')}>
          <div style={s.statValue('#6366f1')}>{totalAgents}</div>
          <div style={s.statLabel}>Total Agents</div>
        </div>
        <div style={s.statCard('#22c55e')}>
          <div style={s.statValue('#22c55e')}>{AGENT_LAYERS.length}</div>
          <div style={s.statLabel}>Inference Layers</div>
        </div>
        <div style={s.statCard('#0ea5e9')}>
          <div style={s.statValue('#0ea5e9')}>{ORCHESTRATION_AGENTS.length}</div>
          <div style={s.statLabel}>Orchestrators</div>
        </div>
        <div style={s.statCard('#f59e0b')}>
          <div style={s.statValue('#f59e0b')}>{PROTOCOL_AGENTS.length}</div>
          <div style={s.statLabel}>Protocols</div>
        </div>
        <div style={s.statCard('#7c3aed')}>
          <div style={s.statValue('#7c3aed')}>{totalEcoAgents}</div>
          <div style={s.statLabel}>Ecosystem Optimizer</div>
        </div>
      </div>

      <div style={s.sectionGrid}>
        {/* Inference Layers */}
        {AGENT_LAYERS.map(layer => (
          <div key={layer.id} style={s.layerCard(layer.color, layer.bg, layer.border)}>
            <div
              style={s.layerHeader(layer.color, layer.bg)}
              onClick={() => toggleLayer(layer.id)}
            >
              <span style={s.layerBadge(layer.color)}>{layer.layer}</span>
              <span style={s.layerTitle}>{layer.title}</span>
              <span style={s.layerDesc}>{layer.description}</span>
              {expanded[layer.id]
                ? <ChevronDown size={16} style={s.chevron} />
                : <ChevronRight size={16} style={s.chevron} />
              }
            </div>
            {expanded[layer.id] && (
              <div style={s.agentsGrid}>
                {layer.agents.map(agent => (
                  <AgentCard key={agent.id} agent={agent} accentColor={layer.color} />
                ))}
              </div>
            )}
          </div>
        ))}

        {/* Orchestration & Crews */}
        <div style={s.sectionTitle}>Orchestration &amp; Crews</div>
        <div style={s.orchestrationGrid}>
          {ORCHESTRATION_AGENTS.map(agent => (
            <AgentCard key={agent.id} agent={agent} accentColor="#60a5fa" />
          ))}
        </div>

        {/* Protocols */}
        <div style={s.sectionTitle}>Communication Protocols</div>
        <div style={s.orchestrationGrid}>
          {PROTOCOL_AGENTS.map(agent => (
            <AgentCard key={agent.id} agent={agent} accentColor="#a78bfa" />
          ))}
        </div>

        {/* Ecosystem Optimizer Crew */}
        <div style={{ marginTop: '0.75rem', borderTop: '2px solid #e2e8f0', paddingTop: '1rem' }}>
          <div style={s.sectionTitle}>Ecosystem Optimizer — Decision Support Crew</div>
          <div style={{
            background: '#f5f3ff', border: '1px solid #ddd6fe', borderRadius: 10,
            padding: '10px 14px', fontSize: '0.78rem', color: '#5b21b6',
            marginBottom: '1rem', lineHeight: 1.6,
          }}>
            <strong>12 specialized AI agents</strong> organized in 3 groups for enterprise-wide ownership-aware investment optimization.
            Stakeholder agents validate per-quadrant metrics, dimension agents translate metrics into cost lines,
            and governance agents reconcile, optimize across Pareto frontiers, and produce board-ready narratives.
          </div>
          {ECOSYSTEM_OPTIMIZER_GROUPS.map(group => (
            <div key={group.id} style={{ ...s.layerCard(group.color, group.bg, group.border), marginBottom: '0.65rem' }}>
              <div
                style={s.layerHeader(group.color, group.bg)}
                onClick={() => toggleEco(group.id)}
              >
                <span style={s.layerBadge(group.color)}>{group.agents.length} agents</span>
                <span style={s.layerTitle}>{group.group}</span>
                <span style={s.layerDesc}>{group.description}</span>
                {ecoExpanded[group.id]
                  ? <ChevronDown size={16} style={s.chevron} />
                  : <ChevronRight size={16} style={s.chevron} />
                }
              </div>
              {ecoExpanded[group.id] && (
                <div style={s.agentsGrid}>
                  {group.agents.map(agent => (
                    <AgentCard key={agent.id} agent={agent} accentColor={group.color} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
