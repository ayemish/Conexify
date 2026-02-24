import {
  BarChart3, Cpu, Zap, Building, Wrench, ClipboardList, Shield, Brain,
  ChevronRight, Activity, Layers, MessageSquare, Upload, GitBranch,
  Target, TrendingUp, Thermometer, Leaf, DollarSign, Users, ArrowRight
} from 'lucide-react'

const BRAND_GRADIENT = 'linear-gradient(135deg, #0f172a 0%, #1e3a5f 40%, #2563eb 100%)'

const CAPABILITIES = [
  {
    icon: BarChart3, color: '#3b82f6', title: '14-KPI Analytics Engine',
    desc: 'Comprehensive savings analysis across energy, maintenance, refrigerant, CapEx, food safety, ESG, and operations with confidence scoring and approval workflows.',
  },
  {
    icon: Cpu, color: '#8b5cf6', title: 'Multi-Agent Orchestration',
    desc: 'Four focused orchestration pipelines CapEx, Preventive Maintenance, Work Orders, and Energy each running specialized AI agent crews against your fleet data.',
  },
  {
    icon: Brain, color: '#ec4899', title: 'Conversational AI Advisor',
    desc: 'Natural-language interface powered by RAG and LLM synthesis. Ask questions about your fleet, run scenarios, and get actionable recommendations.',
  },
  {
    icon: Activity, color: '#22c55e', title: 'Real-Time Operator Dashboard',
    desc: 'Live WebSocket telemetry, alert triage, approval queues, and asset health monitoring with sensor trust scoring.',
  },
  {
    icon: Shield, color: '#f59e0b', title: 'Enterprise Governance',
    desc: '12 governance modules including data quality (ISO 25012), AI risk (NIST RMF), M&V verification (IPMVP), MLOps, security (ISO 27001), and digital thread lineage.',
  },
  {
    icon: GitBranch, color: '#06b6d4', title: 'Scenario Modeling',
    desc: 'What-if analysis with conservative, balanced, and aggressive profiles. Compare scenarios side-by-side with NPV, payback period, and ROI calculations.',
  },
]

const PIPELINES = [
  { icon: Building, color: '#8b5cf6', name: 'CapEx & Asset Replacement', crews: 3, desc: 'NPV-based replacement prioritization using health scores and Weibull survival models' },
  { icon: Wrench, color: '#22c55e', name: 'Preventive Maintenance', crews: 4, desc: 'Condition-based PM optimization with food safety compliance validation' },
  { icon: ClipboardList, color: '#f59e0b', name: 'Work Order Mitigation', crews: 3, desc: 'Shift reactive to planned maintenance, reduce call center and service bureau costs' },
  { icon: Zap, color: '#3b82f6', name: 'Energy Management', crews: 4, desc: 'Energy waste detection, refrigerant leak savings, and carbon reduction modeling' },
]

const KPI_CATEGORIES = [
  { icon: Zap, label: 'Energy Reduction', color: '#3b82f6' },
  { icon: Thermometer, label: 'Refrigerant Leak Reduction', color: '#06b6d4' },
  { icon: ClipboardList, label: 'Work Order Reduction', color: '#f59e0b' },
  { icon: Target, label: 'Asset Failure Prediction', color: '#ef4444' },
  { icon: Building, label: 'CapEx Lifecycle', color: '#8b5cf6' },
  { icon: TrendingUp, label: 'Uptime Maximization', color: '#22c55e' },
  { icon: Shield, label: 'Food Safety Compliance', color: '#f97316' },
  { icon: Leaf, label: 'ESG & Carbon Reduction', color: '#10b981' },
  { icon: DollarSign, label: 'Service Bureau Reduction', color: '#6366f1' },
  { icon: Users, label: 'Call Center Reduction', color: '#ec4899' },
  { icon: Wrench, label: 'PM Optimization', color: '#a855f7' },
  { icon: BarChart3, label: 'PPM Maximization', color: '#14b8a6' },
  { icon: Activity, label: 'Food Temp Diagnostics', color: '#f43f5e' },
  { icon: Cpu, label: 'Food Waste Reduction', color: '#84cc16' },
]

