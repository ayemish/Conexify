import { useState, useEffect, useCallback } from 'react'
import { Activity, AlertTriangle, CheckCircle, Clock, TrendingDown, Wrench, Building, MapPin, ChevronDown, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import FleetApi from '../services/fleetApi'

const HEALTH_BANDS = {
  healthy: { color: '#22c55e', label: 'Healthy', min: 80 },
  monitoring: { color: '#eab308', label: 'Monitoring', min: 60 },
  alert: { color: '#f97316', label: 'Alert', min: 40 },
  action: { color: '#ef4444', label: 'Action Required', min: 20 },
  critical: { color: '#991b1b', label: 'Critical', min: 0 },
}

function getHealthBand(score) {
  if (score >= 80) return 'healthy'
  if (score >= 60) return 'monitoring'
  if (score >= 40) return 'alert'
  if (score >= 20) return 'action'
  return 'critical'
}

function HealthGauge({ score, size = 'medium' }) {
  const band = getHealthBand(score)
  const config = HEALTH_BANDS[band]
  const pct = Math.max(0, Math.min(100, score))
  
  const dimensions = {
    small: { width: 80, height: 48, fontSize: 14, subSize: 7 },
    medium: { width: 120, height: 70, fontSize: 20, subSize: 9 },
    large: { width: 160, height: 95, fontSize: 28, subSize: 11 },
  }
  const dim = dimensions[size]
  
  return (
    <div className="health-gauge">
      <svg viewBox="0 0 120 70" width={dim.width} height={dim.height}>
        <path d="M10 65 A50 50 0 0 1 110 65" fill="none" stroke="#e5e7eb" strokeWidth="10" strokeLinecap="round" />
        <path
          d="M10 65 A50 50 0 0 1 110 65"
          fill="none"
          stroke={config.color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * 157} 157`}
        />
        <text x="60" y="52" textAnchor="middle" fontSize={dim.fontSize} fontWeight="700" fill={config.color}>
          {Math.round(pct)}
        </text>
        <text x="60" y="66" textAnchor="middle" fontSize={dim.subSize} fill="#6b7280">
          {config.label}
        </text>
      </svg>
    </div>
  )
}

function AssetCard({ asset, onClick, selected }) {
  const band = getHealthBand(asset.health_score || 0)
  const config = HEALTH_BANDS[band]
  
  return (
    <div 
      className={clsx('asset-card', band, { selected })}
      onClick={() => onClick?.(asset)}
      style={{ borderLeftColor: config.color }}
    >
      <div className="asset-card-header">
        <span className="asset-id">{asset.asset_id}</span>
        <span className={clsx('asset-status', band)}>{config.label}</span>
      </div>
      
      <div className="asset-card-body">
        <HealthGauge score={asset.health_score || 0} size="small" />
        
        <div className="asset-metrics">
          <div className="metric">
            <span className="metric-label">RUL</span>
            <span className="metric-value">
              {asset.rul_hours === Infinity || asset.rul_hours > 9999 
                ? '∞' 
                : `${Math.round(asset.rul_hours)}h`}
            </span>
          </div>
          <div className="metric">
            <span className="metric-label">Regime</span>
            <span className="metric-value">{asset.regime || 'Unknown'}</span>
          </div>
          <div className="metric">
            <span className="metric-label">Trust</span>
            <span className="metric-value">{Math.round((asset.sensor_trust || 1) * 100)}%</span>
          </div>
        </div>
      </div>
      
      {(asset.estate || asset.location) && (
        <div className="asset-card-location">
          {asset.estate && <span className="location-tag estate-tag"><Building size={11} /> {asset.estate}</span>}
          {asset.location && <span className="location-tag"><MapPin size={11} /> {asset.location}</span>}
        </div>
      )}
      
      {asset.active_alert && (
        <div className={clsx('asset-alert', asset.active_alert.alert_type)}>
          <AlertTriangle size={14} />
          <span>{asset.active_alert.primary_fault || 'Alert Active'}</span>
        </div>
      )}
    </div>
  )
}

function EstateGroup({ estate, locations, assets, onAssetSelect, selectedAssetId, collapsed, onToggle }) {
  const estateAssets = assets.filter(a => (a.estate || 'Unassigned') === estate)
  const healthDist = estateAssets.reduce((acc, a) => {
    const band = getHealthBand(a.health_score || 0)
    acc[band] = (acc[band] || 0) + 1
    return acc
  }, {})
  const criticalCount = (healthDist.critical || 0) + (healthDist.action || 0)
  
  return (
    <div className="estate-group">
      <button className="estate-group-header" onClick={onToggle}>
        <div className="estate-group-left">
          {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          <Building size={16} style={{ color: '#6366f1' }} />
          <span className="estate-group-name">{estate}</span>
          <span className="estate-group-count">{estateAssets.length} assets</span>
        </div>
        <div className="estate-group-right">
          {criticalCount > 0 && (
            <span className="estate-critical-badge">
              <AlertTriangle size={12} /> {criticalCount}
            </span>
          )}
          {Object.entries(HEALTH_BANDS).map(([band, cfg]) => {
            const count = healthDist[band] || 0
            if (count === 0) return null
            return (
              <span key={band} className="estate-health-dot" style={{ background: cfg.color }} title={`${cfg.label}: ${count}`}>
                {count}
              </span>
            )
          })}
        </div>
      </button>
      {!collapsed && (
        <div className="estate-group-body">
          {locations.map(loc => {
            const locAssets = estateAssets.filter(a => (a.location || 'Unknown') === loc)
            if (locAssets.length === 0) return null
            return (
              <div key={loc} className="location-subgroup">
                <div className="location-subgroup-header">
                  <MapPin size={13} style={{ color: '#94a3b8' }} />
                  <span>{loc}</span>
                  <span className="location-subgroup-count">{locAssets.length}</span>
                </div>
                <div className="fleet-grid">
                  {locAssets.map(asset => (
                    <AssetCard
                      key={asset.asset_id}
                      asset={asset}
                      onClick={onAssetSelect}
                      selected={asset.asset_id === selectedAssetId}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function FleetSummaryCard({ icon: Icon, label, value, subValue, color }) {
  return (
    <div className="fleet-summary-card">
      <div className="summary-icon" style={{ backgroundColor: `${color}20`, color }}>
        <Icon size={20} />
      </div>
      <div className="summary-content">
        <div className="summary-value" style={{ color }}>{value}</div>
        <div className="summary-label">{label}</div>
        {subValue && <div className="summary-sub">{subValue}</div>}
      </div>
    </div>
  )
}

export default function FleetOverview({ onAssetSelect, selectedAssetId, wsConnection }) {
  const [assets, setAssets] = useState([])
  const [fleetMetrics, setFleetMetrics] = useState({})
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [sortBy, setSortBy] = useState('health')
  const [estateFilter, setEstateFilter] = useState('all')
  const [locationFilter, setLocationFilter] = useState('all')
  const [groupByEstate, setGroupByEstate] = useState(true)
  const [collapsedEstates, setCollapsedEstates] = useState({})
  
  const fetchFleetData = useCallback(async () => {
    try {
      const [assetsResult, metricsResult] = await Promise.all([
        FleetApi.getAssets(),
        FleetApi.getMetrics(),
      ])
      
      if (assetsResult.ok) {
        setAssets(assetsResult.data.assets || [])
      }
      
      if (metricsResult.ok) {
        setFleetMetrics(metricsResult.data)
      }
    } catch (err) {
      console.error('Failed to fetch fleet data:', err)
    } finally {
      setLoading(false)
    }
  }, [])
  
  useEffect(() => {
    fetchFleetData()
    const interval = setInterval(fetchFleetData, 30000)
    return () => clearInterval(interval)
  }, [fetchFleetData])
  
  useEffect(() => {
    if (!wsConnection) return
    
    const handleMessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'asset_update') {
          setAssets(prev => prev.map(a => 
            a.asset_id === data.asset_id ? { ...a, ...data.update } : a
          ))
        } else if (data.type === 'fleet_metrics') {
          setFleetMetrics(data.metrics)
        }
      } catch (err) {
        console.error('WebSocket message parse error:', err)
      }
    }
    
    wsConnection.addEventListener('message', handleMessage)
    return () => wsConnection.removeEventListener('message', handleMessage)
  }, [wsConnection])
  
  // Extract unique estates and locations
  const estates = [...new Set(assets.map(a => a.estate || 'Unassigned'))].sort()
  const locations = [...new Set(assets.map(a => a.location || 'Unknown'))].sort()
  
  // Filter by location for the location dropdown (scoped to selected estate)
  const filteredLocations = estateFilter === 'all'
    ? locations
    : [...new Set(assets.filter(a => (a.estate || 'Unassigned') === estateFilter).map(a => a.location || 'Unknown'))].sort()
  
  const filteredAssets = assets.filter(asset => {
    // Health filter
    if (filter !== 'all') {
      const band = getHealthBand(asset.health_score || 0)
      if (filter === 'critical' && band !== 'critical' && band !== 'action') return false
      if (filter === 'alert' && band !== 'alert' && band !== 'action' && band !== 'critical') return false
      if (filter === 'healthy' && band !== 'healthy') return false
    }
    // Estate filter
    if (estateFilter !== 'all' && (asset.estate || 'Unassigned') !== estateFilter) return false
    // Location filter
    if (locationFilter !== 'all' && (asset.location || 'Unknown') !== locationFilter) return false
    return true
  })
  
  const sortedAssets = [...filteredAssets].sort((a, b) => {
    if (sortBy === 'health') return (a.health_score || 0) - (b.health_score || 0)
    if (sortBy === 'rul') {
      const aRul = a.rul_hours === Infinity ? 99999 : a.rul_hours
      const bRul = b.rul_hours === Infinity ? 99999 : b.rul_hours
      return aRul - bRul
    }
    if (sortBy === 'name') return a.asset_id.localeCompare(b.asset_id)
    return 0
  })
  
  const healthDistribution = assets.reduce((acc, asset) => {
    const band = getHealthBand(asset.health_score || 0)
    acc[band] = (acc[band] || 0) + 1
    return acc
  }, {})
  
  // Group assets by estate -> location for grouped view
  const groupedEstates = groupByEstate
    ? estates.filter(e => estateFilter === 'all' || e === estateFilter).map(estate => {
        const estateAssets = sortedAssets.filter(a => (a.estate || 'Unassigned') === estate)
        const locs = [...new Set(estateAssets.map(a => a.location || 'Unknown'))].sort()
        return { estate, locations: locs, assets: estateAssets }
      }).filter(g => g.assets.length > 0)
    : []
  
  const toggleEstateCollapse = (estate) => {
    setCollapsedEstates(prev => ({ ...prev, [estate]: !prev[estate] }))
  }
  
  if (loading) {
    return <div className="fleet-loading">Loading fleet data...</div>
  }
  
  return (
    <div className="fleet-overview">
      <div className="fleet-header">
        <h2>Fleet Overview</h2>
        <div className="fleet-controls">
          <select value={estateFilter} onChange={(e) => { setEstateFilter(e.target.value); setLocationFilter('all') }}>
            <option value="all">All Estates</option>
            {estates.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
          <select value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)}>
            <option value="all">All Locations</option>
            {filteredLocations.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All Health</option>
            <option value="critical">Critical Only</option>
            <option value="alert">Needs Attention</option>
            <option value="healthy">Healthy</option>
          </select>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            <option value="health">Sort by Health</option>
            <option value="rul">Sort by RUL</option>
            <option value="name">Sort by Name</option>
          </select>
          <button
            className={clsx('group-toggle-btn', { active: groupByEstate })}
            onClick={() => setGroupByEstate(!groupByEstate)}
            title={groupByEstate ? 'Show flat list' : 'Group by estate'}
          >
            <Building size={14} />
            {groupByEstate ? 'Grouped' : 'Flat'}
          </button>
        </div>
      </div>
      
      <div className="fleet-summary">
        <FleetSummaryCard 
          icon={Activity}
          label="Total Assets"
          value={assets.length}
          color="#3b82f6"
        />
        <FleetSummaryCard 
          icon={CheckCircle}
          label="Healthy"
          value={healthDistribution.healthy || 0}
          subValue={`${Math.round(((healthDistribution.healthy || 0) / assets.length) * 100)}%`}
          color="#22c55e"
        />
        <FleetSummaryCard 
          icon={AlertTriangle}
          label="Needs Attention"
          value={(healthDistribution.alert || 0) + (healthDistribution.action || 0) + (healthDistribution.critical || 0)}
          color="#f97316"
        />
        <FleetSummaryCard 
          icon={Clock}
          label="Avg RUL"
          value={fleetMetrics.avg_rul_hours ? `${Math.round(fleetMetrics.avg_rul_hours)}h` : '—'}
          color="#8b5cf6"
        />
        <FleetSummaryCard 
          icon={TrendingDown}
          label="Degrading"
          value={fleetMetrics.degrading_count || 0}
          color="#ef4444"
        />
        <FleetSummaryCard 
          icon={Wrench}
          label="Open Incidents"
          value={fleetMetrics.open_incidents || 0}
          color="#eab308"
        />
      </div>
      
      {groupByEstate ? (
        <div className="estate-groups">
          {groupedEstates.map(({ estate, locations: locs, assets: estateAssets }) => (
            <EstateGroup
              key={estate}
              estate={estate}
              locations={locs}
              assets={estateAssets}
              onAssetSelect={onAssetSelect}
              selectedAssetId={selectedAssetId}
              collapsed={!!collapsedEstates[estate]}
              onToggle={() => toggleEstateCollapse(estate)}
            />
          ))}
          {groupedEstates.length === 0 && (
            <div className="fleet-empty">No assets match the current filters.</div>
          )}
        </div>
      ) : (
        <div className="fleet-grid">
          {sortedAssets.map(asset => (
            <AssetCard 
              key={asset.asset_id}
              asset={asset}
              onClick={onAssetSelect}
              selected={asset.asset_id === selectedAssetId}
            />
          ))}
          {sortedAssets.length === 0 && (
            <div className="fleet-empty">No assets match the current filters.</div>
          )}
        </div>
      )}
    </div>
  )
}
