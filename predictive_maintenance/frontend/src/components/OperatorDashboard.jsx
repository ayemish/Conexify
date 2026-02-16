import { useState, useEffect, useCallback } from 'react'
import { 
  LayoutDashboard, Users, AlertTriangle, CheckSquare, 
  Settings, Bell, Wifi, WifiOff, RefreshCw
} from 'lucide-react'
import clsx from 'clsx'

import FleetOverview from './FleetOverview'
import ApprovalQueue from './ApprovalQueue'
import AlertTriage from './AlertTriage'
import AssetDetail from './AssetDetail'
import SettingsPanel from './SettingsPanel'
import { useWebSocket, resolveWsUrl } from '../hooks/useWebSocket'

const NAV_ITEMS = [
  { id: 'fleet', label: 'Fleet Overview', icon: LayoutDashboard },
  { id: 'alerts', label: 'Alert Triage', icon: AlertTriangle },
  { id: 'approvals', label: 'Approval Queue', icon: CheckSquare },
  { id: 'settings', label: 'Settings', icon: Settings },
]

function ConnectionStatus({ status }) {
  const config = {
    connected: { icon: Wifi, color: '#22c55e', label: 'Live' },
    disconnected: { icon: WifiOff, color: '#94a3b8', label: 'Offline' },
    reconnecting: { icon: RefreshCw, color: '#eab308', label: 'Connecting...' },
    unavailable: { icon: WifiOff, color: '#94a3b8', label: 'Polling' },
    error: { icon: WifiOff, color: '#ef4444', label: 'WS Error' },
  }
  const cfg = config[status] || config.disconnected
  const Icon = cfg.icon
  
  return (
    <div className={clsx('connection-status', status)} title={cfg.label}>
      <Icon size={16} style={{ color: cfg.color }} className={status === 'reconnecting' ? 'spin' : ''} />
      <span style={{ color: cfg.color }}>{cfg.label}</span>
    </div>
  )
}

function NotificationBell({ count }) {
  return (
    <button className="notification-bell">
      <Bell size={20} />
      {count > 0 && <span className="notification-badge">{count > 99 ? '99+' : count}</span>}
    </button>
  )
}

export default function OperatorDashboard() {
  const [activeTab, setActiveTab] = useState('fleet')
  const [selectedAsset, setSelectedAsset] = useState(null)
  const [notificationCount, setNotificationCount] = useState(0)
  
  const wsUrl = resolveWsUrl('/api/v1/ws/operator')
  
  const { status: wsStatus, ws, lastMessage } = useWebSocket(wsUrl, {
    onMessage: (data) => {
      if (data.type === 'notification') {
        setNotificationCount(prev => prev + 1)
      }
    },
  })
  
  const handleAssetSelect = useCallback((asset) => {
    setSelectedAsset(typeof asset === 'string' ? asset : asset?.asset_id)
    if (asset) {
      setActiveTab('asset_detail')
    }
  }, [])
  
  const handleBackToFleet = useCallback(() => {
    setSelectedAsset(null)
    setActiveTab('fleet')
  }, [])
  
  return (
    <div className="operator-dashboard">
      <header className="dashboard-header">
        <div className="header-brand">
          <LayoutDashboard size={24} style={{ color: '#3b82f6' }} />
          <h1>PdM Operator Dashboard</h1>
        </div>
        
        <nav className="header-nav">
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              className={clsx('nav-item', { active: activeTab === item.id })}
              onClick={() => {
                setActiveTab(item.id)
                if (item.id !== 'asset_detail') setSelectedAsset(null)
              }}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        
        <div className="header-actions">
          <ConnectionStatus status={wsStatus} />
          <NotificationBell count={notificationCount} />
        </div>
      </header>
      
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
        margin: '0 1rem 1rem', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> Real-time <strong>predictive maintenance operator console</strong> with
        fleet-wide asset monitoring, health scores, remaining useful life (RUL) estimates, active alerts,
        and sensor trust indicators. Drill into individual assets for detailed diagnostics, telemetry trends,
        and maintenance history. Connected via WebSocket for live updates.
      </div>

      <main className="dashboard-main">
        {activeTab === 'fleet' && (
          <FleetOverview 
            onAssetSelect={handleAssetSelect}
            selectedAssetId={selectedAsset}
            wsConnection={ws}
          />
        )}
        
        {activeTab === 'alerts' && (
          <AlertTriage 
            assetId={selectedAsset}
            wsConnection={ws}
            onAssetSelect={handleAssetSelect}
          />
        )}
        
        {activeTab === 'approvals' && (
          <ApprovalQueue wsConnection={ws} />
        )}
        
        {activeTab === 'asset_detail' && selectedAsset && (
          <AssetDetail 
            assetId={selectedAsset}
            wsConnection={ws}
            onBack={handleBackToFleet}
          />
        )}
        
        {activeTab === 'settings' && (
          <SettingsPanel />
        )}
      </main>
    </div>
  )
}