const s = {
  page: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    color: '#1e293b', background: '#ffffff', minHeight: '100vh',
  },
  hero: {
    background: BRAND_GRADIENT, color: '#fff', padding: '5rem 2rem 4.5rem',
    textAlign: 'center', position: 'relative', overflow: 'hidden',
  },
  heroGlow: {
    position: 'absolute', top: '-50%', left: '50%', transform: 'translateX(-50%)',
    width: '120%', height: '200%', opacity: 0.08, pointerEvents: 'none',
    background: 'radial-gradient(ellipse at center, #60a5fa 0%, transparent 70%)',
  },
  heroContent: { position: 'relative', zIndex: 1, maxWidth: 900, margin: '0 auto' },
  logoMark: {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: 64, height: 64, borderRadius: 16, marginBottom: '1.5rem',
    background: 'rgba(255,255,255,0.12)', backdropFilter: 'blur(8px)',
    border: '1px solid rgba(255,255,255,0.15)',
  },
  eyebrow: {
    textTransform: 'uppercase', letterSpacing: '0.2em', fontSize: '0.8rem',
    fontWeight: 600, opacity: 0.7, marginBottom: '0.75rem',
  },
  h1: {
    fontSize: 'clamp(2.5rem, 5vw, 4rem)', fontWeight: 800, margin: '0 0 1rem',
    lineHeight: 1.05, letterSpacing: '-0.03em',
  },
  iq: {
    background: 'linear-gradient(90deg, #60a5fa, #a78bfa)', WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent', backgroundClip: 'text',
  },
  subtitle: {
    fontSize: '1.2rem', lineHeight: 1.6, opacity: 0.85, maxWidth: 680,
    margin: '0 auto 2.5rem',
  },
  ctaRow: { display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' },
  ctaPrimary: {
    display: 'inline-flex', alignItems: 'center', gap: 8, padding: '0.85rem 2rem',
    borderRadius: 12, border: 'none', background: '#fff', color: '#1e3a5f',
    fontSize: '1rem', fontWeight: 700, cursor: 'pointer', transition: 'transform 0.15s, box-shadow 0.15s',
    boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
  },
  ctaSecondary: {
    display: 'inline-flex', alignItems: 'center', gap: 8, padding: '0.85rem 2rem',
    borderRadius: 12, border: '1px solid rgba(255,255,255,0.3)', background: 'rgba(255,255,255,0.08)',
    color: '#fff', fontSize: '1rem', fontWeight: 600, cursor: 'pointer', transition: 'background 0.15s',
  },
  section: { maxWidth: 1200, margin: '0 auto', padding: '4rem 2rem' },
  sectionTitle: { fontSize: '1.8rem', fontWeight: 800, margin: '0 0 0.5rem', letterSpacing: '-0.02em' },
  sectionSubtitle: { fontSize: '1rem', color: '#64748b', margin: '0 0 2.5rem', maxWidth: 600 },
  grid3: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' },
  grid4: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' },
  card: {
    background: '#fff', borderRadius: 14, padding: '1.5rem', border: '1px solid #e2e8f0',
    transition: 'transform 0.15s, box-shadow 0.15s',
  },
  divider: { borderTop: '1px solid #f1f5f9', margin: 0 },
  statsBar: {
    background: '#f8fafc', padding: '3rem 2rem', borderTop: '1px solid #e2e8f0',
    borderBottom: '1px solid #e2e8f0',
  },
  statsInner: {
    maxWidth: 1200, margin: '0 auto',
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '2rem',
    textAlign: 'center',
  },
  statNum: { fontSize: '2.2rem', fontWeight: 800, color: '#1d4ed8', lineHeight: 1 },
  statLabel: { fontSize: '0.85rem', color: '#64748b', marginTop: '0.35rem' },
  kpiStrip: {
    display: 'flex', flexWrap: 'wrap', gap: '0.5rem', justifyContent: 'center',
  },
  kpiTag: (color) => ({
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '0.4rem 0.85rem',
    borderRadius: 20, fontSize: '0.78rem', fontWeight: 600,
    background: `${color}12`, color: color, border: `1px solid ${color}25`,
  }),
  footer: {
    background: '#0f172a', color: '#94a3b8', padding: '3rem 2rem', textAlign: 'center',
    fontSize: '0.85rem',
  },
}

