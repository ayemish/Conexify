import { useState, useEffect, useCallback } from 'react'
import {
  BarChart3, Upload, Layers, Cpu,
  Settings, MessageSquare, Home, PanelLeftClose, PanelLeft,
  DollarSign, Box, LogOut, Shield, Bot, Wrench, ClipboardCheck, Scale
} from 'lucide-react'
import './App.css'
import './OperatorDashboard.css'
import {
  OperatorDashboard,
  KpiDashboard,
  DataUpload,
  OrchestrationVisibility,
  OrchestrationView,
  DataMapping,
  ScenarioAdvisorChat,
  LandingPage,
  WorkOrderModule,
  DigitalTwin3D,
} from './components'
import LoginPage from './components/LoginPage'
import NotificationCenter from './components/NotificationCenter'
import SiteSelector from './components/SiteSelector'
import GovernanceDashboard from './components/GovernanceDashboard'
import CapExPage from './components/CapExPage'
import AgentsPage from './components/AgentsPage'
import DecisionMatrixPage from './components/DecisionMatrixPage'
import OwnershipDecisionSupport from './components/OwnershipDecisionSupport'
import DecisionSupportConfig from './components/DecisionSupportConfig'
import { AppProvider, useAppContext } from './context/AppContext'
import './AdvisorChat.css'
import './WorkOrderModule.css'

// ── Hash-based routing helpers ──────────────────────────────────────
function getHashPage() {
  const hash = window.location.hash.replace('#/', '').replace('#', '')
  return hash || 'home'
}

function setHashPage(page) {
  window.location.hash = `#/${page}`
}

// ── Sidebar configuration ───────────────────────────────────────────
const SIDEBAR_ITEMS = [
  // Business Enablement
  { id: 'kpi',             label: 'Overview',                    icon: BarChart3,      section: 'Business Enablement' },
  { id: 'decision-matrix', label: 'Opex Management',             icon: Scale,          section: 'Business Enablement' },
  { id: 'capex',           label: 'CapEx Replacement Planner',   icon: DollarSign,     section: 'Business Enablement' },
  { id: 'advisor',         label: 'Advisory Services',           icon: MessageSquare,  section: 'Business Enablement' },

  // Budget & Strategy
  { id: 'ownership',       label: 'Ecosystem Optimizer',         icon: Scale,          section: 'Budget & Strategy' },

  // Operations
  { id: 'operator',        label: 'Predictive Maintenance',      icon: Wrench,         section: 'Operations' },
  { id: 'workorders',      label: 'Maintenance Management',      icon: ClipboardCheck, section: 'Operations' },

  // Data
  { id: 'upload',          label: 'Data Upload',                 icon: Upload,         section: 'Data' },
  { id: 'mapping',         label: 'Data Mapping',                icon: Settings,       section: 'Data' },

  // Platform
  { id: 'pipeline',        label: 'Pipelines',                   icon: Cpu,            section: 'Platform' },
  { id: 'orchestration',   label: 'Orchestration',               icon: Layers,         section: 'Platform' },
  { id: 'digital-twin',    label: 'Digital Twin',                icon: Box,            section: 'Platform' },
  { id: 'agents',          label: 'Agents',                      icon: Bot,            section: 'Platform' },
  { id: 'governance',      label: 'Governance',                  icon: Shield,         section: 'Platform' },
  { id: 'ds-config',       label: 'Decision Support Config',     icon: Settings,       section: 'Platform' },
]


function AppShell() {
  const { isAuthenticated, user, logout, activeAssetId } = useAppContext()
  const [page, setPageState] = useState(getHashPage)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Sync page state with URL hash
  const setPage = useCallback((p) => {
    setPageState(p)
    setHashPage(p)
  }, [])

  // Listen for browser back/forward
  useEffect(() => {
    const onHashChange = () => setPageState(getHashPage())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Auth gate
  if (!isAuthenticated) {
    return <LoginPage />
  }

  // Landing page gets full-page treatment (no nav bar)
  if (page === 'home') {
    return <LandingPage onNavigate={setPage} />
  }

  // Group sidebar items by section
  const sections = SIDEBAR_ITEMS.reduce((acc, item) => {
    if (!acc[item.section]) acc[item.section] = []
    acc[item.section].push(item)
    return acc
  }, {})

  return (
    <div className="app-shell">
      {/* ── Top Header ─────────────────────────────────────────── */}
      <header className="app-nav">
        <div className="nav-left">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
          </button>
          <button
            className="nav-btn nav-brand"
            onClick={() => setPage('home')}
          >
            <Layers size={16} style={{ color: '#60a5fa' }} />
            <span style={{ color: '#e2e8f0' }}>LoweConex</span>
            <span style={{ color: '#60a5fa' }}>iQ</span>
          </button>
        </div>
        <div className="nav-right" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: 'auto', paddingRight: '1rem' }}>
          <SiteSelector />
          <NotificationCenter />
          {user && (
            <span style={{ fontSize: '0.75rem', color: '#94a3b8', padding: '0 0.5rem' }}>
              {user.name}
            </span>
          )}
          <button
            onClick={logout}
            title="Sign out"
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#64748b', padding: '0.3rem', display: 'flex',
            }}
          >
            <LogOut size={16} />
          </button>
        </div>
      </header>

      <div className="app-body">
        {/* ── Left Sidebar ───────────────────────────────────────── */}
        <aside className={`app-sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
          <nav className="sidebar-nav">
            {Object.entries(sections).map(([section, items]) => (
              <div key={section} className="sidebar-section">
                {sidebarOpen && <div className="sidebar-section-label">{section}</div>}
                {items.map(item => {
                  const Icon = item.icon
                  return (
                    <button
                      key={item.id}
                      className={`sidebar-btn ${page === item.id ? 'active' : ''}`}
                      onClick={() => setPage(item.id)}
                      title={!sidebarOpen ? item.label : undefined}
                    >
                      <Icon size={17} />
                      {sidebarOpen && <span>{item.label}</span>}
                    </button>
                  )
                })}
              </div>
            ))}

          </nav>

          {sidebarOpen && (
            <div className="sidebar-footer">
              <button className="sidebar-btn" onClick={() => setPage('home')}>
                <Home size={17} />
                <span>Back to Home</span>
              </button>
            </div>
          )}
        </aside>

        {/* ── Main Content ───────────────────────────────────────── */}
        <main className={`app-main ${sidebarOpen ? 'sidebar-open' : 'sidebar-collapsed'}`}>
          {page === 'kpi' && <KpiDashboard />}
          {page === 'operator' && <OperatorDashboard />}
          {page === 'orchestration' && <OrchestrationVisibility />}
          {page === 'pipeline' && <OrchestrationView />}
          {page === 'upload' && <DataUpload />}
          {page === 'mapping' && <DataMapping />}
          {page === 'advisor' && <ScenarioAdvisorChat />}
          {page === 'workorders' && <WorkOrderModule />}
          {page === 'digital-twin' && <DigitalTwin3D assetId={activeAssetId || 'RTU-001'} />}
          {page === 'governance' && <GovernanceDashboard />}
          {page === 'capex' && <CapExPage />}
          {page === 'agents' && <AgentsPage />}
          {page === 'decision-matrix' && <DecisionMatrixPage />}
          {page === 'ownership' && <OwnershipDecisionSupport />}
          {page === 'ds-config' && <DecisionSupportConfig />}
        </main>
      </div>
    </div>
  )
}

function App() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  )
}

export default App