export default function LandingPage({ onNavigate }) {
  return (
    <div style={s.page}>
      {/* ── Hero ──────────────────────────────────────────────────── */}
      <section style={s.hero}>
        <div style={s.heroGlow} />
        <div style={s.heroContent}>
          <div style={s.logoMark}>
            <Layers size={32} strokeWidth={2} />
          </div>
          <div style={s.eyebrow}>Energy Consuming Asset Intelligence</div>
          <h1 style={s.h1}>
            LoweConex <span style={s.iq}>iQ</span>
          </h1>
          <p style={s.subtitle}>
            AI-powered predictive maintenance platform for HVAC/R fleet operations.
            Turn sensor data into savings with multi-agent orchestration, 14-KPI analytics,
            and conversational AI advisory.
          </p>
          <div style={s.ctaRow}>
            <button style={s.ctaPrimary} onClick={() => onNavigate('operator')}>
              <Activity size={18} /> Predictive Maintenance <ArrowRight size={18} />
            </button>
            <button style={s.ctaSecondary} onClick={() => onNavigate('kpi')}>
              Business Enablement <ArrowRight size={18} />
            </button>
            <button style={s.ctaSecondary} onClick={() => onNavigate('capex')}>
              <DollarSign size={18} /> CapEx Assistant <ArrowRight size={18} />
            </button>
            <button style={s.ctaSecondary} onClick={() => onNavigate('advisor')}>
              <MessageSquare size={18} /> Talk to Advisor
            </button>
            <button style={s.ctaSecondary} onClick={() => onNavigate('pipeline')}>
              <Cpu size={18} /> Run Orchestration
            </button>
          </div>
        </div>
      </section>

      {/* ── Stats Bar ─────────────────────────────────────────────── */}
      <section style={s.statsBar}>
        <div style={s.statsInner}>
          <div>
            <div style={s.statNum}>14</div>
            <div style={s.statLabel}>KPI Dimensions Analyzed</div>
          </div>
          <div>
            <div style={s.statNum}>4</div>
            <div style={s.statLabel}>Orchestration Pipelines</div>
          </div>
          <div>
            <div style={s.statNum}>6</div>
            <div style={s.statLabel}>Pre-Built Scenarios</div>
          </div>
          <div>
            <div style={s.statNum}>5</div>
            <div style={s.statLabel}>Agent Architecture Layers</div>
          </div>
          <div>
            <div style={s.statNum}>12</div>
            <div style={s.statLabel}>Governance Modules</div>
          </div>
        </div>
      </section>

      {/* ── Capabilities ──────────────────────────────────────────── */}
      <section style={s.section}>
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          <h2 style={s.sectionTitle}>Platform Capabilities</h2>
          <p style={{ ...s.sectionSubtitle, margin: '0.5rem auto 0' }}>
            A complete predictive maintenance intelligence stack from sensor ingestion to executive decision support.
          </p>
        </div>
        <div style={s.grid3}>
          {CAPABILITIES.map((cap, i) => (
            <div key={i} style={s.card}
              onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-3px)'; e.currentTarget.style.boxShadow = '0 8px 30px rgba(0,0,0,0.08)' }}
              onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = '' }}
            >
              <div style={{
                width: 44, height: 44, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: `${cap.color}15`, color: cap.color, marginBottom: '1rem',
              }}>
                <cap.icon size={22} />
              </div>
              <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.05rem', fontWeight: 700, color: '#1e293b' }}>{cap.title}</h3>
              <p style={{ margin: 0, fontSize: '0.88rem', color: '#64748b', lineHeight: 1.55 }}>{cap.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <hr style={s.divider} />

      {/* ── Orchestration Pipelines ───────────────────────────────── */}
      <section style={s.section}>
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          <h2 style={s.sectionTitle}>Orchestration Pipelines</h2>
          <p style={{ ...s.sectionSubtitle, margin: '0.5rem auto 0' }}>
            Four goal-focused agent teams, each running specialized KPI crews against your fleet data.
          </p>
        </div>
        <div style={s.grid4}>
          {PIPELINES.map((p, i) => (
            <div key={i} style={{ ...s.card, cursor: 'pointer', borderTop: `3px solid ${p.color}` }}
              onClick={() => onNavigate('pipeline')}
              onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-3px)'; e.currentTarget.style.boxShadow = '0 8px 30px rgba(0,0,0,0.08)' }}
              onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = '' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: '0.75rem' }}>
                <div style={{
                  width: 38, height: 38, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: `${p.color}18`, color: p.color,
                }}>
                  <p.icon size={20} />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.92rem', color: '#1e293b' }}>{p.name}</div>
                  <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{p.crews} KPI crews</div>
                </div>
              </div>
              <p style={{ margin: 0, fontSize: '0.82rem', color: '#64748b', lineHeight: 1.5 }}>{p.desc}</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: '0.75rem', fontSize: '0.78rem', fontWeight: 600, color: p.color }}>
                Run Pipeline <ChevronRight size={14} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <hr style={s.divider} />

      {/* ── KPI Coverage ──────────────────────────────────────────── */}
      <section style={{ ...s.section, textAlign: 'center' }}>
        <h2 style={s.sectionTitle}>14-Dimension KPI Coverage</h2>
        <p style={{ ...s.sectionSubtitle, margin: '0.5rem auto 2rem' }}>
          Every KPI is computed with confidence scoring, savings ranges, and manual approval workflows.
        </p>
        <div style={s.kpiStrip}>
          {KPI_CATEGORIES.map((kpi, i) => (
            <span key={i} style={s.kpiTag(kpi.color)}>
              <kpi.icon size={14} /> {kpi.label}
            </span>
          ))}
        </div>
      </section>

      <hr style={s.divider} />

      {/* ── How It Works ──────────────────────────────────────────── */}
      <section style={s.section}>
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          <h2 style={s.sectionTitle}>How It Works</h2>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '2rem', textAlign: 'center' }}>
          {[
            { step: '1', icon: Upload, title: 'Upload Data', desc: 'Telemetry, assets, work orders, energy bills, maintenance history, refrigerant records' },
            { step: '2', icon: Cpu, title: 'Agent Orchestration', desc: 'Multi-agent crews analyze your data across 14 KPI dimensions with CrewAI enrichment' },
            { step: '3', icon: BarChart3, title: 'Review Results', desc: 'Interactive dashboards with savings estimates, confidence levels, and approval workflows' },
            { step: '4', icon: MessageSquare, title: 'Ask the Advisor', desc: 'Conversational AI explains findings, runs what-if scenarios, and recommends actions' },
            { step: '5', icon: TrendingUp, title: 'Take Action', desc: 'Export ROI workbooks, prioritize CapEx, optimize PM schedules, and reduce costs' },
          ].map((item, i) => (
            <div key={i}>
              <div style={{
                width: 52, height: 52, borderRadius: '50%', margin: '0 auto 1rem',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'linear-gradient(135deg, #1d4ed8, #7c3aed)', color: '#fff',
                fontSize: '1.1rem', fontWeight: 800,
              }}>{item.step}</div>
              <div style={{ marginBottom: '0.5rem' }}>
                <item.icon size={20} style={{ color: '#3b82f6' }} />
              </div>
              <h4 style={{ margin: '0 0 0.35rem', fontSize: '0.95rem', fontWeight: 700 }}>{item.title}</h4>
              <p style={{ margin: 0, fontSize: '0.82rem', color: '#64748b', lineHeight: 1.5 }}>{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA Banner ────────────────────────────────────────────── */}
      <section style={{
        background: BRAND_GRADIENT, padding: '3.5rem 2rem', textAlign: 'center', color: '#fff',
      }}>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 800, margin: '0 0 0.75rem' }}>
          Ready to optimize your HVAC/R fleet?
        </h2>
        <p style={{ fontSize: '1rem', opacity: 0.8, margin: '0 0 2rem', maxWidth: 500, marginLeft: 'auto', marginRight: 'auto' }}>
          Upload your data and start seeing savings estimates in minutes.
        </p>
        <div style={s.ctaRow}>
          <button style={s.ctaPrimary} onClick={() => onNavigate('upload')}>
            <Upload size={18} /> Upload Data
          </button>
          <button style={s.ctaSecondary} onClick={() => onNavigate('kpi')}>
            View KPI Dashboard <ArrowRight size={18} />
          </button>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────────────── */}
      <footer style={s.footer}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: '0.75rem' }}>
          <Layers size={18} style={{ color: '#60a5fa' }} />
          <span style={{ fontSize: '1rem', fontWeight: 700, color: '#e2e8f0' }}>
            LoweConex <span style={{ color: '#60a5fa' }}>iQ</span>
          </span>
        </div>
        <p style={{ margin: 0 }}>
          AI-Powered Predictive Maintenance Intelligence for HVAC/R Fleet Operations
        </p>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.75rem', color: '#475569' }}>
          Multi-Agent Orchestration &middot; 14-KPI Analytics &middot; Conversational AI Advisory &middot; Enterprise Governance
        </p>
      </footer>
    </div>
  )
}
